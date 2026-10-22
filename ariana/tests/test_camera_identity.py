import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from camera_recognition import current_identity
from frigate_api import CameraError


def setup(number=1, score=0.98):
    now = time.time()
    row = {
        "id": "person-1",
        "camera": "bedroom",
        "label": "person",
        "start_time": now - 3600,
        "end_time": None,
        "false_positive": False,
        "sub_label": "Alex",
        "data": {"sub_label_score": score},
    }
    client = SimpleNamespace(
        current=AsyncMock(return_value={"person_count": number, "observed_at": now}),
        health=AsyncMock(return_value={"online": True, "observed_at": now}),
        api=SimpleNamespace(get=AsyncMock(return_value=[row])),
    )
    return client, row


@pytest.mark.asyncio
async def test_long_running_recognized_person_is_not_lost_to_history_cutoff():
    client, _row = setup()
    result = await current_identity(client, "bedroom", object())
    assert result["identity_now"] == "Alex" and result["current_presence_verified"]
    assert result["unknown_person_count"] == 0
    assert result["person_track_ids"] == ["person-1"]
    assert result["current_recognized_people"][0]["track_id"] == "person-1"
    args = client.api.get.call_args.args
    assert args[1]["in_progress"] == 1 and args[1]["include_thumbnails"] == 0
    assert "after" not in args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"end_time": 1},
        {"camera": "other"},
        {"label": "dog"},
        {"false_positive": True},
        {"id": None},
        {"start_time": float("nan")},
        {"start_time": float("inf")},
        {"start_time": time.time() + 3600},
    ],
)
async def test_ended_invalid_or_unrelated_tracks_cannot_identify_current_person(change):
    client, row = setup()
    client.api.get.return_value = [{**row, **change}]
    result = await current_identity(client, "bedroom", object())
    assert (
        result["identity_now"] == "unknown" and not result["current_presence_verified"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [0.94, None, float("nan"), True, 1.1])
async def test_weak_match_does_not_borrow_old_identity(score):
    client, _row = setup(score=score)
    result = await current_identity(client, "bedroom", object())
    assert result["current_recognized_people"] == []
    assert result["current_presence_verified"] and result["unknown_person_count"] == 1


@pytest.mark.asyncio
async def test_multiple_people_retains_unknown_person_instead_of_naming_everyone():
    client, row = setup(number=2)
    client.api.get.return_value = [
        row,
        {**row, "id": "person-2", "sub_label": None, "data": {}},
    ]
    result = await current_identity(client, "bedroom", object())
    assert len(result["current_recognized_people"]) == 1
    assert (
        result["current_identity_status"] == "partial"
        and result["unknown_person_count"] == 1
    )


@pytest.mark.asyncio
async def test_count_disagreement_stale_count_and_offline_stream_remain_unknown():
    client, _row = setup(number=2)
    assert not (await current_identity(client, "bedroom", object()))[
        "current_presence_verified"
    ]
    client.current.side_effect = CameraError("stale")
    assert (await current_identity(client, "bedroom", object()))[
        "identity_now"
    ] == "unknown"
    client.current.side_effect = None
    client.health.return_value = {"online": False}
    assert not (await current_identity(client, "bedroom", object()))[
        "current_presence_verified"
    ]


@pytest.mark.asyncio
async def test_duplicate_tracks_fail_closed():
    client, row = setup(number=2)
    client.api.get.return_value = [row, row]
    assert not (await current_identity(client, "bedroom", object()))[
        "current_presence_verified"
    ]


@pytest.mark.asyncio
async def test_empty_room_does_not_use_past_recognition():
    client, _row = setup(number=0)
    client.api.get.return_value = []
    result = await current_identity(client, "bedroom", object())
    assert result["current_identity_status"] == "empty"
    assert result["current_recognized_people"] == []
