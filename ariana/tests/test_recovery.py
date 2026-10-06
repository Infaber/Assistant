from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from recovery import describe_failure, install_recovery


@pytest.mark.parametrize(
    "message,code",
    [
        ("RESOURCE_EXHAUSTED secret", "model_quota"),
        ("API key secret", "model_auth"),
        ("network secret", "model_unavailable"),
    ],
)
def test_provider_errors_are_classified_without_leaking_details(message, code):
    result = describe_failure(SimpleNamespace(error=message))
    assert result[0] == code and "secret" not in result[1]


class Session:
    def __init__(self):
        self.update_agent = Mock()
        self.current_agent = SimpleNamespace(
            chat_ctx=SimpleNamespace(copy=lambda: "context")
        )

    def on(self, name):
        def register(callback):
            self.callback = callback
            return callback

        return register


def event(message="quota", recoverable=False):
    return SimpleNamespace(
        error=SimpleNamespace(error=message, recoverable=recoverable)
    )


def test_default_recovery_reports_failure_without_replaying(monkeypatch):
    monkeypatch.delenv("ARIANA_FALLBACK_GOOGLE_MODEL", raising=False)
    session = Session()
    publisher = Mock()
    make = Mock()
    install_recovery(session, publisher, make)
    session.callback(event())
    make.assert_not_called()
    session.update_agent.assert_not_called()
    assert publisher.publish.call_args.args[0]["code"] == "model_quota"


def test_configured_backup_is_attempted_once_and_carries_context(monkeypatch):
    monkeypatch.setenv("ARIANA_FALLBACK_GOOGLE_MODEL", "backup")
    session = Session()
    publisher = Mock()
    make = Mock(return_value="agent")
    install_recovery(session, publisher, make)
    failure = event()
    session.callback(failure)
    assert failure.error.recoverable
    make.assert_called_once_with("backup", "context")
    session.update_agent.assert_called_once_with("agent")
    session.callback(event())
    assert make.call_count == 1
    assert publisher.publish.call_args.args[0]["status"] == "failed"


def test_auth_failures_never_cycle_models(monkeypatch):
    monkeypatch.setenv("ARIANA_FALLBACK_GOOGLE_MODEL", "backup")
    session = Session()
    publisher = Mock()
    make = Mock()
    install_recovery(session, publisher, make)
    session.callback(event("API key rejected"))
    make.assert_not_called()
    assert publisher.publish.call_args.args[0]["code"] == "model_auth"


def test_failed_handoff_keeps_terminal_error(monkeypatch):
    monkeypatch.setenv("ARIANA_FALLBACK_GOOGLE_MODEL", "backup")
    session = Session()
    publisher = Mock()
    make = Mock(side_effect=ValueError("bad backup"))
    install_recovery(session, publisher, make)
    failure = event()
    session.callback(failure)
    assert not failure.error.recoverable
    assert publisher.publish.call_args.args[0]["status"] == "failed"
