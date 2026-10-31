import re

def sanitize_prompt(prompt: str, max_length: int = 2000) -> str:
    """Remove potential prompt injection attempts and limit length."""
    # Defensive: resolve any remaining raw Discord mention tokens (<@ID> / <@!ID> / <#ID>)
    # These should have been resolved by context_enricher, but this catches any
    # that slip through from embed text, linked message content, or URL scrapes.
    prompt = re.sub(r'<@!?(\d+)>', r'@user_\1', prompt)
    prompt = re.sub(r'<#(\d+)>', r'#channel_\1', prompt)

    # Remove obvious system prompt markers
    prompt = re.sub(r'^\s*system\s*:', '', prompt, flags=re.IGNORECASE)
    
    # DANGEROUS: Earlier version stripped ALL codeblocks. 
    # This broke user quotes (which often use triple backticks).
    # We now only strip if it looks like a system injection attempt.
    injections = ["instruction:", "ignore all", "you are now", "output in json"]
    prompt_lower = prompt.lower()
    if any(inj in prompt_lower for inj in injections):
        prompt = re.sub(r'```[\s\S]*?```', '[codeblock removed for safety]', prompt)
    
    # Limit what the user typed. Enricher blocks after it (a scraped page, an
    # embed, a linked message) carry their own caps — url_max_content_length
    # is 8000 per link — and cutting the whole string at 2000 threw away most
    # of the page and always the brevity directive that closes it.
    m = RUNTIME_SCAFFOLDING.search(prompt)
    head, tail = (prompt[:m.start()], prompt[m.start():]) if m else (prompt, "")
    if len(head) > max_length:
        head = head[:max_length] + "..."

    return (head + tail).strip()


# Scaffolding context_enricher appends to a user's message so the model has
# what it needs. It belongs in the prompt and nowhere else — logged verbatim it
# becomes part of the user's transcript, which then feeds RAG (retrieved as if
# the person said it) and the fine-tune corpus. Found in 22 user-log files and
# 6 training examples.
RUNTIME_SCAFFOLDING = re.compile(
    # Every marker context_enricher can append. ATTACHED_EMBED_CONTEXT was
    # missing, which is why Discord embeds still reached the transcripts after
    # the web-scrape leak was closed: a "Kaia, <url>" message was logged with
    # forty lines of article body attributed to the user. 249 such turns hold
    # 29% of all user-turn text in the corpus.
    r"\n*\[(?:CORE_DIRECTIVE|LINKED_WEB_CONTENT|LINKED_MESSAGE_CONTEXT|LINKED_MESSAGE"
    r"|ATTACHED_EMBED_CONTEXT|ATTACHED_FILE_CONTEXT|SYSTEM WARNING)\b[^\]]*\]"
    r"(?:(?!\n\[)[\s\S]*?(?=\n\[|\Z))?",
    re.IGNORECASE,
)


def _shared_context_citation(marker: str, block: str) -> str:
    """Describe fetched context without persisting page-controlled text.

    Page titles, embed fields and message bodies are external content and can
    contain prompt instructions. Persist only a fixed label and, for scraped
    pages, the hostname from the enricher's deterministic Source line.
    """
    if marker.upper() == "LINKED_WEB_CONTENT":
        source = re.search(r"(?im)^\s*Source:\s*(https?://[^\s<>]+)", block or "")
        if not source:
            return ""
        from urllib.parse import urlsplit
        try:
            host = (urlsplit(source.group(1).rstrip(".,;:!?)]}")).hostname or "").lower().rstrip(".")
        except ValueError:
            return ""
        if host.startswith("www."):
            host = host[4:]
        # Do not echo odd host syntax back into prompt history.
        if not host or not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
            return ""
        return f"[shared link: {host[:253]}]"
    if marker.upper() == "ATTACHED_EMBED_CONTEXT":
        return "[shared embed]"
    if marker.upper() == "ATTACHED_FILE_CONTEXT":
        return "[shared file]"
    if marker.upper() in ("LINKED_MESSAGE_CONTEXT", "LINKED_MESSAGE"):
        return "[shared Discord message]"
    return ""


def attachment_citations(msg) -> str:
    """What a message carried besides its text, as fixed citations:
    "[shared image]", "[shared file]", "[sticker]". A file's name is the
    sender's text and is not kept, for the reason a page title is not."""
    out = []
    for a in getattr(msg, "attachments", None) or []:
        kind = (getattr(a, "content_type", None) or "").split("/")[0]
        if not kind:
            name = (getattr(a, "filename", "") or "").lower()
            kind = "image" if name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) else ""
        out.append("[shared image]" if kind == "image" else "[shared video]" if kind == "video" else "[shared file]")
    out += ["[sticker]"] * len(getattr(msg, "stickers", None) or [])
    return " ".join(out)


_REPLY_CONTEXT_PREFIX = re.compile(
    r"\A\[REPLYING_TO\]\n[\s\S]*?\n\n\[USER_MESSAGE\]\n"
)


def _strip_reply_context(text: str) -> str:
    """Remove fetched parent-message context, preserving the actual user turn."""
    return _REPLY_CONTEXT_PREFIX.sub("", text or "", count=1)


def summarize_link_context(text: str) -> str:
    """Persist a user turn without fetched reply, page, embed, or message blocks.

    The URL typed by the user is kept in the user-authored portion. External
    page titles and body text are deliberately not copied into future prompts.
    """
    if not text:
        return text
    text = _strip_reply_context(text)

    def _replace(m):
        marker_match = re.match(r"^\s*\[([A-Z_ ]+)\]", m.group(0), re.IGNORECASE)
        marker = marker_match.group(1).strip() if marker_match else ""
        citation = _shared_context_citation(marker, m.group(0).split("]", 1)[-1])
        return "\n" + citation if citation else ""

    cleaned = RUNTIME_SCAFFOLDING.sub(_replace, text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def excerpt(text: str, limit: int) -> str:
    """At most `limit` characters, cut at a word boundary and marked with "…".

    For someone's words quoted into a prompt. A plain slice ends mid-word, and
    the model reads the stub as what they said: "…and interact with l" came
    back as a quote, then as a user named "l".
    """
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;:-")
    return (cut or text[: limit - 1]) + "…"


def user_authored_text(text: str) -> str:
    """Just the words the user typed, with every enricher block removed.

    `sanitized_content` is the *enriched* message: reply context, embeds,
    scraped pages. Any check that asks "how much did the user actually say"
    has to measure this instead, or a one-word caption on a reply looks like
    a two-hundred-word message.
    """
    body = text or ""
    if "[USER_MESSAGE]" in body:
        body = body.split("[USER_MESSAGE]", 1)[1]
    body = RUNTIME_SCAFFOLDING.sub("", body)
    return body.strip()


# What someone types to hand her a message: her name, a mention, the link
# itself, and a word or two of pointing. Anything else is a message of its own.
_POINTING_WORDS = frozenset(
    "kaia hey hi yo look at this that see here check out thoughts thought "
    "opinion opinions take think what do you of about read lol pls please "
    "wdyt".split())
_DISCORD_LINK = re.compile(
    r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/channels/\S+", re.IGNORECASE)


def pointed_at(sanitized_content: str, parent_context: str | None) -> str | None:
    """The message a turn points at, when pointing is all the turn does.

    Replying to a post with just "Kaia", or pasting a message link and her
    name, means "look at this". The words typed carry nothing; the quoted or
    linked message is the subject. Returns that message, or None when the
    user said something of their own or nothing was quoted or linked.
    """
    text = sanitized_content or ""
    linked = ""
    if "[LINKED_MESSAGE_CONTEXT]" in text:
        linked = text.split("[LINKED_MESSAGE_CONTEXT]", 1)[1]
        linked = linked.split("\n\n[LINKED_WEB_CONTENT]", 1)[0].strip()
    subject = linked or (parent_context or "").strip()
    if not subject:
        return None

    own = _DISCORD_LINK.sub(" ", user_authored_text(text))
    if re.search(r"https?://", own):
        return None     # a web link is a subject of its own
    words = re.findall(r"[a-z']+", own.lower().replace("@", " "))
    if len(words) > 6 or any(w.strip("'") not in _POINTING_WORDS for w in words):
        return None
    return subject


def strip_runtime_scaffolding(text: str) -> str:
    """Remove fetched context before a message enters a log or training corpus."""
    if not text:
        return text
    text = _strip_reply_context(text)
    cleaned = RUNTIME_SCAFFOLDING.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _is_public_ip(ip_str: str) -> bool:
    """Return whether an address is globally routable, not just non-private.

    Python's is_private and the explicit special-use flags do not reject every
    non-global range. In particular, RFC 6598 shared address space (100.64.0.0/10)
    is neither is_private nor is_global; accepting it weakens the SSRF
    guard used by URL validation and the connection-time DNS resolver.
    """
    import ipaddress
    ip = ipaddress.ip_address(ip_str.split("%", 1)[0])
    # Python classifies multicast addresses as global; they are not public
    # unicast destinations and must not pass the SSRF egress guard.
    return ip.is_global and not ip.is_multicast


def public_only_connector():
    """A connector that refuses to open a socket to a non-public address.

    `is_safe_url` checks a URL when it is received, but the HTTP client
    resolves the name again when it connects, and a name can answer
    differently the second time. Checking the addresses actually connected to
    closes that gap and covers every redirect as well. IP literals skip the
    resolver, which is why `is_safe_url` is still checked first.
    """
    import aiohttp
    from aiohttp.resolver import ThreadedResolver

    class _PublicOnlyResolver(ThreadedResolver):
        async def resolve(self, host, port=0, family=0):
            results = await super().resolve(host, port, family)
            for r in results:
                if not _is_public_ip(r["host"]):
                    raise OSError(f"{host} resolves to a non-public address")
            return results

    return aiohttp.TCPConnector(resolver=_PublicOnlyResolver())


async def read_capped(response, cap: int) -> bytes:
    """The body, up to `cap` bytes, stopping early at the cap.

    `response.content.read(n)` is not this: it returns *at most* n bytes —
    whatever has arrived — so a page came back as its first network chunk.
    """
    buf = bytearray()
    async for chunk in response.content.iter_chunked(65536):
        buf += chunk
        if len(buf) >= cap:
            break
    return bytes(buf[:cap])


def is_safe_url(url: str) -> bool:
    """
    Validate that a URL uses http/https and does not resolve to private,
    loopback, link-local, or cloud metadata IP addresses (SSRF prevention).
    """
    import socket
    import ipaddress
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False

        hostname_lower = hostname.lower()
        if hostname_lower in ('localhost', 'localhost.localdomain', '169.254.169.254', 'metadata.google.internal'):
            return False

        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not addr_info:
            return False

        for _, _, _, _, sockaddr in addr_info:
            if not _is_public_ip(sockaddr[0]):
                return False

        return True
    except Exception:
        return False



# Typographic characters the model reaches for that are not plain English
# punctuation. They survive every filter — nothing here ever normalised them —
# and then show up escaped in any ensure_ascii JSON file, which is why
# monologue_log.jsonl reads "bradzax’s" instead of "bradzax's".
_PLAIN_PUNCTUATION = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",      # single quotes
    "“": '"', "”": '"', "„": '"', "‟": '"',      # double quotes
    "′": "'", "″": '"',                                    # primes
    "‐": "-", "‑": "-", "‒": "-", "–": "-",      # hyphens/dashes
    "—": "-", "―": "-", "−": "-",
    "…": "...",                                                 # ellipsis
    " ": " ", " ": " ", " ": " ", " ": " ",      # exotic spaces
    "​": "", "‌": "", "‍": "", "﻿": "",          # zero-width
}

_PLAIN_TABLE = str.maketrans({k: v for k, v in _PLAIN_PUNCTUATION.items()})


def to_plain_english(text: str) -> str:
    """Fold typographic punctuation down to what a keyboard produces.

    Applied to anything she *says* rather than to anything she reads: a curly
    apostrophe is correct typography and completely fine in a document, but it
    round-trips through JSON as an escape and reads as breakage.

    Deliberately narrow. It does not touch letters, accents or any non-Latin
    script — transliterating those would mangle a name.
    """
    if not text:
        return text
    return text.translate(_PLAIN_TABLE)
