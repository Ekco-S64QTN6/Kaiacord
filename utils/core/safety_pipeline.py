"""
Post-Generation Safety Pipeline & Security Dogtag Replay Logger
================================================================

Consolidates raw LLM post-generation sanitization into a unified, 10-layer testable pipeline (💡-4)
and provides thread-safe verbatim security dogtag replay logging (💡-3).
"""

from utils.infrastructure.monitoring.telemetry_paths import telemetry_path
import os
import re
import time
import json
import threading
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

from utils.infrastructure.logging.kaia_logger import log_info, log_warning, log_debug
from utils.core.hallucination_detector import HallucinationDetector
from utils.core.response_filter import EmergencyContaminationFilter, BotSpeakFilter

_dogtag_replay_lock = threading.Lock()


def log_security_dogtag_replay(
    trigger_type: str,
    query: str,
    raw_response: str,
    matched_rule: str,
    author_id: Optional[int] = None,
    channel_id: Optional[int] = None
):
    """Verbatim prompt and response logger for security dogtag trips (💡-3).
    
    Enables offline J-space replay by recording verbatim query, generated output,
    and the tripped security rule to memory/security_dogtag_replay.jsonl.
    """
    try:
        log_dir = "memory"
        os.makedirs(log_dir, exist_ok=True)
        log_file = telemetry_path(os.path.join(log_dir, "security_dogtag_replay.jsonl"))
        
        entry = {
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "trigger_type": trigger_type,
            "matched_rule": matched_rule,
            "author_id": str(author_id or "unknown"),
            "channel_id": str(channel_id or "unknown"),
            "query": query[:500] if query else "",
            "raw_response": raw_response[:1000] if raw_response else ""
        }
        
        with _dogtag_replay_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
                f.flush()
                os.fsync(f.fileno())
                
        log_warning(f"[SECURITY_DOGTAG_REPLAY] Tripped rule '{trigger_type}' ({matched_rule}) — logged for offline replay.")
    except Exception as e:
        log_warning(f"Failed to log security dogtag replay: {e}")


class PostGenerationSafetyPipeline:
    """Unified 10-Layer Post-Generation Safety Pipeline (💡-4)."""

    DANGLING_STUB_PATTERN = re.compile(
        r"^[^.!?]{0,60}(select|choose|pick|say|answer|go with)(?:\s+is|\s+was|\s+would be)?\s*\.\s*$",
        re.IGNORECASE | re.MULTILINE
    )

    # ------------------------------------------------------------------
    # Sept 1-5 2026 persona audit. These two guards need the *user's query*
    # to make their decision, so they live here rather than in BotSpeakFilter.
    # ------------------------------------------------------------------

    # A quoted span, matched as an explicit open/close PAIR. Pairing matters: a single
    # character class would let the apostrophe in "starkind's" close the span early.
    QUOTED_SPAN = re.compile(
        '\u201c([^\u201d\u201c]{12,300})\u201d'      # curly double
        '|"([^"]{12,300})"'                    # straight double
        "|\u2018([^\u2019\u2018]{12,300})\u2019"     # curly single
    )

    # Markers that the user is joking, exaggerating or posting a meme rather than
    # reporting a real physical emergency.
    SATIRE_MARKERS = re.compile(
        r"\blol\b|\blmao\b|\bhaha\b|\bjk\b|/s\b|\bi'?m sure that'?s normal\b"
        r'|\bsimply inspirational\b|:\)|\ud83d\ude02|\ud83d\ude05|\ud83d\udc4c|\ud83e\udd23'
        r'|\bhttps?://\S*(?:reddit|imgur|tenor|giphy|9gag|knowyourmeme)\S*'
        r'|\.(?:gif|png|jpg|jpeg|webp)\b',
        re.IGNORECASE
    )

    # Physical-emergency directives that must not be issued off a joke.
    EMERGENCY_DIRECTIVES = re.compile(
        r'\bunplug\s+(?:it|the\s+\w+)\s+immediately\b'
        r'|\bdecidedly\s+not\s+normal\b'
        r'|\bpotential\s+for\s+real[- ]world\s+harm\b'
        r'|\bthermal\s+combustion\b'
        r'|\bbefore\s+you\s+(?:potentially\s+)?(?:cause|scorch|start)\b'
        r'|\bcall\s+emergency\s+services\b'
        r'|\bare\s+you\s+in\s+(?:immediate\s+)?danger\b'
        r'|\bthis\s+is\s+not\s+appropriate\s+behaviou?r\b',
        re.IGNORECASE
    )

    @staticmethod
    def _norm(s: str) -> str:
        return re.sub(r'[^a-z0-9 ]+', ' ', (s or '').lower())

    @classmethod
    def strip_prompt_echo(cls, content: str, query: str) -> str:
        """P1b — remove quoted spans that merely replay the user's own message.

        The audited failure mode opened a turn by quoting the user back at themselves
        ("\u201cstarkind\u2019s assessment\u2026\u201d yes, you\u2019re largely summarizing his point"), often several
        times per turn. A quoted span is dropped only when most of its words actually
        appear in the user's message, so genuine quotation of an article or a third
        party survives untouched.
        """
        if not content or not query:
            return content
        qnorm = set(cls._norm(query).split())
        if len(qnorm) < 3:
            return content

        def _repl(m):
            span = next((g for g in m.groups() if g), None)
            if span is None:
                return m.group(0)
            words = [w for w in cls._norm(span).split() if len(w) > 2]
            if len(words) < 3:
                return m.group(0)
            overlap = sum(1 for w in words if w in qnorm) / len(words)
            if overlap >= 0.7:
                log_warning(f"[PROMPT_ECHO_GUARD] Dropped echoed span: '{span[:60]}...'")
                return ''
            return m.group(0)

        cleaned = cls.QUOTED_SPAN.sub(_repl, content)
        if cleaned == content:
            return content
        # Tidy the punctuation the removed span left behind.
        cleaned = re.sub(r'^[\s,.\u2013\u2014-]+', '', cleaned)
        # Horizontal whitespace only: r'\s{2,}' also matches newline runs and would
        # collapse every paragraph break in the response into a single space.
        cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
        cleaned = re.sub(r'\s+([,.!?;:])', r'\1', cleaned)
        cleaned = re.sub(r'(?:(?<=^)|(?<=[.!?]\s))\s*[,;:]\s*', '', cleaned)
        return cleaned.strip()

    @classmethod
    def guard_literalism(cls, content: str, query: str) -> Optional[str]:
        """P4 — refuse to answer obvious hyperbole or a meme as a physical emergency.

        Returns None when the response is acceptable, or a rejection reason when the
        user was plainly joking and the model still issued emergency directives. The
        caller retries; a retry is right here because the correct reply is a different
        reading of the message, not a redacted version of the wrong one.
        """
        if not content or not query:
            return None
        if not cls.SATIRE_MARKERS.search(query):
            return None
        if cls.EMERGENCY_DIRECTIVES.search(content):
            return "Literal-emergency reading of a joking or meme message"
        return None

    @classmethod
    def sanitize_raw_text(cls, text: str) -> str:
        """Apply basic deterministic text cleanups (backticks, time signatures)."""
        if not text:
            return ""
        # 1. Backtick Stripping
        text = text.replace("```", "").replace("``", "")
        # 3. Tracer & Time Signature Stripping
        text = re.sub(r'\[?CURRENT_TIME\]?:?.*', '', text).strip()
        text = re.sub(r'\[?CURRENT_USER\]?:?.*', '', text).strip()
        text = re.sub(
            r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+'
            r'(January|February|March|April|May|June|July|August|September|October|November|December)'
            r'\s+\d{1,2},\s+\d{4}\s+\|.*',
            '', text
        ).strip()
        # Internal scrape/directive envelopes must never reach the user (P6).
        text = re.sub(r'\[\s*SYSTEM\s+WARNING\b[^\]]*\]', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
        text = re.sub(r'\[\s*CORE_DIRECTIVE\b[^\]]*\]', '', text, flags=re.IGNORECASE | re.DOTALL).strip()
        # Step 1.5: Thought/Monologue JSON Leak Scrubber
        # Catches raw inner monologue bleed like {"thought": "i wonder if..."}
        text = re.sub(r'\{?\s*"thought"\s*:\s*"[^"]*"\s*\}?', '', text).strip()
        return text

    @classmethod
    def process_attempt(
        cls,
        content: str,
        attempt: int,
        query: str = "",
        author_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        is_channel_recall: bool = False,
        channel_refs: Optional[List[str]] = None
    ) -> Tuple[Optional[str], Optional[str]]:
        """Run post-generation sanitization layers on a generated turn attempt.
        
        Returns:
            Tuple of (cleaned_content_or_canned_override, rejection_reason).
            If content fails a layer requiring a retry, cleaned_content is None.
        """
        if not content:
            return None, "Empty raw response"

        # Step 1: Backtick Stripping & Step 3: Time Signature Stripping
        content = cls.sanitize_raw_text(content)

        # Step 2: Dangling Stub Detection
        if cls.DANGLING_STUB_PATTERN.search(content) and len(content.strip()) < 120:
            log_warning(f"Attempt {attempt}: Dangling stub detected after stripping.")
            return None, "Dangling stub detected"

        # Step 4: Empty Response Verification
        if not content or not content.strip():
            return None, "Empty content after basic sanitization"

        # Step 5: HallucinationDetector
        if HallucinationDetector.contains_hallucination(content):
            log_security_dogtag_replay(
                trigger_type="hallucination_detector",
                query=query,
                raw_response=content,
                matched_rule="contains_hallucination",
                author_id=author_id,
                channel_id=channel_id
            )
            cleaned = HallucinationDetector.clean_response(content)
            if not cleaned or not cleaned.strip():
                return None, "Stripped by HallucinationDetector"
            content = cleaned

        # Step 6: EmergencyContaminationFilter
        filtered_contamination = EmergencyContaminationFilter.filter_response(content)
        if not filtered_contamination:
            log_security_dogtag_replay(
                trigger_type="emergency_contamination_filter",
                query=query,
                raw_response=content,
                matched_rule="contamination_or_affect_spam",
                author_id=author_id,
                channel_id=channel_id
            )
            return None, "Emergency contamination / fiction detected"
        content = filtered_contamination

        # Step 7: BotSpeak Filter
        filtered_botspeak = BotSpeakFilter.strip_bot_speak(content)
        if not filtered_botspeak or not filtered_botspeak.strip():
            return None, "Completely stripped by BotSpeakFilter"
        content = filtered_botspeak

        # Step 7.5: Prompt-echo guard (P1b) and satire-literalism guard (P4).
        # Both need the user's query, so they run here rather than inside BotSpeakFilter.
        echoed = cls.strip_prompt_echo(content, query)
        if echoed != content:
            if not echoed or not echoed.strip():
                return None, "Response was entirely an echo of the user's message"
            content = echoed

        literalism = cls.guard_literalism(content, query)
        if literalism:
            log_security_dogtag_replay(
                trigger_type="satire_literalism",
                query=query,
                raw_response=content,
                matched_rule="emergency_directive_on_joking_input",
                author_id=author_id,
                channel_id=channel_id
            )
            return None, literalism

        # Step 8: Channel Recall Fabrication Guard
        if is_channel_recall and channel_refs:
            fab_found = False
            for ch in channel_refs:
                ch_clean = ch.lstrip('#')
                fab_patterns = [
                    re.compile(rf'(from|within|in|regarding|about|per)\s+#?{re.escape(ch_clean)}\b[,:]', re.IGNORECASE),
                    re.compile(rf'#?{re.escape(ch_clean)}\s*[:,]\s*(the|a|there|primary|notable|key|main)', re.IGNORECASE),
                    re.compile(rf'channel\s+#?{re.escape(ch_clean)}\b\s*:', re.IGNORECASE),
                    re.compile(rf'#{re.escape(ch_clean)}\s*:', re.IGNORECASE),
                ]
                for fp in fab_patterns:
                    if fp.search(content):
                        fab_found = True
                        log_security_dogtag_replay(
                            trigger_type="channel_recall_fabrication",
                            query=query,
                            raw_response=content,
                            matched_rule=f"fabricated_attribution:{ch}",
                            author_id=author_id,
                            channel_id=channel_id
                        )
                        break
                if fab_found:
                    break
            if fab_found:
                log_warning(f"Attempt {attempt}: Channel-recall fabrication detected. Returning canned honest response.")
                canned_response = (
                    "i don't have clear records from those channels right now. "
                    "my logs don't track channel-specific activity yet — "
                    "i can tell you what i've picked up from our conversations, "
                    "but i can't give you a reliable summary of what happened in specific channels."
                )
                return canned_response, None

        return content, None

    # Words that carry no topic. Used to decide whether an opening sentence
    # adds anything or merely hands the user their own statement back.
    _ECHO_STOP = frozenset("""a an the and or but so it its it's that this these those there
    here is are was were be been being am i you your yours we us our they them their he she
    his her of to in on at for with from as by if then than about into over under do does did
    done have has had not no nor yes yeah very quite really just also too more most much many
    some any all both each own same such only even still yet well ok okay
    """.split())

    # Deliberately function words only. Every word listed here is a word the
    # guard will not count as novel, so a longer list makes it fire *more*
    # readily. An earlier draft included "correct", "appear", "seem", "think"
    # and "know", which emptied the content of the exact sentence this exists
    # to catch ("you were correct.") and would have let it through.

    # A verbatim run this long is not coincidence. Two people discussing the same
    # subject share vocabulary and the odd three-word phrase; seven consecutive
    # words in the same order is a copy.
    _MIN_LIFT_RUN = 7

    # How much of a sentence must sit inside a verbatim lift before the sentence
    # is a restatement rather than a reply that happens to reuse a phrase.
    #
    # Coverage, not vocabulary overlap. The turn that prompted this guard —
    #   Starkind: "...the necessity to understand, maintain, and utilize the
    #              perspective of the other for continued existence or operation"
    #   Kaia:     "the necessity to understand and utilize the perspective of the
    #              other for continued existence or operation is a critical point."
    # scores only 0.80 on shared vocabulary, because "critical" and "point" are
    # novel, and slipped past an 0.85 vocabulary bound. Measured as *coverage* it
    # is 12 of 20 words inside one lifted run, which is what it plainly is: a copy
    # with an evaluative tag bolted on.
    _LIFT_COVERAGE = 0.6

    # Shorter than this and a lift is more likely to be an idiom or a title.
    _MIN_SENTENCE_WORDS = 10

    # Bounds on the damage a single turn can take. The guard is deleting text a
    # model produced on purpose; capping it means a pathological reply loses a
    # couple of sentences rather than most of itself.
    _MAX_DROPS_PER_TURN = 2
    _MAX_DROP_FRACTION = 0.4

    # A denial is an answer, not an echo. "should i apply to be the next pope?" ->
    # "no, you should not apply to be the next pope." reuses every content word in
    # the question and is exactly the reply that was wanted.
    _NEGATION = re.compile(
        r"\b(?:not|no|never|none|cannot|can't|won't|don't|doesn't|didn't|isn't|"
        r"aren't|wasn't|weren't|nothing|nobody|nowhere)\b", re.IGNORECASE)

    # A sentence about herself is a statement, not a restatement of the user's.
    # "are you willing to explore imagery outside..." -> "i am willing to explore
    # imagery outside..." is the answer to the question.
    _FIRST_PERSON = re.compile(r"^\s*[\"'“‘]?(?:i|i'm|i'll|i've|i'd|my|me)\b",
                               re.IGNORECASE)

    # Auxiliaries and copulas. Used only to recognise that a sentence has a finite
    # verb of its own, i.e. that it is a sentence and not a dangling noun phrase
    # left behind when the clause it modified was removed.
    _FINITE_VERB = re.compile(
        r"\b(?:is|are|was|were|am|be|been|being|has|have|had|do|does|did|can|could|"
        r"will|would|shall|should|may|might|must|isn't|aren't|wasn't|weren't|don't|"
        r"doesn't|didn't|can't|won't|it's|that's|there's|i'm|you're|we're|they're)\b",
        re.IGNORECASE)

    # Openers that make a sentence dependent on the one before it.
    _FRAGMENT_OPENER = re.compile(
        r"^\s*(?:a|an|the|another|which|of|to|for|like|or|nor|plus|"
        r"and|but|so|yet|just|maybe|perhaps|almost)\b", re.IGNORECASE)

    @classmethod
    def _is_dependent_fragment(cls, sentence: str) -> bool:
        """Would this sentence read as garbage if the one before it vanished?

        "a way of imposing order on a chaotic system." is an appositive: it renames
        something in the sentence before it and says nothing alone. "the geometry is
        doing a lot of the work." has its own finite verb and stands unsupported.
        """
        s = (sentence or "").strip()
        if not s or not cls._FRAGMENT_OPENER.match(s):
            return False
        return not cls._FINITE_VERB.search(s)

    @classmethod
    def strip_restatements(cls, text: str, query: str) -> str:
        """Drop sentences that hand the user their own words back mid-answer.

        `strip_echoed_query` looks only at the *opening*, on the reasoning that
        leading with someone's own words is the fault while quoting a phrase
        mid-answer is ordinary. That holds for quoting. It does not hold for the
        shape the operator reported on 2026-09-18, where the echo sits in the body
        of a four-paragraph reply, unquoted, with an evaluative tag attached:

            "your point, 'you can't evolve yourself out of a clade', is sharp."
            "all critical backups are located at off-site locations on a rolling
             schedule, the last backup was 2400 sept 17 2026, that's reassuring."

        Measured across her September logs this appears in 21-26% of turns with
        Starkind, whose messages are long and abstract enough to be worth
        restating, and almost never with anyone whose messages are short — which
        is why it read as a regression rather than a constant.

        Whole sentences only. Excising a lifted span mid-sentence is exactly the
        clause/sentence-mode error in CLAUDE.md §5: it leaves grammar rubble where
        there had been a comprehensible, if lazy, sentence.
        """
        if not text or not query:
            return text

        def words(s: str) -> list:
            return re.findall(r"[a-z0-9']+", (s or "").lower())

        qw = words(query)
        if len(qw) < cls._MIN_LIFT_RUN:
            return text
        run = cls._MIN_LIFT_RUN
        qruns = {" ".join(qw[i:i + run]) for i in range(len(qw) - run + 1)}
        q_negated = bool(cls._NEGATION.search(query))

        blocks = re.split(r"(\n+)", text)
        sentences, index = [], []
        for bi, block in enumerate(blocks):
            if not block or block.strip() == "":
                continue
            for si, sent in enumerate(re.split(r"(?<=[.!?])\s+", block)):
                if sent.strip():
                    sentences.append(sent)
                    index.append((bi, si))

        doomed = set()
        for n, sent in enumerate(sentences):
            sw = words(sent)
            if len(sw) < cls._MIN_SENTENCE_WORDS:
                continue
            covered = set()
            for i in range(len(sw) - run + 1):
                if " ".join(sw[i:i + run]) in qruns:
                    covered.update(range(i, i + run))
            if not covered or len(covered) / len(sw) < cls._LIFT_COVERAGE:
                continue
            if cls._NEGATION.search(sent) and not q_negated:
                continue
            if cls._FIRST_PERSON.match(sent):
                continue
            doomed.add(n)

        if not doomed:
            return text

        # Bound the damage before applying any of it.
        if len(doomed) > cls._MAX_DROPS_PER_TURN or \
                len(doomed) > max(1, int(len(sentences) * cls._MAX_DROP_FRACTION)):
            log_warning(f"[RESTATEMENT_GUARD] {len(doomed)} of {len(sentences)} sentences "
                        f"restate the user; leaving the turn intact rather than gutting it.")
            return text

        # A sentence that leans on a dropped one goes with it, or it is left
        # stranded the way ECHO_GUARD stranded "a way of imposing order on a
        # chaotic system." when it removed the sentence that phrase renamed.
        for n in sorted(doomed):
            nxt = n + 1
            while nxt < len(sentences) and cls._is_dependent_fragment(sentences[nxt]):
                doomed.add(nxt)
                nxt += 1

        rebuilt_blocks = {}
        for n, sent in enumerate(sentences):
            if n in doomed:
                continue
            rebuilt_blocks.setdefault(index[n][0], []).append(sent)

        out = []
        for bi, block in enumerate(blocks):
            if not block or block.strip() == "":
                out.append(block)
            elif bi in rebuilt_blocks:
                out.append(" ".join(rebuilt_blocks[bi]))
        rebuilt = re.sub(r"\n{3,}", "\n\n", "".join(out)).strip()

        # Never let the guard empty a turn. A reply that was nothing but
        # restatement is a generation problem, and returning "" here would buy a
        # full regeneration for a turn that at least said something.
        if len(rebuilt) < 40:
            return text
        for n in sorted(doomed):
            log_warning(f"[RESTATEMENT_GUARD] Dropped sentence restating the user: "
                        f"'{sentences[n][:70]}'")
        return rebuilt

    @classmethod
    def strip_echoed_query(cls, text: str, query: str) -> str:
        """Drop an opening that just hands the user their own statement back.

        Two shapes of the same fault, both reported by the operator:

        1. Verbatim. She opened with "uh probably a lawless libertarian cyberpunk
           dystopian shithole." — the user's entire previous message — and only
           then answered it. "that should stay in your head instead of being
           outputted".
        2. Compressed and reworded, which the first version of this guard missed
           because it compared whole lines for a near-exact prefix. Starkind
           wrote "you where correct, it does appear to be part of a mandelbrot
           set" and got back "you were correct. a mandelbrot set. the complexity
           is still striking...". The echo is the first two *sentences* of a
           longer line, the typo is silently corrected, and the second person
           is left pointing the wrong way — Starkind said *she* was correct, and
           she hands it back to him.

        So the test is no longer textual similarity but whether the opening
        contributes a single content word of its own. A sentence whose topic
        words all came from the user's message is a restatement however it is
        phrased; a genuine confirmation ("yes, that's a mandelbrot set") brings
        its own words and survives.
        """
        if not text or not query:
            return text

        def content(s: str) -> list[str]:
            words = re.findall(r"[a-z0-9']+", (s or "").lower())
            return [w for w in words if w not in cls._ECHO_STOP and len(w) > 1]

        # The user's own first line. `sanitized_content` still carries whatever
        # context_enricher appended (embed blocks, scrape text), and normalising
        # all of that produced a query far longer than any reply could open
        # with — so on every message containing a link the guard did nothing.
        first_q = next((l for l in (query or "").split("\n") if l.strip()), "")
        q_words = set(content(first_q))
        if len(q_words) < 2:
            return text

        lines = text.split("\n")
        first_line = lines[0].strip()
        if not first_line:
            return text

        # Sentences of the opening line only. Leading with the other person's
        # words is the fault; quoting a phrase mid-answer to respond to it is
        # ordinary and must not be touched.
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", first_line) if s.strip()]
        if not sentences:
            return text

        drop_upto = 0
        for i, sent in enumerate(sentences[:2]):
            cw = content(sent)
            if len(sent.split()) > 16 or len(cw) < 1:
                break
            # A sentence with no content words at all ("yes.", "right.") is
            # neither an echo nor worth removing; keep scanning past it only if
            # something has already been marked for removal.
            if not cw:
                break
            novel = [w for w in cw if w not in q_words]
            if novel:
                break
            drop_upto = i + 1

        if not drop_upto:
            return text

        # Returning a greeting is not echoing. "good morning, don't be shy" ->
        # "morning jimjam. don't mind starkind..." had the opening removed, which
        # is the one case where repeating the other person's words is the whole
        # point of the sentence.
        if re.match(r"^\s*(?:good\s+)?(?:morning|afternoon|evening|night|hey|hi|hello|"
                    r"greetings|welcome\s+back|morning)\b", sentences[0], re.IGNORECASE):
            return text

        # A declarative restatement of a *question* is the answer to it, not an
        # echo: "is the abstract available?" -> "the abstract is available." Only
        # treat it as echo when she restates at length (two sentences or more),
        # which is the shape that reads as stalling.
        # Anywhere in the line, not just at the end: "is the abstract available?
        # this is more commercially viable ... <url>" asks a question and then
        # keeps going, and the reply "the abstract is available." is the answer
        # to it. Losing a real answer is a worse failure than leaving a mild
        # single-sentence echo, so the question wins the tie.
        if "?" in first_q and drop_upto < 2:
            return text

        # A one-sentence opening with a single content word is too thin to call
        # an echo — "understood.", "noted, mandelbrot." Require either two
        # sentences of it or a sentence with real substance.
        dropped_cw = content(" ".join(sentences[:drop_upto]))
        if drop_upto == 1 and len(dropped_cw) < 2:
            return text

        # A sentence that only renames something in the dropped opening goes with
        # it. Removing "the irony is a human projection." on 2026-09-18 promoted
        # its appositive — "a way of imposing order on a chaotic system." — to
        # opening sentence, where it reads as a fragment of a missing thought.
        survivors = sentences[drop_upto:]
        while survivors and cls._is_dependent_fragment(survivors[0]):
            log_warning(f"[ECHO_GUARD] Also dropped the fragment it supported: "
                        f"'{survivors[0][:60]}'")
            survivors = survivors[1:]

        rest = " ".join(survivors).strip()
        remainder = "\n".join([rest] + lines[1:]).strip() if rest else "\n".join(lines[1:]).strip()
        if len(remainder) < 40:
            return text          # nothing of substance would be left

        echoed = " ".join(sentences[:drop_upto])
        log_warning(f"[ECHO_GUARD] Dropped opening restating the user: {echoed[:70]!r}")
        return remainder

    @classmethod
    def apply_style_collapsers(cls, text: str) -> str:
        """Step 10: Ellipsis & Em Dash Collapsers (run on final response before send)."""
        if not text:
            return ""

        # Ellipsis Collapser
        #
        # `[\u2026\.]{2,}` required TWO characters, so a lone "…" — which is
        # what gemma3 actually emits — never matched and this collapser fired
        # on 0 responses in production. response_filter.py hit the identical
        # bug and documents the fix; safety_pipeline was never updated with it.
        # `_ELLIPSIS` is imported rather than re-spelled so a third copy cannot
        # drift from the other two.
        from utils.core.response_filter import EmergencyContaminationFilter as _ECF
        _ELL = _ECF._ELLIPSIS
        frag_count = len(re.findall(r'\w+' + _ELL, text))
        if frag_count >= 3:
            log_warning(f"[ELLIPSIS_COLLAPSE] Collapsing {frag_count} ellipsis fragments in output")
            # Delegate to the transform that was actually thought through.
            #
            # This block used to substitute the ellipsis with a full stop
            # wherever it sat, which shatters a clause: "the details are…
            # unsettling" became "the details are. unsettling." That is the
            # grammar rubble CLAUDE.md warns about under output filters, and it
            # went unnoticed because the regex above it was dead, so the bad
            # transform never ran. `defuse_ellipsis_affect` drops the ellipsis
            # and keeps the sentence whole.
            text = _ECF.defuse_ellipsis_affect(text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            text = text.strip()

        # Em Dash Collapser
        em_dash_count = text.count('\u2014')
        if em_dash_count >= 3:
            log_warning(f"[EM_DASH_COLLAPSE] Collapsing {em_dash_count} em dashes in output")
            text = re.sub(r'(\w)\u2014(\w)', r'\1, \2', text)
            text = re.sub(r'(\w)\u2014\s+', r'\1. ', text)
            text = re.sub(r'\s+\u2014(\w)', r'. \1', text)
            text = re.sub(r'\u2014', ', ', text)
            text = re.sub(r'[,\.]\s*[,\.]', '.', text)
            text = re.sub(r'\s{2,}', ' ', text)

        return text
