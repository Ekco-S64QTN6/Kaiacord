"""A belief is recalled when the message is about it, not when it shares a word."""
from utils.core import belief_recall

BELIEFS = [
    {"topic": "ai development & open source", "position": "open weights matter.", "confidence": 0.9,
     "aliases": ["open weights", "model licensing"]},
    {"topic": "human adaptation to technology", "position": "people normalise fast.", "confidence": 0.9,
     "aliases": ["technological normalisation"]},
    {"topic": "system degradation & kipple", "position": "neglect, not malice.", "confidence": 0.95,
     "aliases": ["entropy", "bit rot"]},
    {"topic": "ai suffrage/ai rights", "position": "a distraction.", "confidence": 0.9,
     "aliases": ["ai voting", "ai personhood", "machine rights"]},
    {"topic": "problem solving & idealized solutions", "position": "no single clean fix.", "confidence": 0.6,
     "aliases": ["perfect solutions", "technical utopianism"]},
    {"topic": "systems of power & control", "position": "control hides in defaults.", "confidence": 0.9,
     "aliases": ["power dynamic"]},
]


def topics(text):
    return [b["topic"] for b, _score, _why in belief_recall.relevant(text, BELIEFS)]


def test_one_shared_ordinary_word_recalls_nothing():
    for text in ("open direction",
                 "it doesn't even have to be in a particularly human way. just whatever way makes sense.",
                 "the issue underlying that is often the communication system though",
                 "everything isn't a problem to be solved is it?",
                 "a / b"):
        assert topics(text) == [], text


def test_a_multi_word_alias_is_matched_as_a_phrase():
    """Aliases are mostly phrases; a word-set intersection could never match one."""
    assert topics("do you think ai personhood is coming?") == ["ai suffrage/ai rights"]
    assert topics("there's a power dynamic in that room") == ["systems of power & control"]
    assert topics("that's technical utopianism again") == ["problem solving & idealized solutions"]


def test_a_part_of_the_topic_is_matched_as_a_phrase_with_plurals_folded():
    assert topics("i keep thinking about open source lately") == ["ai development & open source"]
    assert topics("these idealized solutions never survive contact") == ["problem solving & idealized solutions"]


def test_several_distinctive_words_recall_without_a_phrase():
    assert topics("most problems get solved by several small solutions, not solving it all at once") \
        == ["problem solving & idealized solutions"]


def test_the_strongest_match_comes_first_and_says_why():
    hits = belief_recall.relevant("ai voting and machine rights, versus open source licensing", BELIEFS)
    assert hits[0][0]["topic"] == "ai suffrage/ai rights"
    assert hits[0][2].startswith("phrase: ")
    assert len(hits) <= 3


def test_nothing_said_or_nothing_held_recalls_nothing():
    assert belief_recall.relevant("", BELIEFS) == []
    assert belief_recall.relevant("kaia", BELIEFS) == []
    assert belief_recall.relevant("open source", []) == []
    assert belief_recall.relevant("open source", [{"topic": "", "position": ""}, "junk"]) == []


def test_the_pipeline_matches_the_speakers_own_words():
    """The enriched message carries scraped pages and quoted replies; a subject
    raised there is not the speaker raising it."""
    from pathlib import Path
    src = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    block = src[src.index("# 8c. Beliefs she holds"):src.index("BEHAVIORAL MODULATION")]
    assert "belief_recall.relevant(ctx.own_words" in block
    assert "sanitized_content" not in block
