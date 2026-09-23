"""The 2000-character cap bounds what the user typed, not the enrichment."""
from utils.core.sanitizer import sanitize_prompt


def test_a_linked_page_is_not_cut_by_the_message_cap():
    page = "word " * 1000
    text = (f"Kaia, look\n\n[LINKED_WEB_CONTENT]\n{page}\n\n"
            "[CORE_DIRECTIVE: Keep your response brutally concise.]")
    out = sanitize_prompt(text)
    assert out.endswith("[CORE_DIRECTIVE: Keep your response brutally concise.]")
    assert out.count("word") == 1000


def test_a_long_message_is_still_capped():
    assert len(sanitize_prompt("x" * 5000)) == 2003
