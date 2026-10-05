import httpx
import pytest

import tools


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request(
                "POST", "http://home-assistant.local/api/conversation/process"
            )
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "Home Assistant error", request=request, response=response
            )

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeClient:
    def __init__(self, response: FakeResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url: str, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


async def call_home_assistant(request: str) -> str:
    return await tools.home_assistant_request._func(None, request)


@pytest.mark.asyncio
async def test_home_assistant_requires_configuration(monkeypatch) -> None:
    monkeypatch.delenv("HOME_ASSISTANT_URL", raising=False)
    monkeypatch.delenv("HOME_ASSISTANT_TOKEN", raising=False)

    result = await call_home_assistant("Turn on the kitchen lights")

    assert "not configured" in result


@pytest.mark.asyncio
async def test_home_assistant_returns_spoken_response(monkeypatch) -> None:
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://home-assistant.local/")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "test-token")
    client = FakeClient(
        FakeResponse(
            {
                "response": {
                    "speech": {"plain": {"speech": "The kitchen lights are on."}}
                }
            }
        )
    )
    monkeypatch.setattr(tools.httpx, "AsyncClient", lambda **kwargs: client)

    result = await call_home_assistant("Turn on the kitchen lights")

    assert result == "The kitchen lights are on."
    assert client.calls[0]["url"] == (
        "http://home-assistant.local/api/conversation/process"
    )
    assert client.calls[0]["json"] == {"text": "Turn on the kitchen lights"}
    assert client.calls[0]["headers"]["Authorization"] == "Bearer test-token"


@pytest.mark.asyncio
async def test_home_assistant_handles_auth_error(monkeypatch) -> None:
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://home-assistant.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "bad-token")
    client = FakeClient(FakeResponse({}, status_code=401))
    monkeypatch.setattr(tools.httpx, "AsyncClient", lambda **kwargs: client)

    result = await call_home_assistant("Turn off the lights")

    assert result == "Home Assistant rejected the request. Check the access token."


@pytest.mark.asyncio
async def test_home_assistant_handles_connection_error(monkeypatch) -> None:
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://home-assistant.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "test-token")
    error = httpx.ConnectError(
        "offline", request=httpx.Request("POST", "http://home-assistant.local")
    )
    client = FakeClient(error)
    monkeypatch.setattr(tools.httpx, "AsyncClient", lambda **kwargs: client)

    result = await call_home_assistant("Turn on the fan")

    assert result.startswith("I couldn't reach Home Assistant")


@pytest.mark.asyncio
async def test_home_assistant_handles_invalid_response(monkeypatch) -> None:
    monkeypatch.setenv("HOME_ASSISTANT_URL", "http://home-assistant.local")
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "test-token")
    client = FakeClient(FakeResponse({"unexpected": True}))
    monkeypatch.setattr(tools.httpx, "AsyncClient", lambda **kwargs: client)

    result = await call_home_assistant("What is the temperature?")

    assert result == "Home Assistant returned an unexpected response."
