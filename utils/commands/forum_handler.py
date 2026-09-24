from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info, log_success, log_debug
from utils.core.rag_utils import request_reindex
from utils.commands.embed_style import COLOR_INFO, add_field, box, clean, clean_block, notice


async def handle_forum_command(ctx, msg, send_kaia_response):
    """Handle the !forum command (Admin only, except link)."""
    parts = msg.content.strip().split(None, 2)
    subcommand = parts[1].lower() if len(parts) > 1 else "status"

    if subcommand == "link":
        user_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not user_id:
            await msg.channel.send(embed=notice("usage: `!forum link <forum_id>`"))
            return
        await _handle_link(ctx, msg, user_id)
        return

    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    if not is_owner:
        await msg.channel.send(embed=notice("restricted.", error=True))
        return

    if subcommand == "status":
        await _handle_status(ctx, msg)
    elif subcommand == "stats":
        await _handle_stats(ctx, msg)
    elif subcommand == "scrape":
        await _handle_scrape(ctx, msg)
    elif subcommand == "read":
        thread_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not thread_id:
            await msg.channel.send(embed=notice("usage: `!forum read <thread_id>`"))
            return
        await _handle_read(ctx, msg, thread_id)
    elif subcommand == "user":
        user_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not user_id:
            await msg.channel.send(embed=notice("usage: `!forum user <user_id>`"))
            return
        await _handle_user(ctx, msg, user_id)
    elif subcommand == "post":
        await _handle_post(ctx, msg, parts)
    elif subcommand == "reply":
        thread_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not thread_id:
            await msg.channel.send(embed=notice("usage: `!forum reply <thread_id>`"))
            return
        await _handle_reply(ctx, msg, thread_id)
    else:
        await msg.channel.send(embed=box("🧵  Forum commands", "\n".join((
            "`!forum status` — connection status and rate limits",
            "`!forum stats` — global scraper totals (threads, posts, users)",
            "`!forum scrape` `[forum=ID limit=N full=true]` — scrape Off Topic",
            "`!forum read <id>` — the last posts in a thread",
            "`!forum post <id> <message>` — post a reply",
            "`!forum reply <id>` — draft a reply for review",
            "`!forum user <id>` — deep-scrape a user's post history",
            "`!forum link <id>` — link your Discord account to a forum id",
        ))))


async def _handle_status(ctx, msg):
    """Show forum connection status."""
    from utils.social.kaia_forum import is_forum_configured, get_forum_client

    if not is_forum_configured():
        await msg.channel.send(embed=notice("forum integration is disabled in config."))
        return

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send(embed=notice("couldn't connect to forum.", error=True))
            return

        status = client.get_status()
        # The window and the lurk counter are the two reasons she can be
        # enabled, logged in, and still correctly posting nothing — so they
        # belong here, where the question gets asked.
        lurk = "done" if status['lurk_ready'] else f"reading ({status['lurk_detail']})"
        embed = box("🧵  Forum status", footer=str(status['base_url']))
        for name, value in (
                ("Logged in", status['logged_in']), ("Off-topic posting", status['enabled']),
                ("Tech support", status['tech_support']), ("Auto-reply", status['auto_reply']),
                ("Posting window", status['window']), ("Lurking", lurk),
                ("Posts today", f"{status['posts_today']}/{status['max_posts_per_day']}"),
                ("Min hours between", status['min_hours_between_posts']),
                ("Last post", status['last_post'])):
            add_field(embed, name, str(value), inline=True)
        await msg.channel.send(embed=embed)
    except Exception as e:
        log_error(f"Forum status error: {e}")
        await msg.channel.send(embed=notice(f"error getting forum status: {e}", error=True))


async def _handle_stats(ctx, msg):
    """Show global forum scraper statistics."""
    from utils.social.kaia_forum import get_forum_client

    async with msg.channel.typing():
        try:
            client = await get_forum_client()
            if not client:
                await msg.channel.send(embed=notice("forum not configured."))
                return

            stats = await client.get_global_stats()
            
            embed = box("🧵  Forum stats")
            for name, value in (
                    ("Threads listed", f"{stats['last_listing_count']} (latest snapshot)"),
                    ("Threads scraped", stats['total_threads']),
                    ("Posts collected", stats['total_posts']),
                    ("Users indexed", stats['total_users']),
                    ("Profiles", stats['total_profiles']),
                    ("Disk", f"{stats['disk_usage_mb']:.2f} MB")):
                add_field(embed, name, str(value), inline=True)
            await msg.channel.send(embed=embed)
        except Exception as e:
            log_error(f"Forum stats error: {e}")
            await msg.channel.send(embed=notice(f"error getting forum stats: {e}", error=True))


async def _handle_scrape(ctx, msg):
    """Manually trigger a forum scrape."""
    from utils.social.kaia_forum import get_forum_client

    # Pre-parse to get target_forum_id for the status message
    parts = msg.content.strip().split()
    target_forum_id = None
    for arg in parts:
        if arg.startswith('forum='):
            try:
                target_forum_id = int(arg.split('=')[1])
            except ValueError:
                pass
                
    forum_names = {
        1: "Important", 11: "News & Announcements", 2: "Library",
        16: "General Community", 71: "Starting Zone", 40: "Technical Discussion",
        30: "Rants and Flames", 41: "Screenshots", 19: "Off Topic",
        75: "Green Community", 73: "Green Server Chat", 77: "Green Trading Hub", 80: "Green Guild Discussion",
        76: "Blue Community", 17: "Blue Server Chat", 27: "Blue Trading Hub", 18: "Blue Guild Discussion", 69: "Blue Raid Discussion",
        57: "Red Community", 54: "Red Server Chat", 59: "Red Trading Hub", 58: "Red Guild Discussion", 55: "Red Rants and Flames",
        5: "Server Issues", 6: "Bugs", 56: "PvP Bugs", 14: "Resolved Issues",
        25: "Petition / Exploit", 33: "Guide Applications",
        61: "Class Discussions", 62: "Tanks", 63: "Melee", 64: "Priests", 66: "Casters"
    }
    forum_name = forum_names.get(target_forum_id, f"Forum {target_forum_id}") if target_forum_id else "Off Topic"

    await msg.channel.send(embed=notice(f"scraping {forum_name}..."))

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send(embed=notice("forum not configured or login failed.", error=True))
            return

        async with msg.channel.typing():
            # Parse optional arguments and positional limit
            parts = msg.content.strip().split()
            command_args = parts[2:] if len(parts) > 2 else []
            
            from utils.infrastructure.system.yaml_config import config
            max_posts = config.get('forum.max_posts_per_thread_scrape', 50)
            max_users = config.get('forum.max_active_users_scrape', 15)
            
            target_threads = 20  # Default to one full page (~20 threads)
            start_page = 1
            max_pages_to_process = 1
            full_scrape = False
            target_forum_id = None

            # Check for positional target_threads (e.g., !forum scrape 50)
            if command_args and command_args[0].isdigit():
                target_threads = int(command_args[0])
                command_args = command_args[1:]
                # Auto-calculate pages needed (VBulletin usually shows 20-25 threads per page)
                max_pages_to_process = (target_threads // 20) + (1 if target_threads % 20 > 0 else 0)

            for arg in command_args:
                if arg.startswith('limit='):
                    try:
                        max_users = int(arg.split('=')[1])
                    except ValueError:
                        pass
                elif arg.startswith('page='):
                    try:
                        start_page = int(arg.split('=')[1])
                    except ValueError:
                        pass
                elif arg.startswith('max_pages='):
                    try:
                        max_pages_to_process = int(arg.split('=')[1])
                    except ValueError:
                        pass
                elif arg.startswith('forum='):
                    try:
                        target_forum_id = int(arg.split('=')[1])
                    except ValueError:
                        pass
                elif arg == 'full=true':
                    full_scrape = True

            scraped_threads = 0
            all_posts = []
            pages_processed = 0
            current_page = start_page
            threads = [] # Initialize threads list
            
            while pages_processed < max_pages_to_process and scraped_threads < target_threads:
                # Removed intermediate message to reduce spam: await msg.channel.send(f"```\nscraping Off Topic page {current_page}...\n```")
                page_threads = await client.scrape_forum_listing(page=current_page, forum_id=target_forum_id)
                if not page_threads:
                    break
                
                client.save_forum_listing(page_threads)
                threads.extend(page_threads)

                any_thread_updated = False
                for t in page_threads:
                    if scraped_threads >= target_threads:
                        break
                        
                    if t.is_sticky:
                        continue
                        
                    # SKIP if already up to date
                    if not client.is_thread_update_needed(t.thread_id, t.reply_count):
                        log_info(f"Thread {t.thread_id} ('{t.title}') is up to date. Skipping.")
                        continue
                        
                    thread_data = await client.scrape_thread(t.thread_id, last_n_posts=max_posts, full_scrape=full_scrape)
                    if thread_data.get('posts'):
                        client.save_thread_scrape(thread_data)
                        all_posts.extend(thread_data['posts'])
                        scraped_threads += 1
                        any_thread_updated = True

                pages_processed += 1
                
                # If we processed all threads on this page and none needed updates,
                # and we haven't reached our target yet, we keep going deeper if max_pages allows.
                # If user didn't specify max_pages (it was auto-calculated or defaulted), 
                # we can be a bit more flexible to find new content.
                if not any_thread_updated and pages_processed == max_pages_to_process and scraped_threads < target_threads:
                    # If we haven't found ANY new threads on the requested pages, 
                    # auto-extend by ONE page to see if there's anything fresh just beyond the horizon
                    max_pages_to_process += 1
                    log_info(f"No new content found up to page {current_page}. Extending search to page {current_page + 1}.")
                
                current_page += 1

            # Update forum user profiles from thread posts
            if all_posts:
                client.update_forum_user_profiles(all_posts)

            # Deep-scrape unique users found in threads with the specified limit
            users_scraped = await client.scrape_active_users(threads, all_posts, max_users=max_users)

            # Trigger reindex
            request_reindex()

        embed = box("🧵  Scrape complete", footer="saved to knowledge_base/forum_posts/")
        for name, value in (("Threads listed", len(threads)), ("Threads scraped", scraped_threads),
                            ("Posts collected", len(all_posts)), ("Users deep-scraped", users_scraped)):
            add_field(embed, name, str(value), inline=True)
        await msg.channel.send(embed=embed)
        log_action(f"Forum scrape complete: {len(threads)} threads, {len(all_posts)} posts")

    except Exception as e:
        log_error(f"Forum scrape error: {e}")
        await msg.channel.send(embed=notice(f"scrape failed: {e}", error=True))


async def _handle_read(ctx, msg, thread_id: int):
    """Read and display recent posts from a thread."""
    from utils.social.kaia_forum import get_forum_client

    try:
        # Parse full=true from msg.content
        full_scrape = 'full=true' in msg.content.lower()

        client = await get_forum_client()
        if not client:
            await msg.channel.send(embed=notice("forum not configured or login failed.", error=True))
            return

        async with msg.channel.typing():
            thread_data = await client.scrape_thread(thread_id, last_n_posts=10, full_scrape=full_scrape)

        if not thread_data.get('posts'):
            await msg.channel.send(embed=notice(f"no posts found in thread {thread_id}."))
            return

        # Build a readable summary
        title = thread_data.get('title', f'Thread {thread_id}')
        posts = thread_data['posts']

        # Scraped posts are strangers' text: cleaned into fields, never
        # wrapped in a code block they could close.
        embed = box(f"🧵  {clean(title, 200)}", f"Page {thread_data.get('page', '?')} · "
                    f"last {min(5, len(posts))} of {len(posts)} posts", COLOR_INFO,
                    footer=f"thread {thread_id}")
        for p in posts[-5:]:
            post = p if isinstance(p, dict) else p.to_dict()
            add_field(embed, f"#{post.get('post_number', '?')} · {clean(post.get('author', '?'), 60)}",
                      clean(post.get('content', ''), 300) or "(empty)")
        await msg.channel.send(embed=embed)

        # Also save the full scrape
        client.save_thread_scrape(thread_data)
        request_reindex()

    except Exception as e:
        log_error(f"Forum read error: {e}")
        await msg.channel.send(embed=notice(f"error reading thread: {e}", error=True))


async def _handle_reply(ctx, msg, thread_id: int):
    """Draft a reply to a thread and show it with confirm/cancel buttons.

    Drafts through `forum_drafting.draft_forum_reply`, the same pipeline the
    auto-poster uses, so a manual reply gets RAG, thread history and vision.
    """
    from utils.social.kaia_forum import get_forum_client
    from utils.social.forum_drafting import draft_forum_reply, own_words

    client = await get_forum_client()
    if not client:
        await msg.channel.send(embed=notice("forum client not available."))
        return

    async with msg.channel.typing():
        try:
            thread_data = await client.scrape_thread(thread_id, last_n_posts=15)
            posts = thread_data.get('posts') or []
            if not posts:
                await msg.channel.send(embed=notice(f"couldn't find content for thread {thread_id}.", error=True))
                return

            # Save so RAG sees it
            client.save_thread_scrape(thread_data)
            title = thread_data.get('title', 'Unknown Thread')

            draft = await draft_forum_reply(ctx, thread_id=thread_id, title=title, posts=posts)
            if not draft:
                await msg.channel.send(embed=notice("no reply drafted — see the log for why."))
                return

            quote_post = draft['quote']
            quoted = own_words(quote_post) if quote_post else ""
            if quote_post and quoted:
                ai_reply = client.format_quote(
                    quote_post.get('author', 'Unknown'), quote_post.get('post_id'), quoted,
                ) + draft['text']
            else:
                ai_reply = draft['text']

            # Discord caps a message at 2,000 characters. Trim the preview only;
            # the button posts the full reply.
            shown = ai_reply if len(ai_reply) <= 1800 else ai_reply[:1800] + "…"
            preview = box(f"🧵  Reply preview · {clean(title, 150)}", clean_block(shown, 3900),
                          footer=f"thread {thread_id} · the full reply is what gets posted")
            view = _ForumReplyConfirmView(client, thread_id, title, ai_reply, msg.author.id)
            await msg.channel.send(embed=preview, view=view)

        except Exception as e:
            log_error(f"AI forum reply failed: {e}")
            import traceback
            log_debug(traceback.format_exc())
            await msg.channel.send(embed=notice(f"error generating reply: {e}", error=True))


class _ForumReplyConfirmView:
    """Confirm/Cancel view for forum reply preview. Uses raw discord.ui components."""
    
    def __new__(cls, client, thread_id, title, reply_text, author_id):
        import discord
        
        view = discord.ui.View(timeout=120)
        
        confirm_btn = discord.ui.Button(
            label="✅ Post It", style=discord.ButtonStyle.success
        )
        cancel_btn = discord.ui.Button(
            label="❌ Cancel", style=discord.ButtonStyle.danger
        )
        regen_btn = discord.ui.Button(
            label="🔄 Regenerate", style=discord.ButtonStyle.secondary
        )

        async def _confirm(interaction: discord.Interaction):
            if interaction.user.id != author_id:
                await interaction.response.send_message("not your button.", ephemeral=True)
                return
            await interaction.response.defer()
            success = await client.post_reply(thread_id, reply_text)
            if success:
                await interaction.followup.send(embed=notice(f"✅ posted to '{title[:80]}'."))
                log_success(f"Forum reply posted to thread {thread_id}")
            else:
                await interaction.followup.send(embed=notice("❌ failed to post. check rate limits.", error=True))
            view.stop()

        async def _cancel(interaction: discord.Interaction):
            if interaction.user.id != author_id:
                await interaction.response.send_message("not your button.", ephemeral=True)
                return
            await interaction.response.edit_message(content=None, embed=notice("cancelled."), view=None)
            view.stop()

        async def _regen(interaction: discord.Interaction):
            if interaction.user.id != author_id:
                await interaction.response.send_message("not your button.", ephemeral=True)
                return
            await interaction.response.edit_message(
                content=None, embed=notice("discarded. use `!forum reply` again for a new draft."), view=None
            )
            view.stop()

        confirm_btn.callback = _confirm
        cancel_btn.callback = _cancel
        regen_btn.callback = _regen

        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        view.add_item(regen_btn)

        return view


async def _handle_user(ctx, msg, user_id: int):
    """Deep-scrape a specific user's profile and full post history."""
    from utils.social.kaia_forum import get_forum_client

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send(embed=notice("forum not configured or login failed.", error=True))
            return

        await msg.channel.send(embed=notice(f"deep-scraping user {user_id}..."))

        async with msg.channel.typing():
            # Scrape profile metadata
            profile = await client.scrape_user_profile(user_id)
            username = profile.get('username', f'User_{user_id}')

            # Scrape basic post history (snippets) to get thread links
            posts = await client.scrape_user_post_history(user_id, username, max_pages=20)

            # visit top threads for FULL context (Deep Crawl)
            await msg.channel.send(embed=notice(f"deep-crawling threads for full content..."))
            full_posts = await client.deep_crawl_user_posts(user_id, username, posts)
            
            # Scrape threads started
            threads_started = await client.scrape_user_threads_started(user_id, username, max_pages=10)
            
            # Combine results for saving
            all_results = full_posts + posts + threads_started
            
            # Save consolidated history
            if profile or all_results:
                from utils.social.kaia_forum import PostInfo
                
                # Update narrative profile with fresh metadata
                post_infos = [
                    PostInfo(author=username, user_id=user_id, content=p.get('content') or p.get('content_preview', ''), timestamp='', post_id=p.get('post_id'))
                    for p in all_results[:10]
                ]
                client.update_forum_user_profiles(post_infos, profile)
                
                # Visit the AI to generate a proper personality profile
                await msg.channel.send(embed=notice(f"generating AI personality profile..."))
                await client.generate_personality_profile(username, user_id, all_results, profile)
                
                # Save the big history file
                filepath = client.save_user_post_history(username, user_id, profile, all_results)
                request_reindex()

        # Report
        total = profile.get('total_posts', '?')
        rank = profile.get('rank', '?')
        joined = profile.get('join_date', '?')

        # IDENTITY LINKING: Check for linked Discord ID
        from utils.social.kaia_identities import registry
        linked_discord = registry.get_discord_id(user_id)
        embed = box(f"👤  {clean(username, 100)}",
                    footer=f"saved to knowledge_base/user_logs/forum_{username}_{user_id}/")
        for name, value in (("Rank", clean(str(rank), 100)), ("Forum posts", total),
                            ("Joined", joined), ("Posts scraped", len(posts))):
            add_field(embed, name, str(value), inline=True)
        if linked_discord:
            add_field(embed, "Linked Discord", str(linked_discord), inline=True)
        await msg.channel.send(embed=embed)

    except Exception as e:
        log_error(f"Forum user scrape error: {e}")
        await msg.channel.send(embed=notice(f"user scrape failed: {e}", error=True))


async def _handle_link(ctx, msg, forum_id: int):
    """Link a Discord account to a Forum ID."""
    from utils.social.kaia_identities import registry
    from utils.social.kaia_forum import get_forum_client

    discord_id = f"{msg.author.name}_{msg.author.id}"
    
    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send(embed=notice("forum client failure", error=True))
            return

        # Optional: Verify user exists on forum
        profile = await client.scrape_user_profile(forum_id)
        forum_name = profile.get('username', 'Unknown')
        
        registry.link_discord_to_forum(discord_id, forum_id)
        
        embed = box("🔗  Identity linked")
        add_field(embed, "Discord", str(discord_id), inline=True)
        add_field(embed, "Forum", f"{clean(forum_name, 100)} ({forum_id})", inline=True)
        await msg.channel.send(embed=embed)
    except Exception as e:
        log_error(f"Identity link error: {e}")
        await msg.channel.send(embed=notice(f"link failed: {e}", error=True))


async def _handle_post(ctx, msg, parts):
    """Post a reply to a forum thread."""
    from utils.social.kaia_forum import get_forum_client

    # Parse: !forum post <thread_id> <message>
    if len(parts) < 3:
        await msg.channel.send(embed=notice("usage: `!forum post <thread_id> <message>`"))
        return

    # Re-split to get thread_id and message properly
    remainder = msg.content.strip()
    # Strip "!forum post "
    remainder = remainder.split(None, 2)[-1] if len(remainder.split(None, 2)) > 2 else ''

    post_parts = remainder.split(None, 1)
    if len(post_parts) < 2 or not post_parts[0].isdigit():
        await msg.channel.send(embed=notice("usage: `!forum post <thread_id> <message>`"))
        return

    thread_id = int(post_parts[0])
    message = post_parts[1]

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send(embed=notice("forum not configured or login failed.", error=True))
            return

        async with msg.channel.typing():
            success = await client.post_reply(thread_id, message)

        if success:
            await msg.channel.send(embed=notice(f"posted to thread {thread_id}."))
        else:
            await msg.channel.send(embed=notice(f"failed to post. check rate limits or thread permissions.", error=True))

    except Exception as e:
        log_error(f"Forum post error: {e}")
        await msg.channel.send(embed=notice(f"post failed: {e}", error=True))
