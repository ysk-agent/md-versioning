"""Blob and log storage under the hidden .versioning directory."""

from __future__ import annotations

import json
from pathlib import Path

import blake3


def body_hash(body: str) -> str:
    return blake3.blake3(body.encode("utf-8")).hexdigest()


class Store:
    def __init__(self, root: Path):
        self.base = root / ".versioning"
        self.blobs = self.base / "blobs"
        self.logs = self.base / "log"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)

    def write_blob(self, body: str) -> str:
        digest = body_hash(body)
        path = self.blobs / digest
        if not path.exists():
            path.write_bytes(body.encode("utf-8"))
        return digest

    def log_path(self, file_id: str) -> Path:
        return self.logs / f"{file_id}.jsonl"

    def append_log(self, file_id: str, entry: dict) -> None:
        with self.log_path(file_id).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_log(self, file_id: str) -> list[dict]:
        path = self.log_path(file_id)
        if not path.exists():
            return []
        entries = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                entries.append(json.loads(line))
        return entries
