"""!explain and !news answer in the embed box, and no quoted text can break it."""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from utils.commands.embed_style import clean, describe_source
from utils.news import brief as briefs

BRIEF = """---
title: Global News Brief - 2026-09-23
summary: A summary.
---
# NEWS_BRIEF: 2026-09-23

## EXECUTIVE_SUMMARY
The General Assembly opened with Iran on the agenda.

## GLOBAL_GEOPOLITICS
- Trump threatened Iran from the General Assembly podium in Manhattan.
- Rubio said a meeting with Pezeshkian remained possible.
- QUOTE: "We will act." - Somebody
## SECURITY_INCIDENTS
No verified developments today.
## SCIENCE_AND_HEALTH
- The AMOC has weakened for two decades.
"""


def test_clean_removes_what_broke_explain():
    text = ('how does rag feel ```ansi\n\x1b[1;37m#1\x1b[0m [1;33m2.0[0m ``` '
            '--- summary: "" keywords: [] --- # Interactions [2026-09-15 00:22:17] Ekco: hi')
    out = clean(text, 300)
    assert "```" not in out and "\x1b" not in out and "[1;" not in out
    assert "summary:" not in out and "Ekco: hi" in out


def test_sources_have_names_people_can_read():
    assert describe_source("user_logs/Tenno_Henka_919782120308752425/interactions_202608_archive.md") \
        == "💬 Tenno Henka · chat · Aug 2026"
    assert describe_source("user_logs/forum_Ekco_251675/user_profile.md") == "👤 Ekco (forum) · profile"
    assert describe_source("news/daily/news_brief_20260923.md") == "📰 News brief · Sep 23"
    assert describe_source("books/Book - Neuromancer by William Gibson.md") == "📖 Neuromancer by William Gibson"


def test_brief_parses_into_numbered_stories():
    b = briefs.parse(BRIEF, datetime(2026, 9, 23))
    assert b.summary.startswith("The General Assembly")
    assert "SECURITY_INCIDENTS" not in b.sections          # "no verified developments"
    assert b.quotes["GLOBAL_GEOPOLITICS"].startswith('"We will act."')
    stories = briefs.headlines(b)
    assert [s.number for s in stories] == [1, 2, 3]
    assert stories[2].section == "SCIENCE_AND_HEALTH"


def test_related_needs_a_shared_name_that_is_not_everywhere():
    b = briefs.parse(BRIEF, datetime(2026, 9, 23))
    earlier = briefs.parse("## GLOBAL_GEOPOLITICS\n- Manhattan traffic slowed as the General Assembly began.\n"
                           "- Pezeshkian arrives for the General Assembly next week.\n"
                           "- Crop yields fell in the Midwest.\n", datetime(2026, 9, 21))
    story = briefs.headlines(b)[0]
    _, before = briefs.related(story, b, [earlier])
    texts = [t for _, t in before]
    assert any("Manhattan" in t for t in texts)
    assert not any("Crop" in t for t in texts)


def _msg(content):
    msg = MagicMock()
    msg.content = content
    msg.author.name = "Ekco"
    msg.channel.send = AsyncMock()
    return msg


def test_explain_n_sends_an_embed_even_for_a_fenced_query():
    from utils.commands.explain_handler import handle_explain_command
    from utils.infrastructure.monitoring import retrieval_trace
    retrieval_trace.clear()
    retrieval_trace.record("look ```ansi\n\x1b[1;37mx\x1b[0m``` here", 0.8, [
        {"score": 2.0, "content": "---\nsummary: x\n---\n[2026-09-15 00:22:17] Ekco: hello there",
         "metadata": {"file_path": "/k/knowledge_base/user_logs/Ekco_1/interactions_20260915.md",
                      "source_type": "user_logs", "retrieval_method": "hybrid"}}])
    msg = _msg("!explain 1")
    asyncio.run(handle_explain_command(MagicMock(), msg, AsyncMock()))
    embed = msg.channel.send.call_args.kwargs["embed"]
    assert "```" not in (embed.description or "")
    assert embed.fields[0].name == "1. 💬 Ekco · chat · Sep 15"
    assert "Ekco: hello there" in embed.fields[0].value
    retrieval_trace.clear()


def test_news_number_opens_the_story_the_list_numbered(tmp_path, monkeypatch):
    from utils.commands import news_handler
    daily = tmp_path / "daily"
    daily.mkdir()
    (daily / "news_brief_20260923.md").write_text(BRIEF, encoding="utf-8")
    monkeypatch.setattr(briefs, "NEWS_DIR", tmp_path)
    monkeypatch.setattr(briefs.brief_files, "__defaults__", (tmp_path,))

    msg = _msg("!news")
    asyncio.run(news_handler.handle_news_command(MagicMock(), msg, AsyncMock()))
    overview = msg.channel.send.call_args.kwargs["embed"]
    assert "**3.** The AMOC has weakened for two decades" in "\n".join(f.value for f in overview.fields)

    msg = _msg("!news 3")
    asyncio.run(news_handler.handle_news_command(MagicMock(), msg, AsyncMock()))
    story = msg.channel.send.call_args.kwargs["embed"]
    assert story.title == "📰  Story 3 · Science And Health"
    assert "AMOC" in story.description


def test_command_handlers_reply_in_the_box_not_raw_code_blocks():
    """A reply built as a code block around text is one fence away from breaking."""
    import re
    from pathlib import Path
    send = re.compile(r"""(?:send|send_message|edit(?:_message)?)\(\s*(?:content=)?f?["']```""")
    offenders = []
    for path in sorted(Path("utils/commands").glob("*.py")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if send.search(line) and not line.lstrip().startswith("#"):
                offenders.append(f"{path}:{n}")
    assert offenders == []
