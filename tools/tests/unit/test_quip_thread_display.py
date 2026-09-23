"""A quip thread reaches chat as one labelled message, like the other unprompted posts."""
from utils.social.social_response_generator import thread_messages

LABEL = "🧵 **Train of thought:**"


def test_a_thread_is_one_message_with_the_label_on_the_first_post():
    out = thread_messages(["first.", "second.", "third."], LABEL)
    assert out == [f"{LABEL} first.\n\nsecond.\n\nthird."]
    assert "```" not in out[0] and "[Thread" not in out[0]


def test_a_long_thread_splits_between_posts_never_inside_one():
    posts = ["a" * 900, "b" * 900, "c" * 900]
    out = thread_messages(posts, LABEL)
    assert all(len(m) <= 2000 for m in out)
    assert "".join(out).count("a" * 900) == 1 and "c" * 900 in out[-1]
    assert out[0].startswith(LABEL) and not out[1].startswith(LABEL)


def test_no_label_and_empty_posts():
    assert thread_messages(["x", "", "  ", "y"], "") == ["x\n\ny"]
    assert thread_messages([], LABEL) == []
