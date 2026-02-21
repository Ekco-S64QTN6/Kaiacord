import asyncio
import re
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
        
        # SPECIAL CASE: !news today - returns today's news summary
        if category == "today" or category == "daily":
            log_action(f"Today's news summary request from {msg.author}")
            
            # Get today's date and look for most recent news summary
            today = datetime.now()
            news_dir = Path("knowledge_base/news/daily")
            
            # Look for today's summary first, then fall back to most recent
            todays_summary = news_dir / f"news_summary_{today.strftime('%Y%m%d')}.md"
            
            if todays_summary.exists():
                summary_content = todays_summary.read_text()
                # Filter items: remove metadata and headers
                lines = summary_content.split('\n')
                filtered_items = []
                for line in lines:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"): continue
                    if "scraped from 68k.news" in stripped.lower(): continue
                    if stripped.startswith("QUOTE:"): continue
                    filtered_items.append(stripped)
                
                # Limit to ~6 items and join with double spacing
                compact_summary = '\n\n'.join(filtered_items[:6])
                formatted = f"📰 **Today's News Summary ({today.strftime('%B %d, %Y')})**\n\n{compact_summary}"
                # Add category options footer
                formatted += "\n\n---\n**Other categories:** `!news general` `!news technology` `!news security` `!news hacker` `!news politics` `!news business` `!news science` `!news culture`"
                await send_kaia_response(msg.channel, formatted.strip(), use_code_block=False)
                log_success(f"Sent today's news summary to {msg.author}")
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
                    except:
                        date_display = date_str
                    
                    summary_content = most_recent.read_text()
                    # Filter items: remove metadata and headers
                    lines = summary_content.split('\n')
                    filtered_items = []
                    for line in lines:
                        stripped = line.strip()
                        if not stripped or stripped.startswith("#"): continue
                        if "scraped from 68k.news" in stripped.lower(): continue
                        if stripped.startswith("QUOTE:"): continue
                        filtered_items.append(stripped)
                    
                    # Limit to ~6 items and join with double spacing
                    compact_summary = '\n\n'.join(filtered_items[:6])
                    formatted = f"📰 **Latest News Summary ({date_display})**\n\n{compact_summary}"
                    # Add category options footer
                    formatted += "\n\n---\n**Other categories:** `!news general` `!news technology` `!news security` `!news hacker` `!news politics` `!news business` `!news science` `!news culture`"
                    await send_kaia_response(msg.channel, formatted.strip(), use_code_block=False)
                    log_success(f"Sent latest news summary ({date_display}) to {msg.author}")
                else:
                    await msg.channel.send("```\nNo news summaries found. Run: python tools/maintenance/update_kaia_news.py\n```")
                    log_warning("No news summary files found")
            return
        
        log_action(f"News request from {msg.author} (Category: {category})")
        
        # Get news from manager (returns list of dicts)
        news_items = await ctx.news_manager.get_news_async(category)
        
        if news_items and len(news_items) > 0:
            # Format news items nicely
            formatted_news = f"📰 **{category.title()} News**\n\n"
            
            # Filter and limit items
            display_items = []
            for item in news_items:
                text = item.get('text', str(item)) if isinstance(item, dict) else str(item)
                text = text.strip()
                if text and len(text) > 10:
                    display_items.append(text)
            
            # Limit to 6 items and join with double spacing
            for i, text in enumerate(display_items[:6], 1):
                formatted_news += f"{i}. {text}\n\n"
            
            # Add category options footer
            available_categories = ["today", "technology", "security", "hacking", "politics", "business", "science", "culture", "general"]
            formatted_news += "---\n"
            formatted_news += "**Other categories:** " + " ".join([f"`!news {cat}`" for cat in available_categories if cat != category])
            
            # Send WITHOUT code block
            await send_kaia_response(msg.channel, formatted_news.strip(), use_code_block=False)
            log_success(f"Sent {category} news to {msg.author}")
        else:
            await msg.channel.send(f"```\nNo {category} news found. Try updating: `python tools/maintenance/update_kaia_news.py`\n```")
            log_warning(f"No {category} news available")
            
    except Exception as e:
        log_error(f"Error retrieving news: {e}")
        await msg.channel.send("```\nError retrieving news. Check logs for details.\n```")


