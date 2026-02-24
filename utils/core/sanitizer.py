import re

def sanitize_prompt(prompt: str, max_length: int = 2000) -> str:
    """Remove potential prompt injection attempts and limit length."""
    # Defensive: resolve any remaining raw Discord mention tokens (<@ID> / <@!ID>)
    # These should have been resolved by context_enricher, but this catches any
    # that slip through from embed text, linked message content, or URL scrapes.
    prompt = re.sub(r'<@!?(\d+)>', r'@user_\1', prompt)

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
