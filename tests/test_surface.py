import json

import pytest

from md_versioning import AGENT_PROMPT, AgentSurface

BANNED = ["hash", "blake3", "parents", "dag", "blob", "file_id",
          "sqlite", ".versioning", "version"]


@pytest.fixture()
def surface(tmp_path):
    return AgentSurface(tmp_path / "ws")


def test_full_session_through_surface(surface):
    made = surface.save("contracts", "acme.md", "# Acme\n")
    assert made["filename"] == "acme.md"
    tagged = surface.tag("contracts", "acme.md", "legal")
    assert tagged["tags"] == ["legal"]
    surface.save("notes", "memo.md", "# Memo\n", tags=["legal"])
    found = surface.find(["legal"])
    assert {"directory": "contracts", "filename": "acme.md"} in found
    assert {"directory": "notes", "filename": "memo.md"} in found
    renamed = surface.rename("contracts", "acme.md", "acme-2026.md")
    assert renamed["filename"] == "acme-2026.md"
    opened = surface.open("contracts", "acme.md")  # old name still works
    assert opened["filename"] == "acme-2026.md"
    lines = surface.history("contracts", "acme-2026.md")
    assert any("rename" in line for line in lines)


def test_surface_outputs_hide_engine_terms(surface):
    outputs = []
    outputs.append(surface.save("d", "a.md", "text"))
    outputs.append(surface.tag("d", "a.md", "legal"))
    outputs.append(surface.open("d", "a.md"))
    outputs.append(surface.find(["legal"]))
    outputs.append(surface.rename("d", "a.md", "b.md"))
    blob = json.dumps(outputs).lower()
    for word in BANNED:
        assert word not in blob


def test_prompt_uses_only_plain_vocabulary():
    lowered = AGENT_PROMPT.lower()
    for word in BANNED:
        assert word not in lowered


def test_conflict_through_surface(surface, tmp_path):
    surface.save("d", "a.md", "first")
    surface.open("d", "a.md")
    # Another session changes the document underneath this one.
    from md_versioning import Engine
    other = Engine(tmp_path / "ws")
    other.save("d", "a.md", "changed elsewhere")
    with pytest.raises(Exception) as info:
        surface.save("d", "a.md", "my stale edit")
    assert "changed" in str(info.value) or hasattr(info.value, "current")
    # Re-emit against the current text: now it succeeds.
    current = surface.open("d", "a.md")
    assert current["body"] == "changed elsewhere"
    out = surface.save("d", "a.md", "my edit, in full")
    assert out["body"] == "my edit, in full"


def test_json_lines_round_trip(surface):
    def call(op, **args):
        reply = json.loads(surface.handle_line(
            json.dumps({"op": op, "args": args})))
        assert reply["ok"], reply
        return reply["result"]

    call("save", directory="d", filename="a.md", body="hello")
    call("tag", directory="d", filename="a.md", word="legal")
    assert call("find", tags=["legal"]) == [
        {"directory": "d", "filename": "a.md"}]
    assert call("open", directory="d", filename="a.md")["body"] == "hello"
    lines = call("history", directory="d", filename="a.md")
    assert len(lines) == 2


def test_json_lines_conflict_shape(tmp_path):
    from md_versioning import Engine
    surface = AgentSurface(tmp_path / "ws")
    surface.handle_line(json.dumps(
        {"op": "save", "args": {"directory": "d", "filename": "a.md",
                                "body": "first"}}))
    surface.handle_line(json.dumps(
        {"op": "open", "args": {"directory": "d", "filename": "a.md"}}))
    Engine(tmp_path / "ws").save("d", "a.md", "changed elsewhere")
    reply = json.loads(surface.handle_line(json.dumps(
        {"op": "save", "args": {"directory": "d", "filename": "a.md",
                                "body": "stale"}})))
    assert reply["ok"] is False
    assert reply["error"] == "file changed"
    assert reply["current"]["body"] == "changed elsewhere"
    lowered = json.dumps(reply).lower()
    for word in BANNED:
        assert word not in lowered
