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
        if request["action"] == "apps":
            return {"apps": [{"name": self.app, "pid": 77, "frontmost": True}]}
        if request["action"] in {"browser_search", "browser_open"}:
            self.app = request["app_name"]
            self.query = request.get("query", "")
            self.url = request["url"]
            return {
                "success": True,
                "browser": self.app,
                "url": self.url,
                "message": "Browser navigation dispatched; results not read.",
            }
        if self.denied:
            return {
                "error": "Accessibility access is denied. Enable it in macOS Privacy & Security."
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
                        "focused": True,
                        "editable": True,
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
            self.query = (
                request["text"]
                if request.get("replace")
                else self.query + request["text"]
            )
        elif action == "shortcut" and request["key"] in {"return", "enter"}:
            self.searched = True
        return {"success": True, "message": "Action sent; inspect to verify."}


class SpotifyFixture:
    def __init__(self):
        self.events = []
        self.state = "paused"
        self.query = ""

    def run(self, request):
        self.events.append(dict(request))
        action = request["action"]
        if action == "search":
            self.query = request["query"]
            return {
                "success": True,
                "query": self.query,
                "message": "Spotify search opened; no track selected and results not read.",
            }
        if action == "play":
            self.state = "playing"
        elif action == "pause":
            self.state = "paused"
        return {
            "success": True,
            "player_state": self.state,
            "track": "Fixture track",
            "artist": "Fixture artist",
        }
