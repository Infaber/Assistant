import subprocess
import sys
from pathlib import Path


def test_parent_pipe_close_stops_owned_service(tmp_path):
    script = Path(__file__).parents[1] / "src/service_runner.py"
    runner = subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--",
            sys.executable,
            "-c",
            "import time; print('ready',flush=True); time.sleep(60)",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    assert runner.stdout.readline().strip() == b"ready"
    runner.stdin.close()
    assert runner.wait(timeout=12) == 0


def test_service_crash_preserves_exit_code():
    script = Path(__file__).parents[1] / "src/service_runner.py"
    result = subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--",
            sys.executable,
            "-c",
            "raise SystemExit(7)",
        ],
        stdin=subprocess.PIPE,
    )
    try:
        assert result.wait(timeout=12) == 7
    finally:
        result.stdin.close()


def test_crashed_parent_stops_its_worker_descendants(tmp_path):
    script = Path(__file__).parents[1] / "src/service_runner.py"
    marker = tmp_path / "state"
    grandchild = (
        "import signal,time,pathlib; p=pathlib.Path("
        + repr(str(marker))
        + "); signal.signal(signal.SIGTERM,lambda *_: (p.write_text('stopped'),exit(0))); p.write_text('ready'); time.sleep(60)"
    )
    parent = (
        "import subprocess,sys,time,pathlib; subprocess.Popen([sys.executable,'-c',"
        + repr(grandchild)
        + "]); p=pathlib.Path("
        + repr(str(marker))
        + ");\nwhile not p.exists(): time.sleep(.01)\nraise SystemExit(7)"
    )
    runner = subprocess.Popen(
        [sys.executable, str(script), "--", sys.executable, "-c", parent],
        stdin=subprocess.PIPE,
    )
    try:
        assert runner.wait(timeout=12) == 7
        assert marker.read_text() == "stopped"
    finally:
        runner.stdin.close()
