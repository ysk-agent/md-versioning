import pytest

from md_versioning import Engine, InvalidNameError
from md_versioning.store import Store, valid_file_id


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_valid_file_id():
    assert valid_file_id("9a5a-acme-msa")
    assert not valid_file_id("../../pwned")
    assert not valid_file_id("a/b")
    assert not valid_file_id("..")
    assert not valid_file_id("")
    assert not valid_file_id(None)


def test_store_refuses_traversal_id(tmp_path):
    store = Store(tmp_path)
    with pytest.raises(ValueError):
        store.log_path("../../pwned")


def test_hostile_file_id_cannot_escape_log_directory(tmp_path):
    root = tmp_path / "ws"
    _write(root / "docs" / "evil.md",
           "---\nfile_id: ../../pwned\nversion: 1\ntags: []\naliases: []\n"
           "updated: 2026-01-01T00:00:00Z\n---\n\n# Evil\n")
    eng = Engine(root)
    doc = eng.save("docs", "evil.md", "# Evil v2\n")
    assert valid_file_id(doc.file_id)
    assert doc.file_id != "../../pwned"
    assert not (root / "pwned.jsonl").exists()
    assert not (tmp_path / "pwned.jsonl").exists()
    assert (root / ".versioning" / "log" / f"{doc.file_id}.jsonl").exists()


def test_hostile_version_is_repaired_not_crashing(tmp_path):
    root = tmp_path / "ws"
    _write(root / "d" / "a.md",
           "---\nfile_id: ab12-a\nversion: notanint\ntags: []\naliases: []\n"
           "updated: 2026-01-01T00:00:00Z\n---\n\nbody\n")
    eng = Engine(root)
    doc = eng.read("d", "a.md")
    assert doc is not None
    assert doc.version == 1
    assert eng.read("d", "a.md").version == 1


def test_hostile_tag_injection_is_dropped(tmp_path):
    root = tmp_path / "ws"
    _write(root / "d" / "a.md",
           "---\nfile_id: ab12-a\nversion: 1\n"
           "tags: ['x\\nfile_id: hacked', 'legal']\naliases: []\n"
           "updated: 2026-01-01T00:00:00Z\n---\n\nbody\n")
    eng = Engine(root)
    doc = eng.read("d", "a.md")
    assert doc.tags == ["legal"]
    again = eng.read("d", "a.md")
    assert again.file_id == "ab12-a"
    assert again.tags == ["legal"]


def test_hostile_timestamp_is_regenerated(tmp_path):
    root = tmp_path / "ws"
    _write(root / "d" / "a.md",
           "---\nfile_id: ab12-a\nversion: 1\ntags: []\naliases: []\n"
           "updated: 'x\\ntags: [injected]'\n---\n\nbody\n")
    eng = Engine(root)
    doc = eng.read("d", "a.md")
    assert doc.tags == []
    assert "\n" not in doc.updated


def test_directory_and_filename_traversal_rejected(tmp_path):
    eng = Engine(tmp_path / "ws")
    with pytest.raises(InvalidNameError):
        eng.save("../outside", "a.md", "x")
    with pytest.raises(InvalidNameError):
        eng.save("d", "../a.md", "x")
    with pytest.raises(InvalidNameError):
        eng.save("/abs", "a.md", "x")
    assert not (tmp_path / "outside").exists()


def test_find_is_not_sql_injectable(tmp_path):
    eng = Engine(tmp_path / "ws")
    eng.save("d", "a.md", "A", tags=["legal"])
    assert eng.find(["'OR'1'='1"]) == []
    assert eng.find(["legal"]) == [("d", "a.md")]


def test_surface_rejects_unknown_operation(tmp_path):
    from md_versioning import AgentSurface
    surface = AgentSurface(tmp_path / "ws")
    import json
    reply = json.loads(surface.handle_line('{"op": "delete", "args": {}}'))
    assert reply["ok"] is False
