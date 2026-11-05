import pytest

from md_versioning import Engine, NameCollisionError


@pytest.fixture()
def engine(tmp_path):
    eng = Engine(tmp_path / "ws")
    eng.save("contracts", "acme-msa.md", "# Acme\n", tags=["legal"])
    eng.save("contracts", "other.md", "# Other\n")
    return eng


def test_rename_moves_file_and_keeps_identity(engine, tmp_path):
    before = engine.read("contracts", "acme-msa.md")
    doc = engine.rename("contracts", "acme-msa.md", "acme-msa-2026.md")
    assert doc.file_id == before.file_id
    assert doc.filename == "acme-msa-2026.md"
    assert not (tmp_path / "ws" / "contracts" / "acme-msa.md").exists()
    assert (tmp_path / "ws" / "contracts" / "acme-msa-2026.md").exists()


def test_read_by_old_name_after_rename(engine):
    engine.rename("contracts", "acme-msa.md", "renamed.md")
    doc = engine.read("contracts", "acme-msa.md")
    assert doc is not None
    assert doc.filename == "renamed.md"


def test_aliases_accumulate(engine):
    engine.rename("contracts", "acme-msa.md", "second.md")
    doc = engine.rename("contracts", "second.md", "third.md")
    assert "acme-msa.md" in doc.aliases
    assert "second.md" in doc.aliases
    assert engine.read("contracts", "acme-msa.md").filename == "third.md"
    assert engine.read("contracts", "second.md").filename == "third.md"


def test_rename_writes_one_log_entry(engine):
    before = engine.read("contracts", "acme-msa.md")
    count = len(engine.store.read_log(before.file_id))
    doc = engine.rename("contracts", "acme-msa.md", "renamed.md")
    entries = engine.store.read_log(doc.file_id)
    assert len(entries) == count + 1
    assert entries[-1]["intent"] == "rename renamed.md"
    assert entries[-1]["rename"]["from"] == "acme-msa.md"


def test_history_follows_identity(engine):
    engine.rename("contracts", "acme-msa.md", "renamed.md")
    text = engine.history("contracts", "renamed.md")
    assert "rename renamed.md" in text


def test_rename_collision_fails(engine):
    with pytest.raises(NameCollisionError):
        engine.rename("contracts", "acme-msa.md", "other.md")


def test_find_after_rename_uses_new_name(engine):
    engine.rename("contracts", "acme-msa.md", "renamed.md")
    assert engine.find(["legal"]) == [("contracts", "renamed.md")]


def test_move_to_another_directory(engine):
    doc = engine.rename("contracts", "acme-msa.md", "acme-msa.md",
                        new_directory="legal")
    assert doc.directory == "legal"
    assert engine.read("contracts", "acme-msa.md").directory == "legal"
