from instructions import ARIANA_INSTRUCTIONS, configured_instructions


def test_default_persona_is_unchanged(monkeypatch):
    monkeypatch.delenv("ARIANA_PERSONA", raising=False)
    monkeypatch.setattr("preferences_tools.read_preferences", lambda: {})
    assert configured_instructions().startswith(ARIANA_INSTRUCTIONS)


def test_demo_preserves_all_shared_behavior_and_action_rules(monkeypatch):
    monkeypatch.setenv("ARIANA_PERSONA", "jarvis")
    result = configured_instructions()
    assert result.startswith("You are Jarvis")
    assert "British English" in result and "male voice" in result
    assert (
        result.split("Actions and grounding:", 1)[1].split(
            "Current local date/time", 1
        )[0]
        == ARIANA_INSTRUCTIONS.split("Actions and grounding:", 1)[1] + "\n"
    )
    monkeypatch.setenv("ARIANA_PERSONA", "ariana")
    assert configured_instructions().startswith(ARIANA_INSTRUCTIONS)
