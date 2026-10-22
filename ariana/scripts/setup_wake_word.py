"""Download and verify the free local wake model; never opens a microphone."""

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wake_config import (
    MODEL_NAME,
    MODEL_SHA256,
    MODEL_URL,
    model_directory,
    model_files,
)

MAX_DOWNLOAD = 24 * 1024 * 1024


def prepare_keywords(directory, phrase):
    import sentencepiece

    phrase = phrase.strip().upper()
    if (
        not phrase
        or len(phrase) > 60
        or not all(c.isalpha() or c == " " for c in phrase)
    ):
        raise ValueError("Use a short phrase containing only letters and spaces")
    tokenizer = sentencepiece.SentencePieceProcessor(
        model_file=str(directory / "bpe.model")
    )
    pieces = tokenizer.encode(phrase, out_type=str)
    vocabulary = {
        line.split()[0]
        for line in (directory / "tokens.txt").read_text().splitlines()
        if line.strip()
    }
    if not pieces or any(
        piece not in vocabulary or piece == "<unk>" for piece in pieces
    ):
        raise ValueError("The English model cannot encode this phrase")
    return " ".join(pieces) + "\n"


def unpack_model(data, directory):
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise ValueError("Wake model checksum mismatch; download rejected")
    names = {p.name for k, p in model_files(directory).items() if k != "keywords_file"}
    names.update({"bpe.model", "README.md"})
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as archive:
        # Never extract paths, links or executable contents from the archive.
        for name in names:
            member = archive.getmember(f"{MODEL_NAME}/{name}")
            if not member.isfile() or member.size > 16 * 1024 * 1024:
                raise ValueError("Unexpected model archive entry")
            content = archive.extractfile(member).read()
            (directory / name).write_bytes(content)
            hashes[name] = hashlib.sha256(content).hexdigest()
    (directory / "model-manifest.json").write_text(
        json.dumps({"archive": MODEL_SHA256, "files": hashes})
    )


def installed(directory):
    try:
        manifest = json.loads((directory / "model-manifest.json").read_text())
        expected = {
            p.name for k, p in model_files(directory).items() if k != "keywords_file"
        } | {"bpe.model", "README.md"}
        return (
            manifest["archive"] == MODEL_SHA256
            and set(manifest["files"]) == expected
            and all(
                hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
                for name, digest in manifest["files"].items()
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def setup(directory, phrase=None):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not installed(directory):
        import httpx

        data = bytearray()
        with httpx.stream(
            "GET", MODEL_URL, follow_redirects=True, timeout=90
        ) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_DOWNLOAD:
                    raise ValueError("Wake model download exceeds size limit")
        with tempfile.TemporaryDirectory(dir=directory.parent) as staging:
            staging = Path(staging)
            unpack_model(data, staging)
            for file in staging.iterdir():
                os.replace(file, directory / file.name)
    keywords = model_files(directory)["keywords_file"]
    if phrase is not None or not keywords.is_file():
        text = prepare_keywords(directory, phrase or "Ariana")
        temporary = keywords.with_suffix(".tmp")
        temporary.write_text(text)
        os.replace(temporary, keywords)
    print("Free local wake model ready. Enable Wake word in Ariana's menu.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phrase", help="Wake phrase (default on first install: Ariana)"
    )
    args = parser.parse_args()
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
    try:
        setup(model_directory(), args.phrase)
    except Exception:
        # Paths and network exceptions may include private local configuration.
        print(
            "Wake setup failed. Check network access, disk space and the wake-word dependencies.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
