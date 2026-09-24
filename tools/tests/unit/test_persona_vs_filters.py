"""DECISIONS Q5: what the persona tells her to say, the filters must let through.

The persona once told her to report "system entropy" while a filter deleted
that exact phrase. The two files are maintained separately, so this runs every
phrase the persona *encourages* — a bullet that is only a quote, or a quote in
a sentence that says "Say", "naturally:" or "e.g.," and forbids nothing, before
any "instead of" — through the output filters and checks every word survives.
Quotes in a sentence that says never / avoid / don't are prohibitions and are
left out.
"""
import re
from pathlib import Path

PERSONA = Path("knowledge_base/kaia_persona.md")
_QUOTE = re.compile(r'["“]([^"“”]{3,120}?)["”]')
_PROHIBITS = re.compile(r"\b(never|avoid|do not|don't|not|no)\b", re.I)


def encouraged_phrases(text: str) -> list:
    found = []
    for line in text.splitlines():
        bare = line.strip().lstrip("-* ").strip()
        whole = re.fullmatch(r'["“]([^"“”]+)["”]', bare)
        if whole:
            found.append(whole.group(1))
            continue
        for sentence in re.split(r"(?<=[.!?])\s+(?=[A-Z*])", line):
            head = sentence.split("instead of")[0]
            if (re.search(r"\b(Say|naturally:|e\.g\.,)", head)
                    and not _PROHIBITS.search(_QUOTE.sub("", head))):
                found += _QUOTE.findall(head)
    return found


def test_the_persona_encourages_something_to_check():
    assert len(encouraged_phrases(PERSONA.read_text(encoding="utf-8"))) >= 8


def test_no_filter_deletes_a_phrase_the_persona_asks_for():
    from utils.core.response_filter import BotSpeakFilter, EmergencyContaminationFilter
    lost = []
    for phrase in encouraged_phrases(PERSONA.read_text(encoding="utf-8")):
        said = phrase.replace("[Title]", "Neuromancer").rstrip(".…")
        said = said[0].lower() + said[1:]
        out = EmergencyContaminationFilter.filter_response(
            BotSpeakFilter.harden(f"{said} and it stuck with me.")) or ""
        missing = [w for w in re.findall(r"[a-z’']{3,}", said.lower()) if w not in out.lower()]
        if missing:
            lost.append(f"{phrase!r} lost {missing}")
    assert not lost, "persona phrases the filters remove:\n" + "\n".join(lost)
