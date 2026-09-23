"""
!news           — today's brief: the summary and numbered headlines.
!news N         — story N in full, with related items from today and earlier briefs.
!news <category> — a category feed (technology, security, politics, ...).

The headlines and the stories come from the latest filed news brief
(`utils.news.brief`), so `!news 5` always opens what `!news` listed as 5.
"""
import asyncio

from utils.commands.embed_style import (
    COLOR_ERROR, COLOR_NEWS, add_field, box, clean)
from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_success, log_warning
from utils.news import brief as briefs

CATEGORIES = ["general", "technology", "security", "hacker", "politics",
              "business", "science", "culture"]
_OVERVIEW_WORDS = {"", "today", "daily", "brief", "headlines"}

#: Earlier briefs searched for a story's background.
BACKGROUND_BRIEFS = 14


def _day(brief) -> str:
    return f"{brief.date:%A}, {brief.date:%B} {brief.date.day}" if brief.date else "latest brief"


def _short_day(date) -> str:
    return f"{date:%b} {date.day}"


def _load(with_background: bool):
    """Latest brief, plus earlier ones when a story needs background. Blocking."""
    files = briefs.brief_files()
    if not files:
        return None, []
    date, path = files[0]
    latest = briefs.parse(path.read_text(encoding="utf-8", errors="replace"), date)
    earlier = []
    if with_background:
        for d, p in files[1:1 + BACKGROUND_BRIEFS]:
            try:
                earlier.append(briefs.parse(p.read_text(encoding="utf-8", errors="replace"), d))
            except OSError:
                continue
    return latest, earlier


def overview_embed(brief):
    stories = briefs.headlines(brief)
    embed = box(f"📰  News · {_day(brief)}", clean(brief.summary, 900), COLOR_NEWS,
                footer="!news <number> for the full story · !news <category> for a feed")
    by_section = {}
    for story in stories:
        by_section.setdefault(story.section, []).append(story)
    for section, items in by_section.items():
        value = "\n".join(f"**{s.number}.** {clean(briefs.headline(s.text), 150)}" for s in items)
        add_field(embed, briefs.section_title(section), value)
    return embed, len(stories)


def story_embed(brief, earlier, number: int):
    stories = briefs.headlines(brief)
    if not 1 <= number <= len(stories):
        return box("📰  News", f"There are {len(stories)} stories today — "
                               f"pick one from `!news`.", COLOR_ERROR)
    story = stories[number - 1]
    embed = box(f"📰  Story {number} · {briefs.section_title(story.section)}",
                f"**{clean(story.text, 1500)}**", COLOR_NEWS,
                footer=f"Global News Brief, {_short_day(brief.date) if brief.date else 'latest'}"
                       " · !news for all headlines")

    same_day, before = briefs.related(story, brief, earlier)
    if same_day:
        add_field(embed, "Related today", "\n".join(f"• {clean(t, 220)}" for t in same_day))
    else:
        rest = [t for t in brief.sections.get(story.section, []) if t != story.text][:3]
        if rest:
            add_field(embed, f"More in {briefs.section_title(story.section)}",
                      "\n".join(f"• {clean(t, 220)}" for t in rest))
    if before:
        add_field(embed, "Earlier mentions",
                  "\n".join(f"• **{_short_day(d)}** — {clean(t, 200)}" for d, t in before))
    quote = brief.quotes.get(story.section)
    if quote:
        add_field(embed, "Quote", f"> {clean(quote, 400)}")
    return embed


async def handle_news_command(ctx, msg, send_kaia_response):
    """Handle the !news command."""
    try:
        parts = msg.content.strip().split(maxsplit=1)
        arg = parts[1].lower().strip() if len(parts) > 1 else ""
        if arg == "hacking":
            arg = "hacker"

        if arg in _OVERVIEW_WORDS or arg.isdigit():
            number = int(arg) if arg.isdigit() else 0
            log_action(f"News {'story ' + str(number) if number else 'brief'} for {msg.author}")
            latest, earlier = await asyncio.to_thread(_load, bool(number))
            if latest is None:
                await msg.channel.send(embed=box(
                    "📰  News", "No news brief has been filed yet.", COLOR_ERROR))
                log_warning("No news brief files found")
                return
            if number:
                await msg.channel.send(embed=story_embed(latest, earlier, number))
            else:
                embed, count = overview_embed(latest)
                await msg.channel.send(embed=embed)
                log_success(f"Sent news brief ({count} headlines) to {msg.author}")
            return

        category = arg
        log_action(f"News request from {msg.author} (Category: {category})")
        news_items = await ctx.news_manager.get_news_async(category)
        items = []
        for item in news_items or []:
            text = item.get('text', str(item)) if isinstance(item, dict) else str(item)
            if len(text.strip()) > 10:
                items.append(text.strip())

        if not items:
            await msg.channel.send(embed=box(
                f"📰  {category.title()} News",
                f"Nothing filed under {category}.\nCategories: "
                + " ".join(f"`{c}`" for c in CATEGORIES), COLOR_ERROR))
            log_warning(f"No {category} news available")
            return

        embed = box(f"📰  {category.title()} News",
                    "\n\n".join(f"**{i}.** {clean(t, 400)}" for i, t in enumerate(items[:6], 1)),
                    COLOR_NEWS, footer="!news for today's headlines")
        add_field(embed, "Other feeds",
                  " ".join(f"`!news {c}`" for c in CATEGORIES if c != category))
        await msg.channel.send(embed=embed)
        log_success(f"Sent {category} news to {msg.author}")

    except Exception as e:
        log_error(f"Error retrieving news: {e}")
        await msg.channel.send(embed=box(
            "📰  News", "Something went wrong reading the news. It's in the log.", COLOR_ERROR))
