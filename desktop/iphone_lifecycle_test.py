"""Exercise the owner lifecycle with fake Tailscale, frontend and agent processes."""

import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class PhoneLifecycleTests(unittest.TestCase):
    def test_owned_private_listener_and_agent_end_together(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "ariana/.venv/bin").mkdir(parents=True)
            (root / "frontend").mkdir()
            state, key, marker = (
                root / name for name in ("state", "key", "serve-marker")
            )
            agent_pid = root / "agent-pid"
            agent = root / "ariana/.venv/bin/python"
            agent.write_text(
                f"#!{sys.executable}\nimport os,time,pathlib\npathlib.Path({str(agent_pid)!r}).write_text(str(os.getpid()))\ntime.sleep(120)\n"
            )
            agent.chmod(0o700)
            node = root / "fake-node"
            node.write_text(f"""#!{sys.executable}
import json,os
from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(json.dumps({{"ok":True,"instance":os.environ["ARIANA_DESKTOP_INSTANCE"]}}).encode())
 def log_message(self,*args):pass
HTTPServer(("127.0.0.1",3031),Handler).serve_forever()
""")
            node.chmod(0o700)
            tailscale = root / "fake-tailscale"
            tailscale.write_text(f"""#!{sys.executable}
import json,sys,time,signal
from pathlib import Path
marker=Path({str(marker)!r})
if sys.argv[1:]==["status","--json"]:
 print(json.dumps({{"BackendState":"Running","Self":{{"DNSName":"mac.fixture.ts.net."}}}}))
elif sys.argv[1:]==["serve","status","--json"]:
 config={{"TCP":{{"8443":{{"HTTPS":True}}}},"Web":{{"mac.fixture.ts.net:8443":{{"Handlers":{{"/":{{"Proxy":"http://127.0.0.1:3031"}}}}}}}}}}
 print(json.dumps({{"Foreground":{{"owned":config}}}} if marker.exists() else {{}}))
else:
 assert sys.argv[1:]==["serve","--https=8443","http://127.0.0.1:3031"]
 marker.write_text("foreground")
 def stop(*args):raise SystemExit(0)
 signal.signal(signal.SIGTERM,stop)
 try:time.sleep(120)
 finally:marker.unlink(missing_ok=True)
""")
            tailscale.chmod(0o700)
            harness = f"""import sys
sys.path.insert(0,{str(Path(__file__).parent)!r})
from pathlib import Path
from unittest.mock import patch
import iphone_access
with patch.object(iphone_access,"tailscale_binary",return_value={str(tailscale)!r}):
 sys.exit(iphone_access.run(Path({str(root)!r}),Path({str(state)!r}),Path({str(key)!r}),"fixture-instance",{str(node)!r}))
"""
            owner = subprocess.Popen(
                [sys.executable, "-c", harness],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 15
                snapshot = {}
                while time.monotonic() < deadline and owner.poll() is None:
                    if state.exists():
                        snapshot = json.loads(state.read_text())
                        if snapshot["phase"] == "ready":
                            break
                    time.sleep(0.05)
                self.assertEqual(snapshot.get("phase"), "ready", snapshot)
                self.assertEqual(snapshot["url"], "https://mac.fixture.ts.net:8443")
                self.assertEqual(snapshot["code"], key.read_text())
                self.assertTrue(marker.exists())
                pid = int(agent_pid.read_text())
                owner.terminate()
                self.assertEqual(owner.wait(timeout=10), 0)
                self.assertFalse(marker.exists())
                with self.assertRaises(ProcessLookupError):
                    import os

                    os.kill(pid, 0)
                with socket.socket() as client:
                    self.assertNotEqual(client.connect_ex(("127.0.0.1", 3031)), 0)
                self.assertNotIn("code", json.loads(state.read_text()))
            finally:
                if owner.poll() is None:
                    owner.terminate()
                    owner.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
