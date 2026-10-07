"""Private stable target mappings, separate from conversational memories."""

import hashlib
import json
import os
import sqlite3

from preferences_tools import preferences_path


class AliasStore:
    def __init__(self, url, path=None):
        self.scope = hashlib.sha256(url.encode()).hexdigest()
        self.path = path or preferences_path().with_name("home-assistant.sqlite3")

    def run(self, action, alias="", target=None):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic private creation before SQLite opens the file.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        with sqlite3.connect(self.path, timeout=5) as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS aliases (scope TEXT, alias TEXT, target TEXT, PRIMARY KEY(scope,alias))"
            )
            if action == "remember":
                if not alias or len(alias) > 100 or any(ord(c) < 32 for c in alias):
                    raise ValueError("Alias must be short, nonempty text.")
                count = db.execute(
                    "SELECT count(*) FROM aliases WHERE scope=?", (self.scope,)
                ).fetchone()[0]
                exists = db.execute(
                    "SELECT 1 FROM aliases WHERE scope=? AND alias=?",
                    (self.scope, alias),
                ).fetchone()
                if count >= 100 and not exists:
                    raise ValueError(
                        "Home Assistant alias limit reached; forget an old alias first."
                    )
                db.execute(
                    "INSERT OR REPLACE INTO aliases VALUES (?,?,?)",
                    (self.scope, alias, json.dumps(target)),
                )
            elif action == "forget":
                db.execute(
                    "DELETE FROM aliases WHERE scope=? AND alias=?", (self.scope, alias)
                )
            return {
                a: json.loads(t)
                for a, t in db.execute(
                    "SELECT alias,target FROM aliases WHERE scope=? LIMIT 100",
                    (self.scope,),
                )
            }
