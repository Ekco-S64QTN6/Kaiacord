"""DECISIONS S1: her feed stops opening every post the same way."""
from utils.social.social_response_generator import drop_tag_opener, repeats_opening

RECENT = [
    "it’s fascinating how quickly narratives shift, isn’t it? a few years ago nobody said this.",
    "it's a strange confluence of things, isn't it? anthropic and stripe in the same week.",
    "it’s a long read, but necessary.",
    "it’s a peculiar mix. stripe integrating ai into payments.",
]


def test_a_tag_question_opener_goes_when_substance_follows():
    post = "it’s unsettling how the cycles repeat, isn’t it? the same three stories, every spring, with new names."
    assert drop_tag_opener(post) == "the same three stories, every spring, with new names."


def test_a_short_post_keeps_its_only_sentence():
    post = "it's a lot, isn't it? yeah."
    assert drop_tag_opener(post) == post


def test_an_opening_worn_by_recent_posts_is_caught():
    assert "it's a" in repeats_opening("it's a funny week for payments.", RECENT)
    assert repeats_opening("stripe shipped the thing everyone predicted.", RECENT) == ""


def test_the_news_brief_frame_is_caught_once_used():
    recent = RECENT + ["reading these news briefs, it all blurs."]
    assert repeats_opening("honestly, reading this news brief made me tired.", recent)
