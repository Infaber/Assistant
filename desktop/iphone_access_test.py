import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iphone_access import (
    our_listener,
    pairing_key,
    phone_environment,
    phone_origin,
    port_in_use,
    private_write,
    stop_children,
    tailscale_environment,
)


class PrivatePhoneTests(unittest.TestCase):
    def test_only_running_private_https_hosts_are_accepted(self):
        self.assertEqual(
            phone_origin(
                {"BackendState": "Running", "Self": {"DNSName": "mac.fixture.ts.net."}}
            ),
            "https://mac.fixture.ts.net:8443",
        )
        for status in [
            {},
            {"BackendState": "NeedsLogin"},
            {"BackendState": "Running", "Self": {"DNSName": "evil.example"}},
            {"BackendState": "Running", "Self": {"DNSName": "mac.ts.net/attacker"}},
        ]:
            with self.assertRaises(RuntimeError):
                phone_origin(status)

    def test_existing_servers_and_public_funnel_are_never_replaced(self):
        for config in [
            {"TCP": {"8443": {"HTTPS": True}}},
            {"Web": {"mac.ts.net:8443": {}}},
            {"AllowFunnel": {"mac.ts.net:8443": True}},
            {"Foreground": {"session": {"TCP": {"8443": {}}}}},
        ]:
            self.assertTrue(port_in_use(config))
        self.assertFalse(port_in_use({"TCP": {"443": {"HTTPS": True}}}))
        for config in [None, {"TCP": None}, {"Foreground": {"bad": None}}]:
            with self.assertRaises(RuntimeError):
                port_in_use(config)

    def test_ready_requires_our_exact_https_target(self):
        config = {
            "TCP": {"8443": {"HTTPS": True}},
            "Web": {
                "mac.fixture.ts.net:8443": {
                    "Handlers": {"/": {"Proxy": "http://127.0.0.1:3031"}}
                }
            },
        }
        self.assertTrue(
            our_listener(
                {"Foreground": {"owned": config}}, "https://mac.fixture.ts.net:8443"
            )
        )
        self.assertFalse(our_listener(config, "https://other.fixture.ts.net:8443"))
        config["Web"]["mac.fixture.ts.net:8443"]["Handlers"]["/"]["Proxy"] = (
            "http://127.0.0.1:9999"
        )
        self.assertFalse(our_listener(config, "https://mac.fixture.ts.net:8443"))
        config["AllowFunnel"] = {"mac.fixture.ts.net:8443": True}
        with self.assertRaises(RuntimeError):
            our_listener(config, "https://mac.fixture.ts.net:8443")

    def test_pairing_key_is_private_stable_and_resettable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "key"
            first = pairing_key(path)
            self.assertGreaterEqual(len(first), 40)
            self.assertEqual(pairing_key(path), first)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            path.unlink()
            self.assertNotEqual(pairing_key(path), first)
            alias = Path(folder) / "alias"
            alias.symlink_to(path)
            with self.assertRaises(RuntimeError):
                pairing_key(alias)
            with self.assertRaises(RuntimeError):
                private_write(alias, "unexpected")
            self.assertNotEqual(path.read_text(), "unexpected")

    def test_separate_worker_and_exact_origin_do_not_reuse_desktop_auth(self):
        with patch.dict(
            os.environ,
            {
                "ARIANA_ACCESS_CODE": "desktop-secret",
                "LIVEKIT_API_SECRET": "fixture-secret",
            },
        ):
            environment = phone_environment(
                "https://mac.fixture.ts.net:8443", "phone-key", "instance"
            )
            self.assertEqual(environment["ARIANA_ACCESS_CODE"], "phone-key")
            self.assertEqual(
                environment["APP_ORIGIN"], "https://mac.fixture.ts.net:8443"
            )
            self.assertTrue(
                environment["LIVEKIT_AGENT_NAME"].startswith("ariana-iphone-")
            )
            self.assertEqual(
                environment["ARIANA_AGENT_NAME"], environment["LIVEKIT_AGENT_NAME"]
            )
            self.assertEqual(environment["ARIANA_PHONE_ACCESS"], "1")
            self.assertNotIn("ARIANA_ACCESS_CODE", tailscale_environment())
            self.assertNotIn("LIVEKIT_API_SECRET", tailscale_environment())

    def test_stopping_phone_owner_ends_its_children(self):
        children = [
            subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
            for _ in range(2)
        ]
        try:
            stop_children(children)
            self.assertTrue(all(child.poll() is not None for child in children))
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    unittest.main()
