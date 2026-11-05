import pytest

from md_versioning import Engine


@pytest.fixture()
def root(tmp_path):
    return tmp_path / "ws"


def _seed(root):
    eng = Engine(root)
    eng.save("d", "a.md", "A", tags=["legal"])
    eng.save("d", "b.md", "B", tags=["legal", "tax"])
    eng.save("e", "c.md", "C", tags=["tax"])
    return eng


def test_rebuild_after_index_deleted(root):
    eng = _seed(root)
    expected = eng.find(["legal"])
    eng.index.close()
    (root / ".versioning" / "index.db").unlink()
    eng2 = Engine(root)
    assert eng2.find(["legal"]) == expected
    assert eng2.find(["tax"]) == [("d", "b.md"), ("e", "c.md")]


def test_rebuild_is_idempotent(root):
    eng = _seed(root)
    before = {t: eng.find([t]) for t in ("legal", "tax")}
    eng.rebuild_index()
    eng.rebuild_index()
    after = {t: eng.find([t]) for t in ("legal", "tax")}
    assert before == after


def test_index_consistent_after_tag_changes(root):
    eng = _seed(root)
    eng.tag("e", "c.md", "legal")
    assert ("e", "c.md") in eng.find(["legal"])
    eng.untag("e", "c.md", "legal")
    assert ("e", "c.md") not in eng.find(["legal"])
