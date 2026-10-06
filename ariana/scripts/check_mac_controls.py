"""Opt-in real Mac controls smoke test; uses temporary windows, never personal files."""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mac_native import run as native
from mac_tools import mac_control


async def check():
    if sys.platform != "darwin":
        raise RuntimeError("This smoke test requires macOS.")
    status = native({"action": "status"})
    if not status.get("accessibility_allowed") or status.get("screen_locked"):
        raise RuntimeError(
            "Unlock your Mac and enable Accessibility for the launcher before this test."
        )
    source = Path(__file__).with_name("mac_test_app.swift")
    with tempfile.TemporaryDirectory(prefix="ariana-controls-test-") as folder:
        binary = Path(folder) / "ariana-controls-test"
        subprocess.run(
            ["xcrun", "swiftc", str(source), "-o", str(binary)], check=True, timeout=90
        )
        app = subprocess.Popen([str(binary)])
        try:
            for _ in range(40):
                if any(
                    a["name"] == binary.name and a["frontmost"]
                    for a in native({"action": "apps"}).get("apps", [])
                ):
                    break
                await asyncio.sleep(0.1)
            else:
                raise RuntimeError(
                    "Test app did not become foreground; no UI actions attempted."
                )
            ctx = SimpleNamespace(session=SimpleNamespace(userdata={}))
            control = mac_control._func

            async def inspect(query=""):
                view = await control(ctx, "inspect", query=query)
                assert view.get("window") == "Ariana Controls QA", (
                    "Test window is not foreground."
                )
                return view

            view = await inspect("Ariana Test Search")
            assert (
                await control(
                    ctx,
                    "type",
                    snapshot_id=view["snapshot_id"],
                    text="Ariana café 😀",
                    replace=True,
                )
            )["success"]
            view = await inspect("Ariana Test Search")
            assert any(e["value"] == "Ariana café 😀" for e in view["elements"])
            assert (
                await control(
                    ctx,
                    "shortcut",
                    snapshot_id=view["snapshot_id"],
                    key="a",
                    modifiers=["cmd"],
                )
            )["success"]
            await asyncio.sleep(0.15)
            view = await inspect()
            assert any(e.get("selected_range") == [0, 14] for e in view["elements"]), [
                (e["role"], e.get("selected_range")) for e in view["elements"]
            ]
            text = "Ariana café 😀 " * 4
            assert (
                await control(ctx, "type", snapshot_id=view["snapshot_id"], text=text)
            )["success"]
            view = await inspect("Ariana Test Search")
            assert any(e["value"] == text for e in view["elements"]), [
                (e["role"], e["value"]) for e in view["elements"]
            ]
            for label, expected in [
                ("Ariana Test Button", "Button clicked"),
                ("Ariana Frame Button", "Frame clicked"),
            ]:
                view = await inspect(label)
                element = next(e for e in view["elements"] if e["role"] == "AXButton")
                assert (
                    await control(
                        ctx,
                        "click",
                        snapshot_id=view["snapshot_id"],
                        element_id=element["id"],
                    )
                )["success"]
                await asyncio.sleep(0.1)
                view = await inspect(expected)
                assert any(e["value"] == expected for e in view["elements"])
            for action, expected in [
                ("context_click", "Context clicked"),
                ("double_click", "Double clicked"),
            ]:
                view = await inspect("Ariana Frame Button")
                element = next(e for e in view["elements"] if e["role"] == "AXButton")
                result = await control(
                    ctx,
                    action,
                    snapshot_id=view["snapshot_id"],
                    element_id=element["id"],
                )
                assert result["success"], result
                assert any(
                    e["value"] == expected for e in result["observation"]["elements"]
                ), result
            view = await inspect("Ariana Covered Frame")
            element = next(e for e in view["elements"] if e["role"] == "AXButton")
            result = await control(
                ctx, "click", snapshot_id=view["snapshot_id"], element_id=element["id"]
            )
            assert result.get("code") == "occluded", result
            view = await inspect("Double clicked")
            assert any(e["value"] == "Double clicked" for e in view["elements"])
            view = await inspect()
            assert (
                await control(
                    ctx, "scroll", snapshot_id=view["snapshot_id"], direction="right"
                )
            )["success"]
            view = await control(ctx, "windows")
            target = next(
                w for w in view["windows"] if w["title"] == "Ariana Second QA Window"
            )
            assert (
                await control(
                    ctx,
                    "focus_window",
                    snapshot_id=view["snapshot_id"],
                    window_id=target["id"],
                )
            )["success"]
            view = await control(ctx, "inspect")
            assert view["window"] == "Ariana Second QA Window"
            print(
                "PASS: Unicode replacement, focused typing, layout-aware shortcut, native press, verified frame click, interactive-child rejection, context click, double click, directional scroll dispatch, window switching."
            )
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait()


if __name__ == "__main__":
    asyncio.run(check())
