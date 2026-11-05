import pytest

from md_versioning import ConflictError, Engine


@pytest.fixture()
def engine(tmp_path):
    eng = Engine(tmp_path / "ws")
    eng.save("d", "a.md", "v1 text")
    return eng


def test_stale_save_is_reported(engine):
    with pytest.raises(ConflictError) as info:
        engine.save("d", "a.md", "stale edit", base_version=99)
    assert info.value.current.body == "v1 text"


def test_reemission_succeeds_and_records_both_parents(engine):
    first = engine.save("d", "a.md", "v2 text")  # now at version 2
    with pytest.raises(ConflictError):
        engine.save("d", "a.md", "based on v1", base_version=1)
    doc = engine.save("d", "a.md", "re-emitted in full",
                      base_version=first.version)
    entries = engine.store.read_log(doc.file_id)
    parents = entries[-1]["parents"]
    assert f"{doc.file_id}@1" in parents
    assert f"{doc.file_id}@2" in parents


def test_history_hides_parents(engine):
    engine.save("d", "a.md", "v2 text")
    with pytest.raises(ConflictError):
        engine.save("d", "a.md", "based on v1", base_version=1)
    current = engine.read("d", "a.md")
    engine.save("d", "a.md", "final", base_version=current.version)
    text = engine.history("d", "a.md")
    assert "@" not in text
    assert "parents" not in text


def test_sequential_save_with_correct_base_is_ordinary(engine):
    doc = engine.read("d", "a.md")
    out = engine.save("d", "a.md", "next", base_version=doc.version)
    entries = engine.store.read_log(out.file_id)
    assert entries[-1]["parents"] == [f"{out.file_id}@1"]
