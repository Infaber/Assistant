"""Session-local arrival attribution; recognition never authorizes an action."""

from collections import deque
from dataclasses import dataclass


def count_value(state):
    try:
        number = float(state)
        return int(number) if number.is_integer() and 0 <= number <= 100 else None
    except (ValueError, TypeError):
        return None


def verified_track_ids(result):
    ids = result.get("person_track_ids")
    count = result.get("person_count")
    if (
        result.get("current_presence_verified") is not True
        or type(count) is not int
        or not isinstance(ids, list)
        or not 0 <= count < 20
        or len(ids) != count
        or any(
            not isinstance(track, str) or not track or len(track) > 160 for track in ids
        )
        or len(set(ids)) != count
    ):
        return None
    return frozenset(ids)


@dataclass(frozen=True)
class Arrival:
    entity: str
    count: int
    added: int
    excluded_tracks: frozenset
    can_name: bool
    stable_at: float

    def names(self, result):
        tracks = verified_track_ids(result)
        if not self.can_name or tracks is None or len(tracks) != self.count:
            return []
        newcomers = tracks - self.excluded_tracks
        # Track churn or an incomplete baseline cannot identify which person entered.
        if len(newcomers) != self.added:
            return []
        names = []
        for person in result.get("current_recognized_people", []):
            if person.get("track_id") not in newcomers:
                continue
            name = person.get("reported_name", "").strip()
            if (
                name
                and len(name) <= 40
                and all(c.isalpha() or c in " '-" for c in name)
            ):
                names.append(name)
        return list(dict.fromkeys(names))[:3]


class ArrivalTracks:
    def __init__(self):
        self.seen = deque(maxlen=512)
        self.ready = False

    def remember(self, result):
        tracks = verified_track_ids(result)
        if tracks is None:
            return
        self.ready = True
        for track in sorted(tracks):
            if track in self.seen:
                self.seen.remove(track)
            self.seen.append(track)

    def arrival(self, entity, before, after, now, pending=None):
        if pending is not None and pending.entity == entity and pending.count == before:
            # Several people can enter during the same cooldown/name lookup.
            return Arrival(
                entity,
                after,
                pending.added + after - before,
                pending.excluded_tracks,
                pending.can_name,
                now + 3,
            )
        return Arrival(
            entity,
            after,
            after - before,
            frozenset() if before == 0 else frozenset(self.seen),
            before == 0 or self.ready,
            now + 3 if before else now,
        )
