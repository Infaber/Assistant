"""Install a local Ollama model and create the bounded Ariana alias. No cloud tags."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main():
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env.local")
    from local_config import local_model, local_url

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=(
            "huihui_ai/qwen3-abliterated:4b"
            if local_model() == "ariana-local:4b"
            else "huihui_ai/qwen3-abliterated:8b-v2"
        ),
        choices=[
            "huihui_ai/qwen3-abliterated:8b-v2",
            "huihui_ai/qwen3-abliterated:4b",
            "huihui_ai/qwen3.5-abliterated:4B",
        ],
    )
    parser.add_argument(
        "--skip-router",
        action="store_true",
        help="Keep routing on the answer model instead of installing the small classifier.",
    )
    args = parser.parse_args()
    environment = {**os.environ, "OLLAMA_HOST": local_url()}
    subprocess.run(["ollama", "pull", args.source], env=environment, check=True)
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=90) as client:
        result = client.post(
            local_url() + "/api/create",
            json={
                "model": local_model(),
                "from": args.source,
                "parameters": {"num_ctx": 16384, "num_predict": 700},
                "stream": False,
            },
        )
        result.raise_for_status()
    if not args.skip_router:
        # Explicit setup may download weights; ordinary conversations never do.
        router = os.getenv("ARIANA_LOCAL_ROUTER_MODEL", "qwen3:0.6b").strip()
        if router:
            if (
                len(router) > 120
                or any(c.isspace() for c in router)
                or "cloud" in router.lower()
            ):
                raise ValueError("Choose a local router model.")
            subprocess.run(["ollama", "pull", router], env=environment, check=True)
    print("Created", local_model(), "from", args.source, "with a 16K context window.")


if __name__ == "__main__":
    main()
