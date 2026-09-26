"""Asked for a favourite she named titles that do not exist. The turn now
carries what she actually keeps coming back to."""
import json

import pytest

from utils.core import kaia_tastes


@pytest.mark.parametrize("words,asks", [
    ("what's your favorite album?", True),
    ("got another song recommendation?", True),
    ("what should i read next", True),
    ("how are you doing", False),
    ("do you like cats", False),
])
def test_only_a_question_about_her_taste_carries_it(words, asks):
    assert kaia_tastes.asks_for_taste(words) is asks


def test_the_block_names_what_she_has(tmp_path, monkeypatch):
    kb = tmp_path / "knowledge_base"
    (kb / "books").mkdir(parents=True)
    (kb / "books" / "Book - Neuromancer by William Gibson.md").write_text("x")
    cons = kb / "kaia_dreams" / "consolidated" / "books"
    cons.mkdir(parents=True)
    (cons / "Neuromancer.md").write_text("# Neuromancer\n\n*43 reflections about a book, 2026.*\n")
    log = tmp_path / "growth.jsonl"
    log.write_text(json.dumps({"type": "creation", "kind": "music", "summary": "[i played a trance set]",
                               "detail": {"genre": "trance"}}) + "\n")
    monkeypatch.setattr(kaia_tastes, "KB", kb)
    monkeypatch.setattr(kaia_tastes, "telemetry_path", lambda p: str(log))
    monkeypatch.setattr(kaia_tastes, "_cache", (0.0, None))
    note = kaia_tastes.note_for("what's your favourite book?")
    assert "Neuromancer by William Gibson (43)" in note
    assert "trance (1 set)" in note
    assert "rather than naming a title" in note
    assert kaia_tastes.note_for("hello") == ""
