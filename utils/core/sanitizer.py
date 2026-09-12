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
    
    # Limit length
    if len(prompt) > max_length:
        prompt = prompt[:max_length] + "..."
    
    return prompt.strip()


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
    r"|ATTACHED_EMBED_CONTEXT|SYSTEM WARNING)\b[^\]]*\]"
    r"(?:(?!\n\[)[\s\S]*?(?=\n\[|\Z))?",
    re.IGNORECASE,
)


def _link_title(block: str) -> str:
    """The best one-line title from an embed or scrape block, or ''."""
    for line in (block or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("title:"):
            return line.split(":", 1)[1].strip()[:120]
        # Otherwise the first substantial line that is not a bare fragment.
        # Only accept something that actually looks like a page title: a site
        # separator, or Title Case. The first substantial line after a URL is
        # just as often the user's own next sentence, and "just get it over
        # with" is not a citation.
        if not (6 <= len(line) <= 160) or " " not in line or line.startswith("["):
            continue
        looks_titled = (
            any(sep in line for sep in (" – ", " — ", " | ", " - ")) or
            sum(1 for w in line.split() if w[:1].isupper()) >= max(2, len(line.split()) // 2)
        )
        if looks_titled:
            return line[:120]
    return ""


def summarize_link_context(text: str) -> str:
    """Replace an enricher block with a one-line citation of what was linked.

    Stripping the block outright loses the page title, which is the only part
    of a shared link that carries topic for retrieval — a bare URL is opaque to
    an embedding. Keeping the whole article is worse: 249 turns of scraped body
    text held 29% of all user-turn text in the corpus, attributed to whoever
    pasted the link.
    """
    if not text:
        return text

    def _replace(m):
        title = _link_title(m.group(0).split("]", 1)[-1])
        return f"\n[shared link: {title}]" if title else ""

    cleaned = RUNTIME_SCAFFOLDING.sub(_replace, text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


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


def strip_runtime_scaffolding(text: str) -> str:
    """Remove enricher-injected blocks before a message is written to a log.

    Deliberately not part of sanitize_prompt: generation needs the scaffolding.
    Only persistence does not.
    """
    if not text:
        return text
    cleaned = RUNTIME_SCAFFOLDING.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


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
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False

        return True
    except Exception:
        return False

