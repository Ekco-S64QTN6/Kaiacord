"""When she says she is keeping a note, she keeps one.

Six replies on 25 Sept ended "i'm adding this to my notes as `x.txt`" with
nothing behind them. The claim now writes knowledge_base/kaia_notes/x.md.
"""
from datetime import datetime
from pathlib import Path

import pytest

from utils.core import kaia_notes


@pytest.fixture
def notes(tmp_path, monkeypatch):
    monkeypatch.setattr(kaia_notes, "notes_dir", lambda: tmp_path / "kaia_notes")
    monkeypatch.setattr(kaia_notes, "_last", {})
    return tmp_path / "kaia_notes"


@pytest.mark.parametrize("reply,name", [
    ('i\'m adding this to my notes as "ppg_worm_analysis_2026.txt". it\'s a reminder.', "ppg_worm_analysis_2026"),
    ('i\'m saving this thread as "bach_llm_thinking_2026.txt" for later reference.', "bach_llm_thinking_2026"),
    ("the file is saved under “creative_ai_impact_2026.txt” if you’re interested.", "creative_ai_impact_2026"),
    ("i’m adding your perspective to my notes on the topic.", None),
])
def test_her_phrasings_are_recognised(reply, name):
    assert kaia_notes.find_claim(reply)[1] == name


@pytest.mark.parametrize("reply", [
    "the config lives in settings.txt on most systems.",
    "i noted that earlier.",
    "notes are useful. so is a readme.md.",
])
def test_ordinary_mentions_are_not_notes(reply):
    assert kaia_notes.find_claim(reply) is None


def test_the_note_is_written_and_the_reply_names_it(notes):
    reply = ("the worm spreads through steam workshop.\n\n"
             'i\'m adding this to my notes as "ppg_worm_analysis_2026.txt". a stark reminder.')
    out = kaia_notes.keep(reply, "Ekco", "Kaia, https://example.com/worm",
                          "Kaia, https://example.com/worm\n[shared link: Worm Breakdown]",
                          datetime(2026, 9, 25, 4, 21))
    assert '"ppg_worm_analysis_2026.md"' in out and ".txt" not in out
    text = (notes / "ppg_worm_analysis_2026.md").read_text()
    assert text.startswith("---\ntitle:")
    assert "<https://example.com/worm>" in text and "Worm Breakdown" in text
    assert "the worm spreads through steam workshop." in text
    assert "adding this to my notes" not in text


def test_a_second_note_under_the_same_name_is_appended(notes):
    kaia_notes.keep("first. adding this to my notes as topic.md.", "Ekco", "a", "", datetime(2026, 9, 25, 1))
    kaia_notes.keep("second. adding this to my notes as topic.md.", "Starkind", "b", "", datetime(2026, 9, 26, 2))
    text = (notes / "topic.md").read_text()
    assert text.count("---\ntitle:") == 1
    assert "with Ekco" in text and "with Starkind" in text and text.index("first.") < text.index("second.")


def test_a_reply_without_a_claim_is_untouched(notes):
    assert kaia_notes.keep("just a reply.", "Ekco", "hi") == "just a reply."
    assert not notes.exists()


def test_a_named_file_cannot_escape_the_folder(notes):
    kaia_notes.keep("adding this to my notes as ..%2f..%2fetc.txt.", "Ekco", "x", "", datetime(2026, 9, 25))
    assert all(p.parent == notes for p in notes.rglob("*"))


def test_notes_are_labelled_as_hers_and_kept_out_of_ingress():
    src = Path("utils/core/context_optimizer.py").read_text()
    assert "YOUR OWN NOTE" in src
    import importlib.util
    spec = importlib.util.spec_from_file_location("_pi", "tools/maintenance/process_ingress.py")
    pi = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pi)
    assert "kaia_notes" not in pi.ALLOWED_FOLDERS


def test_notes_on_the_topic_go_into_the_note_she_just_took(notes):
    kaia_notes.keep('good thread. i\'m saving this thread as "bach_thinking.txt" for later.', "Ekco", "link",
                    "", datetime(2026, 9, 25, 1, 39))
    kaia_notes.keep("i agree. i’m adding your perspective to my notes on the topic.", "Ekco",
                    "be kind to llms", "", datetime(2026, 9, 25, 1, 44))
    assert [p.name for p in notes.iterdir()] == ["bach_thinking.md"]
    assert "be kind to llms" in (notes / "bach_thinking.md").read_text()
