import re

def sanitize_prompt(prompt: str, max_length: int = 2000) -> str:
    """Remove potential prompt injection attempts and limit length."""
    # Remove system prompt markers
    prompt = re.sub(r'\s*system\s*:', '', prompt, flags=re.IGNORECASE)
    prompt = re.sub(r'```[\s\S]*?```', '', prompt)
    
    # Limit length
    if len(prompt) > max_length:
        prompt = prompt[:max_length] + "..."
    
    return prompt.strip()
