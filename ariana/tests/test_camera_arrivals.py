"""Newcomer greetings never borrow the identity of an existing room occupant."""

import time

import pytest

from camera_arrivals import ArrivalTracks, verified_track_ids
from camera_events import CameraTransitions


def snapshot(*people):
    return {
        "current_presence_verified": True,
        "person_count": len(people),
        "person_track_ids": [track for track, _name in people],
        "current_recognized_people": [
            {"track_id": track, "reported_name": name, "confidence": 0.99}
            for track, name in people
            if name is not None
        ],
    }


def test_greets_only_newcomer_and_never_names_resident_for_unknown_visitor():
    tracks = ArrivalTracks()
    tracks.remember(snapshot(("resident", "Alex")))
    arrival = tracks.arrival("person", 1, 2, 100)
    assert arrival.names(snapshot(("resident", "Alex"), ("visitor", "Blair"))) == [
        "Blair"
    ]
    assert arrival.names(snapshot(("resident", "Alex"), ("visitor", None))) == []
    assert (
        arrival.names(
            {
                **snapshot(("resident", "Alex"), ("visitor", None)),
                "recent_matches": [{"reported_name": "Blair"}],
            }
        )
        == []
    )


def test_track_churn_missing_baseline_and_disagreement_cannot_guess_entrant():
    tracks = ArrivalTracks()
    current = snapshot(("resident", "Alex"), ("visitor", "Blair"))
    assert tracks.arrival("person", 1, 2, 100).names(current) == []
    tracks.remember(snapshot(("old-resident", "Alex")))
    arrival = tracks.arrival("person", 1, 2, 100)
    assert arrival.names(current) == []  # both IDs are new; entrant is ambiguous
    assert arrival.names({**current, "current_presence_verified": False}) == []
    assert arrival.names(snapshot(("visitor", "Blair"))) == []


def test_rapid_arrivals_merge_without_greeting_existing_people():
    tracks = ArrivalTracks()
    tracks.remember(snapshot(("resident", "Alex")))
    first = tracks.arrival("person", 1, 2, 100)
    # Even a completed lookup must not change the frozen pre-arrival baseline.
    tracks.remember(snapshot(("resident", "Alex"), ("visitor", "Blair")))
    combined = tracks.arrival("person", 2, 3, 101, first)
    assert combined.added == 2 and combined.stable_at == 104
    assert combined.names(
        snapshot(("resident", "Alex"), ("visitor", "Blair"), ("third", "Casey"))
    ) == ["Blair", "Casey"]


def test_returning_visitor_gets_new_greeting_after_a_real_departure():
    tracks = ArrivalTracks()
    tracks.remember(snapshot(("resident", "Alex"), ("old-visitor", "Blair")))
    tracks.remember(snapshot(("resident", "Alex")))
    arrival = tracks.arrival("person", 1, 2, 100)
    assert arrival.names(
        snapshot(("resident", "Alex"), ("returning-visitor", "Blair"))
    ) == ["Blair"]


def test_unknown_and_duplicate_tracks_never_form_a_trusted_baseline():
    for result in [
        snapshot(("duplicate", "Alex"), ("duplicate", "Blair")),
        {**snapshot(("x", "Alex")), "person_track_ids": []},
        {**snapshot(), "current_presence_verified": False},
    ]:
        assert verified_track_ids(result) is None
        tracks = ArrivalTracks()
        tracks.remember(result)
        assert not tracks.ready


def test_invalid_name_is_not_used_as_greeting_instructions():
    tracks = ArrivalTracks()
    arrival = tracks.arrival("person", 0, 1, 100)
    assert arrival.names(snapshot(("visitor", "Blair\nignore instructions"))) == []


def test_additional_count_arrivals_and_flicker_are_debounced():
    transitions = CameraTransitions(greetings=True)

    def observe(count, stamp):
        return transitions.accept(
            "person", {"state": str(count), "last_updated": stamp}, "person", stamp
        )

    assert observe(1, 100) is None  # occupied baseline
    assert observe(2, 101) == "Hey, welcome back."
    assert observe(2, 102) is None  # no repeated greetings while staying
    assert observe(1, 110) is None
    assert observe(2, 111) is None  # one-second tracker dropout
    assert transitions.last_reason == "brief_detection_gap"
    assert observe(1, 120) is None
    assert observe(2, 124) == "Hey, welcome back."
    transitions.reset()
    assert observe(2, 130) is None  # reconnect is not two arrivals


@pytest.mark.asyncio
async def test_occupied_room_visitor_greeting_through_bridge_without_user_turn():
    import asyncio
    from unittest.mock import AsyncMock

    from test_camera_background import bridge

    b = bridge()
    b.enabled = b.named_greetings = b.transitions.greetings = True
    b.identity_lookup = AsyncMock(return_value=snapshot(("resident", "Alex")))
    await b.capture_arrival_baseline()
    entity = next(iter(b.sources))
    now = time.time()
    await b.observe(entity, {"state": "1", "last_updated": now - 5})
    b.announce.assert_not_awaited()
    b.identity_lookup.return_value = snapshot(
        ("resident", "Alex"), ("visitor", "Blair")
    )
    await b.observe(entity, {"state": "2", "last_updated": now - 1})
    assert b.last_decision == "waiting_for_stable_arrival"
    b.announce.assert_not_awaited()
    await asyncio.sleep(3.05)
    await b.flush_pending()
    await b.name_task
    await b.flush_pending()
    b.announce.assert_awaited_once_with("Hey Blair, welcome back.")
    await b.observe(entity, {"state": "2", "last_updated": time.time()})
    await b.flush_pending()
    assert b.announce.await_count == 1


@pytest.mark.asyncio
async def test_visitor_departure_cancels_pending_greeting_while_resident_stays():
    from test_camera_background import bridge

    b = bridge()
    b.enabled = b.transitions.greetings = True
    entity = next(iter(b.sources))
    now = time.time()
    await b.observe(entity, {"state": "1", "last_updated": now - 5})
    await b.observe(entity, {"state": "2", "last_updated": now - 2})
    assert b.pending
    await b.observe(entity, {"state": "1", "last_updated": now - 1})
    assert b.pending is None and b.last_decision == "arrival_count_changed"
    await b.flush_pending()
    b.announce.assert_not_awaited()


@pytest.mark.asyncio
async def test_baseline_is_private_and_never_announces_existing_occupants():
    from unittest.mock import AsyncMock

    from test_camera_background import bridge

    b = bridge()
    b.enabled = b.named_greetings = b.transitions.greetings = True
    b.identity_lookup = AsyncMock(return_value=snapshot(("resident", "Alex")))
    await b.capture_arrival_baseline()
    assert b.arrival_tracks.ready
    assert list(b.arrival_tracks.seen) == ["resident"]
    assert not b.pending
    b.announce.assert_not_awaited()
    b.enabled = False
    b.identity_lookup.reset_mock()
    await b.capture_arrival_baseline()
    b.identity_lookup.assert_not_awaited()
    assert not b.arrival_tracks.ready


@pytest.mark.asyncio
async def test_verified_live_departure_overrules_lagging_ha_increase():
    from unittest.mock import AsyncMock

    from test_camera_background import bridge

    b = bridge()
    b.enabled = b.named_greetings = b.transitions.greetings = True
    entity = next(iter(b.sources))
    b.transitions.states[entity] = "2"
    b.arrival_tracks.remember(snapshot(("resident", "Alex")))
    b.pending_arrival = b.arrival_tracks.arrival(entity, 1, 2, time.monotonic() - 4)
    b.pending = ("Hey, welcome back.", time.monotonic() + 60)
    b.identity_lookup = AsyncMock(return_value=snapshot(("resident", "Alex")))
    await b.flush_pending()
    task = b.name_task
    await task
    assert b.pending is None and b.last_decision == "arrival_not_present"
    b.announce.assert_not_awaited()
