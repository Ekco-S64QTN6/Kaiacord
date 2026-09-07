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
    @classmethod
    def filter_response(cls, response: str) -> Optional[str]:
        """Remove ANY contamination from response. If too much is removed, return None to trigger retry."""
        if not response:
            return None

        # Check for scattered ellipsis-affect spam (e.g. "it's...", "is...", "that's...")
        # Since this affects generation globally, we check the entire response
        # instead of line-by-line.
        #
        # ELLIPSIS matches either a single U+2026 or two-or-more ASCII dots.
        # The previous character class `[\u2026\.]{2,}` required TWO characters,
        # so a lone "…" — which is what gemma3 actually emits — never matched and
        # this guard fired on 0 of 2,163 logged responses. It was dead code.
        affect_spams = cls.RE_AFFECT_ELLIPSIS.findall(response)
        general_ellipses = cls.RE_ANY_ELLIPSIS.findall(response)

        # Thresholds measured against 2,163 logged Kaia responses: the copula
        # pattern at >=2 flags 0.18% and the catch-all at >=3 flags 0.05%, and
        # every flagged sample was genuine affect spam. The catch-all at >=2
        # would have flagged 0.65%, taking legitimate text ("projecting output
        # in three... two... one.") with it — and each rejection costs a full
        # regeneration, so the extra sensitivity is not worth the added latency.
        if len(affect_spams) >= 2 or len(general_ellipses) >= 3:
            log_warning(f"[VERACITY GUARD] Too much ellipsis-affect spam (common: {len(affect_spams)}, total: {len(general_ellipses)}). Triggering full retry.")
            return None

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
    
    
class BotSpeakFilter:
    """
    Minimal filter to catch only the most egregious system leaks.
    Most behavioral constraints should be handled by the Persona prompt.
    """
    
    # Strip roleplay actions only — targeted patterns to avoid legitimate content
    RE_PARENS = re.compile(r'\((?![0-9]{4})([^\)]+?)\)', re.IGNORECASE)
    RE_ASTERISKS = re.compile(r'(?<!\*)\*(?!\*)([^\*]+?)\*(?!\*)', re.IGNORECASE)
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
    
    # Apology patterns that the LLM frequently ignores from prompt instructions.
    # These are stripped deterministically as a post-generation safety net.
    # Concessional PREFIXES. These lead a sentence and are followed by real content
    # ("you're right; the cron job was the culprit"), so they are excised as a clause and
    # the substance is kept.
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
    # Sept 1-5 2026 persona audit: structural guards for the eight
    # generation-layer failure patterns found in the interaction logs.
    # ------------------------------------------------------------------

    # Addressees Kaia speaks to. Used by the name-echo and dissociation guards.
    ADDRESSEE_NAMES = (
        r"ekco|ecko|starkind|cecily|jimjam|guardngnowm|tenn[o\u014d](?:[_ ]?henka)?"
        r"|lune|toxigen|milla"
    )

    # P1a — formulaic bare-addressee opener ("ekco,\n\n<body>"). The name carries no
    # information; it is a tic the model falls into on nearly every turn.
    #
    # The separator class was [,:] — comma or colon only. Measured across 250
    # turns from Sept 4-6 the model had moved to a full stop ("starkind. ..."),
    # 39 uses against 19 comma, so the dominant form went unmatched and 22.4% of
    # turns still opened with a bare name. Adding '.' is safe because
    # ADDRESSEE_NAMES is an explicit allowlist: an ordinary sentence opening
    # "yes." or "right." cannot match it.
    RE_ADDRESSEE_OPENER = re.compile(
        rf'^[ \t]*(?:{ADDRESSEE_NAMES})[ \t]*[.,:][ \t]*(?:\n+|(?=\S))',
        re.IGNORECASE
    )

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
    DIRECTIVE_LEAK_PATTERNS = [
        r"\[?\s*system\s+warning\s*:?\s*\]?",
        r"\[?\s*core[_ ]directive\s*:?\s*\]?",
        r"\bcould\s+not\s+be\s+scraped\b",
        r"\bdo\s+not\s+pretend\s+to\s+have\s+read\b",
        r"\bhallucinate\s+their\s+details\b",
        r"\bsafeguard[_ ]block\b",
        r"\brecorded_knowledge\b",
        r"\bobs[_ ]digest\b",
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

    # P2 — third-person dissociation. Either Kaia narrating herself from outside, or
    # (the log-observed failure) mirroring a user who writes about themselves in the
    # third person, so she talks *about* the person she is talking *to*.
    # Only Kaia narrating *herself* by name. The generic-noun form ("the model is...",
    # "the code is...", "the system is...") was removed after review: those are ordinary
    # technical subjects Kaia discusses constantly ("the model is gemma3 12b running on
    # ollama", "the system is designed to fail closed"), and sentence-mode stripping was
    # deleting the substantive answer outright. The persona SECOND PERSON rule covers the
    # rest, and the Sept log audit found zero self-third-person instances, so this guard
    # is a backstop and must not be destructive.
    RE_SELF_DISSOCIATION = re.compile(
        r"\bkaia\s+(?:is|was|has|will|does|feels|thinks|seems|remains|acknowledges)\b"
        r"|\bthis\s+unit\s+(?:is|was|has|will|does)\b",
        re.IGNORECASE
    )

    # Self-model capitulation: agreeing to REVISE her own identity, description or
    # workspace because a user offered a theory about it. This is the residue the Aug 13
    # incident left after praise was stripped ("...i'll revise the prompt"), and no other
    # guard catches it, because on its face it is an ordinary cooperative sentence.
    # Only applied when the consistency watchdog has flagged a belief conflict.
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
        # --- Sept 2026 audit: structural capitulation the earlier two patterns missed. ---
        # "your interpretation is astute", "your insights are proving invaluable",
        # "your framing is compelling" — praise attached to the user's *analysis* rather
        # than to the user, which is how the Aug 13 capitulation incident was phrased.
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

    
    ACTION_VERBS = {
        'nods', 'sighs', 'grins', 'smiles', 'laughs', 'pauses', 'frowns', 'shrugs', 
        'blinks', 'tilts', 'leans', 'taps', 'looks', 'waves', 'winks', 'checks', 
        'points', 'whispers', 'mumbles', 'groans', 'hisses', 'pouts', 'scoffs',
        'types', 'adjusts', 'swallows', 'stares', 'recalibrates', 'processes'
    }

    RE_EMPTY_PARENS = re.compile(r'\(\s*\)')
    
    # We strip the full token *including* leading spaces if it's an action, 
    # so we don't leave things like 'sighs yeah' instead of 'yeah'.
    RE_ASTERISK_BLOCK = re.compile(r' ?(?<!\*)\*(?!\*)([^\*]+?)\*(?!\*) ?', re.IGNORECASE)
    RE_PAREN_BLOCK = re.compile(r' ?\((?![0-9]{4})([^\)]+?)\) ?', re.IGNORECASE)
    
    RE_EMPTY_ASTERISKS = re.compile(r'(?<!\*)\*\s*\*(?!\*)')
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
    def _selective_strip(cls, match):
        """Callback to strip markers and decide if content is an action or emphasis."""
        content = match.group(1).strip()
        clean_content = content.lower().rstrip('.?!… ')
        
        # Heuristic: If it's a known action verb, strip it.
        if clean_content in cls.ACTION_VERBS:
            return ''
            
        # If it's a multi-word phrase that looks like roleplay (e.g. *scratches head*)
        # We check if it's all lowercase and doesn't contain numbers.
        if ' ' in clean_content:
            is_roleplay = all(word.islower() for word in clean_content.split() if word.isalpha())
            has_no_numbers = not any(char.isdigit() for char in clean_content)
            if is_roleplay and has_no_numbers:
                return ' '
        
        # Otherwise, assume it's emphasis and keep the word but remove the markers.
        # Add a trailing space to prevent concatenating with next word if space was consumed
        return f" {content} "

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
        # Also clean any starting markdown dividers (e.g. --- or *** at the start)
        cleaned = re.sub(r'^(?:[\s-]*\n*|[\s\*]*\n*)+', '', cleaned)

        # Strip any BBCode quote blocks generated by the LLM to prevent double-quoting
        cleaned = re.sub(r'\[QUOTE[^\]]*\].*?\[/QUOTE\]', '', cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        last_cleaned = None
        
        # Repetitive cleaning until no more patterns match (handles nested/adjacent)
        while cleaned != last_cleaned:
            last_cleaned = cleaned
            
            # 1. Selective stripping for parens and asterisks
            cleaned = cls.RE_PAREN_BLOCK.sub(cls._selective_strip, cleaned)
            cleaned = cls.RE_ASTERISK_BLOCK.sub(cls._selective_strip, cleaned)
            
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

        # 3.3. Sept 1-5 2026 persona audit guards. Order matters: the directive scrub
        # runs first so leaked plumbing never survives into a later sentence filter.
        cleaned = cls.scrub_directive_leaks(cleaned)          # P6
        cleaned = cls.strip_fictional_status(cleaned)         # P3
        cleaned = cls.strip_phantom_hardware(cleaned)         # P5
        cleaned = cls.strip_hostility(cleaned)                # P7
        cleaned = cls.strip_self_dissociation(cleaned)        # P2
        cleaned = cls.collapse_bullets(cleaned)               # P8
        cleaned = cls.strip_addressee_opener(cleaned)         # P1a

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
            
        # Post-harden guard: If output consists solely of an addressee prefix with no body (e.g. 'starkind,' or 'ekco:'), fail it
        body_only = cls.RE_LEADING_NAME.sub('', cleaned).strip()
        if len(body_only) < 2:
            log_warning(f"[BAIT_GUARD] Output contains only addressee prefix without message body: '{cleaned}'. Returning empty string to trigger retry.")
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
        # Consume the connector that joined the concession to its substance.
        brk = cls._CLAUSE_BREAK.match(tail)
        if brk:
            tail = tail[brk.end():]
        remainder = (head + tail).strip(' \t,;:-\u2014\u2013')
        # A leading concession ("you're right to flag that, i'll drop it") leaves a
        # dangling infinitive; if the head was empty and the tail still starts with a
        # connective fragment, take everything after the next comma instead.
        if not head.strip() and remainder:
            first = remainder.split()[0].strip(',')
            # "you're right to flag that phrasing, i'll drop it" -> dangling infinitive
            if first in ('to', 'that', 'about', 'for', 'on', 'in'):
                after = re.split(r',\s+', remainder, maxsplit=1)
                remainder = after[1].strip() if len(after) > 1 else ''
            # "that's a great point, and the chain is weak" -> the praised noun is left
            # stranded ahead of the connector; drop it with the connector.
            elif re.match(r'^\w+\s*,\s+(?:and|but|so|though|although)\b', remainder):
                remainder = re.split(r',\s+', remainder, maxsplit=1)[1].strip()
                remainder = re.sub(r'^(?:and|but|so)\s+', '', remainder)
        if len(remainder.split()) < cls._MIN_KEEP_WORDS:
            return None
        # Kaia writes in lowercase; preserve the surviving fragment's own casing.
        return remainder

    @classmethod
    def _strip_matching_sentences(cls, text: str, pattern, tag: str, mode: str = "sentence") -> str:
        r"""Remove offending clauses, preserving the substance that carried them.

        Sept 2026 fix. This previously dropped the WHOLE sentence on any match, and split
        only on `.!?` so an addressee line was fused to the following paragraph. Observed
        production consequences:

            "ekco,\n\nyou're right; the cron job was the culprit and i've fixed it now."
                -> ""   (entire turn deleted, forcing a full regeneration)
            "you're right; it possesses a simplicity that distinguishes it from others."
                -> ""   (substantive content destroyed along with the concession)

        Both are visible in logs/kaiacord.log as APOLOGY_GUARD strips of bare "ekco," and
        of full sentences. Returning "" makes harden() emit "", which triggers a retry, so
        over-stripping was directly buying latency for no quality gain.

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
        # Early exit: most turns match no pattern, and harden() runs eight of these passes
        # back to back. Checking before splitting skips the split entirely on the common
        # path. (Measured cost of harden() is ~1 ms against ~15 s of inference, so this is
        # tidiness rather than a meaningful latency win.)
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
            log_warning("[DIRECTIVE_LEAK_GUARD] Scrubbed internal directive text from output.")
            scrubbed = cls.RE_DOUBLE_SPACES.sub(' ', scrubbed)
            scrubbed = re.sub(r'\s+([,\.\?!])', r'\1', scrubbed)
            scrubbed = re.sub(r'(?:(?<=^)|(?<=[.!?]\s))\s*[.,]\s*', '', scrubbed)
            scrubbed = re.sub(r'\.\s*\.', '.', scrubbed).strip()
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
                if m:
                    before = current_line[:m.start()]
                    after = current_line[m.end():]
                    
                    before_clean = before.strip()
                    before_clean = cls.RE_LEADING_NAME.sub('', before_clean).strip()
                    
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
                        remainder_body = cls.RE_LEADING_NAME.sub('', remainder).strip().rstrip('.,!? ')
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

