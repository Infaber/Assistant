"""Deterministic desktop backend; simulations never touch the real Mac."""


class DesktopFixture:
    def __init__(self, denied: bool = False):
        self.denied = denied
        self.events = []
        self.app = "Finder"
        self.query = ""
        self.searched = False

    def run(self, request: dict) -> dict:
        self.events.append(dict(request))
        if self.denied:
            return {
                "error": "Accessibility and Automation access to System Events are denied. Enable them in macOS Privacy & Security."
            }
        action = request["action"]
        if action == "open":
            self.app = request["app_name"]
            return {"success": True, "message": "App opened."}
        if action == "apps":
            return {"apps": [{"name": self.app, "pid": 77, "frontmost": True}]}
        if action == "inspect":
            return {
                "app": self.app,
                "pid": 77,
                "window": self.app,
                "elements": [
                    {
                        "id": "e0",
                        "role": "AXButton",
                        "subrole": "",
                        "name": "Search",
                        "label": "Search",
                        "value": "",
                        "secure": False,
                        "enabled": True,
                        "path": ["window", 0, 0],
                        "signature": "search-button",
                    },
                    {
                        "id": "e1",
                        "role": "AXTextField",
                        "subrole": "",
                        "name": "Search",
                        "label": "Search",
                        "value": self.query,
                        "secure": False,
                        "enabled": True,
                        "path": ["window", 0, 1],
                        "signature": "search-field",
                    },
                    {
                        "id": "e2",
                        "role": "AXStaticText",
                        "subrole": "",
                        "name": "Results",
                        "label": "Search results",
                        "value": "Daft Punk" if self.searched else "",
                        "secure": False,
                        "enabled": True,
                        "path": ["window", 0, 2],
                        "signature": "results",
                    },
                ],
                "truncated": False,
            }
        if request["pid"] != 77 or request["window"] != self.app:
            return {"error": "The foreground app changed. Inspect again."}
        if action == "type":
            if request["target"]["id"] != "e1":
                return {"error": "Not a text field"}
            self.query += request["text"]
        elif action == "shortcut" and request["key"] in {"return", "enter"}:
            self.searched = True
        return {"success": True, "message": "Action sent; inspect to verify."}
