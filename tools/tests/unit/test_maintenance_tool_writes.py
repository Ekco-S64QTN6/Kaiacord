"""Maintenance tools write safely: append lock, atomic documents, repeatable rollups, no refusal replacing a profile."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_append_lock_is_the_one_appends_use(tmp_path):
    from utils.core import atomic_write
    log = tmp_path / "interactions.md"
    atomic_write.append_atomic(log, "one\n")
    with atomic_write.append_lock(log):
        assert (tmp_path / ".interactions.md.append.lock").exists()
        assert log.read_text() == "one\n"


def test_the_ledger_rereads_before_it_writes(tmp_path):
    from utils.social.forum_participation import PostLedger
    a = PostLedger(path=tmp_path / "ledger.json")
    b = PostLedger(path=tmp_path / "ledger.json")
    a.load(); b.load()
    a.record(1, "first")
    b.record(2, "second")                  # b never saw a's entry in memory
    c = PostLedger(path=tmp_path / "ledger.json")
    c.load()
    assert sorted(p["thread_id"] for p in c.posts) == [1, 2]


def test_consolidated_documents_are_written_atomically():
    src = (ROOT / "tools/maintenance/consolidate_dreams.py").read_text(encoding="utf-8")
    assert "write_atomic(path" in src and ".write_text(" not in src


def test_a_day_already_in_the_archive_is_not_merged_twice(tmp_path):
    from tools.maintenance.rollup_user_logs import build_archive
    day = tmp_path / "interactions_20260101.md"
    day.write_text("---\ntitle: x\n---\n\n[2026-01-01 10:00:00] A: hello\n", encoding="utf-8")
    first, _ = build_archive("A_1", "202601", [day])
    second, turns = build_archive("A_1", "202601", [day], existing=first)
    assert second.count("hello") == 1 and turns == 1


def test_a_refusal_does_not_replace_a_profile():
    from tools.maintenance.generate_user_profiles import unusable_profile
    assert unusable_profile("I'm sorry, I can't help with that.")
    good = "\n".join(f"## Section {i}\n" + "they talk about boats and ale. " * 8 for i in range(5))
    assert unusable_profile(good) == ""


def test_the_kb_audit_check_ignores_the_metadata_backlog(monkeypatch):
    from collections import Counter
    from tools.maintenance import audit_knowledge_base as akb
    monkeypatch.setattr(akb, "audit", lambda: ({"_backfill_pending": ["x.md"]}, Counter(news=1)))
    monkeypatch.setattr(akb, "KB", Path(__file__).parent)           # exists
    monkeypatch.setattr("sys.argv", ["audit_knowledge_base.py", "--check"])
    assert akb.main() == 0
    monkeypatch.setattr(akb, "audit", lambda: ({"empty_file": ["y.md"]}, Counter(news=1)))
    assert akb.main() == 1


def test_a_consolidated_document_is_written_whole_and_leaves_no_temporary(tmp_path, monkeypatch):
    import yaml
    from tools.maintenance import consolidate_dreams as cd
    monkeypatch.setattr(cd, "OUT", tmp_path / "consolidated")
    path = cd.write_document("books/Dune", "Dune", [("2026-01-01", Path("a.md"), "r")], "word " * 60)
    head = path.read_text(encoding="utf-8").split("---", 2)[1]
    assert yaml.safe_load(head)["consolidated_from"] == 1
    assert [p.name for p in path.parent.iterdir()] == ["Dune.md"]

