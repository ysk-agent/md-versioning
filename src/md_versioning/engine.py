"""The versioning engine.

One save path for every mutation. Identity, counters, blobs, logs, and
the index are maintained here and nowhere else.
"""

from __future__ import annotations

import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import frontmatter
from .errors import (
    ConflictError,
    InvalidNameError,
    InvalidTagError,
    NameCollisionError,
    UnknownDocumentError,
)
from .index import Index
from .store import Store, body_hash

_TAG_FORBIDDEN = set("#,[]")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(filename: str) -> str:
    stem = filename[:-3] if filename.endswith(".md") else filename
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    return slug or "doc"


@dataclass
class Document:
    directory: str
    filename: str
    file_id: str
    version: int
    tags: list = field(default_factory=list)
    aliases: list = field(default_factory=list)
    updated: str = ""
    body: str = ""


class Engine:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.root)
        fresh_index = not (self.root / ".versioning" / "index.db").exists()
        self.index = Index(self.root / ".versioning")
        self._pending_conflicts: dict[str, list[str]] = {}
        if fresh_index or self.index.is_empty():
            docs = [d for d in self._scan() if d.file_id]
            if docs:
                self.index.rebuild(docs)

    # -- validation -----------------------------------------------------

    @staticmethod
    def _check_directory(directory: str) -> str:
        if directory in ("", "."):
            return ""
        path = Path(directory)
        if path.is_absolute() or ".." in path.parts:
            raise InvalidNameError(f"bad directory: {directory!r}")
        return str(path)

    @staticmethod
    def _check_filename(filename: str) -> str:
        if (
            not filename.endswith(".md")
            or "/" in filename
            or "\\" in filename
            or filename in (".md", "..")
        ):
            raise InvalidNameError(f"bad filename: {filename!r}")
        return filename

    @staticmethod
    def _check_tag(word: str) -> str:
        if (
            not word
            or any(c.isspace() for c in word)
            or any(c in _TAG_FORBIDDEN for c in word)
        ):
            raise InvalidTagError(f"bad tag: {word!r}")
        return word

    @classmethod
    def _check_tags(cls, tags) -> list[str]:
        out: list[str] = []
        for word in tags or []:
            cls._check_tag(word)
            if word not in out:
                out.append(word)
        return out

    # -- file helpers ---------------------------------------------------

    def _path(self, directory: str, filename: str) -> Path:
        return self.root / directory / filename if directory else self.root / filename

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _scan(self) -> list[Document]:
        docs = []
        for path in sorted(self.root.rglob("*.md")):
            if ".versioning" in path.relative_to(self.root).parts:
                continue
            meta, body = frontmatter.parse(path.read_text(encoding="utf-8"))
            rel = path.relative_to(self.root)
            docs.append(
                Document(
                    directory=str(rel.parent) if str(rel.parent) != "." else "",
                    filename=rel.name,
                    file_id=str(meta.get("file_id") or ""),
                    version=int(meta.get("version") or 1),
                    tags=list(meta.get("tags") or []),
                    aliases=list(meta.get("aliases") or []),
                    updated=str(meta.get("updated") or ""),
                    body=body,
                )
            )
        return docs

    def _new_file_id(self, filename: str) -> str:
        known = self.index.known_file_ids()
        known |= {p.stem for p in self.store.logs.glob("*.jsonl")}
        known |= {d.file_id for d in self._scan() if d.file_id}
        while True:
            candidate = f"{secrets.token_hex(2)}-{_slug(filename)}"
            if candidate not in known:
                return candidate

    def _load(self, directory: str, filename: str) -> Document | None:
        """Load a document at an exact path, repairing frontmatter."""
        path = self._path(directory, filename)
        if not path.exists():
            return None
        meta, body = frontmatter.parse(path.read_text(encoding="utf-8"))
        changed = False
        if not meta.get("file_id"):
            meta["file_id"] = self._new_file_id(filename)
            changed = True
        if not meta.get("version"):
            meta["version"] = 1
            changed = True
        for key in ("tags", "aliases"):
            if not isinstance(meta.get(key), list):
                meta[key] = []
                changed = True
        if not meta.get("updated"):
            meta["updated"] = _now()
            changed = True
        if changed:
            self._atomic_write(path, frontmatter.serialize(meta, body))
        return Document(
            directory=directory,
            filename=filename,
            file_id=str(meta["file_id"]),
            version=int(meta["version"]),
            tags=list(meta["tags"]),
            aliases=list(meta["aliases"]),
            updated=str(meta["updated"]),
            body=body,
        )

    # -- read -------------------------------------------------------------

    def read(self, directory: str, filename: str) -> Document | None:
        directory = self._check_directory(directory)
        filename = self._check_filename(filename)
        doc = self._load(directory, filename)
        if doc is not None:
            return doc
        found = self.index.by_alias(filename)
        if found is not None:
            return self._load(found[0], found[1])
        for candidate in self._scan():
            if filename in candidate.aliases:
                return self._load(candidate.directory, candidate.filename)
        return None

    # -- save -------------------------------------------------------------

    def save(self, directory, filename, body, tags=None, intent=None,
             base_version=None) -> Document:
        directory = self._check_directory(directory)
        filename = self._check_filename(filename)
        new_tags = None if tags is None else self._check_tags(tags)
        path = self._path(directory, filename)
        ts = _now()

        if not path.exists():
            file_id = self._new_file_id(filename)
            final_tags = new_tags or []
            digest = self.store.write_blob(body)
            meta = {
                "file_id": file_id,
                "version": 1,
                "tags": final_tags,
                "aliases": [],
                "updated": ts,
            }
            self.store.append_log(file_id, {
                "v": 1, "hash": digest, "parents": [], "tags": final_tags,
                "aliases": [], "intent": intent or "create", "ts": ts,
            })
            self._atomic_write(path, frontmatter.serialize(meta, body))
            self.index.upsert(file_id, directory, filename, final_tags, [])
            return Document(directory, filename, file_id, 1, final_tags,
                            [], ts, body)

        doc = self._load(directory, filename)
        final_tags = doc.tags if new_tags is None else new_tags

        # No-op guard: body, tags, and filename all unchanged.
        if body == doc.body and final_tags == doc.tags:
            return doc

        if base_version is not None and int(base_version) != doc.version:
            pending = self._pending_conflicts.setdefault(doc.file_id, [])
            marker = f"{doc.file_id}@{int(base_version)}"
            if marker not in pending:
                pending.append(marker)
            raise ConflictError(doc)

        parents = [f"{doc.file_id}@{doc.version}"]
        pending = self._pending_conflicts.pop(doc.file_id, [])
        for marker in pending:
            if marker not in parents:
                parents.append(marker)

        new_version = doc.version + 1
        digest = self.store.write_blob(body)
        meta = {
            "file_id": doc.file_id,
            "version": new_version,
            "tags": final_tags,
            "aliases": doc.aliases,
            "updated": ts,
        }
        self.store.append_log(doc.file_id, {
            "v": new_version, "hash": digest, "parents": parents,
            "tags": final_tags, "aliases": doc.aliases,
            "intent": intent or "save", "ts": ts,
        })
        self._atomic_write(path, frontmatter.serialize(meta, body))
        self.index.upsert(doc.file_id, directory, filename, final_tags,
                          doc.aliases)
        return Document(directory, filename, doc.file_id, new_version,
                        final_tags, doc.aliases, ts, body)

    # -- tag / untag --------------------------------------------------------

    def tag(self, directory, filename, word) -> Document:
        self._check_tag(word)
        doc = self.read(directory, filename)
        if doc is None:
            raise UnknownDocumentError(filename)
        if word in doc.tags:
            return doc
        return self.save(doc.directory, doc.filename, doc.body,
                         tags=[*doc.tags, word], intent=f"tag {word}",
                         base_version=doc.version)

    def untag(self, directory, filename, word) -> Document:
        self._check_tag(word)
        doc = self.read(directory, filename)
        if doc is None:
            raise UnknownDocumentError(filename)
        if word not in doc.tags:
            return doc
        return self.save(doc.directory, doc.filename, doc.body,
                         tags=[t for t in doc.tags if t != word],
                         intent=f"untag {word}", base_version=doc.version)

    # -- find ---------------------------------------------------------------

    def find_by_scan(self, tags) -> list[tuple[str, str]]:
        words = self._check_tags(tags)
        if not words:
            raise InvalidTagError("find needs at least one tag")
        return sorted(
            (d.directory, d.filename)
            for d in self._scan()
            if all(w in d.tags for w in words)
        )

    def find(self, tags) -> list[tuple[str, str]]:
        words = self._check_tags(tags)
        if not words:
            raise InvalidTagError("find needs at least one tag")
        return self.index.find(words)

    def rebuild_index(self) -> None:
        self.index.rebuild([d for d in self._scan() if d.file_id])

    # -- rename ---------------------------------------------------------------

    def rename(self, directory, filename, new_name, new_directory=None) -> Document:
        directory = self._check_directory(directory)
        filename = self._check_filename(filename)
        new_name = self._check_filename(new_name)
        target_dir = directory if new_directory is None else self._check_directory(new_directory)
        doc = self.read(directory, filename)
        if doc is None:
            raise UnknownDocumentError(filename)
        if new_name == doc.filename and target_dir == doc.directory:
            return doc
        target = self._path(target_dir, new_name)
        if target.exists():
            raise NameCollisionError(new_name)

        ts = _now()
        aliases = list(doc.aliases)
        if doc.filename not in aliases:
            aliases.append(doc.filename)
        new_version = doc.version + 1
        digest = self.store.write_blob(doc.body)
        meta = {
            "file_id": doc.file_id,
            "version": new_version,
            "tags": doc.tags,
            "aliases": aliases,
            "updated": ts,
        }
        self.store.append_log(doc.file_id, {
            "v": new_version, "hash": digest,
            "parents": [f"{doc.file_id}@{doc.version}"],
            "tags": doc.tags, "aliases": aliases,
            "intent": f"rename {new_name}", "ts": ts,
            "rename": {
                "from_dir": doc.directory, "from": doc.filename,
                "to_dir": target_dir, "to": new_name,
            },
        })
        self._atomic_write(target, frontmatter.serialize(meta, doc.body))
        old_path = self._path(doc.directory, doc.filename)
        if old_path != target and old_path.exists():
            old_path.unlink()
        self.index.upsert(doc.file_id, target_dir, new_name, doc.tags, aliases)
        return Document(target_dir, new_name, doc.file_id, new_version,
                        doc.tags, aliases, ts, doc.body)

    # -- history ---------------------------------------------------------------

    def history(self, directory, filename) -> str:
        doc = self.read(directory, filename)
        if doc is None:
            raise UnknownDocumentError(filename)
        lines = []
        for entry in self.store.read_log(doc.file_id):
            tags = ", ".join(entry.get("tags") or []) or "none"
            lines.append(
                f"{entry['v']}. {entry.get('intent') or 'save'} "
                f"({entry.get('ts', '')}) tags: {tags}"
            )
        return "\n".join(lines)
