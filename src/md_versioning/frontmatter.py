"""Parsing and serialising Markdown documents with YAML frontmatter.

Field order on disk is fixed: file_id, version, tags, aliases, updated.
The body is preserved byte for byte after the closing fence.
"""

from __future__ import annotations

import yaml

FIELDS = ("file_id", "version", "tags", "aliases", "updated")


def _flow_list(values) -> str:
    items = ", ".join(str(v) for v in values)
    return f"[{items}]"


def serialize(meta: dict, body: str) -> str:
    lines = [
        "---",
        f"file_id: {meta.get('file_id', '')}",
        f"version: {int(meta.get('version', 1))}",
        f"tags: {_flow_list(meta.get('tags') or [])}",
        f"aliases: {_flow_list(meta.get('aliases') or [])}",
        f"updated: {meta.get('updated', '')}",
        "---",
    ]
    return "\n".join(lines) + "\n\n" + body


def parse(text: str) -> tuple[dict, str]:
    """Split a document into (frontmatter dict, body).

    A document without a frontmatter block is returned with an empty
    dict and the whole text as its body; the engine repairs it.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[4:end]
    rest = text[end + 4 :]
    if rest.startswith("\n"):
        rest = rest[1:]
    if rest.startswith("\n"):
        rest = rest[1:]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(meta, dict):
        return {}, text
    return meta, rest
