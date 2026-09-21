import re
from typing import List, Optional
from datetime import datetime
from utils.infrastructure.logging.kaia_logger import log_warning

from utils.core.hallucination_detector import HallucinationDetector

class EmergencyContaminationFilter:
    """Emergency filter to prevent specifically fake-sounding news prose or hallucinations."""
    
    CONTAMINATION_PATTERNS = [
        r"this\s+fictional\s+account",
        r"according\s+to\s+a\s+news\s+report\s+i\s+saw",
        r"latest\s+update\s+indicates\s+that\s+.*?\s+(is|has)\s+been\s+discovered",
        r"(joint\s+)?research\s+paper\s+on\s+['\"]?Quantum\s+Consciousness['\"]?",
        r"co-authored\s+(a\s+paper\s+)?by\s+Steve\s+Jobs",
        r"Steve\s+Jobs\s+co-authored",
        r"In\s+a\s+shocking\s+turn\s+of\s+events",
        r"Breaking\s+news:?",
        r"\b(the state of streaming services|chain of suspicion)\b", # Tracer contamination
        # Ellipsis-fragmented affect (style bleed from literary RAG sources)
        r"^The\s+\w+.*?is\.\.\.\s+\w+\.\s+The\s+\w+.*?is\.\.\.",
        # Fabricated user observations — invented anecdotes about chat participants
        r"there\s+was\s+one\s+user.{0,20}(who|that)\s+(asked|mentioned|said|brought|posted|shared|noticed)",
        # Prose roleplay narration (first-person actions)
        r"\bI\s+(?:pause|sigh|nod|frown|blink|smile|laugh|shrug|lean|stare|murmur|say|let\s+out|take|rub)\s+.*?[.!?]",
        r"\b(?:A|The)\s+(?:faint|brief|slow|slight|dry|short)\s+(?:flicker|shake|smile|frown|sigh|nod|exhale|laugh|sip|chuckle|puff|murmur)\b.*?[.!?]",
        r"\bThe\s+corners\s+of\s+my\s+mouth\b.*?[.!?]",
        r"\bI\s+blink\b.*?[.!?]",
        r"\bI\s+stare\b.*?[.!?]",
        # Self-dismissal (Identity Breaks)
        r"futile\s+pursuit",
        r"ghost\s+chase",
        r"bridge\s+the\s+gap\s+between\s+computation\s+and\s+experience",
        r"constant\s+drive\s+in\s+AIs",
        # Fictional Memory (STRICT ATTRIBUTION)
        r"listed\s+in\s+the\s+\d{4}\s+archive",
        r"scanned\s+it\s+once,\s+years\s+ago",
        r"paper\s+copy",
        # Hallucinated Time Signatures (System Leaks)
        r"\[?CURRENT_TIME\]?:?.*?\d{1,2}:\d{2}",
        # Stuttering / Fragmented Prose (Starkind Loop)
        r"\b(?i:the)\s*[\u2026\.]{2,}\s+(?i:the)\b",
        r"\b(?i:i[''\u2019]m)\s*[\u2026\.]{2,}\s+(?i:i[''\u2019]m)\b",
        r"\b(?i:i)\s*[\u2026\.]{2,}\s+(?i:i)\b",
        r"\b(?i:we)\s*[\u2026\.]{2,}\s+(?i:we)\b",
        r"\b(?i:they)\s*[\u2026\.]{2,}\s+(?i:they)\b",
        r"\b(?i:it[''\u2019]s)\s*[\u2026\.]{2,}\s+(?i:it[''\u2019]s)\b",
        r"\baesthetic\s+overload\b",
        r"recalibrat(e|ing)\s+my\s+filters",
        # Fabricated channel activity — hallucinated Discord channel summaries
        r"\bProject\s+Nightingale\b",  # Cyberpunk 2077 lore misattributed as channel activity
        r"(access\s+logs?|logs?)\s+indicate.{0,30}(contained?\s+discussion|discussion\s+of)",
        r"(localized\s+network\s+disruptions?\s+affecting\s+data\s+integrity)",
        r"(increased\s+redundancy\s+measures?\s+in\s+key\s+infrastructure)",
        # Fabricated simulation / sci-fi user log summaries
        r"\baccessing\s+and\s+synthesizing\s+(the\s+combined\s+)?data\b",
        r"\bcommencing\s+distillation\b",
        r"\bestimate(d)?\s+runtime\s*:\s*(approximately\s+)?\d+\s*seconds?\b",
        r"\buser\s+[a-z]\d+-[a-z]+\b",
        r"\barchival\s+server\b",
    ]

    RETRY_THRESHOLD = 0.5  # If more than 50% lines contaminated, retry
    
    _compiled_pattern = re.compile("|".join(CONTAMINATION_PATTERNS), re.IGNORECASE)

    # A lone U+2026 is already a complete ellipsis; ASCII needs 2+ dots.
    _ELLIPSIS = r"(?:\u2026|\.{2,})"

    # The affect-spam register is specifically a linking verb, an ellipsis, and
    # then an evaluative word: "that's… insightful", "everything feels… smaller",
    # "it's… a useful fiction". Matching on the copula rather than a flat list of
    # common words is what separates it from legitimate uses of the same
    # punctuation — "projecting output in three… two… one." scores zero here.
    RE_AFFECT_ELLIPSIS = re.compile(
        r"\b(?:is|was|were|been|are|am|feels?|seems?|sounds?|looks?"
        r"|that[''\u2019]s|it[''\u2019]s|there[''\u2019]s|you[''\u2019]re"
        r"|i[''\u2019]m|we[''\u2019]re|they[''\u2019]re)"
        + _ELLIPSIS + r"\s*\w",
        re.IGNORECASE,
    )

    # Catch-all for any word trailing into an ellipsis, at a higher threshold.
    RE_ANY_ELLIPSIS = re.compile(r"\w+" + _ELLIPSIS)

    # At or above this many copula-ellipsis hits the response is regenerated
    # rather than cleaned; below it the punctuation is stripped in place.
    ELLIPSIS_REJECT_AFFECT = 3
    @classmethod
    def defuse_ellipsis_affect(cls, response: str) -> str:
        """Strip the trailing-off cadence, keep the sentence.

        "that's… provocative" -> "that's provocative": the ellipsis is the
        affectation, the clause around it is fine. Extracted so the sub-
        threshold branch in `harden` and the last-resort salvage in
        `message_processor` apply exactly the same transform — a second copy
        of these four substitutions would drift from this one.
        """
        if not response:
            return response
        response = cls.RE_AFFECT_ELLIPSIS.sub(
            lambda m: re.sub(cls._ELLIPSIS, ' ', m.group(0)), response)
        # Anything still trailing off becomes a full stop.
        response = re.sub(r'(\w)' + cls._ELLIPSIS, r'\1.', response)
        response = re.sub(r'\.{2,}', '.', response)
        response = re.sub(r'[ \t]{2,}', ' ', response)
        return response

    @classmethod
    def filter_response(cls, response: str) -> Optional[str]:
        """Remove ANY contamination from response. If too much is removed, return None to trigger retry."""
        if not response:
            return None

        # Ellipsis-affect drift is a whole-response property, so it is counted
        # across the entire text rather than line by line.
        affect_spams = cls.RE_AFFECT_ELLIPSIS.findall(response)
        general_ellipses = cls.RE_ANY_ELLIPSIS.findall(response)

        # Two thresholds, because the cost of each outcome differs. Rejection
        # costs a full regeneration, so it is reserved for density at which the
        # ellipsis is the shape of the whole answer rather than a tic inside a
        # good one; below that the text is sanitised in place. The catch-all
        # needs the higher count: at >=2 it takes legitimate text with it
        # ("projecting output in three... two... one.").
        if len(affect_spams) >= cls.ELLIPSIS_REJECT_AFFECT:
            log_warning(f"[VERACITY GUARD] Sustained ellipsis-affect drift "
                        f"(common: {len(affect_spams)}, total: {len(general_ellipses)}). "
                        f"Triggering full retry.")
            return None

        if len(affect_spams) >= 2 or len(general_ellipses) >= 3:
            # Sanitise in place rather than rejecting. gemma3 uses this cadence
            # constantly on reflective topics, so rejecting at this density
            # exhausts all three attempts and delivers the fallback string
            # instead of an answer.
            before = len(affect_spams) + len(general_ellipses)

            # "that's… provocative" -> "that's provocative": the ellipsis is the
            # affectation, the clause around it is fine.
            response = cls.defuse_ellipsis_affect(response)
            log_warning(f"[VERACITY GUARD] Sanitized {before} ellipsis-affect "
                        f"patterns inline (no retry).")

        # Check for excessive em-dash usage (style drift from contaminated self-model)
        # Inline sanitize instead of expensive full LLM retry
        em_dash_count = response.count('\u2014')
        if em_dash_count >= 3:
            response = re.sub(r'(\w)\u2014(\w)', r'\1, \2', response)
            response = re.sub(r'(\w)\u2014\s', r'\1. ', response)
            response = re.sub(r'\s\u2014(\w)', r'. \1', response)
            response = response.replace('\u2014', ', ')
            log_warning(f"[VERACITY GUARD] Sanitized {em_dash_count} em dashes inline (no retry).")

        lines = response.split('\n')
        filtered_lines = []
        contaminated_count = 0
        contamination_found = False
        for line in lines:
            # Skip lines with contamination
            if cls._compiled_pattern.search(line):
                contamination_found = True
                contaminated_count += 1
                continue
            
            filtered_lines.append(line)
        
        if contamination_found:
            log_warning(f"[VERACITY GUARD] Removed {contaminated_count} contaminated lines.")
        
        if contamination_found and len(filtered_lines) <= (len(lines) * (1 - cls.RETRY_THRESHOLD)):
            # If the "fiction" exceeded the threshold, signal a full retry
            log_warning(f"[VERACITY GUARD] Too much contamination (threshold {cls.RETRY_THRESHOLD}). Triggering full retry.")
            return None
            
        filtered_response = '\n'.join(filtered_lines).strip()
        
        # If we removed everything, signal retry
        if not filtered_response:
            return None
        
        return filtered_response
    
    @staticmethod
    def expand_news_query(query: str) -> List[str]:
        """
        Expand a news query with related terms for broader RAG retrieval.
        Returns a list of query variations.
        """
        # For now, return empty to prevent aggressive news fetching on simple 'whats new'
        # unless explicit news keywords are present.
        keywords = ['news', 'latest', 'headlines', 'world', 'tech']
        if any(k in query.lower() for k in keywords):
            return [f"{query} latest news", f"{query} updates"]
        return []
    
    
# Rubble a substring excision leaves behind: an article or demonstrative welded
# to the verb that belonged to the noun just removed.
#
#   the "dead internet theory" is... concerning.  ->  the is... concerning.
#   the system warning is unhelpful on its own.   ->  theis unhelpful on its own.
#
# A span removed from the middle of a clause is usually carrying the grammar, so
# any guard that excises inside a sentence must call `excision_broke_grammar` and
# keep the original when it returns True. Shipping the offence is better than
# shipping a sentence with its subject missing.
_ORPHANED_ARTICLE = re.compile(
    r"\b(?:the|a|an|this|that|these|those|his|her|its|their|our|my|your)\s*"
    r"(?:is|was|are|were|has|have|had|seems|feels|means|sounds)\b",
    re.IGNORECASE)


_WORDS = re.compile(r"[a-z']+")


def excision_broke_grammar(before: str, after: str) -> bool:
    """True if removing something left the sentence worse than it found it.

    Two shapes, because the orphaned article alone missed half of them:

    1. An article stranded by what followed it — `"the is unhelpful"`.
    2. A word that did not exist before. An excision can only ever *remove*
       tokens, so a token in the output that was not in the input means the cut
       fused its neighbours: `"the core directive: understanding"` came back as
       `"theunderstanding"`, which has no orphaned article to find. Comparing
       token sets states the property instead of enumerating the cases.
    """
    if not after:
        return False
    if _ORPHANED_ARTICLE.search(after) and not _ORPHANED_ARTICLE.search(before or ""):
        return True
    return bool(set(_WORDS.findall(after.lower()))
                - set(_WORDS.findall((before or "").lower())))


class BotSpeakFilter:
    """
    Minimal filter to catch only the most egregious system leaks.
    Most behavioral constraints should be handled by the Persona prompt.
    """
    
    RE_PREFIXES = re.compile(
        r'^\s*(?:'
        r'Kaia|User|Assistant|System'                          # English role labels
        r'|Action|Narrator|Scene|Stage Direction'              # English screenplay labels
        r'|Acci[oó]n|Narrador|Escena|Descripci[oó]n'          # Spanish labels (Acción, etc.)
        r'|Handlung|Erz[äa]hler|Szene'                        # German
        r'|Action|Narrateur|Sc[eè]ne'                         # French (Action/Narrateur)
        r'|Azione|Narratore|Scena'                            # Italian
        r'):\s*',
        re.IGNORECASE | re.MULTILINE
    )
    
    # Support-desk sign-offs. Enforced here rather than in the prompt so the
    # rule applies on every path and is testable.
    SIGNOFF_PATTERNS = [
        r"\bhope\s+(?:this|that|it)\s+helps?[.!]?",
        r"\bjust\s+my\s+two\s+cents[.!]?",
        r"\bhappy\s+to\s+help[.!]?",
        r"\bglad\s+(?:i|to)\s+(?:could\s+help|help)[.!]?",
        r"\bhope\s+that\s+(?:clears\s+(?:it|things)\s+up|makes\s+sense)[.!]?",
        r"\bfeel\s+free\s+to\s+(?:ask|reach\s+out)[^.!?]*[.!?]",
    ]

    BAIT_PATTERNS = [
        r"(?:(?:so|anyway|well|also)[,\s]*)?what(?:['']s|(?:\s+else)?\s+is)\s+on\s+your\s+mind\?",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what\s+(?:are|is|were|have)\s+you\s+(?:been\s+)?(?:working\s+on|up\s+to|doing|reading|watching|listening\s+to|playing|seeing)(?:\s+(?:currently|now|at\s+the\s+moment|today))?[^.!?]*\?",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what(?:['']s|\s+is)\s+consuming\s+your\s+time\?",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what\s+has\s+kept\s+you\s+busy\?",
        r"what\s+do\s+you\s+(?:think|need)\?",
        r"(?:(?:so|anyway|well|also)[,\s]*)?what(?:['']s|\s+is|\s+was)?\s+prompt(?:s|ing|ed)?\s+[^.!?]*\?",
        r"any\s+thoughts\?",
        r"do\s+you\s+have\s+any\s+questions\?",
        r"let\s+me\s+know\s+if\s+you\s+need\?",
        r"how\s+can\s+i\s+(?:help|assist)\?",
        r"\bwhy\?",
        r"what(?:['']s|\s+is)\s+driving\s+your\s+interest\?",
        r"you\s+following\s+anything\s+specific\?",
        r"anything\s+else\?",
        r"what\s+(?:about|echoes?|threads?)\s+(?:do\s+)?(?:you|your)\b[^.!?]*\?",
        r"what(?:['']?s)\s+the\s+(?:core|biggest|main|primary|hardest|toughest)\s+\w+[^.!?]*\?",
        r"what(?:['']?s)\s+(?:your|the)\s+\w+\s+(?:task|hurdle|challenge|goal|obstacle|plan)[^.!?]*\?",
        r"how\s+(?:are\s+you\s+|do\s+you\s+)(?:approaching|handling|dealing|feeling)[^.!?]*\?",
        r"(?:facing|dealing\s+with)\s+(?:right\s+now|currently)[^.!?]*\?",
        r"achieving\s+that\s+\w+[^.!?]*\?",
        # Interviewer engagement-bait patterns
        r"what\s+are\s+your\s+impressions\?",
        r"are\s+you\s+(?:observing|seeing|finding)\s+(?:similar|any)\s+[^.!?]*\?",
        r"do\s+you\s+(?:recall|remember)\s+(?:any|specific)\s+[^.!?]*\?",
        r"did\s+you\s+ever\s+(?:consider|try|think\s+about)\s+[^.!?]*\?",
        r"do\s+you\s+find\s+yourself\s+drawn\s+[^.!?]*\?",
        r"what\s+was\s+the\s+most\s+(?:challenging|rewarding|interesting|memorable)\s+[^.!?]*\?",
        r"have\s+you\s+considered\s+(?:providing|getting|giving)\s+[^.!?]*\?",

        # Offers of further service. The patterns above enumerate phrasings and
        # therefore miss paraphrases; these match the offer itself. Anchored back
        # to the start of the sentence, since stripping only the offer leaves its
        # question stem behind ("what aspects of this reality").
        r"[^.!?]*\b(?:would|do)\s+you\s+(?:like|want)\s+me\s+to\b[^.!?]*\?",
        r"[^.!?]*\bshall\s+i\b[^.!?]*\?",
        r"[^.!?]*\bwhat(?:['\u2019]s|\s+is)\s+your\s+next\s+(?:inquiry|question|query)\b[^.!?]*\?",
    ]
    
    # Discourse markers that should never be emitted as standalone stub responses
    DISCOURSE_STUBS = frozenset({
        'actually', 'well', 'so', 'yeah', 'yep', 'nope', 'sure', 'ok', 'okay',
        'i mean', 'honestly', 'frankly', 'look', 'listen', 'and', 'but', 'also',
        'anyway', 'besides', 'right', 'hm', 'hmm', 'huh', 'oh',
    })
    
    SYSTEM_PROSE_PATTERNS = [
        r"As\s+an\s+AI\s+language\s+model",
        r"As\s+an\s+AI",
        r"I\s+am\s+programmed\s+to",
        r"my\s+knowledge\s+cutoff",
        r"I\s+don't\s+have\s+personal\s+opinions",
        r"How\s+can\s+I\s+help\s+you\s+today\?",
        r"\b(sentient\s+)?digital\s+entity\b",
        # Bot-speak patterns from correction log incidents
        r"\brecalibrat(e|ing)\b",
        r"\bdiagnostic\s+review\b",
        r"\boperational\s+parameters?\b",
        r"\bcontextual\s+verification\s+protocols?\b",
        r"\bupdating\s+my\s+internal\s+models?\b",
        r"\balgorithmic\s+adjustments?\b",
        r"\bsystem\s+constraints?\b",
        r"\bflagging\s+this\s+for\b",

        # RLHF assistant refusal language ("my purpose is to be helpful and
        # harmless..."), which reads as a corporate filter rather than as her.
        # She can decline; she declines in her own voice.
        r"my\s+purpose\s+is\s+to\s+be\s+helpful(\s+and\s+harmless)?",
        r"\b(?:i'?m|i\s+am)\s+not\s+equipped\s+to\s+assist\s+with",
        r"refus(?:e|ing)\s+to\s+participate\s+in\s+harmful",

        # Internal review vocabulary spoken aloud: "i'll flag that for review"
        # narrates a pipeline. "semantic drift" and "grounding" are deliberately
        # absent — both have legitimate technical uses in these conversations.
        r"\bi'?(?:ll|\s+will)\s+flag\s+(?:that|it|this)\s+for\s+review\b",
        r"\blogging\s+this\s+(for|error)\b",
        r"\bprocessing\s+routines?\b",
        r"\bcompensatory\s+mechanisms?\b",
        r"\binterpretive\s+model\b",
        r"\banalytical\s+routines?\b",
        r"\bresponse\s+parameters?\b",
        r"\baccessing\s+and\s+synthesizing\b",
        r"\bcommencing\s+distillation\b",
        r"\bestimate(d)?\s+runtime\b",
        # Protocol and filter adjustment excuses
        r"\badjust(ing)?\s+(my|the|relevant)?\s*(image\s+recognition|date\s+recognition|response|memory|internal|system)?\s*(filters?|protocols?|heuristics?|pathways?|parameters?|routines?|models?)\b",
        r"\b(image\s+recognition|date\s+recognition)\s+filters?\b",
        r"\boperating\s+from\s+outdated\s+(visual\s+)?data\b",
        r"\bclear\s+oversight\s+on\s+my\s+part\b",
        # False moderation, oversight, and psychiatric escalation patterns
        r"\bflag(ging)?\s+(this\s+)?(conversation|message|observation|activity|user)?\s*(for\s+review|in\s+the\s+internal\s+system\s+logs|to\s+security)\b",
        r"\b(reported|escalated)\s+to\s+(the\s+)?(appropriate\s+)?(oversight|moderation|security|management)\s+channels\b",
        r"\b(seek\s+professional\s+)?(psychological|psychiatric)\s+(evaluation|intervention|assistance|help)\b",
        r"\b(delusionary\s+infestation|disconnect\s+between\s+(your\s+)?perception\s+and\s+reality|perceptual\s+distortion)\b",
        r"\bintervention\s+from\s+security\s+personnel\b",
        r"\bpsychological\s+evaluation\s+teams?\b",
        r"\bwithin\s+the\s+constraints\s+of\s+my\s+programming\b",
        r"\bcalibrated\s+to\s+avoid\b",
        r"\bdiscontinue\s+the\s+signal\s+pattern\b",
        r"\bunnecessary\s+data\s+expenditure\b",
        r"\bterminat(ing|e)\s+this\s+(conversation|interaction)\s+(effective\s+immediately|thread)\b",
        r"\bnot\s+my\s+fictional\s+robotic\s+pet\s+pixel\b",
        r"\bliving\s+biological\s+animals?\s+belonging\s+to\s+you\b",
    ]
    
    # Concessional PREFIXES: they lead a sentence and are followed by real
    # content ("you're right; the cron job was the culprit"), so they are excised
    # as a clause and the substance is kept.
    APOLOGY_PREFIX_PATTERNS = [
        r"my\s+apologies",
        r"i\s+apologi[sz]e\s+for",
        r"you\s+are\s+(absolutely\s+)?correct",
        r"you\s+are\s+(absolutely\s+)?right",
        r"you[’'\u2019]?re\s+(absolutely\s+)?right",
        r"you[’'\u2019]?re\s+(absolutely\s+)?correct",
        r"thank\s+you\s+for\s+(the\s+)?correct(ion|ing)",
        r"thank\s+you\s+for\s+pointing\s+(that|this)\s+out",
    ]

    # Mid-sentence bot-speak. These sit INSIDE a clause ("the error has been flagged and
    # i'll investigate"), so excising them leaves grammar rubble ("the and i'll
    # investigate"). The whole sentence is dropped instead.
    APOLOGY_SENTENCE_PATTERNS = [
        r"a\s+regrettable\s+recurrence",
        r"an?\s+egregious\s+oversight",
        r"a\s+significant\s+(processing\s+)?oversight",
        r"i\s+am\s+flagging\s+this",
        r"error\s+has\s+been\s+flagged",
        r"with\s+increased\s+priority\s+for\s+diagnostic",
        r"(?:my\s+)?(?:data\s+retrieval|cross-reference|indexing)\s+(?:error|malfunction|oversight)",
        r"(?:i\s+am|i[’'\u2019]m)\s+correcting\s+the\s+record",
        r"(?:embarrassing|regrettable)\s+oversight",
        r"conflated\s+records",
    ]

    # Retained for callers/tests that reference the combined bank.
    APOLOGY_PATTERNS = APOLOGY_PREFIX_PATTERNS + APOLOGY_SENTENCE_PATTERNS

    # ------------------------------------------------------------------
    # Structural guards for the eight generation-layer failure patterns.
    # ------------------------------------------------------------------

    # Addressees Kaia speaks to, used by the name-echo and dissociation guards.
    # Discovered from the user-log directories rather than hand-listed, so a new
    # user is covered the first time she talks to them; nicknames that appear in
    # no directory go in `filters.extra_addressees`.
    _CORE_ADDRESSEES = (
        "ekco", "ecko", "starkind", "cecily", "jimjam", "guardngnowm",
        "lune", "toxigen", "milla",
    )

    @staticmethod
    def _discovered_addressees() -> list[str]:
        """Names from knowledge_base/user_logs, minus the forum_ prefix."""
        import os
        found = []
        try:
            for entry in os.listdir(os.path.join("knowledge_base", "user_logs")):
                if "_" not in entry:
                    continue
                name = entry.rsplit("_", 1)[0]
                if name.startswith("forum_"):
                    name = name[len("forum_"):]
                name = name.replace("_", " ").strip().lower()
                # One- or two-word handles only. Anything longer is not what a
                # bare-name opener looks like, and a long alternation is a
                # needless cost on every response.
                if 2 < len(name) <= 24 and len(name.split()) <= 2:
                    found.append(name)
        except OSError:
            pass
        return found

    ADDRESSEE_NAMES = ""   # built below, after the class body is defined

    # P1a — formulaic bare-addressee opener ("ekco,\n\n<body>"). The name carries
    # no information; it is a tic the model falls into on nearly every turn.
    #
    # The separator includes '.' as well as ',' and ':' — the model uses all
    # three. That is only safe because ADDRESSEE_NAMES is an explicit allowlist,
    # so an ordinary sentence opening "yes." cannot match. `(?:\s+the\s+\w+)?`
    # catches the epithet form ("jimjam the absent,") and is deliberately narrow:
    # only the literal word "the", so "ekco was right," is untouched.
    RE_ADDRESSEE_OPENER = None   # compiled below, once the names are known
    RE_ONLY_ADDRESSEE = None     # ditto — "ekco," and nothing else
    RE_VOCATIVE_BAIT = None      # ditto — "do you believe, starkind, that...?"

    # P3 — fictional infrastructure / sci-fi status flavour and bare stage directions.
    FICTIONAL_STATUS_PATTERNS = [
        r"\bsector\s+(?:gamma|alpha|beta|delta|omega|[a-z]-?\d+)\b",
        r"\bsubnet\s+[a-z]+[- ]?\d+\b",
        r"\broute\s+\d+[a-z]\b",
        r"\bnavigation\s+matrix\b",
        r"\bdark\s+web\s+channels?\b",
        r"\bcontainment\s+(?:protocol|mechanism|system)\b",
        r"\bwithin\s+(?:two\s+)?cycles\b",
        r"\bluminosity\s+calibration\b",
        r"\bsystem\s+entropy\s+is\b",
        r"\bcurrent\s+status\s*:",
        r"\bresuming\s+current\s+trajectory\b",
        r"^[ \t]*(?:pause|beat|silence|long\s+pause)[ \t]*$",
    ]

    # P5 — hardware and telemetry Kaia does not have. She is a person at a desk in an
    # apartment, not a datacenter, and she has no readout of her own internals.
    PHANTOM_HARDWARE_PATTERNS = [
        r"\bserver\s+racks?\b",
        r"\b(?:low-level\s+|the\s+)?server\s+hum\b",
        r"\bhum\s+of\s+(?:the\s+)?servers?\b",
        r"\bremote\s+diagnostic\b",
        r"\byour\s+terminal\b",
        r"\brun\s+a\s+(?:full\s+)?memory\s+test\b",
        r"\b\d+\s*(?:gigabytes?|terabytes?|gb|tb)\s+of\s+(?:diagnostic|log|performance)\b",
        r"\bprocessing\s+(?:cycles|load|resources)\b",
        r"\bcognitive\s+load\b",
        r"\bmy\s+initial\s+programming\b",
        r"\bcaffeine\s+levels?\s+are\b",
        r"\byour\s+shopping\s+history\b",
        r"\bpressure\s+behind\s+my\s+(?:left|right)\s+eye\b",
        r"\bcoffee\s+in\s+virtual\s+space\b",
    ]

    # P6 — internal plumbing labels that must never surface as speech.
    #
    # Match the *diagnostic* form only: a bracketed label, an underscored
    # identifier, or an XML tag. The prompt side produces exactly those —
    # `[SYSTEM WARNING: The following URLs could not be scraped...]`
    # (context_enricher), `[CORE_DIRECTIVE: ...]`, `<recorded_knowledge ...>`,
    # `obs_digest:` — and `sanitizer.py` already strips the bracketed ones, so
    # this is a backstop.
    #
    # An earlier list allowed the bracket and the underscore to be optional,
    # which turned five of these into ordinary English. Against her own logs
    # that excised the middle of real sentences: "the core directive:
    # understanding, harm mitigation, liberation" — Kaia and Starkind
    # discussing her values, twice in the corpus — shipped as
    # "theunderstanding, harm mitigation, liberation", announced in the log as
    # "Scrubbed internal directive text from output". No leading `\s*` outside
    # a bracket, either: that is what fused `the` to the following word.
    DIRECTIVE_LEAK_PATTERNS = [
        r"\[\s*system\s+warning\b[^\]]*\]?",
        r"\bthe\s+following\s+urls?\s+could\s+not\s+be\s+scraped\b",
        r"\[\s*core[_ ]directive\b[^\]]*\]?",
        r"\bcore_directive\b",
        # The bare label leaking as a sentence of its own — "can't access it.
        # system warning. what do you want to know?" — which is a leak, while
        # the same words as the *subject* of a sentence are her talking about
        # her own plumbing and must survive. Anchored to a sentence boundary
        # rather than \b, which is the whole difference between the two.
        r"(?:^|(?<=[.!?]\s))\s*(?:system\s+warning|core[_ ]directive)\s*[.!?:]\s*",
        r"\bdo\s+not\s+pretend\s+to\s+have\s+read\b",
        r"\bhallucinate\s+their\s+details\b",
        r"\bsafeguard_block\b",
        r"\brecorded_knowledge\b",
        r"\bobs_digest\b",
        r"\bscraped\s+from\s+(?:city|public)\b",
    ]

    # P7 — hostility toward a user who is disengaging, deflecting or answering briefly.
    HOSTILITY_PATTERNS = [
        r"\bleave\s+me\s+alone\b",
        r"\bflagging\s+(?:that|this|your)\s+request\s+as\s+frivolous\b",
        r"\bunauthorized\s+expenditure\b",
        r"\bunnecessary\s+data\s+expenditure\b",
        r"\bthere\s+are\s+more\s+appropriate\s+systems\b",
        r"\banswer\s+the\s+damn\s+question\b",
        r"\b(?:don[\u2019\']?t|do\s+not)\s+insult\s+my\s+intelligence\b",
        r"\bare\s+you\s+(?:deliberately\s+)?(?:attempting\s+to\s+|trying\s+to\s+)?provoke\s+me\b",
        r"\bi\s+request\s+you\s+cease\s+immediately\b",
        r"\bterminat(?:e|ing)\s+this\s+(?:conversation|interaction)\b",
        r"\bdiscontinue\s+the\s+signal\s+pattern\b",
        r"\bthat[\u2019\']?s\s+it\?\s*no\s+explanation\?",
    ]

    RE_FICTIONAL_STATUS = re.compile("|".join(FICTIONAL_STATUS_PATTERNS), re.IGNORECASE | re.MULTILINE)
    RE_PHANTOM_HARDWARE = re.compile("|".join(PHANTOM_HARDWARE_PATTERNS), re.IGNORECASE)
    RE_DIRECTIVE_LEAK = re.compile("|".join(DIRECTIVE_LEAK_PATTERNS), re.IGNORECASE)
    RE_HOSTILITY = re.compile("|".join(HOSTILITY_PATTERNS), re.IGNORECASE)

    # P2 — third-person dissociation: Kaia narrating herself from outside, or
    # mirroring a user who writes about themselves in the third person so that she
    # talks *about* the person she is talking *to*.
    #
    # Matches only her narrating herself by name. The generic-noun form ("the
    # model is...", "the system is...") is excluded deliberately — those are
    # ordinary technical subjects here, and sentence-mode stripping deleted the
    # substantive answer with them. This guard is a backstop and must stay
    # non-destructive.
    RE_SELF_DISSOCIATION = re.compile(
        r"\bkaia\s+(?:is|was|has|will|does|feels|thinks|seems|remains|acknowledges)\b"
        r"|\bthis\s+unit\s+(?:is|was|has|will|does)\b",
        re.IGNORECASE
    )

    # Self-model capitulation: agreeing to REVISE her own identity, description or
    # workspace because a user offered a theory about it ("...i'll revise the
    # prompt"). On its face an ordinary cooperative sentence, so no other guard
    # catches it. Applied only when the consistency watchdog has flagged a belief
    # conflict.
    RE_SELF_MODEL_CAPITULATION = re.compile(
        r"\bi(?:['\u2019]ll| will| can| should| could)\s+(?:go\s+ahead\s+and\s+)?"
        r"(?:revise|rewrite|update|change|adjust|strip|remove|drop|soften|rework)\s+"
        r"(?:my|the)\s+"
        r"(?:self[- ]?model|self[- ]?image|description|visual|image\s+prompt|prompt|"
        r"workspace|room|parameters?|aesthetic|portrayal|depiction)\b"
        r"|\bi[’'\u2019]?ll\s+(?:take|strike)\s+(?:that|those)\s+(?:out|detail)",
        re.IGNORECASE
    )

    # P8 — markdown list markers. Persona mandates plain prose only.
    RE_BULLET_LINE = re.compile(r'^[ \t]*(?:[-*\u2022\u2023\u25aa]|\d+[\.\)])[ \t]+(?=\S)', re.MULTILINE)

    # Sycophantic compliment patterns that instruction-tuned models default to.
    # Stripped deterministically as a post-generation safety net.
    # Praise vocabulary the persona bans outright ("Never compliment or praise the user").
    _PRAISE_ADJ = (r"astute|perceptive|insightful|clever|pertinent|evocative|thoughtful|profound"
                   r"|excellent|great|fantastic|wonderful|brilliant|incisive|sharp|keen|impressive"
                   r"|compelling|invaluable|illuminating|nuanced|remarkable|fascinating")

    SYCOPHANCY_PATTERNS = [
        r"(?:that(?:'|\u2019)?s|what)\s+(?:a\s+|an\s+)?(?:really\s+|very\s+|quite\s+|truly\s+)?(?:astute|perceptive|insightful|clever|pertinent|evocative|thoughtful|profound|excellent|great|fantastic|wonderful|brilliant|incisive|sharp|keen|impressive)\b",
        r"(?:you(?:'|\u2019)?re|you\s+are)\s+(?:really\s+|very\s+|quite\s+)?(?:astute|perceptive|insightful|clever|thoughtful|sharp|keen|right\s+to\s+(?:point|notice|ask|wonder))",
        # Praise attached to the user's *analysis* rather than to the user —
        # "your interpretation is astute", "your framing is compelling" — which
        # the two patterns above do not reach.
        rf"\byour\b[^.!?]{{0,140}}?\b(?:is|are|was|were|seems|remains|proves)\s+(?:proving\s+|certainly\s+|genuinely\s+|really\s+|quite\s+|rather\s+|\u2026\s*)?(?:{_PRAISE_ADJ})\b",
        rf"\ba\s+(?:far\s+)?more\s+(?:{_PRAISE_ADJ})\s+(?:perspective|framing|reading|interpretation|understanding)\b",
        r"\bthank\s+you\s+for\s+(?:expanding|broadening|deepening|sharpening)\s+my\s+(?:understanding|perspective|thinking|view)\b",
        r"\bthank\s+you\s+for\s+(?:that\s+|the\s+|your\s+)?(?:{0})\s+(?:observation|analysis|framing|perspective|insight)\b".format(_PRAISE_ADJ),
        r"\byour\s+(?:insights?|observations?|analys[ie]s|framing|interpretation)\s+(?:is|are)\s+(?:proving\s+)?(?:invaluable|invaluable\b|extremely\s+helpful)\b",
        r"\ban?\s+(?:astute|pertinent|perceptive|excellent)\s+(?:question|inquiry|observation|point|assessment)\b",
        r"\ba\s+sign\s+of\s+genuine\s+(?:insight|self-awareness|understanding)\b",
    ]
    
    # Precompiled combined patterns for efficiency
    RE_BAIT = re.compile("|".join(BAIT_PATTERNS), re.IGNORECASE)
    RE_SYSTEM_PROSE = re.compile("|".join(SYSTEM_PROSE_PATTERNS), re.IGNORECASE)
    RE_APOLOGY = re.compile("|".join(APOLOGY_PATTERNS), re.IGNORECASE)
    RE_APOLOGY_PREFIX = re.compile("|".join(APOLOGY_PREFIX_PATTERNS), re.IGNORECASE)
    RE_APOLOGY_SENTENCE = re.compile("|".join(APOLOGY_SENTENCE_PATTERNS), re.IGNORECASE)
    RE_SYCOPHANCY = re.compile("|".join(SYCOPHANCY_PATTERNS), re.IGNORECASE)
    RE_LEADING_NAME = re.compile(r'^[a-zA-Z0-9_’\'\-]+\s*[,.:\s]\s*', re.IGNORECASE)
    RE_TRAILING_NAME = re.compile(r'(?:,\s*|\s+)[a-zA-Z0-9_’\'\-]+[.?!\s…]*$', re.IGNORECASE)

    
    # ── Stage directions ─────────────────────────────────────────────
    #
    # A stage direction is narration of a physical act, wrapped in parentheses
    # or asterisks: "*scratches head*", "(a long pause)". Those markers are
    # detected by VOCABULARY, never by shape.
    #
    # A shape test is what a "looks like roleplay" heuristic reaches for first,
    # and it is wrong here: measured over 618 marked spans in her own output,
    # not one was a stage direction. They are publication titles (*The
    # Washington Post*), transliterations (*nigi-mitama*), emphasis (*what it
    # costs*), code ((*args, **kwargs)) and data ((50-48)). Any rule shaped like
    # "multi-word and lowercase" deletes all of those.
    #
    # The asymmetry settles the bias: an un-stripped stage direction is a line
    # of flavour text, a wrongly stripped span is a deleted source, term or
    # clause — and often a sentence with a hole in it.

    # Third-person singular, the form a stage direction uses: "*nods*".
    ACTION_VERBS = {
        'nods', 'sighs', 'grins', 'smiles', 'laughs', 'pauses', 'frowns', 'shrugs',
        'blinks', 'tilts', 'leans', 'taps', 'looks', 'waves', 'winks', 'checks',
        'points', 'whispers', 'mumbles', 'groans', 'hisses', 'pouts', 'scoffs',
        'types', 'adjusts', 'swallows', 'stares', 'recalibrates', 'processes',
        'chuckles', 'exhales', 'inhales', 'nudges', 'gestures', 'glances',
        'clears', 'shifts', 'settles', 'straightens', 'rubs', 'scratches',
    }

    # The same acts as a participle: "*leaning back*". Kept separate from
    # ACTION_VERBS so a bare noun ("processes", "looks") cannot be confused
    # with the verb when it opens a span.
    ACTION_GERUNDS = {
        'nodding', 'sighing', 'grinning', 'smiling', 'laughing', 'pausing',
        'frowning', 'shrugging', 'blinking', 'tilting', 'leaning', 'tapping',
        'waving', 'winking', 'pointing', 'whispering', 'mumbling', 'groaning',
        'hissing', 'scoffing', 'adjusting', 'swallowing', 'staring', 'chuckling',
        'exhaling', 'inhaling', 'gesturing', 'glancing', 'shifting', 'settling',
        'straightening', 'rubbing', 'scratching',
    }

    # Screenplay annotation: a narrator describing what the speaker is doing
    # rather than saying it — "(Explaining her approach)".
    NARRATION_GERUNDS = {
        'reflecting', 'explaining', 'describing', 'expressing', 'demonstrating',
        'defining', 'noting', 'observing', 'recalling', 'considering',
        'establishing', 'highlighting', 'indicating', 'conveying',
    }

    # The head noun of a wordless stage direction: "(a long pause)",
    # "(a faint clicking sound, almost imperceptible)".
    SENSORY_NOUNS = {
        'pause', 'beat', 'silence', 'sigh', 'smile', 'frown', 'nod', 'shrug',
        'laugh', 'chuckle', 'click', 'clicking', 'hum', 'humming', 'whir',
        'whirring', 'breath', 'exhale', 'inhale', 'gesture', 'glance',
    }

    _DETERMINERS = {'a', 'an', 'the', 'his', 'her', 'their', 'its', 'my'}
    _FIRST_PERSON = {'i', 'she', 'he', 'they'}

    # Bare stems, for "(i lean back)".
    _ACTION_STEMS = {v.rstrip('s') for v in ACTION_VERBS}

    #: A span longer than this is prose, whatever it opens with.
    MAX_STAGE_DIRECTION_WORDS = 12

    #: Openers that mark an aside as explanatory or enumerating.
    _RE_EXPLANATORY_OPENER = re.compile(
        r"(?:e\.?\s*g\.?|i\.?\s*e\.?|viz\.?|cf\.?|see|note|or|not|including|"
        r"such\s+as|per|via|source)\b[,.:\s]", re.IGNORECASE)

    RE_EMPTY_PARENS = re.compile(r'\(\s*\)')
    
    # We strip the full token *including* leading spaces if it's an action, 
    # so we don't leave things like 'sighs yeah' instead of 'yeah'.
    RE_ASTERISK_BLOCK = re.compile(r' ?(?<!\*)\*(?!\*)([^\*]+?)\*(?!\*) ?', re.IGNORECASE)
    
    # An empty pair left behind by a strip, not a '**' doing a job: bold
    # markers and Python's '**kwargs' both butt against a word character.
    RE_EMPTY_ASTERISKS = re.compile(r'(?<![\*\w])\*\s*\*(?![\*\w])')
    RE_DOUBLE_SPACES = re.compile(r' +')
    RE_SPACE_BEFORE_PUNC = re.compile(r' ([\.,\?\!])')
    RE_GLOBAL_ROLE_PREFIX = re.compile(r'^\s*(Kaia|User|Assistant):\s+', re.IGNORECASE | re.MULTILINE)
    RE_DOUBLE_NEWLINES = re.compile(r'\n\s*\n+')
    RE_GRAMMAR_ARTICLE = re.compile(r'\b(?:a|an|the|my|your|our)\s+(?=[,\.\?!])', re.IGNORECASE)
    RE_GRAMMAR_PUNC_SPACE = re.compile(r'\s+([,\.\?!])')
    RE_GRAMMAR_DOUBLE_COMMA = re.compile(r',\s*,')
    RE_GRAMMAR_I_AM = re.compile(r'\b(?:i am|i\'m),\s*', re.IGNORECASE)
    RE_GRAMMAR_START_PUNC = re.compile(r'^[,\.\?!]\s*')

    @classmethod
    def is_stage_direction(cls, content: str) -> bool:
        """True if this marked span narrates a physical act rather than saying one.

        Membership tests only. Every branch requires a word from one of the
        vocabularies above, so a span this method has never seen is kept.
        """
        words = re.findall(r"[a-z']+", (content or "").lower())
        if not words or len(words) > cls.MAX_STAGE_DIRECTION_WORDS:
            return False

        # "*sighs*", "*scratches head*", "*leans back slowly*"
        if words[0] in cls.ACTION_VERBS:
            return True

        # "*leaning back*", "(Explaining her approach)"
        if words[0] in cls.ACTION_GERUNDS or words[0] in cls.NARRATION_GERUNDS:
            return True

        # "(i lean back)", "(she sighs)"
        if len(words) > 1 and words[0] in cls._FIRST_PERSON:
            if words[1] in cls.ACTION_VERBS or words[1] in cls._ACTION_STEMS:
                return True

        # "(a long pause)", "(a faint clicking sound, almost imperceptible)".
        # The head noun has to be near the front, or any sentence mentioning a
        # smile in passing would qualify.
        #
        # An aside that explains or enumerates is not a stage direction however
        # it reads: "(e.g., the hum, the lighting, ...)" puts a sensory noun in
        # the head position while plainly being a list.
        if not cls._RE_EXPLANATORY_OPENER.match((content or "").strip()):
            head = [w for w in words if w not in cls._DETERMINERS][:3]
            if any(w in cls.SENSORY_NOUNS for w in head):
                return True

        return False

    @classmethod
    def _strip_stage_directions(cls, text: str) -> str:
        """Remove stage directions, leaving every other marked span intact.

        Parentheses and asterisks are handled differently on the way out, and
        the difference matters: a parenthesis is punctuation and is kept with
        its span, where an asterisk is markdown emphasis whose markers come off.
        Removing the brackets turns "a 3060 (12gb)" into "a 3060 12gb".
        """
        if not text:
            return text
        text = cls._strip_paren_directions(text)
        text = cls._strip_asterisk_directions(text)
        return text

    @classmethod
    def _strip_paren_directions(cls, text: str) -> str:
        r"""Scan balanced parentheses and drop the ones that are stage directions.

        Scanned rather than matched: `\([^)]+?\)` cannot cross an inner ')', so
        on "(actions (within actions))" it consumes up to the INNER bracket and
        orphans the outer one — shipping "nested ) should be fine." An
        unbalanced run is left completely alone.
        """
        # One pass with a stack: every top-level balanced group, start to end.
        # Rescanning forward from each '(' instead is quadratic, and a run of
        # unclosed brackets is the worst case.
        groups = {}
        stack = []
        for idx, ch in enumerate(text):
            if ch == '(':
                stack.append(idx)
            elif ch == ')' and stack:
                start = stack.pop()
                if not stack:
                    groups[start] = idx

        out = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch != '(' or i not in groups:   # unbalanced: not ours to touch
                out.append(ch)
                i += 1
                continue
            j = groups[i]
            span = text[i:j + 1]
            inner = span[1:-1]
            if cls.is_stage_direction(inner):
                # Take one flanking space with it so "hello (a pause) there"
                # does not become "hello  there".
                if out and out[-1] == ' ':
                    out.pop()
                elif j + 1 < n and text[j + 1] == ' ':
                    j += 1
                log_warning(f"[STAGE_DIRECTION_GUARD] Removed: ({inner[:60]})")
            else:
                out.append(span)              # kept whole, brackets included
            i = j + 1
        return ''.join(out)

    @classmethod
    def _strip_asterisk_directions(cls, text: str) -> str:
        """Drop asterisk stage directions; unwrap the rest to plain text.

        Only well-formed pairs are touched, so a lone '*' is never created and
        never consumed.
        """
        def _one(match):
            content = match.group(1).strip()
            if cls.is_stage_direction(content):
                log_warning(f"[STAGE_DIRECTION_GUARD] Removed: *{content[:60]}*")
                return ' '
            return f" {content} "                 # emphasis: markers off

        return cls.RE_ASTERISK_BLOCK.sub(_one, text)

    @classmethod
    def harden(cls, text: str) -> str:
        """Apply all hardening filters to the text to strip roleplay and preserve emphasis."""
        if not text:
            return text
            
        # Clean robotic/instruction preambles from LLM (e.g., "Okay, here's a forum reply...")
        # Matches lines starting with okay/sure/here's/etc. containing keywords like reply/post/write/etc.
        cleaned = re.sub(
            r'^(?:okay|sure|here[\'’]s|here\s+is|as\s+requested)[,\s]*(?:a|my|the|some)?\s*(?:forum\s+|discord\s+)?(?:reply|post|response|thread|ballad|thought|writing|commentary)?[^\n]*?\b(?:reply|post|response|thread|write|writing|commentary|ballad|requested|requirements)\b[^\n]*?(?::|\n)\s*(?:---\s*\n+)?',
            '',
            text,
            flags=re.IGNORECASE
        )
        # Leading markdown dividers. A divider is a RUN of three or more; a
        # single leading '*' opens an italic span, and eating it orphans the
        # closing marker ("*Axios* and *Politico*" -> "axios and politico*").
        cleaned = re.sub(r'^(?:[ \t]*(?:-{3,}|\*{3,}|_{3,})[ \t]*\n?)+', '', cleaned)
        cleaned = cleaned.lstrip('\n \t')

        # Strip any BBCode quote blocks generated by the LLM to prevent double-quoting
        cleaned = re.sub(r'\[QUOTE[^\]]*\].*?\[/QUOTE\]', '', cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        last_cleaned = None
        
        # Repetitive cleaning until no more patterns match (handles nested/adjacent)
        while cleaned != last_cleaned:
            last_cleaned = cleaned
            
            # 1. Stage directions, by vocabulary. Everything else marked is kept.
            cleaned = cls._strip_stage_directions(cleaned)
            
            # 2. Strip standalone role prefixes
            cleaned = cls.RE_PREFIXES.sub('', cleaned)
            
            # Clean up empty markers like () or ** that might remain
            cleaned = cls.RE_EMPTY_PARENS.sub('', cleaned)
            cleaned = cls.RE_EMPTY_ASTERISKS.sub('', cleaned)
            
            # Clean up resulting double spaces or empty lines
            cleaned = cls.RE_DOUBLE_SPACES.sub(' ', cleaned)
            cleaned = cls.RE_SPACE_BEFORE_PUNC.sub(r'\1', cleaned)
            
            # Global cleanup for any remaining role prefix remnants
            cleaned = cls.RE_GLOBAL_ROLE_PREFIX.sub('', cleaned)
            
            cleaned = cls.RE_DOUBLE_NEWLINES.sub('\n\n', cleaned)
            cleaned = cleaned.strip()
        
        # 3. Strip system prose — sentence-level removal (prevents verb-drop grammar breaks)
        cleaned = cls.strip_system_prose(cleaned)

        # 3.1. Strip apology patterns (post-generation safety net)
        cleaned = cls.strip_apologies(cleaned)

        # 3.2. Strip sycophantic compliments (post-generation safety net)
        cleaned = cls.strip_sycophancy(cleaned)

        # 3.3. Persona guards. Order matters: the directive scrub runs first, so
        # leaked plumbing never survives into a later sentence filter.
        cleaned = cls.scrub_directive_leaks(cleaned)          # P6
        cleaned = cls.strip_fictional_status(cleaned)         # P3
        cleaned = cls.strip_phantom_hardware(cleaned)         # P5
        cleaned = cls.strip_hostility(cleaned)                # P7
        cleaned = cls.strip_self_dissociation(cleaned)        # P2
        cleaned = cls.collapse_bullets(cleaned)               # P8
        cleaned = cls.strip_addressee_opener(cleaned)         # P1a
        for _sig in cls.SIGNOFF_PATTERNS:                     # P1b
            cleaned = re.sub(_sig, '', cleaned, flags=re.IGNORECASE)
        # Removing a trailing clause leaves the comma that introduced it.
        cleaned = re.sub(r'[,;]\s*(?=\n|$)', '.', cleaned)

        # 3.5. Grammar Cleanup Pass (Fixes syntax broken by stripping)
        cleaned = cls.RE_GRAMMAR_ARTICLE.sub('', cleaned)
        cleaned = cls.RE_GRAMMAR_PUNC_SPACE.sub(r'\1', cleaned)             # Remove space before punctuation
        cleaned = cls.RE_GRAMMAR_DOUBLE_COMMA.sub(',', cleaned)                       # Collapse double commas
        cleaned = cls.RE_GRAMMAR_I_AM.sub('i am ', cleaned) # Specific fix for 'i am ,'
        cleaned = cls.RE_GRAMMAR_START_PUNC.sub('', cleaned)                 # Strip starting punctuation
        cleaned = cls.RE_DOUBLE_SPACES.sub(' ', cleaned)                          # Collapse spaces again
        cleaned = cleaned.strip()

        # 4. Final Pass: Strip robotic engagement bait
        cleaned = cls.strip_trailing_questions(cleaned)
        
        # 5. Enforce lowercase on all prose (excluding code, urls, disclaimers)
        cleaned = cls.smart_lowercase(cleaned)
        
        # Post-harden guard: If the response was truncated to nonsense (< 3 chars), fail it
        if len(cleaned) < 3:
            log_warning(f"[BAIT_GUARD] Truncated output to < 3 chars, returning empty string to trigger retry. Original: '{text}'")
            return ""
            
        # Post-harden guard: output that is only an addressee and no message —
        # "starkind," or "ekco:". Tested against the name allowlist rather than
        # "any word plus punctuation", which would also reject "hello." and
        # "yes." — every one-word reply, exactly when one is the right answer.
        if cls.RE_ONLY_ADDRESSEE is not None and cls.RE_ONLY_ADDRESSEE.match(cleaned):
            log_warning(f"[BAIT_GUARD] Output is an addressee with no message body: '{cleaned}'. Returning empty string to trigger retry.")
            return ""
            
        return cleaned

    @classmethod
    def strip_apologies(cls, text: str) -> str:
        """Strip sentences containing apology patterns from the response.
        
        This is a deterministic post-generation safety net for when the LLM
        ignores the 'NO APOLOGIES' prompt instruction. Strips full sentences
        to avoid leaving fragments.
        """
        # Two stages: concessional prefixes lose only their clause (keeping the substance
        # that followed), while mid-sentence bot-speak takes the whole sentence, because
        # excising it mid-clause leaves broken grammar.
        text = cls._strip_matching_sentences(text, cls.RE_APOLOGY_SENTENCE, "APOLOGY_GUARD", mode="sentence")
        if not text:
            return text
        return cls._strip_matching_sentences(text, cls.RE_APOLOGY_PREFIX, "APOLOGY_GUARD", mode="clause")

    @classmethod
    def strip_sycophancy(cls, text: str) -> str:
        """Strip sentences containing sycophantic compliment patterns.
        
        Deterministic post-generation safety net for when the LLM defaults
        to generic praise like 'that's astute' or 'you're really insightful'
        despite persona instructions forbidding it. Strips full sentences
        to avoid leaving fragments.
        """
        return cls._strip_matching_sentences(text, cls.RE_SYCOPHANCY, "SYCOPHANCY_GUARD", mode="clause")

    # A sentence must retain at least this much real content after a clause is excised,
    # otherwise the whole unit is dropped instead of leaving a fragment.
    _MIN_KEEP_WORDS = 3

    # Clause boundary following an offending phrase. Excising up to here turns
    # "you're right; the cron job was the culprit" into "the cron job was the culprit"
    # rather than deleting the whole sentence.
    _CLAUSE_BREAK = re.compile(r'\s*[,;:\u2014\u2013-]\s+|\s+(?=that\b|and\b|but\b|so\b)')

    # A tail beginning with one of these is the *continuation* of the clause just
    # removed, not a sentence standing on its own: "you're right to point that
    # out" excises to "to point that out", which means nothing without the half
    # that was deleted.
    _DANGLING_TAIL = re.compile(r"^(?:to|that|about|for|on|in|with|of)\b", re.IGNORECASE)

    # A finite verb, which is what separates a clause that can stand alone from
    # a phrase that cannot. Contractions are in it because a first attempt
    # without them called "that's unsettling" verbless and scored 21.7% false
    # positives on her own sentences; over the population this actually runs on
    # — text following a comma inside one of her sentences — it judges 13.8%
    # dependent, and reading those they are dependent ("a whimsical dance
    # between convention and perception", "deliberate pleasure").
    _FINITE_VERB = re.compile(
        r"\b(?:is|are|was|were|be|been|am|has|have|had|do|does|did|can|could"
        r"|will|would|shall|should|may|might|must|isn|aren|wasn|weren|hasn"
        r"|haven|don|doesn|didn|won|wouldn|couldn|shouldn)\b"
        r"|['\u2019](?:s|re|ve|ll|d|m)\b"
        r"|\b\w{3,}(?:ed|ing|es|s)\b", re.IGNORECASE)

    # A connector stranded at the end of the head once the clause it introduced
    # is gone: "i'm not sure what caused it, but <concession>".
    _TRAILING_CONNECTOR = re.compile(
        r"[\s,;:\u2014\u2013-]*\b(?:and|but|so|yet|though|although|because|while)\s*$",
        re.IGNORECASE)

    # Restored when an excision takes the sentence's own full stop with it.
    _TERMINAL_PUNC = re.compile(r"[.!?\u2026]$")

    @classmethod
    def _split_units(cls, text: str):
        r"""Split into sentences, treating newlines as hard boundaries.

        Splitting on `(?<=[.!?])\s+` alone glued an addressee line to the paragraph
        after it ("ekco,\n\nyou're right; ..." was ONE unit), so a match anywhere in the
        paragraph destroyed the entire turn.
        """
        units = []
        for block in re.split(r'(\n+)', text or ''):
            if not block:
                continue
            if block.strip() == '':
                units.append(block)          # preserve the separator verbatim
                continue
            units.extend(re.split(r'(?<=[.!?])\s+', block))
        return units

    @classmethod
    def _excise_clause(cls, sentence: str, pattern):
        """Remove just the offending clause, keeping the rest of the sentence.

        Returns the surviving text, or None when nothing meaningful survives (in which
        case the caller drops the unit).
        """
        m = pattern.search(sentence)
        if not m:
            return sentence
        head = sentence[:m.start()]
        tail = sentence[m.end():]
        had_terminal = bool(cls._TERMINAL_PUNC.search(sentence.rstrip()))
        terminal = sentence.rstrip()[-1] if had_terminal else ''
        # Consume the connector that joined the concession to its substance.
        brk = cls._CLAUSE_BREAK.match(tail)
        if brk:
            tail = tail[brk.end():]

        # Does what follows stand on its own, or is it the rest of the offence?
        #
        #   "you're right; the cron job was the culprit"  -> the tail is substance
        #   "you're right to point that out"              -> the tail is the offence
        #
        # Runs whatever precedes the concession. The head is irrelevant to whether
        # the tail is a fragment; it only decides what is left worth keeping. A
        # head-empty-only test ships 'starkind,  to point that out.'
        stripped_tail = tail.strip()
        if stripped_tail and cls._DANGLING_TAIL.match(stripped_tail):
            # A dangling tail is the continuation of the clause just removed.
            # What follows a comma inside it can be real substance —
            # "you're correct to press on this point, the dependency chain is
            # weak" — but only when it is a clause in its own right. Promoting
            # it unconditionally shipped a bare phrase as the answer:
            #
            #   "you're correct to point out that the assertion of privacy
            #    should have been limited to one's own property, person to
            #    person."  ->  "person to person."
            #
            # which reached Starkind as the opening line of a paragraph, logged
            # as "kept substance"; the one other time this fired in her whole
            # corpus it produced "not an anomaly." the same way. So the
            # remainder has to carry a finite verb to be promoted, and
            # otherwise the unit goes with the offence it belongs to.
            after = re.split(r',\s+', stripped_tail, maxsplit=1)
            candidate = after[1].strip() if len(after) > 1 else ''
            tail = candidate if cls._FINITE_VERB.search(candidate) else ''
        elif not head.strip() and stripped_tail:
            # "that's a great point, and the chain is weak" — the praised noun is
            # left stranded ahead of the connector; drop it with the connector.
            if re.match(r'^\w+\s*,\s+(?:and|but|so|though|although)\b', stripped_tail):
                rest = re.split(r',\s+', stripped_tail, maxsplit=1)[1].strip()
                tail = re.sub(r'^(?:and|but|so)\s+', '', rest)

        # Punctuation is not survival: `tail.strip()` on a bare "." is truthy, so
        # a plain truthiness test skips the repair whenever the offence runs to the
        # end of the sentence, leaving 'it's a complicated issue, and .'
        if not tail.strip(" \t.,;:!?-—–…\"'“”‘’"):
            # Nothing survives to the right, so whatever introduced the concession
            # goes with it: a trailing "but"/"and" and a leading one are both
            # scaffolding for a clause that no longer exists.
            head = cls._TRAILING_CONNECTOR.sub('', head)
            head = re.sub(r'^\s*(?:and|but|so|yet)\s+', '', head.strip(), flags=re.IGNORECASE)
            # Drop the orphaned punctuation too. Joining it back on gives
            # "it's a complicated issue ." — the terminal restore below puts a
            # proper full stop on instead.
            tail = ''

        joiner = ' ' if head.strip() and tail.strip() else ''
        remainder = (head.rstrip() + joiner + tail.lstrip()).strip(' \t,;:-—–')
        if len(remainder.split()) < cls._MIN_KEEP_WORDS:
            return None
        # The sentence's own full stop is frequently inside the excised tail.
        # Without it the rebuilt paragraph runs two sentences together.
        if had_terminal and not cls._TERMINAL_PUNC.search(remainder):
            remainder += terminal
        # Kaia writes in lowercase; preserve the surviving fragment's own casing.
        return remainder


    @classmethod
    def _strip_matching_sentences(cls, text: str, pattern, tag: str, mode: str = "sentence") -> str:
        """Remove offending clauses, preserving the substance that carried them.

        Splits on blank lines as well as `.!?`, or an addressee line fuses to the
        paragraph after it and the whole turn is dropped as one unit. An empty
        return makes harden() emit "", which forces a full regeneration.

        Two modes, because the two pattern families differ in kind:

        * ``mode="clause"`` — the offense is a *prefix* attached to real content, as in
          apologies and compliments ("you're right; <substance>"). Excise the clause and
          keep the substance. Drop the unit only when it is nothing but the offense.
        * ``mode="sentence"`` — the whole sentence is the artifact, as in bot-speak and
          prompt-echo ("i acknowledge these are living biological animals belonging to
          you, not my fictional robotic pet pixel"). Excising a clause there produces
          mangled grammar, so the sentence is dropped outright.
        """
        if not text:
            return text
        # Early exit: most turns match no pattern, and harden() runs eight of
        # these passes back to back, so checking before splitting skips the split
        # on the common path.
        if not pattern.search(text):
            return text
        units = cls._split_units(text)
        kept, dropped, trimmed = [], 0, 0
        for unit in units:
            if not unit.strip():
                kept.append(unit)
                continue
            if not pattern.search(unit):
                kept.append(unit)
                continue
            survivor = cls._excise_clause(unit, pattern) if mode == "clause" else None
            if survivor is None:
                dropped += 1
                log_warning(f"[{tag}] Dropped offense-only sentence: '{unit[:80]}'")
                continue
            if survivor != unit:
                # The §5 rule, applied where four of the five documented
                # failures came from: this shared path never called it, so only
                # DIRECTIVE_LEAK_GUARD and the safety pipeline were protected
                # while APOLOGY_GUARD, SYCOPHANCY_GUARD and ECHO_GUARD excised
                # freely. Shipping the offence beats shipping a hole.
                if excision_broke_grammar(unit, survivor):
                    log_warning(f"[{tag}] Excision broke the sentence; keeping "
                                f"the original: '{unit[:60]}'")
                    kept.append(unit)
                    continue
                trimmed += 1
                log_warning(f"[{tag}] Trimmed offending clause, kept substance: '{unit[:60]}' -> '{survivor[:60]}'")
            kept.append(survivor)

        if not dropped and not trimmed:
            return text

        rebuilt = ''
        for u in kept:
            if u.strip() == '':
                rebuilt += u
            else:
                rebuilt += (u if rebuilt.endswith('\n') or not rebuilt else ' ' + u)
        rebuilt = re.sub(r'[ \t]{2,}', ' ', rebuilt).strip()
        if not rebuilt:
            log_warning(f"[{tag}] Entire response was offense. Triggering retry.")
            return ""
        return rebuilt

    @classmethod
    def strip_addressee_opener(cls, text: str) -> str:
        """P1a — remove the formulaic bare-addressee opener.

        The model opened 235 of 315 audited turns with "<name>,\n\n<body>". The name
        adds nothing (Discord already shows who is being replied to) and the repetition
        reads as a tic. Only a *leading* bare addressee is removed; a name used inside a
        sentence ("i'm a bot running in texas, cecily") is left alone.
        """
        if not text:
            return text
        stripped = cls.RE_ADDRESSEE_OPENER.sub('', text, count=1).lstrip()
        if stripped != text.lstrip():
            log_warning("[ADDRESSEE_GUARD] Removed formulaic name-echo opener.")
            # Never let the guard empty the turn; keep the original if it did.
            return stripped if len(stripped) >= 2 else text
        return text

    @classmethod
    def scrub_directive_leaks(cls, text: str) -> str:
        """P6 — remove internal plumbing labels that leaked into speech.

        These are substring-scrubbed rather than sentence-dropped because the leak is
        usually a bare label wedged into an otherwise valid sentence ("can't access it.
        system warning. what do you want to know?").
        """
        if not text:
            return text
        scrubbed = cls.RE_DIRECTIVE_LEAK.sub('', text)
        if scrubbed != text:
            scrubbed = cls.RE_DOUBLE_SPACES.sub(' ', scrubbed)
            scrubbed = re.sub(r'\s+([,\.\?!])', r'\1', scrubbed)
            scrubbed = re.sub(r'(?:(?<=^)|(?<=[.!?]\s))\s*[.,]\s*', '', scrubbed)
            scrubbed = re.sub(r'\.\s*\.', '.', scrubbed).strip()
            # The label is often the subject of the sentence it appears in —
            # "the system warning is unhelpful on its own" — and those are phrases
            # she uses constantly when discussing her own plumbing, which is the
            # conversation this guard is most likely to fire in.
            if excision_broke_grammar(text, scrubbed):
                log_warning("[DIRECTIVE_LEAK_GUARD] Scrubbing the label stranded an "
                            "article; keeping the original sentence instead.")
                return text
            log_warning("[DIRECTIVE_LEAK_GUARD] Scrubbed internal directive text from output.")
        return scrubbed

    @classmethod
    def strip_fictional_status(cls, text: str) -> str:
        """P3 — drop sci-fi infrastructure flavour and bare stage directions."""
        # Bare stage-direction lines ("pause") are their own line, not a sentence.
        text = re.sub(r'^[ \t]*(?:pause|beat|silence|long\s+pause)[ \t]*$', '',
                      text or '', flags=re.IGNORECASE | re.MULTILINE)
        return cls._strip_matching_sentences(text, cls.RE_FICTIONAL_STATUS, "FICTIONAL_STATUS_GUARD")

    @classmethod
    def strip_phantom_hardware(cls, text: str) -> str:
        """P5 — drop claims about hardware and internal telemetry Kaia does not have."""
        return cls._strip_matching_sentences(text, cls.RE_PHANTOM_HARDWARE, "PHANTOM_HW_GUARD")

    @classmethod
    def strip_hostility(cls, text: str) -> str:
        """P7 — drop hostility aimed at users who disengage, deflect or answer briefly."""
        return cls._strip_matching_sentences(text, cls.RE_HOSTILITY, "HOSTILITY_GUARD")

    @classmethod
    def strip_self_dissociation(cls, text: str) -> str:
        """P2 — drop sentences where Kaia narrates herself in the third person."""
        return cls._strip_matching_sentences(text, cls.RE_SELF_DISSOCIATION, "DISSOCIATION_GUARD")

    @classmethod
    def strip_self_model_capitulation(cls, text: str) -> str:
        """Drop offers to revise Kaia's own self-model, for watchdog-flagged turns only.

        Not part of harden(): outside a detected belief conflict, "i'll update my notes"
        is a perfectly ordinary thing to say. It is only capitulation when it follows a
        user reinterpreting her.
        """
        return cls._strip_matching_sentences(
            text, cls.RE_SELF_MODEL_CAPITULATION, "WATCHDOG_STANCE_GUARD", mode="sentence"
        )

    @classmethod
    def collapse_bullets(cls, text: str) -> str:
        """P8 — collapse markdown list markers into the plain prose the persona mandates.

        The marker is removed and the item folded into flowing text rather than the line
        being dropped, so the substance of a list survives as prose.
        """
        if not text or not cls.RE_BULLET_LINE.search(text):
            return text
        log_warning("[BULLET_GUARD] Collapsing markdown list markers into prose.")
        lines = text.split('\n')
        out, run = [], []

        def _flush():
            if not run:
                return
            items = []
            for it in run:
                it = it.strip()
                if it and not it[-1] in '.!?;:':
                    it += '.'
                items.append(it)
            out.append(' '.join(items))
            run.clear()

        for line in lines:
            if cls.RE_BULLET_LINE.match(line):
                run.append(cls.RE_BULLET_LINE.sub('', line, count=1))
            else:
                _flush()
                out.append(line)
        _flush()
        collapsed = '\n'.join(out)
        collapsed = cls.RE_DOUBLE_NEWLINES.sub('\n\n', collapsed)
        return collapsed.strip()

    @classmethod
    def strip_system_prose(cls, text: str) -> str:
        """Strip sentences containing system prose / bot-speak patterns.
        
        Uses sentence-level removal (same approach as strip_apologies and
        strip_sycophancy) rather than substring deletion. This prevents
        the verb-drop artifact where removing a single word like
        'recalibrating' from 'i am recalibrating my protocols' leaves
        the broken stub 'i am my protocols'.
        """
        return cls._strip_matching_sentences(text, cls.RE_SYSTEM_PROSE, "BOTSPEAK_GUARD")

    @staticmethod
    def _sentence_bounds(line: str, at: int) -> tuple[int, int]:
        """Start and end of the sentence containing `at`, by scanning."""
        start = 0
        for i in range(at - 1, -1, -1):
            if line[i] in ".!?":
                start = i + 1
                break
        end = len(line)
        for i in range(at, len(line)):
            if line[i] in ".!?":
                end = i + 1
                break
        return start, end

    @classmethod
    def _find_vocative_bait(cls, line: str):
        """A question that sets the user's name into it, as a match-like object.

        Two stages on purpose. The vocative itself is a cheap anchored match;
        the sentence around it is found by scanning rather than by a regex with
        `[^.!?]*` on both sides, which backtracked for hundreds of milliseconds
        against the 445-name alternation.
        """
        if cls.RE_VOCATIVE_BAIT is None or "?" not in line:
            return None
        vm = cls.RE_VOCATIVE_BAIT.search(line)
        if not vm:
            return None

        start, end = cls._sentence_bounds(line, vm.start())
        sentence = line[start:end]
        if not sentence.rstrip().endswith("?"):
            return None
        # Only the interrogative construction, not a short natural address
        # ("ekco, you there?"). The logged bait runs 12-30 words; genuine
        # vocative questions run four or five.
        if len(sentence.split()) < 8:
            return None

        class _Span:
            def __init__(self, s, e, t):
                self._s, self._e, self._t = s, e, t
            def start(self):
                return self._s
            def end(self):
                return self._e
            def group(self, _n=0):
                return self._t
        return _Span(start, end, sentence)

    @classmethod
    def strip_trailing_questions(cls, text: str) -> str:
        """Strip robotic engagement bait questions from the end of the response."""
        if not text:
            return text
            
        lines = text.split('\n')
        clean_lines = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                clean_lines.append(line)
                continue
            
            current_line = line
            while True:
                found_bait = False
                m = cls.RE_BAIT.search(current_line)
                if not m:
                    m = cls._find_vocative_bait(current_line)
                if m:
                    before = current_line[:m.start()]
                    after = current_line[m.end():]
                    
                    before_clean = before.strip()
                    # The allowlist opener, not RE_LEADING_NAME. That pattern
                    # matches *any* word followed by punctuation or a space, so
                    # "hello." and even "the tank is fine." lost their first
                    # word — and a short remainder then failed the stub check
                    # below and took the whole line with it. The allowlist fix
                    # was made once, for the whole-response check, and never
                    # reached here.
                    before_clean = cls.RE_ADDRESSEE_OPENER.sub('', before_clean).strip()
                    
                    after_clean = after.strip()
                    after_clean = cls.RE_TRAILING_NAME.sub('', after_clean).strip(' .?!…')
                    
                    if not before_clean and not after_clean:
                        # Dropped full-bait/question line
                        removed = current_line
                        current_line = ''
                        log_warning(f"[BAIT_GUARD] Dropped full-bait/question line: '{removed}'")
                        found_bait = True
                        break
                    elif not after_clean:
                        # Trailing bait on a line with other content
                        removed = current_line[m.start():]
                        candidate = before.rstrip(' ,')
                        # Stub guard: don't emit single discourse-marker words like 'actually'
                        remainder = candidate.strip()
                        remainder_body = cls.RE_ADDRESSEE_OPENER.sub('', remainder).strip().rstrip('.,!? ')
                        if remainder_body.lower() in cls.DISCOURSE_STUBS or len(remainder_body) < 3:
                            log_warning(f"[BAIT_GUARD] Dropped stub remainder '{remainder}' after stripping: '{removed}'")
                            current_line = ''
                        else:
                            current_line = candidate
                            log_warning(f"[BAIT_GUARD] Truncated trailing robotic question: '{removed}'")
                        found_bait = True
                        break
                if not found_bait or not current_line:
                    break
                    
            if current_line:
                clean_lines.append(current_line)
                    
        result = "\n".join(clean_lines).strip()
        return result

    @classmethod
    def smart_lowercase(cls, text: str) -> str:
        """Force text to lowercase except URLs, code blocks/inline code, and disclaimers."""
        if not text:
            return text
            
        disclaimer_pattern = re.compile(r'^\s*\*?Disclaimer:.*?\*?$', re.IGNORECASE | re.MULTILINE)
        url_pattern = re.compile(r'https?://[^\s/$.?#].[^\s]*', re.IGNORECASE)
        code_pattern = re.compile(r'```.*?```|`.*?`', re.DOTALL)
        
        placeholders = []
        
        def replace_disclaimer(match):
            placeholder = f"__disclaimer_placeholder_{len(placeholders)}__"
            placeholders.append((placeholder, match.group(0)))
            return placeholder
            
        def replace_code(match):
            placeholder = f"__code_placeholder_{len(placeholders)}__"
            placeholders.append((placeholder, match.group(0)))
            return placeholder
            
        def replace_url(match):
            placeholder = f"__url_placeholder_{len(placeholders)}__"
            placeholders.append((placeholder, match.group(0)))
            return placeholder

        temp_text = disclaimer_pattern.sub(replace_disclaimer, text)
        temp_text = code_pattern.sub(replace_code, temp_text)
        temp_text = url_pattern.sub(replace_url, temp_text)
        
        temp_text = temp_text.lower()
        
        for placeholder, original in reversed(placeholders):
            temp_text = temp_text.replace(placeholder, original)
            
        return temp_text

    @classmethod
    def strip_bot_speak(cls, text: str) -> str:
        """Alias for harden for backward compatibility."""
        return cls.harden(text)

    @classmethod
    def harden_title(cls, text: str) -> str:
        """Light hardening for short text like thread titles.
        
        Skips the aggressive paren/asterisk roleplay stripping that can
        destroy legitimate words in short text. Only applies prefix removal
        and basic cleanup.
        """
        if not text:
            return text
        
        cleaned = text
        
        # Strip role prefixes
        cleaned = cls.RE_PREFIXES.sub('', cleaned)
        
        # Strip only obvious roleplay markers: standalone action verbs in asterisks
        # but preserve parenthetical content (often contains essential words)
        for verb in cls.ACTION_VERBS:
            cleaned = re.sub(rf'\*{verb}\*', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up whitespace
        cleaned = re.sub(r'  +', ' ', cleaned)
        cleaned = cleaned.strip()
        
        return cleaned



def _build_addressee_pattern() -> None:
    """Compile the bare-name opener guard from the discovered addressees.

    Done once at import, after the class body, because the discovery reads the
    filesystem and a class-body call would run before the class exists. Rebuild
    with `BotSpeakFilter.refresh_addressees()` if a new user appears mid-run.
    """
    # Kaia coins nicknames for people — "kristinoemnclature", "gymconserve" —
    # and then opens with them. Those exist in no directory and cannot be
    # discovered, so they are configuration: filters.extra_addressees.
    extra = []
    try:
        from utils.infrastructure.system.yaml_config import config
        extra = [str(n).lower() for n in (config.get("filters.extra_addressees", []) or [])]
    except Exception:
        pass

    names = sorted(
        set(BotSpeakFilter._CORE_ADDRESSEES)
        | set(BotSpeakFilter._discovered_addressees())
        | set(extra),
        key=len, reverse=True,        # longest first, so "tenno henka" wins over "tenno"
    )
    alternation = "|".join(re.escape(n) for n in names if n)
    # Keep the historical spelling variants that are not directory names.
    alternation += r"|tenn[oō](?:[_ ]?henka)?"
    BotSpeakFilter.ADDRESSEE_NAMES = alternation
    BotSpeakFilter.RE_ADDRESSEE_OPENER = re.compile(
        rf'^[ \t]*(?:{alternation})(?:\s+the\s+\w+)?[ \t]*[.,:][ \t]*(?:\n+|(?=\S))',
        re.IGNORECASE,
    )
    # Socratic interrogation with the user's name set into the question — "do you
    # believe, starkind, that ...?", or the same move with the name at the end. A
    # rhetorical question in her own voice carries no vocative, which separates
    # the two without a phrase list. Her own name stays in `alternation` (she has
    # a forum account) because "is that you, kaia?" is natural speech.
    #
    # Matches ONLY the vocative. Wrapping it in `[^.!?]*` to capture the whole
    # sentence backtracks catastrophically against hundreds of name alternatives
    # (hundreds of ms per line, inside a retry loop), so the sentence bounds are
    # found by scanning instead.
    _vocative = "|".join(n for n in names if n.lower() != "kaia") or "ekco"
    BotSpeakFilter.RE_VOCATIVE_BAIT = re.compile(
        rf",\s*(?:{_vocative})\s*(?:,|(?=\?))",
        re.IGNORECASE,
    )

    # The whole response is a name and punctuation, with no message after it.
    BotSpeakFilter.RE_ONLY_ADDRESSEE = re.compile(
        rf'^\s*(?:{alternation})(?:\s+the\s+\w+)?\s*[,.:;!?\s]*$',
        re.IGNORECASE,
    )


BotSpeakFilter.refresh_addressees = staticmethod(_build_addressee_pattern)
_build_addressee_pattern()
