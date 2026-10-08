"""Bounded, deterministic discovery matching; names are untrusted data."""

import re
import unicodedata
from difflib import SequenceMatcher

DOMAINS = {
    "sensor",
    "binary_sensor",
    "light",
    "switch",
    "cover",
    "climate",
    "media_player",
    "fan",
    "weather",
    "camera",
}
MAX_ENTITIES = 1500


def normalized(value):
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    return " ".join(re.findall(r"[^\W_]+", text.replace("_", " "), re.UNICODE))


def terms(value):
    return {
        word.rstrip("s") if word in {"lights", "leds", "sensors"} else word
        for word in normalized(value).split()
    } - {"my", "the", "what", "whats", "is", "in", "of", "a", "please"}


def phrase_in(phrase, query):
    return bool(phrase) and f" {normalized(phrase)} " in f" {normalized(query)} "


class Inventory:
    def __init__(self, states, registries, safe_text):
        self.safe = safe_text
        self.areas = {}
        self.devices = {}
        for row in registries.get("area", []):
            if isinstance(row, dict) and isinstance(row.get("area_id"), str):
                self.areas[row["area_id"]] = {
                    "id": row["area_id"],
                    "name": safe_text(row.get("name")),
                    "aliases": [
                        safe_text(a)
                        for a in (row.get("aliases") or [])[:20]
                        if isinstance(a, str)
                    ],
                }
        for row in registries.get("device", []):
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                self.devices[row["id"]] = {
                    "id": row["id"],
                    "name": safe_text(row.get("name_by_user") or row.get("name")),
                    "area_id": row.get("area_id"),
                }
        registry = {
            row["entity_id"]: row
            for row in registries.get("entity", [])
            if isinstance(row, dict) and isinstance(row.get("entity_id"), str)
        }
        self.entities = {}
        self.truncated = False
        for row in states:
            if not isinstance(row, dict):
                continue
            eid = row.get("entity_id", "")
            if (
                not isinstance(eid, str)
                or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", eid)
                or eid.split(".")[0] not in DOMAINS
            ):
                continue
            entry = registry.get(eid, {})
            if entry.get("disabled_by") or entry.get("hidden_by"):
                continue
            if len(self.entities) >= MAX_ENTITIES:
                self.truncated = True
                continue
            attrs = row.get("attributes") or {}
            if not isinstance(attrs, dict):
                continue
            device = self.devices.get(entry.get("device_id"), {})
            area_id = entry.get("area_id") or device.get("area_id")
            area = self.areas.get(area_id, {})
            self.entities[eid] = {
                "entity_id": eid,
                "registry_id": entry.get("id"),
                "platform": entry.get("platform", ""),
                "name": safe_text(
                    attrs.get("friendly_name")
                    or entry.get("name")
                    or entry.get("original_name")
                    or eid
                ),
                "entity_name": safe_text(
                    entry.get("name") or entry.get("original_name")
                ),
                "original_name": safe_text(entry.get("original_name")),
                "aliases": [
                    safe_text(a)
                    for a in (entry.get("aliases") or [])[:20]
                    if isinstance(a, str)
                ],
                "domain": eid.split(".")[0],
                "device_class": safe_text(
                    attrs.get("device_class")
                    or entry.get("device_class")
                    or entry.get("original_device_class")
                ),
                "unit": safe_text(
                    attrs.get("unit_of_measurement") or entry.get("unit_of_measurement")
                ),
                "area_id": area_id,
                "area": area.get("name", ""),
                "device_id": entry.get("device_id"),
                "device": device.get("name", ""),
                "state": safe_text(row.get("state")),
                "available": row.get("state") not in {"unknown", "unavailable", None},
                "supported_features": features(
                    attrs.get("supported_features", entry.get("supported_features", 0))
                ),
            }

    @staticmethod
    def public(entity):
        return {
            k: entity[k]
            for k in (
                "entity_id",
                "name",
                "domain",
                "device_class",
                "unit",
                "area",
                "device",
                "available",
                "supported_features",
            )
        }

    def stable_target(self, kind, row):
        return {
            "kind": kind,
            "id": row.get("registry_id") or row["entity_id"]
            if kind == "entity"
            else row["id"],
            "name": row["name"],
            "entity_id": row.get("entity_id", ""),
            "stable": bool(row.get("registry_id")) if kind == "entity" else True,
        }

    def alias_rows(self, mapping):
        kind = mapping["kind"]
        if kind == "entity":
            # Registry identity survives entity-ID renames; do not bind an alias to a recycled ID.
            return [
                r
                for r in self.entities.values()
                if (
                    r.get("registry_id") == mapping["id"]
                    if mapping.get("stable")
                    else r["entity_id"] == mapping["id"]
                    and r["name"] == mapping["name"]
                )
            ]
        source = self.areas if kind == "area" else self.devices
        row = source.get(mapping["id"])
        return (
            [r for r in self.entities.values() if r.get(kind + "_id") == row["id"]]
            if row
            else []
        )

    def find(self, query, aliases=None, domain="", device_class=""):
        query = query.strip()
        if not query or len(query) > 250:
            return {
                "error": "Describe one Home Assistant target in at most 250 characters."
            }
        aliases = aliases or {}
        q = terms(query)
        candidates = list(self.entities.values())
        matched_aliases = [a for a in aliases if phrase_in(a, query)]
        if matched_aliases:
            longest = max(len(terms(a)) for a in matched_aliases)
            rows = {
                r["entity_id"]: r
                for a in matched_aliases
                if len(terms(a)) == longest
                for r in self.alias_rows(aliases[a])
            }
            if not rows:
                return {
                    "error": "That saved Home Assistant target disappeared. Find it again and explicitly update the alias; no old ID will be dispatched.",
                    "code": "stale_alias",
                    "alias": matched_aliases[0],
                }
            candidates = list(rows.values())
        if domain:
            candidates = [r for r in candidates if r["domain"] == domain]
        if device_class:
            candidates = [r for r in candidates if r["device_class"] == device_class]
        # Lexical metadata lookup only; the model chooses actions and interprets user intent.
        classes = q & {r["device_class"] for r in candidates if r["device_class"]}
        if classes:
            candidates = [r for r in candidates if r["device_class"] in classes]
        area_ids = {
            aid
            for aid, a in self.areas.items()
            if any(phrase_in(n, query) for n in [a["name"], *a["aliases"]])
        }
        if not area_ids and not matched_aliases and {"room", "bedroom"} & q:
            # Personal ownership is not inferred. A unique configured bedroom is a
            # useful default; multiple bedroom areas remain ambiguous.
            area_ids = {
                aid for aid, a in self.areas.items() if "bedroom" in terms(a["name"])
            }
        exact = [
            r
            for r in candidates
            if normalized(query) == normalized(r["name"]) or query == r["entity_id"]
        ]
        ha_alias = [
            r
            for r in candidates
            if any(normalized(query) == normalized(a) for a in r["aliases"])
        ]
        if not matched_aliases and (exact or ha_alias):
            candidates = exact or ha_alias
        elif area_ids and not matched_aliases:
            candidates = [r for r in candidates if r["area_id"] in area_ids]
        scores = []
        for r in candidates:
            names = [
                r["name"],
                r["entity_name"],
                r["original_name"],
                r["entity_id"].split(".")[1],
            ]
            exact_name = any(normalized(query) == normalized(n) for n in names[:1])
            exact_alias = any(phrase_in(a, query) for a in r["aliases"])
            namescore = max(
                (len(q & terms(n)) / max(len(q), 1) for n in names), default=0
            )
            fuzzy = max(
                (
                    SequenceMatcher(None, normalized(query), normalized(n)).ratio()
                    for n in names
                ),
                default=0,
            )
            device_score = len(q & terms(r["device"])) / max(len(q), 1)
            score = (
                100
                if exact_name
                else 90
                if exact_alias
                else (50 if area_ids else 0)
                + 25 * device_score
                + 20 * namescore
                + (10 if classes else 0)
                + 10 * fuzzy
            )
            if fuzzy >= 0.82:
                score += 30
            if matched_aliases:
                score += 150
            if query == r["entity_id"]:
                score = 300
            covered = set().union(
                *(terms(n) for n in [*names, r["device"], r["area"], *r["aliases"]])
            )
            required = q - classes - {r["domain"], "sensor"}
            if (
                not matched_aliases
                and not area_ids
                and not exact_name
                and not exact_alias
                and required - covered
                and fuzzy < 0.82
            ):
                continue
            if score >= 16 and (
                namescore
                or device_score
                or classes
                or area_ids
                or matched_aliases
                or fuzzy >= 0.68
            ):
                scores.append((score, r))
        scores.sort(key=lambda pair: (-pair[0], pair[1]["entity_id"]))
        if not scores:
            return {
                "code": "not_found",
                "error": "No clear Home Assistant target matched. Try an area/device name or refresh discovery.",
            }
        best = scores[0][0]
        top = [r for score, r in scores if best - score <= 8]
        result = {
            "status": "resolved" if len(top) == 1 else "ambiguous",
            "candidates": [self.public(r) for r in top[:8]],
            "candidate_count": len(top),
        }
        if len(top) == 1:
            result["entity"] = self.public(top[0])
        else:
            result["message"] = (
                "Ask which target the user means; do not choose or control one silently."
            )
        return result


def features(value):
    return value if isinstance(value, int) and 0 <= value <= 2**31 else 0
