"""Scan tracked files and historical blobs; print locations/types, never values.
Candidates require review; removing a file does not revoke a leaked credential.
"""

import re
import subprocess

PATTERNS = {
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "OpenAI API key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{40,}"),
    "GitHub token": re.compile(rb"(?:ghp_|github_pat_)[A-Za-z0-9_]{30,}"),
    "JWT credential": re.compile(
        rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "assigned credential": re.compile(
        rb"""(?im)^\s*(?:LIVEKIT_API_SECRET|GOOGLE_API_KEY|GEMINI_API_KEY|HOME_ASSISTANT_TOKEN|ARIANA_ACCESS_CODE|PORCUPINE_ACCESS_KEY)\s*=\s*["']?([A-Za-z0-9_./+-]{24,})"""
    ),
}


def audit():
    listed = subprocess.check_output(["git", "rev-list", "--objects", "--all"])
    findings = []
    for entry in listed.splitlines():
        parts = entry.split(b" ", 1)
        if len(parts) != 2:
            continue
        sha, path = parts
        if subprocess.check_output(["git", "cat-file", "-t", sha]).strip() != b"blob":
            continue
        data = subprocess.check_output(["git", "cat-file", "blob", sha])
        for kind, pattern in PATTERNS.items():
            if (match := pattern.search(data)) and not (
                kind == "assigned credential"
                and match.group(1)
                in {b"your-long-lived-access-token", b"your-picovoice-access-key"}
            ):
                findings.append((sha.decode(), path.decode(errors="replace"), kind))
    for sha, path, kind in findings:
        print(f"REVIEW {kind}: blob {sha} file {path}")
    print(f"Credential candidate count: {len(findings)}; values are redacted.")
    return findings


if __name__ == "__main__":
    raise SystemExit(bool(audit()))
