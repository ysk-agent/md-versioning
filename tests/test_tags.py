import pytest

from md_versioning import Engine, InvalidTagError


@pytest.fixture()
def engine(tmp_path):
    eng = Engine(tmp_path / "ws")
    eng.save("d", "a.md", "A", tags=["legal"])
    eng.save("d", "b.md", "B", tags=["legal", "q3-review"])
    eng.save("e", "c.md", "C", tags=["q3-review"])
    return eng


def test_find_single_tag(engine):
    assert engine.find(["legal"]) == [("d", "a.md"), ("d", "b.md")]


def test_find_and_semantics(engine):
    assert engine.find(["legal", "q3-review"]) == [("d", "b.md")]


def test_find_unknown_tag(engine):
    assert engine.find(["missing"]) == []


def test_find_scan_agrees_with_index(engine):
    assert engine.find_by_scan(["q3-review"]) == engine.find(["q3-review"])


def test_find_empty_tags_rejected(engine):
    with pytest.raises(InvalidTagError):
        engine.find([])


def test_tag_and_untag(engine):
    doc = engine.tag("d", "a.md", "signed")
    assert "signed" in doc.tags
    entries = engine.store.read_log(doc.file_id)
    assert entries[-1]["intent"] == "tag signed"
    doc = engine.untag("d", "a.md", "signed")
    assert "signed" not in doc.tags
    entries = engine.store.read_log(doc.file_id)
    assert entries[-1]["intent"] == "untag signed"


def test_tag_only_change_writes_log_entry(engine):
    before = engine.read("d", "a.md")
    count = len(engine.store.read_log(before.file_id))
    engine.tag("d", "a.md", "extra")
    after = engine.read("d", "a.md")
    assert len(engine.store.read_log(after.file_id)) == count + 1
    assert after.version == before.version + 1
    assert after.body == before.body


def test_duplicate_tag_is_noop(engine):
    before = engine.read("d", "a.md")
    doc = engine.tag("d", "a.md", "legal")
    assert doc.version == before.version


def test_untag_absent_is_noop(engine):
    before = engine.read("d", "a.md")
    doc = engine.untag("d", "a.md", "absent")
    assert doc.version == before.version


@pytest.mark.parametrize("bad", ["#legal", "two words", "a,b", "", "x]"])
def test_invalid_tags_rejected(engine, bad):
    with pytest.raises(InvalidTagError):
        engine.tag("d", "a.md", bad)
