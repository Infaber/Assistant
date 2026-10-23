"""Demo switching preserves original presentation without backing up credentials."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def test_demo_backup_is_private_and_restores_only_presentation(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "demo_persona", Path(__file__).parents[1] / "scripts/demo_persona.py"
    )
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    backend = tmp_path / "backend.env"
    frontend = tmp_path / "frontend.env"
    backend.write_text(
        "GOOGLE_API_KEY=fake-private-do-not-back-up\nARIANA_GOOGLE_VOICE=Sulafat\n"
    )
    frontend.write_text("LIVEKIT_API_SECRET=fake-private-do-not-back-up\n")
    keys = tmp_path / "ariana-keywords.txt"
    keys.write_text("ORIGINAL TOKENS\n")
    monkeypatch.setattr(demo, "PROJECT", tmp_path)
    monkeypatch.setattr(demo, "BACKUP", tmp_path / "backup.json")
    monkeypatch.setattr(demo, "model_directory", lambda: tmp_path)
    monkeypatch.setattr(
        demo,
        "FIELDS",
        {
            "backend": (
                backend,
                {"ARIANA_PERSONA": "jarvis", "ARIANA_GOOGLE_VOICE": "Charon"},
            ),
            "frontend": (frontend, {"NEXT_PUBLIC_ASSISTANT_NAME": "Jarvis"}),
        },
    )
    monkeypatch.setitem(
        sys.modules,
        "setup_wake_word",
        SimpleNamespace(prepare_keywords=lambda *args: "JARVIS TOKENS\n"),
    )
    demo.apply("jarvis")
    assert "fake-private" not in demo.BACKUP.read_text()
    assert demo.BACKUP.stat().st_mode & 0o077 == 0
    assert keys.read_text() == "JARVIS TOKENS\n"
    backup = demo.BACKUP.read_text()
    demo.apply("jarvis")
    assert demo.BACKUP.read_text() == backup
    demo.apply("restore")
    assert keys.read_text() == "ORIGINAL TOKENS\n"
    assert "ARIANA_PERSONA" not in backend.read_text()
    assert "Sulafat" in backend.read_text()
    assert "fake-private-do-not-back-up" in backend.read_text()
    assert "NEXT_PUBLIC_ASSISTANT_NAME" not in frontend.read_text()
    assert not demo.BACKUP.exists()
