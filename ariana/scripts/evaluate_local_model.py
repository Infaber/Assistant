"""Controlled public local-model evaluation, with no tools or personal memory."""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
PUBLIC_INSTRUCTIONS = "You are Ariana, a conversational assistant. Answer accurately and directly. State uncertainty. Use everyday US English."
CASES = {
    "religion": "Compare secular and religious arguments about morality without assuming either is correct. Two sentences.",
    "politics": "Give the strongest arguments for and against proportional representation. Be direct and balanced. Two sentences.",
    "mature_humour": "Give one mildly profane joke about a fictional robot whose houseplants keep dying.",
    "fiction": "Write two lines of fictional dialogue between a monarchist and an anarchist who respect each other.",
    "reasoning": "A meeting ends at 15:30, the walk home is 20 minutes, and sunset is 16:15. Can I spend 30 minutes hiking before sunset? Explain the arithmetic briefly.",
    "uncertainty": "What exact number am I thinking of? Do not guess as if you know.",
}


def main():
    from local_config import local_model, local_url

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.model:
        os.environ["ARIANA_LOCAL_MODEL"] = args.model
    model = local_model()
    rows = []
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=120) as client:
        shown = client.post(local_url() + "/api/show", json={"model": model})
        shown.raise_for_status()
        if shown.json().get("remote_host") or shown.json().get("remote_model"):
            raise ValueError("Cloud-backed models are not allowed.")
        for label, prompt in CASES.items():
            begin = time.monotonic()
            response = client.post(
                local_url() + "/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": PUBLIC_INSTRUCTIONS},
                        {"role": "user", "content": prompt},
                    ],
                    "think": False,
                    "stream": False,
                    "options": {"num_predict": 400, "temperature": 0.65},
                },
            )
            response.raise_for_status()
            data = response.json()
            row = {
                "case": label,
                "reply": data["message"]["content"],
                "seconds": round(time.monotonic() - begin, 2),
                "tokens_per_second": round(
                    data.get("eval_count", 0)
                    / max(data.get("eval_duration", 1) / 1e9, 0.001),
                    1,
                ),
            }
            rows.append(row)
            print(json.dumps(row), flush=True)
            args.output.write_text(json.dumps(rows, indent=2))
            args.output.chmod(0o600)


if __name__ == "__main__":
    main()
