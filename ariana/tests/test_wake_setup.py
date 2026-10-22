"""Installer integrity and phrase validation, without downloads or microphone access."""

import importlib.util
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "wake_setup", Path(__file__).parents[1] / "scripts/setup_wake_word.py"
)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


def test_download_checksum_rejected_before_writes(tmp_path):
    with pytest.raises(ValueError, match="checksum"):
        setup.unpack_model(b"not-the-official-model", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_archive_links_rejected(tmp_path, monkeypatch):
    import hashlib

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:bz2") as archive:
        for name in [
            "bpe.model",
            "README.md",
            "tokens.txt",
            *[
                p.name
                for key, p in setup.model_files(tmp_path).items()
                if key not in {"tokens", "keywords_file"}
            ],
        ]:
            member = tarfile.TarInfo(f"{setup.MODEL_NAME}/{name}")
            member.type = tarfile.SYMTYPE
            member.linkname = "/tmp/forbidden-target"
            archive.addfile(member)
    payload = data.getvalue()
    monkeypatch.setattr(setup, "MODEL_SHA256", hashlib.sha256(payload).hexdigest())
    with pytest.raises(ValueError, match="archive entry"):
        setup.unpack_model(payload, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_manifest_cannot_verify_arbitrary_paths(tmp_path):
    (tmp_path / "model-manifest.json").write_text(
        json.dumps({"archive": setup.MODEL_SHA256, "files": {"../private": "whatever"}})
    )
    assert not setup.installed(tmp_path)


def test_phrase_uses_real_tokenizer_output_and_rejects_unknown(tmp_path, monkeypatch):
    import sys

    tokenizer = SimpleNamespace(encode=lambda phrase, out_type: ["▁ARI", "ANA"])
    monkeypatch.setitem(
        sys.modules,
        "sentencepiece",
        SimpleNamespace(SentencePieceProcessor=lambda **kwargs: tokenizer),
    )
    (tmp_path / "tokens.txt").write_text("▁ARI 1\nANA 2\n")
    assert setup.prepare_keywords(tmp_path, "Ariana") == "▁ARI ANA\n"
    with pytest.raises(ValueError, match="letters"):
        setup.prepare_keywords(tmp_path, "Ariana\nINJECT")
    tokenizer.encode = lambda phrase, out_type: ["<unk>"]
    with pytest.raises(ValueError, match="cannot encode"):
        setup.prepare_keywords(tmp_path, "Ariana")


def test_reinstall_preserves_phrase_and_never_downloads_when_verified(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(setup, "installed", lambda directory: True)
    monkeypatch.setattr(
        setup, "prepare_keywords", lambda directory, phrase: phrase + "\n"
    )
    file = setup.model_files(tmp_path)["keywords_file"]
    file.write_text("HEY ARIANA\n")
    setup.setup(tmp_path)
    assert file.read_text() == "HEY ARIANA\n"
    setup.setup(tmp_path, "Ariana")
    assert file.read_text() == "Ariana\n"
