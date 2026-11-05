"""SQLite index over files, tags, and aliases. Rebuildable from disk."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
  file_id  TEXT PRIMARY KEY,
  dir      TEXT NOT NULL,
  filename TEXT NOT NULL,
  UNIQUE (dir, filename)
);
CREATE TABLE IF NOT EXISTS tags (
  file_id TEXT NOT NULL,
  word    TEXT NOT NULL,
  PRIMARY KEY (file_id, word)
);
CREATE TABLE IF NOT EXISTS aliases (
  file_id TEXT NOT NULL,
  alias   TEXT NOT NULL,
  PRIMARY KEY (file_id, alias)
);
"""


class Index:
    def __init__(self, base: Path):
        self.path = base / "index.db"
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def is_empty(self) -> bool:
        row = self.db.execute("SELECT COUNT(*) FROM files").fetchone()
        return row[0] == 0

    def upsert(self, file_id: str, directory: str, filename: str,
               tags: list[str], aliases: list[str]) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO files(file_id, dir, filename) VALUES (?, ?, ?) "
                "ON CONFLICT(file_id) DO UPDATE SET dir=excluded.dir, "
                "filename=excluded.filename",
                (file_id, directory, filename),
            )
            self.db.execute("DELETE FROM tags WHERE file_id = ?", (file_id,))
            self.db.executemany(
                "INSERT OR IGNORE INTO tags(file_id, word) VALUES (?, ?)",
                [(file_id, t) for t in tags],
            )
            self.db.execute("DELETE FROM aliases WHERE file_id = ?", (file_id,))
            self.db.executemany(
                "INSERT OR IGNORE INTO aliases(file_id, alias) VALUES (?, ?)",
                [(file_id, a) for a in aliases],
            )

    def rebuild(self, documents: list) -> None:
        """Replace the whole index from parsed documents. Idempotent."""
        with self.db:
            self.db.execute("DELETE FROM files")
            self.db.execute("DELETE FROM tags")
            self.db.execute("DELETE FROM aliases")
            for doc in documents:
                self.db.execute(
                    "INSERT OR REPLACE INTO files(file_id, dir, filename) "
                    "VALUES (?, ?, ?)",
                    (doc.file_id, doc.directory, doc.filename),
                )
                self.db.executemany(
                    "INSERT OR IGNORE INTO tags(file_id, word) VALUES (?, ?)",
                    [(doc.file_id, t) for t in doc.tags],
                )
                self.db.executemany(
                    "INSERT OR IGNORE INTO aliases(file_id, alias) VALUES (?, ?)",
                    [(doc.file_id, a) for a in doc.aliases],
                )

    def find(self, words: list[str]) -> list[tuple[str, str]]:
        placeholders = ",".join("?" for _ in words)
        rows = self.db.execute(
            f"SELECT f.dir, f.filename FROM files f "
            f"JOIN tags t ON t.file_id = f.file_id "
            f"WHERE t.word IN ({placeholders}) "
            f"GROUP BY f.file_id HAVING COUNT(DISTINCT t.word) = ? "
            f"ORDER BY f.dir, f.filename",
            (*words, len(words)),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def by_alias(self, alias: str):
        row = self.db.execute(
            "SELECT f.dir, f.filename FROM aliases a "
            "JOIN files f ON f.file_id = a.file_id WHERE a.alias = ?",
            (alias,),
        ).fetchone()
        return (row[0], row[1]) if row else None

    def known_file_ids(self) -> set[str]:
        rows = self.db.execute("SELECT file_id FROM files").fetchall()
        return {r[0] for r in rows}
