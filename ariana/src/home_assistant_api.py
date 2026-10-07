"""Bounded Home Assistant transport. Credentials and raw errors never leave here."""

import asyncio
import json
import os
import re
from urllib.parse import urlsplit, urlunsplit

import aiohttp
import httpx

MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 10000


class HAError(Exception):
    def __init__(self, code, uncertain=False):
        self.code = code
        self.uncertain = uncertain
        super().__init__(code)

    def result(self):
        messages = {
            "configuration": "Set HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN in Ariana's private environment file.",
            "auth": "Home Assistant rejected the token or permissions. Check its access token and account permissions.",
            "missing": "That Home Assistant entity no longer exists. Refresh discovery before choosing another target.",
            "offline": "Home Assistant is unreachable. Check its network connection and URL.",
            "timeout": "Home Assistant timed out.",
            "response": "Home Assistant returned an invalid or oversized response.",
            "registry": "Some Home Assistant registries could not be read; area/device discovery is incomplete.",
            "http": "Home Assistant rejected the API request.",
        }
        result = {"error": messages.get(self.code, messages["http"]), "code": self.code}
        if self.uncertain:
            result.update(
                uncertain=True,
                error="The command may have reached Home Assistant. Check the device state before retrying.",
            )
        return result


def configuration():
    url = os.getenv("HOME_ASSISTANT_URL", "").strip().rstrip("/")
    token = os.getenv("HOME_ASSISTANT_TOKEN", "").strip()
    p = urlsplit(url)
    if (
        not token
        or p.scheme not in {"http", "https"}
        or not p.hostname
        or p.username
        or p.password
        or p.query
        or p.fragment
    ):
        raise HAError("configuration")
    try:
        _ = p.port
    except ValueError:
        raise HAError("configuration") from None
    return url, token


class HomeAssistantAPI:
    def __init__(self, url, token):
        self.url = url
        self._token = token

    def safe_text(self, value, limit=160):
        # Do not export arbitrary attributes, URLs, exception bodies or credentials.
        text = str(value or "").replace(self._token, "[redacted]")
        text = re.sub(
            r"AIza[0-9A-Za-z_-]{35}|(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}|sk-(?:proj-)?[A-Za-z0-9_-]{40,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}|https?://[^\s]+",
            "[redacted]",
            text,
        )
        return text[:limit]

    async def request(self, method, path, data=None):
        dispatched = method == "POST"
        try:
            async with (
                httpx.AsyncClient(timeout=10, follow_redirects=False) as client,
                client.stream(
                    method,
                    self.url + path,
                    headers={"Authorization": "Bearer " + self._token},
                    json=data,
                ) as response,
            ):
                if response.status_code in {401, 403}:
                    raise HAError("auth")
                if response.status_code == 404:
                    raise HAError("missing")
                if (
                    response.status_code >= 400
                    or response.status_code < 200
                    or response.status_code >= 300
                ):
                    raise HAError(
                        "http",
                        dispatched
                        and (
                            response.status_code >= 500
                            or 300 <= response.status_code < 400
                            or response.status_code == 408
                        ),
                    )
                content = bytearray()
                async for block in response.aiter_bytes():
                    content.extend(block)
                    if len(content) > MAX_BYTES:
                        raise HAError("response", dispatched)
            result = json.loads(content)
            if isinstance(result, list) and len(result) > MAX_ROWS:
                raise HAError("response", dispatched)
            return result
        except httpx.ConnectError:
            raise HAError("offline") from None
        except httpx.TimeoutException:
            raise HAError("timeout", dispatched) from None
        except httpx.RequestError:
            raise HAError("offline", dispatched) from None
        except (ValueError, TypeError):
            raise HAError("response", dispatched) from None

    async def registries(self):
        names = ("entity", "device", "area")
        replies = await self.websocket(
            [{"type": f"config/{name}_registry/list"} for name in names]
        )
        if any(not isinstance(rows, list) or len(rows) > MAX_ROWS for rows in replies):
            raise HAError("response")
        return dict(zip(names, replies, strict=True))

    async def registry_entity(self, entity_id):
        rows = await self.websocket(
            [{"type": "config/entity_registry/get", "entity_id": entity_id}]
        )
        if not isinstance(rows[0], dict):
            raise HAError("response")
        return rows[0]

    async def websocket(self, commands):
        try:
            return await asyncio.wait_for(self._websocket(commands), 10)
        except (asyncio.TimeoutError, TimeoutError):
            raise HAError("registry") from None

    async def _websocket(self, commands):
        p = urlsplit(self.url)
        url = urlunsplit(
            (
                "wss" if p.scheme == "https" else "ws",
                p.netloc,
                p.path + "/api/websocket",
                "",
                "",
            )
        )
        try:
            async with (
                aiohttp.ClientSession() as client,
                client.ws_connect(
                    url,
                    max_msg_size=MAX_BYTES,
                    timeout=aiohttp.ClientWSTimeout(ws_close=1),
                ) as ws,
            ):
                greeting = await ws.receive_json()
                if greeting.get("type") != "auth_required":
                    raise HAError("response")
                await ws.send_json({"type": "auth", "access_token": self._token})
                if (await ws.receive_json()).get("type") != "auth_ok":
                    raise HAError("auth")
                results = []
                for number, command in enumerate(commands, 1):
                    await ws.send_json({"id": number, **command})
                    reply = await ws.receive_json()
                    if reply.get("id") != number or reply.get("type") != "result":
                        raise HAError("response")
                    if not reply.get("success"):
                        code = reply.get("error", {}).get("code")
                        raise HAError(
                            "missing"
                            if code == "not_found"
                            else "auth"
                            if code == "unauthorized"
                            else "registry"
                        )
                    results.append(reply.get("result"))
                return results
        except (TimeoutError, aiohttp.ClientError, OSError):
            raise HAError("registry") from None
        except (ValueError, TypeError, AttributeError):
            raise HAError("response") from None
