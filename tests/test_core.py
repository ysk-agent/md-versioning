import json

import pytest

from md_versioning import Engine


@pytest.fixture()
def engine(tmp_path):
    return Engine(tmp_path / "ws")


def test_create_and_read(engine):
    doc = engine.save("contracts", "acme.md", "# Acme\n\nBody.\n")
    assert doc.version == 1
    assert doc.file_id.endswith("-acme")
    again = engine.read("contracts", "acme.md")
    assert again.body == "# Acme\n\nBody.\n"
    assert again.file_id == doc.file_id


def test_read_unknown_returns_none(engine):
    assert engine.read("contracts", "nope.md") is None


def test_save_five_times_dedup(engine):
    engine.save("d", "a.md", "one")
    engine.save("d", "a.md", "one")          # identical: no-op
    engine.save("d", "a.md", "two")
    engine.save("d", "a.md", "two")          # identical: no-op
    doc = engine.save("d", "a.md", "three")
    assert doc.version == 3
    entries = engine.store.read_log(doc.file_id)
    assert [e["v"] for e in entries] == [1, 2, 3]


def test_noop_leaves_file_untouched(engine, tmp_path):
    engine.save("d", "a.md", "same")
    path = tmp_path / "ws" / "d" / "a.md"
    before = path.read_bytes()
    engine.save("d", "a.md", "same")
    assert path.read_bytes() == before


def test_history_is_plain(engine):
    doc = engine.save("d", "a.md", "one", intent="create")
    engine.save("d", "a.md", "two", intent="revise")
    text = engine.history("d", "a.md")
    assert "create" in text and "revise" in text
    entries = engine.store.read_log(doc.file_id)
    for entry in entries:
        assert entry["hash"] not in text
    assert doc.file_id not in text
    assert "parents" not in text


def test_frontmatter_repair(engine, tmp_path):
    path = tmp_path / "ws" / "notes"
    path.mkdir(parents=True)
    (path / "raw.md").write_text("# Raw\n\nNo frontmatter.\n", encoding="utf-8")
    doc = engine.read("notes", "raw.md")
    assert doc is not None and doc.file_id
    assert doc.body == "# Raw\n\nNo frontmatter.\n"
    repaired = engine.read("notes", "raw.md")
    assert repaired.file_id == doc.file_id


def test_body_preserved_and_field_order(engine, tmp_path):
    body = "# Title\n\n- a\n- b\n\n```\ncode ---\n```\n"
    engine.save("d", "a.md", body)
    raw = (tmp_path / "ws" / "d" / "a.md").read_text(encoding="utf-8")
    order = [raw.index(k) for k in ("file_id", "version", "tags", "aliases", "updated")]
    assert order == sorted(order)
    assert engine.read("d", "a.md").body == body


def test_atomic_write_failure_keeps_old_file(engine, tmp_path, monkeypatch):
    engine.save("d", "a.md", "old")
    path = tmp_path / "ws" / "d" / "a.md"
    before = path.read_bytes()

    def boom(src, dst):
        raise OSError("simulated interruption")

    monkeypatch.setattr("md_versioning.engine.os.replace", boom)
    with pytest.raises(OSError):
        engine.save("d", "a.md", "new")
    assert path.read_bytes() == before


def test_log_format(engine):
    doc = engine.save("d", "a.md", "one")
    lines = engine.store.log_path(doc.file_id).read_text().splitlines()
    entry = json.loads(lines[0])
    assert entry["v"] == 1
    assert entry["parents"] == []
    assert entry["tags"] == []
    assert "hash" in entry and "ts" in entry
