import asyncio
import re
import discord
from datetime import datetime
from pathlib import Path
from utils.infrastructure.logging.kaia_logger import log_action, log_success, log_error, log_warning, log_info

async def handle_news_command(ctx, msg, send_kaia_response):
    """Handle the !news command"""
    try:
        # Parse category from command
        parts = msg.content.strip().split(maxsplit=1)
        category = parts[1].lower().strip() if len(parts) > 1 else "general"
        
        # CATEGORY REDIRECTS
        if category == "hacking":
            category = "hacker"
            
        available_categories = ["today", "general", "technology", "security", "hacker", "politics", "business", "science", "culture"]

        # SPECIAL CASE: !news today/daily - returns today's news summary
        if category in ("today", "daily"):
            log_action(f"Today's news summary request from {msg.author}")
            
            # Get today's date and look for most recent news summary
            today = datetime.now()
            news_dir = Path("knowledge_base/news/daily")
            
            # Look for today's summary first, then fall back to most recent
            todays_summary = news_dir / f"news_summary_{today.strftime('%Y%m%d')}.md"
            
            summary_content = None
            date_display = None
            
            if todays_summary.exists():
                summary_content = todays_summary.read_text()
                date_display = today.strftime("%B %d, %Y")
            else:
                # Find most recent summary file
                summary_files = sorted(news_dir.glob("news_summary_*.md"), reverse=True)
                if summary_files:
                    most_recent = summary_files[0]
                    # Extract date from filename
                    date_str = most_recent.stem.replace("news_summary_", "")
                    try:
                        file_date = datetime.strptime(date_str, "%Y%m%d")
                        date_display = file_date.strftime("%B %d, %Y")
                    except Exception as e:
                        log_warning(f"Unexpected error: {type(e).__name__}: {e}")
                        date_display = date_str
                    summary_content = most_recent.read_text()

            if summary_content:
                # Filter items: remove metadata and headers
                lines = summary_content.split('\n')
                filtered_items = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"): continue
                    if "scraped from 68k.news" in stripped.lower(): continue
                    if stripped.startswith("QUOTE:"): continue
                    filtered_items.append(stripped)
                
                # Format bullet points beautifully
                desc_lines = []
                for i, text in enumerate(filtered_items[:6], 1):
                    desc_lines.append(f"**{i}.** {text}")
                description = "\n\n".join(desc_lines)
                
                embed = discord.Embed(
                    title=f"📰  NEWS SUMMARY — {date_display}",
                    description=description,
                    color=0xe0a96d
                )
                other_cats = [cat for cat in available_categories if cat not in ("today", "daily")]
                embed.add_field(
                    name="Available Categories",
                    value=" ".join([f"`!news {cat}`" for cat in other_cats]),
                    inline=False
                )
                embed.set_footer(text="Daily summary compiled from syndicated feeds")
                await msg.channel.send(embed=embed)
                log_success(f"Sent news summary ({date_display}) to {msg.author}")
            else:
                embed = discord.Embed(
                    title="📰  NEWS SUMMARY",
                    description="No daily news summaries are compiled yet.\nRun maintenance task: `python tools/maintenance/update_kaia_news.py`",
                    color=0xcc4444
                )
                await msg.channel.send(embed=embed)
                log_warning("No news summary files found")
            return
        
        log_action(f"News request from {msg.author} (Category: {category})")
        
        # Get news from manager (returns list of dicts)
        news_items = await ctx.news_manager.get_news_async(category)
        
        if news_items and len(news_items) > 0:
            # Filter and limit items
            display_items = []
            for item in news_items:
                text = item.get('text', str(item)) if isinstance(item, dict) else str(item)
                text = text.strip()
                if text and len(text) > 10:
                    display_items.append(text)
            
            desc_lines = []
            for i, text in enumerate(display_items[:6], 1):
                desc_lines.append(f"**{i}.** {text}")
            description = "\n\n".join(desc_lines)
            
            embed = discord.Embed(
                title=f"📰  {category.upper()} NEWS SUMMARY",
                description=description,
                color=0xe0a96d
            )
            
            other_cats = [cat for cat in available_categories if cat != category]
            embed.add_field(
                name="Other Categories",
                value=" ".join([f"`!news {cat}`" for cat in other_cats]),
                inline=False
            )
            embed.set_footer(text="Synthesized real-time feed updates")
            await msg.channel.send(embed=embed)
            log_success(f"Sent {category} news to {msg.author}")
        else:
            embed = discord.Embed(
                title=f"📰  {category.upper()} NEWS",
                description=f"No {category} news found.\nTry updating news feeds: `python tools/maintenance/update_kaia_news.py`",
                color=0xcc4444
            )
            await msg.channel.send(embed=embed)
            log_warning(f"No {category} news available")
            
    except Exception as e:
        log_error(f"Error retrieving news: {e}")
        embed = discord.Embed(
            title="📰  NEWS ERROR",
            description="Unexpected error retrieving daily news logs. Check system logs for detail.",
            color=0xcc4444
        )
        await msg.channel.send(embed=embed)


