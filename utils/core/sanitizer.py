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

