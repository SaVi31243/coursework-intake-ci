import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Registration:
    number: int
    group: str
    created: bool


class Register:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.open() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    id INTEGER PRIMARY KEY,
                    group_code TEXT NOT NULL,
                    submission_key TEXT NOT NULL UNIQUE
                )
            """)

    @contextmanager
    def open(self):
        db = sqlite3.connect(self.path, timeout=4)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def register(self, group, key):
        with self.open() as db:
            new = db.execute(
                """INSERT INTO submissions (group_code, submission_key)
                   VALUES (?, ?) ON CONFLICT(submission_key) DO NOTHING
                   RETURNING id, group_code""",
                (group, key),
            ).fetchone()
            if new is None:
                row = db.execute(
                    "SELECT id, group_code FROM submissions WHERE submission_key = ?", (key,)
                ).fetchone()
            else:
                row = new
        return Registration(row["id"], row["group_code"], new is not None)

    def lookup(self, number):
        with self.open() as db:
            row = db.execute(
                "SELECT * FROM submissions WHERE id = ?", (number,)
            ).fetchone()
        return dict(row) if row is not None else None
