import pytest
import sys
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.social.kaia_bluesky import _split_into_thread, needs_thread_expansion

def test_split_into_thread_basic():
    text = "This is a short post."
    chunks = _split_into_thread(text)
    assert chunks == [text]

def test_split_into_thread_long():
    text = "Sentence one. " * 30 # ~420 chars
    chunks = _split_into_thread(text, max_chars=300)
    assert len(chunks) == 2
    assert len(chunks[0]) <= 300
    assert chunks[0].endswith(".")
    assert chunks[1].startswith("Sentence one.")

def test_split_into_thread_multi_punctuation():
    text = "Is this a question? Yes! And an exclamation! Fine."
    chunks = _split_into_thread(text, max_chars=20)
    # "Is this a question?" (19)
    # "Yes! And an" (11) -> actually "Yes!" (4) "And an exclamation!" (19)
    # "exclamation!" (12)
    # "Fine." (5)
    assert len(chunks) >= 3
    for c in chunks:
        assert len(c) <= 20

def test_split_into_thread_no_sentence_boundary():
    text = "word " * 100 # No periods
    chunks = _split_into_thread(text, max_chars=100)
    assert len(chunks) > 4
    for c in chunks[:-1]:
        assert c.endswith("...")
        assert len(c) <= 100

def test_needs_thread_expansion():
    # Long post that splits into [~300, ~50]
    long_text = "A" * 290 + ". " + "B" * 50
    needs, remainder = needs_thread_expansion(long_text, min_second_chunk=100)
    assert needs is True
    assert remainder == "B" * 50

    # Long post that splits into [~300, ~150]
    long_text_2 = "A" * 290 + ". " + "B" * 150
    needs, remainder = needs_thread_expansion(long_text_2, min_second_chunk=100)
    assert needs is False

