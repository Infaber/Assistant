"""Switch the local demo presentation; never copies API keys into the backup."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from dotenv import dotenv_values, load_dotenv, set_key, unset_key

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wake_config import model_directory

PROJECT = Path(__file__).resolve().parents[1]

BACKUP = Path.home() / "Library/Application Support/Ariana/demo-persona.json"
FIELDS = {
    "backend": (
        PROJECT / ".env.local",
        {"ARIANA_PERSONA": "jarvis", "ARIANA_GOOGLE_VOICE": "Charon"},
    ),
    "frontend": (
        PROJECT.parent / "frontend/.env.local",
        {"NEXT_PUBLIC_ASSISTANT_NAME": "Jarvis"},
    ),
}


def apply(profile):
    load_dotenv(PROJECT / ".env.local")
    keywords = model_directory() / "ariana-keywords.txt"
    if profile == "jarvis":
        # Tokenization is local; validate dependencies/model before changing any settings.
        from setup_wake_word import prepare_keywords

        new_keywords = (
            prepare_keywords(model_directory(), "Jarvis")
            if keywords.is_file()
            else None
        )
        if not BACKUP.exists():
            backup = {
                "version": 1,
                "wake_keywords": keywords.read_text() if keywords.is_file() else None,
            }
            for label, (path, values) in FIELDS.items():
                previous = dotenv_values(path)
                backup[label] = {key: previous.get(key) for key in values}
            BACKUP.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", dir=BACKUP.parent, delete=False
            ) as f:
                json.dump(backup, f)
                temporary = f.name
            os.replace(temporary, BACKUP)
        for path, values in FIELDS.values():
            for key, value in values.items():
                set_key(str(path), key, value)
        if new_keywords is not None:
            keywords.write_text(new_keywords)
        print(
            "Jarvis demo configured: Charon voice; Jarvis wake phrase when installed."
        )
    else:
        if not BACKUP.exists():
            raise ValueError("No saved demo settings to restore")
        previous = json.loads(BACKUP.read_text())
        if previous.get("version") != 1:
            raise ValueError("Unsupported demo backup")
        for label, (path, values) in FIELDS.items():
            for key in values:
                value = previous[label][key]
                if value is None:
                    unset_key(str(path), key)
                else:
                    set_key(str(path), key, value)
        if previous.get("wake_keywords") is not None and keywords.is_file():
            keywords.write_text(previous["wake_keywords"])
        BACKUP.unlink()
        print("Original name, voice and wake phrase restored.")
    print("Rebuild the frontend and reopen the companion to load these settings.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=["jarvis", "restore"])
    try:
        apply(parser.parse_args().profile)
    except Exception:
        print(
            "Demo configuration failed. Check the local model, dependencies and settings files.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
