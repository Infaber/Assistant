from instructions import ARIANA_INSTRUCTIONS, configured_instructions


def test_default_persona_is_unchanged(monkeypatch):
    monkeypatch.delenv("ARIANA_PERSONA", raising=False)
    assert configured_instructions() == ARIANA_INSTRUCTIONS


def test_demo_preserves_all_shared_behavior_and_action_rules(monkeypatch):
    monkeypatch.setenv("ARIANA_PERSONA", "jarvis")
    result = configured_instructions()
    assert result.startswith("You are Jarvis")
    assert "British male voice" in result
    assert (
        result.split("Plain spoken prose", 1)[1]
        == ARIANA_INSTRUCTIONS.split("Plain spoken prose", 1)[1]
    )
    monkeypatch.setenv("ARIANA_PERSONA", "ariana")
    assert configured_instructions() == ARIANA_INSTRUCTIONS
