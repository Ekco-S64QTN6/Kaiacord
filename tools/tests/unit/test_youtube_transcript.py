"""YouTube transcript conversion.

Auto-generated captions arrive as thousands of three-to-eight-word fragments.
Measured on a 130-minute interview: 3,811 snippets, 26,223 words. Modern
YouTube ASR punctuates (1,404 sentence marks — normal prose density), so the
work is structural, not linguistic.

No test here touches the network; snippets are synthetic.
"""
import re

import pytest

from tools.maintenance.youtube_to_kb_md import (
    PARAGRAPH_WORDS,
    YouTubeError,
    build_paragraphs,
    clean_paragraph,
    derive_keywords,
    extract_video_id,
    safe_filename,
    timestamp,
    to_markdown,
)


class Snip:
    """Stands in for the library's snippet object."""
    def __init__(self, text, start=0.0, duration=2.0):
        self.text, self.start, self.duration = text, start, duration


def _snips(sentences, per=4.0):
    """Split sentences into caption-sized fragments, as YouTube does."""
    out, t = [], 0.0
    for sentence in sentences:
        words = sentence.split()
        for i in range(0, len(words), 5):
            out.append(Snip(" ".join(words[i:i + 5]), t)); t += per
    return out


# ── URL handling ─────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=nTqCVJFr7XM",
    "https://www.youtube.com/watch?v=nTqCVJFr7XM&t=42s&list=PLxyz",
    "https://youtu.be/nTqCVJFr7XM",
    "https://youtu.be/nTqCVJFr7XM?si=share_token",
    "https://www.youtube.com/shorts/nTqCVJFr7XM",
    "https://www.youtube.com/live/nTqCVJFr7XM",
    "https://www.youtube.com/embed/nTqCVJFr7XM",
    "https://m.youtube.com/watch?v=nTqCVJFr7XM",
    "<https://youtu.be/nTqCVJFr7XM>",          # Discord angle-bracket wrapping
    "  https://youtu.be/nTqCVJFr7XM  ",
    "nTqCVJFr7XM",
])
def test_video_id_is_extracted_from_every_url_form(url):
    assert extract_video_id(url) == "nTqCVJFr7XM"


@pytest.mark.parametrize("bad", [
    "https://vimeo.com/12345",
    "https://example.com/watch?v=nTqCVJFr7XM",
    "not a url",
    "",
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/",
])
def test_non_youtube_input_is_rejected_with_a_usable_message(bad):
    with pytest.raises(YouTubeError) as e:
        extract_video_id(bad)
    assert str(e.value)


# ── Caption artefacts ────────────────────────────────────────────────

def test_profanity_mask_is_replaced():
    """YouTube splits "[ __ ]" across snippets, so it is stripped after joining
    — a per-snippet replace never sees it whole."""
    assert "__" not in clean_paragraph("we have to do [ __ ] like move cities")
    assert "[expletive]" in clean_paragraph("we have to do [ __ ] like move cities")


@pytest.mark.parametrize("tag", ["[Music]", "[Applause]", "[Laughter]", "[music]"])
def test_bracketed_sound_tags_are_removed(tag):
    assert tag.lower() not in clean_paragraph(f"a sentence {tag} continues").lower()


def test_speaker_change_markers_become_readable():
    out = clean_paragraph(">> yes exactly >> well let's talk about that")
    assert not out.startswith(">>")
    assert ">>" not in out


def test_cleaning_collapses_runs_of_whitespace():
    assert "  " not in clean_paragraph("a    b\n\nc")


# ── Paragraph assembly ───────────────────────────────────────────────

def test_fragments_become_paragraphs():
    sentences = ["This is a sentence about economics and policy." * 1] * 40
    paras = build_paragraphs(_snips(sentences))
    assert len(paras) > 1
    assert all(isinstance(t, float) for t, _p in paras)


def test_paragraphs_end_on_a_sentence_boundary():
    """A hard cut at the word limit produced breaks like "...I think a lot" /
    "of people wouldn't use it"."""
    sentences = ["Word " * 30 + "end of thought." for _ in range(20)]
    paras = build_paragraphs(_snips(sentences))
    unfinished = [p for _t, p in paras[:-1]
                  if not re.search(r"[.!?]['\")\]]?$", p.strip())]
    assert not unfinished, unfinished[:1]


def test_a_paragraph_is_not_absurdly_long():
    sentences = ["Short sentence here." for _ in range(200)]
    paras = build_paragraphs(_snips(sentences))
    assert max(len(p.split()) for _t, p in paras) <= PARAGRAPH_WORDS * 3


def test_unpunctuated_captions_still_produce_paragraphs():
    """Older auto-captions carry no punctuation at all; the hard limit is the
    only thing that can break them."""
    paras = build_paragraphs([Snip("word " * 5, i * 2.0) for i in range(400)])
    assert len(paras) > 1


def test_empty_transcript_yields_nothing():
    assert build_paragraphs([]) == []
    assert build_paragraphs([Snip("  "), Snip("")]) == []


def test_paragraph_start_times_increase():
    paras = build_paragraphs(_snips(["A sentence of some length here." ] * 60))
    times = [t for t, _p in paras]
    assert times == sorted(times)


# ── Keywords ─────────────────────────────────────────────────────────

def test_sentence_openers_are_not_treated_as_topics():
    """Counting every capital returned "Yeah", "Well", "Right" and "Okay" as
    the topics of a two-hour interview."""
    body = ("Yeah. Well I think so. Right. Okay. Yeah. Well. Right. Okay. "
            "Yeah. Well. Right. Okay. Yeah. Well. Right. Okay.")
    kws = derive_keywords("", "", body)
    assert not {"Yeah", "Well", "Right", "Okay"} & set(kws)


def test_recurring_proper_nouns_are_picked_up():
    body = " ".join(["We discussed Google today." ,
                     "Later we returned to Google again.",
                     "And Google once more, plus Google."])
    assert "Google" in derive_keywords("", "", body)


def test_pronoun_contractions_are_excluded():
    body = " ".join(["Then I'm sure of it." for _ in range(10)])
    assert not [k for k in derive_keywords("", "", body) if k.startswith("I'")]


def test_title_and_channel_words_are_always_included():
    kws = derive_keywords("Cory Doctorow on AI", "Novara Media", "body text")
    assert "Doctorow" in kws and "Novara" in kws


def test_one_off_capitals_are_not_keywords():
    """A proper noun recurs; a stray capital does not."""
    body = "We mentioned Zanzibar once. " + "Other words here. " * 30
    assert "Zanzibar" not in derive_keywords("", "", body)


# ── Rendering ────────────────────────────────────────────────────────

@pytest.fixture
def rendered():
    snips = _snips(["This is a substantive sentence about the topic at hand."] * 60)
    meta = {"title": "A Talk | With Someone", "author_name": "Some Channel"}
    return to_markdown("abcdefghijk", meta, snips, "English (auto-generated)")


def test_document_has_frontmatter_and_a_title(rendered):
    md, _stats = rendered
    assert md.startswith("---")
    assert 'title: "A Talk | With Someone"' in md
    assert "# A Talk | With Someone" in md


def test_document_records_its_source(rendered):
    md, stats = rendered
    assert "https://www.youtube.com/watch?v=abcdefghijk" in md
    assert stats["url"].endswith("abcdefghijk")


def test_timestamp_anchors_are_present_for_citation(rendered):
    md, _stats = rendered
    assert re.search(r"(?m)^## \[\d+:\d\d", md)


def test_language_label_is_not_doubled(rendered):
    md, _stats = rendered
    assert md.count("(auto-generated)") == 1


def test_stats_report_real_figures(rendered):
    _md, stats = rendered
    assert stats["words"] > 100
    assert stats["paragraphs"] >= 1
    assert stats["duration_seconds"] >= 0


def test_empty_transcript_raises_rather_than_writing_a_stub():
    with pytest.raises(YouTubeError):
        to_markdown("abcdefghijk", {"title": "x"}, [], "English")


# ── Filenames ────────────────────────────────────────────────────────

def test_filename_matches_the_existing_transcript_convention():
    assert safe_filename("Some Talk").startswith("Transcript - ")
    assert safe_filename("Some Talk").endswith(".md")


@pytest.mark.parametrize("title,banned", [
    ("../../etc/passwd", "/"),
    ("a/b\\c", "\\"),
    ("what? really! yes: no", "?"),
])
def test_filenames_cannot_traverse_or_carry_shell_characters(title, banned):
    name = safe_filename(title)
    assert banned not in name
    assert ".." not in name


def test_filename_length_is_bounded():
    assert len(safe_filename("x" * 500)) < 160


# ── Timestamps ───────────────────────────────────────────────────────

@pytest.mark.parametrize("seconds,expected", [
    (0, "0:00"), (5, "0:05"), (65, "1:05"), (600, "10:00"),
    (3600, "1:00:00"), (7758, "2:09:18"),
])
def test_timestamp_formatting(seconds, expected):
    assert timestamp(seconds) == expected
