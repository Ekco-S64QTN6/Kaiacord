"""Her feed stops opening every post the same way."""
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


def test_a_quip_is_seeded_with_her_reflection_not_the_source(tmp_path, monkeypatch):
    """The fragment is the source text. Seeded with a news brief's, a quip went
    out as "# news_brief: 2026-07-25 ## executive_summary ..." — a July brief,
    posted in September as a passing thought."""
    import asyncio
    from datetime import date, timedelta
    from utils.social import social_response_generator as g
    dreams = tmp_path / "knowledge_base" / "kaia_dreams" / "other"
    dreams.mkdir(parents=True)
    fresh = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
    for name, source in (("dream_1_old.md", "news_brief_20260725.md"),
                         ("dream_2_book.md", "Book - Neuromancer.md"),
                         ("dream_3_new.md", f"news_brief_{fresh}.md")):
        (dreams / name).write_text(
            f"# Dream Reflection: x Source: {source}\n\n## Original Fragment\n> # NEWS_BRIEF\n## EXECUTIVE_SUMMARY raw\n\n"
            f"## Kaia's Reflection\nthat one stayed with me longer than i expected it to.\n")
    monkeypatch.setattr(g, "__file__", str(tmp_path / "utils" / "social" / "x.py"))
    got = asyncio.run(g.get_random_dream_reflection(10))
    assert sorted(d["source"] for d in got) == ["Book - Neuromancer.md", f"news_brief_{fresh}.md"]
    assert all(d["text"] == "that one stayed with me longer than i expected it to." for d in got)
