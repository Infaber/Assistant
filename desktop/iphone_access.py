"""Opt-in private iPhone access, owned by the Mac companion's service runner.

Tailscale Serve stays in foreground: stopping Ariana removes this listener. A
separate agent worker lets disabling phone access also end its active sessions.
No credentials are printed, sent to Tailscale, or placed in command arguments.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from contextlib import suppress
from pathlib import Path


class PhoneSetupError(RuntimeError):
    """An actionable setup failure, safe to display without CLI output."""


PHONE_PORT = 3031
AGENT_PORT = 8084
HTTPS_PORT = 8443


def tailscale_binary():
    for candidate in (
        "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
        "/usr/local/bin/tailscale",
        "/opt/homebrew/bin/tailscale",
    ):
        if os.access(candidate, os.X_OK):
            return candidate
    raise PhoneSetupError(
        "Install Tailscale on this Mac and your iPhone, then sign in to the same account."
    )


def tailscale_environment():
    return {
        **{
            key: os.environ[key]
            for key in ("HOME", "PATH", "TMPDIR", "USER", "LOGNAME")
            if key in os.environ
        },
        "TAILSCALE_BE_CLI": "1",
    }


def cli_json(binary, arguments):
    result = subprocess.run(
        [binary, *arguments],
        capture_output=True,
        check=False,
        timeout=12,
        env=tailscale_environment(),
        stdin=subprocess.DEVNULL,
    )
    if result.returncode or len(result.stdout) > 2_000_000:
        raise PhoneSetupError(
            "Open Tailscale on this Mac, sign in and connect, then retry."
        )
    try:
        value = json.loads(result.stdout)
    except (ValueError, UnicodeError) as error:
        raise PhoneSetupError(
            "Tailscale status is unavailable. Open Tailscale and retry."
        ) from error
    if not isinstance(value, dict):
        raise PhoneSetupError(
            "Tailscale returned an unsupported status. Update Tailscale and retry."
        )
    return value


def phone_origin(status):
    if status.get("BackendState") != "Running":
        raise PhoneSetupError("Connect Tailscale on this Mac, then retry.")
    identity = status.get("Self")
    if not isinstance(identity, dict) or not isinstance(identity.get("DNSName"), str):
        raise PhoneSetupError(
            "Tailscale did not provide this Mac’s private DNS name. Enable MagicDNS and retry."
        )
    name = identity["DNSName"].rstrip(".")
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,240})\.ts\.net", name):
        raise PhoneSetupError(
            "Enable MagicDNS and HTTPS certificates in Tailscale, then retry."
        )
    return f"https://{name}:{HTTPS_PORT}"


def port_in_use(config, port=HTTPS_PORT):
    if not isinstance(config, dict) or any(
        not isinstance(config.get(key, {}), dict)
        for key in ("TCP", "Web", "AllowFunnel", "Foreground")
    ):
        raise PhoneSetupError(
            "Unsupported Tailscale Serve configuration. Update Tailscale and retry."
        )
    # Foreground Serve sessions are nested configs. Never replace another one.
    if str(port) in config.get("TCP", {}):
        return True
    if any(key.endswith(f":{port}") for key in config.get("Web", {})):
        return True
    if any(
        key.endswith(f":{port}") and enabled
        for key, enabled in config.get("AllowFunnel", {}).items()
    ):
        return True
    return any(
        port_in_use(value, port) for value in config.get("Foreground", {}).values()
    )


def our_listener(config, origin):
    port_in_use(config)  # Validate the supported config shape before inspecting it.
    hostname = origin.removeprefix("https://")
    if any(
        key.endswith(f":{HTTPS_PORT}") and enabled
        for key, enabled in config.get("AllowFunnel", {}).items()
    ):
        raise PhoneSetupError(
            "Public Funnel is enabled on the iPhone port. Disable it before using private iPhone access."
        )
    web = config.get("Web", {}).get(hostname, {})
    handler = web.get("Handlers", {}).get("/", {})
    own = (
        config.get("TCP", {}).get(str(HTTPS_PORT), {}).get("HTTPS") is True
        and handler.get("Proxy", "").rstrip("/") == f"http://127.0.0.1:{PHONE_PORT}"
    )
    return own or any(
        our_listener(value, origin) for value in config.get("Foreground", {}).values()
    )


def private_write(path, payload):
    if path.is_symlink():
        raise PhoneSetupError("Phone settings file must not be a symbolic link.")
    temporary = path.with_name(path.name + "." + secrets.token_hex(8))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(payload)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def pairing_key(path):
    if path.is_symlink():
        raise PhoneSetupError("Phone pairing key must not be a symbolic link.")
    if path.exists():
        key = path.read_text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{40,128}", key):
            raise PhoneSetupError(
                "Turn iPhone access off and on to reset its pairing key."
            )
        os.chmod(path, 0o600)
        return key
    key = secrets.token_urlsafe(36)
    private_write(path, key)
    return key


def phone_environment(origin, key, instance):
    worker = "ariana-iphone-" + hashlib.sha256(key.encode()).hexdigest()[:16]
    return {
        **os.environ,
        "ARIANA_PHONE_ACCESS": "1",
        "NODE_ENV": "production",
        "APP_ORIGIN": origin,
        "ARIANA_ACCESS_CODE": key,
        "LIVEKIT_AGENT_NAME": worker,
        "ARIANA_AGENT_NAME": worker,
        "ARIANA_AGENT_PORT": str(AGENT_PORT),
        "ARIANA_DESKTOP_INSTANCE": instance,
        "TAILSCALE_BE_CLI": "1",
    }


def check_ports():
    for port in (PHONE_PORT, AGENT_PORT):
        with socket.socket() as listener:
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise PhoneSetupError(
                    f"iPhone service port {port} is busy. Stop the other service and retry."
                ) from error


def stop_children(children):
    for child in reversed(children):
        if child.poll() is None:
            with suppress(ProcessLookupError):
                child.terminate()
    deadline = time.monotonic() + 5
    for child in reversed(children):
        try:
            child.wait(timeout=max(0.01, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                child.kill()
            child.wait()


def run(root, state_path, key_path, instance, node):
    children = []
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    def state(phase, message, **values):
        private_write(
            state_path,
            json.dumps(
                {"instance": instance, "phase": phase, "message": message, **values}
            ),
        )

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    state("starting", "Checking the private iPhone connection…")
    try:
        binary = tailscale_binary()
        origin = phone_origin(cli_json(binary, ["status", "--json"]))
        if port_in_use(cli_json(binary, ["serve", "status", "--json"])):
            raise PhoneSetupError(
                "Tailscale port 8443 is already configured. Ariana will not replace that service."
            )
        check_ports()
        key = pairing_key(key_path)
        environment = phone_environment(origin, key, instance)
        commands = [
            (
                [
                    str(root / "ariana/.venv/bin/python"),
                    "-m",
                    "livekit.agents",
                    "start",
                    "src/agent.py",
                ],
                root / "ariana",
            ),
            (
                [
                    node,
                    str(root / "frontend/node_modules/next/dist/bin/next"),
                    "start",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(PHONE_PORT),
                ],
                root / "frontend",
            ),
        ]
        for command, folder in commands:
            children.append(
                subprocess.Popen(
                    command, cwd=folder, env=environment, stdin=subprocess.DEVNULL
                )
            )
        deadline = time.monotonic() + 45
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise PhoneSetupError(
                    "The iPhone services stopped. Check Ariana’s connection and retry."
                )
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PHONE_PORT}/api/health", timeout=1
                ) as response:
                    health = json.load(response)
                if health.get("ok") and health.get("instance") == instance:
                    break
            except (OSError, ValueError):
                pass
            if time.monotonic() > deadline:
                raise PhoneSetupError(
                    "The iPhone frontend did not become ready. Rebuild Ariana and retry."
                )
            time.sleep(0.25)
        if stopping:
            return 0
        # No --bg or Funnel. This listener disappears when the owned CLI exits.
        serve = subprocess.Popen(
            [
                binary,
                "serve",
                f"--https={HTTPS_PORT}",
                f"http://127.0.0.1:{PHONE_PORT}",
            ],
            env=tailscale_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        children.append(serve)
        time.sleep(1)
        if serve.poll() is not None:
            raise PhoneSetupError(
                "Enable HTTPS certificates in the Tailscale admin console, then retry iPhone access."
            )
        # An alive CLI alone is insufficient: require its actual HTTPS mapping.
        config = cli_json(binary, ["serve", "status", "--json"])
        if not our_listener(config, origin):
            raise PhoneSetupError(
                "The private HTTPS listener is not ready. Check Tailscale’s HTTPS setup and retry."
            )
        state("ready", "Ready to pair your iPhone.", url=origin, code=key)
        while not stopping:
            if any(child.poll() is not None for child in children):
                raise PhoneSetupError(
                    "The private iPhone connection stopped. Open Tailscale and retry."
                )
            time.sleep(0.5)
        state("off", "iPhone access is off.")
        return 0
    except (
        RuntimeError,
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        subprocess.TimeoutExpired,
    ) as error:
        message = (
            str(error)
            if isinstance(error, PhoneSetupError)
            else "The iPhone connection could not start. Open Tailscale and retry."
        )
        state("error", message)
        return 1
    finally:
        stop_children(children)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--node", required=True)
    args = parser.parse_args()
    sys.exit(run(args.root, args.state, args.key, args.instance, args.node))
