"""Misheard-name correction for YouTube transcripts."""
import asyncio
import json
import types

import pytest

import tools.maintenance.transcript_names as tn

DOC = """---
title: 'DUNE: Entire Timeline Explained'
summary: in the shadows of oracus lies the end of house ATT treaties
keywords:
- DUNE
---
# DUNE: Entire Timeline Explained

**Source:** [https://www.youtube.com/watch?v=x](https://www.youtube.com/watch?v=x)

## [0:00]

in the shadows of oracus lie many secrets and the end of house ATT treaties hey guys neat here

## [5:00]

the simx attacked oracus again and the atres fled
"""

EXCERPT = " ".join(tn.prose_chunks(DOC))


@pytest.mark.parametrize("heard, correct", [
    ("oracus", "Arrakis"),               # not a word, sounds alike
    ("ATT treaties", "Atreides"),         # a phrase, sounds alike
    ("atres", "Atreides"),
])
def test_real_mishearings_are_accepted(heard, correct):
    assert tn.valid_pair(heard, correct, EXCERPT)


@pytest.mark.parametrize("heard, correct, why", [
    ("neat", "Ned", "a real word, used as itself elsewhere"),
    ("simx", "thinking machines", "does not sound alike, and is not a name"),
    ("oracus", "coalesced", "not a name"),
    ("sorceresses", "Bene Gesserit", "does not sound alike"),
    ("oracus", "Oracus", "only a recasing"),
    ("dune planet", "Arrakis", "not in the excerpt"),
    ("oracus", "Arrakis; rm -rf", "not a safe replacement"),
])
def test_bad_pairs_are_rejected(heard, correct, why):
    assert not tn.valid_pair(heard, correct, EXCERPT), why


def test_corrections_touch_prose_and_summary_but_not_anchors_or_links():
    fixed, counts = tn.apply_corrections(DOC, {"oracus": "Arrakis", "att treaties": "Atreides"})
    assert counts == {"oracus": 3, "att treaties": 2}
    assert "summary: in the shadows of Arrakis lies the end of house Atreides" in fixed
    assert "## [0:00]" in fixed and "## [5:00]" in fixed
    assert "https://www.youtube.com/watch?v=x" in fixed
    assert "neat here" in fixed


def test_the_model_only_supplies_a_glossary():
    """Whatever the model says, only validated pairs are applied."""
    reply = json.dumps({"corrections": [
        {"heard": "oracus", "correct": "Arrakis"},
        {"heard": "simx", "correct": "thinking machines"},
        {"heard": "neat", "correct": "Ned"},
    ]})

    async def chat(_prompt):
        return reply

    glossary = asyncio.run(tn.find_corrections(DOC, "Dune", "FilmComicsExplained", chat))
    assert glossary == {"oracus": "Arrakis"}


def test_a_disagreeing_model_changes_nothing():
    replies = iter([
        json.dumps({"corrections": [{"heard": "oracus", "correct": "Arrakis"}]}),
        json.dumps({"corrections": [{"heard": "oracus", "correct": "Arakis"}]}),
    ])

    async def chat(_prompt):
        return next(replies)

    doc = DOC + "\n" + ("word " * tn.CHUNK_WORDS) + "oracus\n"
    assert asyncio.run(tn.find_corrections(doc, "Dune", "", chat)) == {}


def test_garbage_from_the_model_is_ignored():
    async def chat(_prompt):
        return "sure! here are the corrections: none"

    assert asyncio.run(tn.find_corrections(DOC, "Dune", "", chat)) == {}


def test_youtube_command_stages_the_corrected_transcript(monkeypatch, tmp_path):
    from utils.commands import youtube_handler as yh
    import tools.maintenance.youtube_to_kb_md as conv

    monkeypatch.setattr(yh, "INGRESS", tmp_path)
    monkeypatch.setattr(yh, "_last_used", {})
    stats = {"title": "DUNE Explained", "channel": "FilmComicsExplained",
             "url": "https://www.youtube.com/watch?v=abcdefghijk",
             "duration_seconds": 600, "words": 40}
    monkeypatch.setattr(conv, "convert", lambda _vid: (DOC, stats))

    async def fake_chat(**_kwargs):
        return {"message": {"content": json.dumps(
            {"corrections": [{"heard": "oracus", "correct": "Arrakis"}]})}}

    sent = []

    class Channel:
        id = 1
        async def send(self, text=None, **_):
            sent.append(text)
            return types.SimpleNamespace(delete=_noop, edit=_noop)

    async def _noop(*_a, **_k):
        return None

    ctx = types.SimpleNamespace(
        config=types.SimpleNamespace(chat_model="gemma3:12b"),
        ollama_client=types.SimpleNamespace(chat=fake_chat))
    msg = types.SimpleNamespace(
        content="!youtube https://youtu.be/abcdefghijk", channel=Channel(),
        author=types.SimpleNamespace(display_name="ekco", id=1))

    asyncio.run(yh.handle_youtube_command(ctx, msg, _noop))

    staged = next(tmp_path.glob("*.md")).read_text()
    assert "oracus" not in staged and "Arrakis" in staged
    meta = json.loads(next(tmp_path.glob("*.meta.json")).read_text())
    assert meta["name_corrections"] == {"oracus": "Arrakis"}
    assert any("oracus → Arrakis" in (s or "") for s in sent)
