"""Splitting a cross-post into a Bluesky thread: every post fits, nothing is lost."""
import random
import re

from utils.social.kaia_bluesky import _split_into_thread


def test_a_token_longer_than_a_post_is_cut_so_every_post_fits():
    text = "see this. " + "https://example.com/" + "a" * 400 + " done."
    assert all(len(c) <= 300 for c in _split_into_thread(text))


def test_paragraph_breaks_survive_the_split():
    text = "first paragraph ends.\n\nsecond one begins. " + "filler words here. " * 30
    assert _split_into_thread(text)[0].startswith("first paragraph ends.\n\nsecond one begins.")


def test_a_thread_cut_short_says_so():
    posts = _split_into_thread("A sentence of some length goes here. " * 60, max_posts=3)
    assert len(posts) == 3 and posts[-1].endswith("…")


def test_no_text_is_lost_when_nothing_is_cut():
    rng = random.Random(7)
    for _ in range(200):
        text = " ".join(rng.choice(["a", "bb", "end.", "wow!", "e" * rng.randint(1, 400), "\n\n"])
                        for _ in range(rng.randint(1, 250)))
        posts = _split_into_thread(text, max_posts=999)
        assert all(0 < len(p) <= 300 for p in posts)
        squash = lambda s: re.sub(r"\s", "", s.replace("…", ""))
        assert "".join(squash(p) for p in posts) == squash(text.strip())
