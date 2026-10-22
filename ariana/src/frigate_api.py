"""Authenticated, bounded read-only Frigate transport; never exports raw errors."""

import asyncio
import json
import os
import re
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import httpx

MAX_BYTES = 5 * 1024 * 1024


class CameraError(Exception):
    def result(self):
        return {"error": str(self), "verified": False}


def enabled():
    return os.getenv("ARIANA_CAMERA_ENABLED", "false").lower() == "true"


def identifier(value):
    if (
        not isinstance(value, str)
        or value in {".", ".."}
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", value)
    ):
        raise CameraError("Invalid camera or event identifier.")
    return value


class FrigateAPI:
    def __init__(self, url, token="", username="", password="", transport=None):
        try:
            p = urlsplit(url)
            valid = p.scheme in {"http", "https"} and p.hostname and p.port != 5000
        except ValueError:
            valid = False
        if (
            not valid
            or p.username
            or p.password
            or p.query
            or p.fragment
            or p.path not in {"", "/"}
        ):
            raise CameraError(
                "Use an authenticated Frigate URL, never port 5000 or embedded credentials."
            )
        if not token and not (username and password):
            raise CameraError(
                "Set FRIGATE_TOKEN or FRIGATE_USERNAME and FRIGATE_PASSWORD privately."
            )
        self.url = url.rstrip("/")
        self._token, self._username, self._password = token, username, password
        self._transport = transport
        self._lock = asyncio.Lock()

    @classmethod
    def configured(cls):
        if not enabled():
            raise CameraError(
                "Camera access is disabled. Enable ARIANA_CAMERA_ENABLED explicitly."
            )
        return cls(
            os.getenv("FRIGATE_URL", ""),
            os.getenv("FRIGATE_TOKEN", ""),
            os.getenv("FRIGATE_USERNAME", ""),
            os.getenv("FRIGATE_PASSWORD", ""),
        )

    async def _read(self, client, method, path, params=None, data=None):
        headers = {"Authorization": "Bearer " + self._token} if self._token else {}
        async with client.stream(
            method, self.url + path, headers=headers, params=params, json=data
        ) as response:
            if response.status_code in {401, 403}:
                raise CameraError(
                    "Frigate authentication or camera permission was rejected."
                )
            if response.status_code == 404:
                raise CameraError(
                    "This camera or API feature is unavailable on this Frigate instance."
                )
            if response.status_code != 200:
                raise CameraError("Frigate rejected the request.")
            result = bytearray()
            async for chunk in response.aiter_bytes():
                result.extend(chunk)
                if len(result) > MAX_BYTES:
                    raise CameraError("Frigate returned an oversized response.")
            return bytes(result)

    async def get(self, path, params=None, image=False, text=False):
        # No arbitrary endpoint supplied by a model; callers use fixed read routes.
        async with self._lock:
            try:
                async with httpx.AsyncClient(
                    timeout=8, follow_redirects=False, transport=self._transport
                ) as client:
                    if not self._token:
                        await self._read(
                            client,
                            "POST",
                            "/api/login",
                            data={"user": self._username, "password": self._password},
                        )
                        self._token = client.cookies.get("frigate_token", "")
                        if not self._token:
                            raise CameraError(
                                "Frigate login did not return an authenticated session."
                            )
                    try:
                        data = await self._read(client, "GET", path, params)
                    except CameraError as error:
                        if self._username and "authentication" in str(error):
                            self._token = ""  # Next user request can authenticate again; no polling/replay.
                        raise
                if image:
                    return data
                if text:
                    return data.decode().strip('"\n ')[:80]
                return json.loads(data)
            except httpx.TimeoutException:
                raise CameraError(
                    "Frigate timed out; current camera state is unknown."
                ) from None
            except httpx.RequestError:
                raise CameraError(
                    "Frigate is unreachable; check its connection."
                ) from None
            except (ValueError, UnicodeError):
                raise CameraError("Frigate returned an invalid response.") from None

    async def live_activity(self, camera):
        """One bounded authenticated UI state query; never publishes mutations."""
        identifier(camera)
        # Reuse the verified login flow, including bearer-token expiry handling.
        await self.get("/api/version", text=True)
        p = urlsplit(self.url)
        url = urlunsplit(
            ("wss" if p.scheme == "https" else "ws", p.netloc, "/ws", "", "")
        )
        trace = aiohttp.TraceConfig()

        async def reject_redirect(*args):
            raise CameraError("Frigate live-state redirects are refused.")

        trace.on_request_redirect.append(reject_redirect)

        async def read():
            async with (
                aiohttp.ClientSession(trace_configs=[trace]) as client,
                client.ws_connect(
                    url,
                    headers={"Authorization": "Bearer " + self._token},
                    max_msg_size=MAX_BYTES,
                ) as ws,
            ):
                # Frigate explicitly allows onConnect for authenticated viewer
                # roles. Its handler publishes current state, never changes it.
                await ws.send_json({"topic": "onConnect", "payload": ""})
                for _ in range(32):
                    frame = await ws.receive_json()
                    if (
                        not isinstance(frame, dict)
                        or frame.get("topic") != "camera_activity"
                    ):
                        continue
                    payload = frame.get("payload")
                    data = json.loads(payload) if isinstance(payload, str) else payload
                    row = data.get(camera) if isinstance(data, dict) else None
                    if not isinstance(row, dict) or not isinstance(
                        row.get("objects"), list
                    ):
                        raise CameraError(
                            "Current Frigate activity is unavailable for this camera."
                        )
                    config = row.get("config") or {}
                    if (
                        not isinstance(config, dict)
                        or config.get("enabled") is not True
                        or config.get("detect") is not True
                    ):
                        raise CameraError(
                            "Camera detection is disabled or its state is unknown."
                        )
                    objects = row["objects"]
                    if len(objects) > 100:
                        raise CameraError("Current camera activity is oversized.")
                    ids = []
                    for item in objects:
                        if not isinstance(item, dict) or not isinstance(
                            item.get("label"), str
                        ):
                            raise CameraError("Current camera objects are invalid.")
                        if item["label"] in {"person", "person-verified"}:
                            ids.append(identifier(item.get("id")))
                    if len(set(ids)) != len(ids):
                        raise CameraError("Current person track IDs are inconsistent.")
                    return ids
                raise CameraError("Frigate did not return a current activity snapshot.")

        try:
            return await asyncio.wait_for(read(), 8)
        except aiohttp.WSServerHandshakeError as error:
            if error.status in {401, 403}:
                if self._username:
                    self._token = ""
                raise CameraError(
                    "Frigate live-state authentication was rejected."
                ) from None
            raise CameraError(
                "Frigate live activity is unavailable on this version."
            ) from None
        except (aiohttp.ClientError, OSError, ValueError, TimeoutError):
            raise CameraError(
                "Frigate live activity could not be verified; no stale value was reused."
            ) from None
