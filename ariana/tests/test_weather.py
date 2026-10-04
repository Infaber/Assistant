import httpx
import pytest

import tools


class FakeResponse:
    def __init__(self, payload, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://weather.test")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError(
                "weather error", request=request, response=response
            )

    def json(self):
        return self.payload


class FakeClient:
    def __init__(self, responses) -> None:
        self.responses = iter(responses)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, *args, **kwargs):
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


async def call_weather(location: str) -> str:
    return await tools.weather_forecast._func(None, location)


@pytest.mark.asyncio
async def test_weather_requires_location() -> None:
    assert await call_weather("  ") == "Tell me which place you want the weather for."


@pytest.mark.asyncio
async def test_weather_returns_yr_forecast(monkeypatch) -> None:
    monkeypatch.setattr(
        tools.httpx,
        "AsyncClient",
        lambda **kwargs: FakeClient(
            [
                FakeResponse(
                    [{"lat": "59.91", "lon": "10.75", "display_name": "Oslo, Norway"}]
                ),
                FakeResponse(
                    {
                        "properties": {
                            "timeseries": [
                                {
                                    "data": {
                                        "instant": {
                                            "details": {
                                                "air_temperature": 8.2,
                                                "wind_speed": 3.4,
                                            }
                                        },
                                        "next_1_hours": {
                                            "summary": {
                                                "symbol_code": "partlycloudy_day"
                                            }
                                        },
                                    }
                                }
                            ]
                        }
                    }
                ),
            ]
        ),
    )

    result = await call_weather("Oslo")

    assert result == (
        "In Oslo, it's 8 degrees Celsius with partlycloudy day. "
        "Wind is around 3 meters per second."
    )


@pytest.mark.asyncio
async def test_weather_handles_unknown_location(monkeypatch) -> None:
    monkeypatch.setattr(
        tools.httpx,
        "AsyncClient",
        lambda **kwargs: FakeClient([FakeResponse([])]),
    )

    result = await call_weather("A place that does not exist")

    assert result == "I couldn't find a location called A place that does not exist."


@pytest.mark.asyncio
async def test_weather_handles_connection_error(monkeypatch) -> None:
    error = httpx.ConnectError(
        "offline", request=httpx.Request("GET", "https://weather.test")
    )
    monkeypatch.setattr(
        tools.httpx,
        "AsyncClient",
        lambda **kwargs: FakeClient([error]),
    )

    result = await call_weather("Oslo")

    assert (
        result == "I couldn't retrieve the weather right now. Please try again shortly."
    )
