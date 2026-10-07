"""Own one service process group; shut it down when the native app pipe closes."""

import os
import select
import signal
import subprocess
import sys
import time
from contextlib import suppress


def run(command):
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, start_new_session=True)
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while child.poll() is None and not stopping:
            readable, _, _ = select.select([sys.stdin], [], [], 1)
            if readable and not os.read(sys.stdin.fileno(), 1024):
                break
        if child.poll() is not None:
            return child.returncode
    finally:
        deadline = time.monotonic() + 8
        # Even a crashed parent may leave worker descendants in the owned group.
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGTERM)
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        # Reap/stop surviving descendants too, including after a parent crash.
        while time.monotonic() < deadline:
            try:
                os.killpg(child.pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        with suppress(ProcessLookupError):
            os.killpg(child.pid, signal.SIGKILL)
    return 0


if __name__ == "__main__":
    command = sys.argv[1:]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("Provide a service command.")
    raise SystemExit(run(command))
