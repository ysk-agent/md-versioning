"""Agent surface: only directory, filename, and tag.

Everything the engine keeps privately stays out of these calls, out of
their results, and out of the prompt text below.
"""

from __future__ import annotations

import json

from .engine import Engine
from .errors import ConflictError, VersioningError

AGENT_PROMPT = """\
You work with documents. A document lives in a directory and has a
filename. A tag is a plain word that says what a document is about.

You may use only these actions:
- open a document by its directory and filename
- save a document by its directory and filename, with its full text
  and, when needed, its tags
- add a tag to a document, or remove a tag from a document
- find documents by one or more tags
- give a document a new filename
- read the past record of a document

When you save, always give the full text of the document as you want
it to be. If you are told a document changed since you opened it, you
will be shown its current text; describe the document as you want it
to be, in full, against that current text.
"""


def _doc_dict(doc) -> dict:
    return {
        "directory": doc.directory,
        "filename": doc.filename,
        "tags": list(doc.tags),
        "body": doc.body,
    }


class AgentSurface:
    """One surface instance is one agent session.

    The surface privately remembers the state each document was in when
    this session last saw it, so a save based on an older state can be
    reported as a change without the agent ever handling that detail.
    """

    def __init__(self, root):
        self.engine = Engine(root)
        self._seen: dict[tuple[str, str], int] = {}

    def _remember(self, doc, *keys) -> None:
        for key in keys:
            self._seen[key] = doc.version

    def open(self, directory, filename):
        doc = self.engine.read(directory, filename)
        if doc is None:
            return None
        self._remember(doc, (directory, filename),
                       (doc.directory, doc.filename))
        return _doc_dict(doc)

    def save(self, directory, filename, body, tags=None, intent=None):
        base = self._seen.get((directory, filename))
        try:
            doc = self.engine.save(directory, filename, body, tags=tags,
                                   intent=intent, base_version=base)
        except ConflictError as exc:
            self._remember(exc.current, (directory, filename))
            raise
        self._remember(doc, (directory, filename))
        return _doc_dict(doc)

    def tag(self, directory, filename, word):
        doc = self.engine.tag(directory, filename, word)
        self._remember(doc, (directory, filename))
        return _doc_dict(doc)

    def untag(self, directory, filename, word):
        doc = self.engine.untag(directory, filename, word)
        self._remember(doc, (directory, filename))
        return _doc_dict(doc)

    def find(self, tags):
        return [
            {"directory": d, "filename": f}
            for d, f in self.engine.find(tags)
        ]

    def rename(self, directory, filename, new_name):
        doc = self.engine.rename(directory, filename, new_name)
        self._remember(doc, (doc.directory, doc.filename))
        return {
            "directory": doc.directory,
            "filename": doc.filename,
            "tags": list(doc.tags),
        }

    def history(self, directory, filename):
        text = self.engine.history(directory, filename)
        return text.splitlines() if text else []

    # -- JSON-lines protocol -------------------------------------------

    def handle_line(self, line: str) -> str:
        try:
            request = json.loads(line)
            op = request["op"]
            args = request.get("args") or {}
            handler = {
                "open": self.open,
                "save": self.save,
                "tag": self.tag,
                "untag": self.untag,
                "find": self.find,
                "rename": self.rename,
                "history": self.history,
            }[op]
            result = handler(**args)
            return json.dumps({"ok": True, "result": result},
                              ensure_ascii=False)
        except ConflictError as exc:
            return json.dumps(
                {
                    "ok": False,
                    "error": "file changed",
                    "current": _doc_dict(exc.current),
                },
                ensure_ascii=False,
            )
        except (VersioningError, KeyError, TypeError, ValueError) as exc:
            return json.dumps({"ok": False, "error": str(exc)},
                              ensure_ascii=False)
