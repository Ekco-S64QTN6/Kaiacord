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
    msg.channel.id = 7
    msg.channel.send = AsyncMock()
    return msg


def test_explain_n_sends_an_embed_even_for_a_fenced_query():
    from utils.commands.explain_handler import handle_explain_command
    from utils.infrastructure.monitoring import retrieval_trace
    retrieval_trace.clear()
    retrieval_trace.record("look ```ansi\n\x1b[1;37mx\x1b[0m``` here", 0.8, [
        {"score": 2.0, "content": "---\nsummary: x\n---\n[2026-09-15 00:22:17] Ekco: hello there",
         "metadata": {"file_path": "/k/knowledge_base/user_logs/Ekco_1/interactions_20260915.md",
                      "source_type": "user_logs", "retrieval_method": "hybrid"}}], channel=7)
    msg = _msg("!explain 1")
    asyncio.run(handle_explain_command(MagicMock(), msg, AsyncMock()))
    embed = msg.channel.send.call_args.kwargs["embed"]
    assert "```" not in embed.description and "\x1b" not in embed.description
    assert "**1.** 💬 Ekco · chat · Sep 15" in embed.description
    retrieval_trace.clear()


def test_explain_shows_only_what_was_asked_in_its_own_channel():
    from utils.commands.explain_handler import handle_explain_command
    from utils.infrastructure.monitoring import retrieval_trace
    retrieval_trace.clear()
    retrieval_trace.record("asked here", 0.8, [], channel="7")
    retrieval_trace.record("asked in another channel", 0.8, [], channel="8")
    retrieval_trace.record("a background retrieval", 0.8, [], channel="global")
    for command in ("!explain", "!explain 0"):
        msg = _msg(command)
        asyncio.run(handle_explain_command(MagicMock(), msg, AsyncMock()))
        embed = msg.channel.send.call_args.kwargs["embed"]
        assert "asked here" in embed.description and "another" not in embed.description
    retrieval_trace.clear()


def test_flag_flags_the_sources_this_channel_was_shown():
    from utils.commands.audit_handler import handle_flag_command
    from utils.infrastructure.monitoring import retrieval_trace
    retrieval_trace.clear()
    retrieval_trace.record("q", 0.8, [{"node_id": "a", "metadata": {}},
                                      {"node_id": "b", "metadata": {}}], channel=7)
    retrieval_trace.record("elsewhere", 0.8, [{"node_id": "z", "metadata": {}}], channel=8)
    ctx = MagicMock()
    ctx.config.get = lambda key, default=None: default
    ctx.config.is_owner.return_value = True
    ctx.rag.flag_nodes.return_value = 2
    msg = _msg("!flag hedge density")
    asyncio.run(handle_flag_command(ctx, msg, AsyncMock()))
    ctx.rag.flag_nodes.assert_called_once_with(["a", "b"], "hedge_density")
    assert msg.channel.send.call_args.kwargs["embed"].title == "🏷️  Flagged"
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


def test_explain_lists_each_source_once_by_name():
    from utils.commands.explain_handler import render_sources
    rows = [{"score": 1.0, "source": "documents/Architecture - HyMem Hybrid Memory Systems.md",
             "head": "HyMem page 1"}] * 8
    embed = render_sources("t", "q", 1.0, 16, rows, "f", when="6 min ago")
    lines = [l for l in embed.description.splitlines() if l.startswith("**")]
    assert lines == ["**1.** 📄 HyMem Hybrid Memory Systems · 8 passages"]
    assert "score" not in embed.description and "HyMem page 1" not in embed.description
    assert "6 min ago" in embed.description


def test_a_pasted_link_is_not_a_request_for_a_stored_document():
    from utils.core.kaia_rag_query import RAGQueryMixin
    turn = ("Kaia, https://pastebin.com/raw/abc\n\n[LINKED_WEB_CONTENT]\n"
            "This document summarizes your memory systems report.\n")
    own = RAGQueryMixin._own_words(turn)
    assert "document" not in own and "pastebin" not in own
    assert not RAGQueryMixin._is_document_request(own)
    assert RAGQueryMixin._is_document_request(
        RAGQueryMixin._own_words("kaia summarize the HyMem paper"))


def test_snapshot_writes_local_times_and_names_not_mention_ids(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from utils.commands import snapshot_handler
    from utils.core import rag_utils
    from utils.infrastructure.system.yaml_config import config
    monkeypatch.setattr(config, "is_owner", lambda *a, **k: True)
    real_get = config.get
    monkeypatch.setattr(config, "get", lambda key, default=None:
                        str(tmp_path) if key == "paths.knowledge_base" else real_get(key, default))
    monkeypatch.setattr(rag_utils, "request_reindex", lambda: None)

    when = datetime(2026, 9, 24, 18, 5, tzinfo=timezone.utc)
    history = []
    for i in range(3):
        m = MagicMock()
        m.content = "hey <@123> look at this long enough message"
        m.clean_content = "hey @Starkind look at this long enough message"
        m.created_at = when
        m.author.display_name, m.author.bot = "Ekco", False
        history.append(m)

    async def _history(limit):
        for m in history:
            yield m

    msg = _msg("!snapshot")
    msg.channel.history = _history
    msg.channel.name = "general"
    asyncio.run(snapshot_handler.handle_snapshot_command(MagicMock(), msg, AsyncMock()))

    [saved] = (tmp_path / "runtime" / "snapshots").glob("*.md")
    text = saved.read_text(encoding="utf-8")
    assert "<@123>" not in text and "@Starkind" in text
    assert f"[{when.astimezone().strftime('%H:%M')}] Ekco:" in text
    assert msg.channel.send.call_args.kwargs["embed"].title == "📸  Snapshot"
