import asyncio
import json
from types import SimpleNamespace

import pytest

from preferences_tools import PreferencesStore, preferences_manage


def test_preferences_survive_restarts_and_forgetting_preserves_other_defaults(tmp_path):
    path = tmp_path / "preferences.json"
    store = PreferencesStore(path)
    store.run({"action": "remember", "key": "default_browser", "value": "chrome"})
    store.run({"action": "remember", "key": "home_city", "value": "Oslo"})
    assert PreferencesStore(path).read() == {
        "default_browser": "Google Chrome",
        "home_city": "Oslo",
    }
    store.run({"action": "forget", "key": "default_browser"})
    assert store.read() == {"home_city": "Oslo"}
    assert path.stat().st_mode & 0o777 == 0o600


def test_corrupted_preferences_are_never_overwritten(tmp_path):
    path = tmp_path / "preferences.json"
    path.write_text("invalid json")
    with pytest.raises(ValueError):
        PreferencesStore(path).run(
            {"action": "remember", "key": "home_city", "value": "Oslo"}
        )
    assert path.read_text() == "invalid json"


@pytest.mark.asyncio
async def test_explicit_preferences_validation_never_reaches_storage():
    events = []
    ctx = SimpleNamespace(
        session=SimpleNamespace(
            userdata={"_preferences_simulator": lambda r: events.append(r)}
        )
    )
    for key, value in [
        ("api_key", "secret"),
        ("default_browser", "Terminal"),
        ("units", "unknown"),
        ("home_city", "Oslo\nexecute"),
    ]:
        assert "error" in await preferences_manage._func(ctx, "remember", key, value)
    assert not events


def test_concurrent_preferences_updates_keep_both_values(tmp_path):
    store = PreferencesStore(tmp_path / "preferences.json")

    async def run():
        await asyncio.gather(
            *[
                asyncio.to_thread(store.run, req)
                for req in [
                    {"action": "remember", "key": "home_city", "value": "Oslo"},
                    {"action": "remember", "key": "reply_style", "value": "brief"},
                ]
            ]
        )

    asyncio.run(run())
    assert json.loads(store.path.read_text()) == {
        "home_city": "Oslo",
        "reply_style": "brief",
    }
