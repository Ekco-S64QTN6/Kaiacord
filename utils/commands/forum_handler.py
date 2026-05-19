from utils.infrastructure.logging.kaia_logger import log_action, log_error, log_info, log_success, log_debug
from pathlib import Path


async def handle_forum_command(ctx, msg, send_kaia_response):
    """Handle the !forum command (Admin only)."""
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))

    if not is_owner:
        await msg.channel.send("```\nrestricted.\n```")
        return

    parts = msg.content.strip().split(None, 2)
    subcommand = parts[1].lower() if len(parts) > 1 else "status"

    if subcommand == "status":
        await _handle_status(ctx, msg)
    elif subcommand == "stats":
        await _handle_stats(ctx, msg)
    elif subcommand == "scrape":
        await _handle_scrape(ctx, msg)
    elif subcommand == "read":
        thread_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not thread_id:
            await msg.channel.send("```\nusage: !forum read <thread_id>\n```")
            return
        await _handle_read(ctx, msg, thread_id)
    elif subcommand == "user":
        user_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not user_id:
            await msg.channel.send("```\nusage: !forum user <user_id>\n```")
            return
        await _handle_user(ctx, msg, user_id)
    elif subcommand == "link":
        user_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not user_id:
            await msg.channel.send("```\nusage: !forum link <forum_id>\n```")
            return
        await _handle_link(ctx, msg, user_id)
    elif subcommand == "post":
        await _handle_post(ctx, msg, parts)
    elif subcommand == "reply":
        thread_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        if not thread_id:
            await msg.channel.send("```\nusage: !forum reply <thread_id>\n```")
            return
        await _handle_reply(ctx, msg, thread_id)
    else:
        await msg.channel.send(
            "```\n"
            "!forum status    — connection status and rate limits\n"
            "!forum stats     — global scraper totals (threads, posts, users)\n"
            "!forum scrape    — scrape Off Topic [forum=ID limit=N full=true]\n"
            "!forum read <id> — read last posts from a thread\n"
            "!forum post <id> <message> — post a reply\n"
            "!forum reply <id> — AI-generated reply to a thread\n"
            "!forum user <id> — deep-scrape a user's full post history\n"
            "!forum link <id> — link YOUR discord account to a forum id\n"
            "```"
        )


async def _handle_status(ctx, msg):
    """Show forum connection status."""
    from utils.social.kaia_forum import is_forum_configured, get_forum_client

    if not is_forum_configured():
        await msg.channel.send("```\nforum integration is disabled in config.\n```")
        return

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send("```\ncouldn't connect to forum.\n```")
            return

        status = client.get_status()
        await msg.channel.send(
            f"```\n"
            f"Forum Status\n"
            f"  logged in: {status['logged_in']}\n"
            f"  auto-reply: {status['auto_reply']}\n"
            f"  posts today: {status['posts_today']}/{status['max_posts_per_day']}\n"
            f"  min hours between posts: {status['min_hours_between_posts']}\n"
            f"  last post: {status['last_post']}\n"
            f"  url: {status['base_url']}\n"
            f"```"
        )
    except Exception as e:
        log_error(f"Forum status error: {e}")
        await msg.channel.send(f"```\nerror getting forum status: {e}\n```")


async def _handle_stats(ctx, msg):
    """Show global forum scraper statistics."""
    from utils.social.kaia_forum import get_forum_client

    async with msg.channel.typing():
        try:
            client = await get_forum_client()
            if not client:
                await msg.channel.send("```\nforum not configured.\n```")
                return

            stats = await client.get_global_stats()
            
            await msg.channel.send(
                f"```\n"
                f"Forum Global Stats\n"
                f"  threads listed: {stats['last_listing_count']} (latest snapshot)\n"
                f"  threads scraped: {stats['total_threads']}\n"
                f"  posts collected: {stats['total_posts']}\n"
                f"  users indexed: {stats['total_users']}\n"
                f"  profiles generated: {stats['total_profiles']}\n"
                f"  disk usage: {stats['disk_usage_mb']:.2f} MB\n"
                f"```"
            )
        except Exception as e:
            log_error(f"Forum stats error: {e}")
            await msg.channel.send(f"```\nerror getting forum stats: {e}\n```")


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

    await msg.channel.send(f"```\nscraping {forum_name}...\n```")

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send("```\nforum not configured or login failed.\n```")
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
            Path("./knowledge_base/.trigger_reindex").touch()

        await msg.channel.send(
            f"```\n"
            f"scrape complete.\n"
            f"  threads listed: {len(threads)}\n"
            f"  threads scraped: {scraped_threads}\n"
            f"  posts collected: {len(all_posts)}\n"
            f"  users deep-scraped: {users_scraped}\n"
            f"  saved to: knowledge_base/forum_posts/\n"
            f"```"
        )
        log_action(f"Forum scrape complete: {len(threads)} threads, {len(all_posts)} posts")

    except Exception as e:
        log_error(f"Forum scrape error: {e}")
        await msg.channel.send(f"```\nscrape failed: {e}\n```")


async def _handle_read(ctx, msg, thread_id: int):
    """Read and display recent posts from a thread."""
    from utils.social.kaia_forum import get_forum_client

    try:
        # Parse full=true from msg.content
        full_scrape = 'full=true' in msg.content.lower()

        client = await get_forum_client()
        if not client:
            await msg.channel.send("```\nforum not configured or login failed.\n```")
            return

        async with msg.channel.typing():
            thread_data = await client.scrape_thread(thread_id, last_n_posts=10, full_scrape=full_scrape)

        if not thread_data.get('posts'):
            await msg.channel.send(f"```\nno posts found in thread {thread_id}.\n```")
            return

        # Build a readable summary
        title = thread_data.get('title', f'Thread {thread_id}')
        posts = thread_data['posts']

        lines = [f"Thread: {title}", f"Page: {thread_data.get('page', '?')}", ""]
        for p in posts[-5:]:  # Show last 5 in Discord
            post = p if isinstance(p, dict) else p.to_dict()
            author = post.get('author', '?')
            content = post.get('content', '')[:300]
            lines.append(f"#{post.get('post_number', '?')} {author}:")
            lines.append(f"  {content}")
            lines.append("")

        # Truncate to fit Discord's 2000 char limit
        output = '\n'.join(lines)
        if len(output) > 1900:
            output = output[:1900] + "\n..."

        await msg.channel.send(f"```\n{output}\n```")

        # Also save the full scrape
        client.save_thread_scrape(thread_data)
        Path("./knowledge_base/.trigger_reindex").touch()

    except Exception as e:
        log_error(f"Forum read error: {e}")
        await msg.channel.send(f"```\nerror reading thread: {e}\n```")


async def _handle_reply(ctx, msg, thread_id: int):
    """Generate an AI reply and post it to a thread with confirm/cancel preview."""
    from utils.social.kaia_forum import get_forum_client
    from utils.social.kaia_social_responder import load_persona
    from ollama import AsyncClient
    import discord

    client = await get_forum_client()
    if not client:
        await msg.channel.send("```\nforum client not available.\n```")
        return

    async with msg.channel.typing():
        try:
            # 1. Scrape latest context (last 15 posts for better context)
            thread_data = await client.scrape_thread(thread_id, last_n_posts=15)
            if not thread_data.get('posts'):
                await msg.channel.send(f"```\ncouldn't find content for thread {thread_id}.\n```")
                return

            # Save so RAG sees it
            client.save_thread_scrape(thread_data)

            # 2. Detect forum category from thread content
            title = thread_data.get('title', 'Unknown Thread')
            posts = thread_data['posts']

            # Heuristic: detect if this is a tech support thread
            tech_keywords = [
                'install', 'crash', 'error', 'titanium', 'wineq', 'dgvoodoo',
                'resolution', 'fps', 'lag', 'login', 'password', 'patch',
                'client', 'eqclient.ini', 'directx', 'driver', 'firewall',
                'port', 'connection', 'timeout', 'freeze', 'black screen',
                'wine', 'mac', 'linux', 'proton', 'lutris', 'sound', 'audio',
                'zone', 'loading', 'disconnect', 'help me', 'how do i',
                'can someone help', 'having trouble', 'not working', 'broken',
            ]
            all_text = (title + ' ' + ' '.join(
                (p.get('content', '') if isinstance(p, dict) else p.to_dict().get('content', ''))[:200]
                for p in posts
            )).lower()
            is_tech_thread = sum(1 for kw in tech_keywords if kw in all_text) >= 2

            # 3. Format thread for the LLM
            thread_summary = [f"Thread Title: {title}\n"]
            for p in posts:
                post = p if isinstance(p, dict) else p.to_dict()
                author = post.get('author', 'Unknown')
                content = post.get('content', '')
                thread_summary.append(f"#{post.get('post_number')} {author}: {content}")

            context_text = "\n---\n".join(thread_summary)
            if len(context_text) > 6000:
                context_text = "...\n" + context_text[-6000:]

            # 4. Query RAG for relevant knowledge (tech threads only)
            rag_context = ""
            if is_tech_thread:
                try:
                    from utils.core.kaia_rag_query import query_rag
                    # Build a search query from the thread title and first post
                    first_post_content = ""
                    if posts:
                        fp = posts[0] if isinstance(posts[0], dict) else posts[0].to_dict()
                        first_post_content = fp.get('content', '')[:500]
                    search_query = f"{title} {first_post_content}"

                    rag_results = await query_rag(search_query, top_k=3)
                    if rag_results:
                        rag_snippets = []
                        for r in rag_results:
                            text = r.get('text', '') if isinstance(r, dict) else str(r)
                            if text:
                                rag_snippets.append(text[:800])
                        if rag_snippets:
                            rag_context = (
                                "\n\nRELEVANT KNOWLEDGE BASE (use this to inform your answer):\n"
                                + "\n---\n".join(rag_snippets)
                            )
                            log_info(f"RAG retrieved {len(rag_snippets)} relevant docs for forum reply")
                except Exception as e:
                    log_debug(f"RAG query for forum reply failed (non-fatal): {e}")

            # 5. Construct forum-aware prompt
            system_prompt = load_persona()

            if is_tech_thread:
                task_prompt = (
                    f"You are replying to a TECHNICAL SUPPORT thread on the Project 1999 forums.\n\n"
                    f"THREAD CONTEXT:\n{context_text}\n"
                    f"{rag_context}\n\n"
                    f"TASK:\n"
                    f"Write a helpful, knowledgeable reply as a P99 community veteran.\n"
                    f"- Address the specific technical issue in the thread\n"
                    f"- Provide clear, actionable steps if you know the fix\n"
                    f"- Reference specific files, settings, or tools when relevant\n"
                    f"- If you don't know the answer, suggest where they might look\n"
                    f"- Write naturally like a forum regular, not like a support bot\n"
                    f"- Keep it concise (2-5 sentences)\n\n"
                    f"REPLY:"
                )
            else:
                task_prompt = (
                    f"You are replying to a thread on the Project 1999 forums.\n\n"
                    f"THREAD CONTEXT:\n{context_text}\n\n"
                    f"TASK:\n"
                    f"Write a natural, human-like forum reply.\n"
                    f"- Match the tone of the thread (casual, serious, humorous)\n"
                    f"- Reference specific things people said in the thread\n"
                    f"- Share a relevant opinion or experience if applicable\n"
                    f"- Write like a real forum regular — no corporate speak\n"
                    f"- Keep it concise (2-4 sentences)\n\n"
                    f"REPLY:"
                )

            # 6. Generate with LLM
            from utils.infrastructure.system.yaml_config import config
            ollama_url = config.get('ollama.host', 'http://localhost:11434')
            ollama_client = AsyncClient(host=ollama_url)

            from utils.infrastructure.gpu.gpu_manager import OllamaGPUManager
            gpu_manager = OllamaGPUManager(config.chat_model)
            options = gpu_manager.get_gpu_options(for_chat=True)
            options['temperature'] = 0.7 if is_tech_thread else 0.8

            response = await asyncio.wait_for(
                ollama_client.chat(
                    model=config.chat_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": task_prompt}
                    ],
                    options=options,
                    keep_alive=-1
                ),
                timeout=120.0
            )

            ai_reply = response['message']['content'].strip()

            # Apply bot speak filtering (strip roleplay markers)
            from utils.core.response_filter import BotSpeakFilter
            ai_reply = BotSpeakFilter.harden(ai_reply)

            if not ai_reply:
                await msg.channel.send("```\nfailed to generate a coherent reply.\n```")
                return

            # 7. Show preview with confirm/cancel buttons
            mode_label = "🔧 TECH SUPPORT" if is_tech_thread else "💬 CASUAL"
            preview_text = (
                f"```\n"
                f"[{mode_label}] Reply preview for '{title}':\n\n"
                f"{ai_reply}\n"
                f"```"
            )

            # Create confirm/cancel view
            view = _ForumReplyConfirmView(client, thread_id, title, ai_reply, msg.author.id)
            await msg.channel.send(preview_text, view=view)
            return  # Don't post yet — wait for button click

        except Exception as e:
            log_error(f"AI forum reply failed: {e}")
            import traceback
            log_debug(traceback.format_exc())
            await msg.channel.send(f"```\nerror generating reply: {e}\n```")


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
                await interaction.followup.send(
                    f"```\n✅ posted to '{title}':\n\n{reply_text}\n```"
                )
                log_success(f"Forum reply posted to thread {thread_id}")
            else:
                await interaction.followup.send("```\n❌ failed to post. check rate limits.\n```")
            view.stop()

        async def _cancel(interaction: discord.Interaction):
            if interaction.user.id != author_id:
                await interaction.response.send_message("not your button.", ephemeral=True)
                return
            await interaction.response.edit_message(content="```\ncancelled.\n```", view=None)
            view.stop()

        async def _regen(interaction: discord.Interaction):
            if interaction.user.id != author_id:
                await interaction.response.send_message("not your button.", ephemeral=True)
                return
            await interaction.response.edit_message(
                content="```\nregenerating... use !forum reply again.\n```", view=None
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
            await msg.channel.send("```\nforum not configured or login failed.\n```")
            return

        await msg.channel.send(f"```\ndeep-scraping user {user_id}...\n```")

        async with msg.channel.typing():
            # Scrape profile metadata
            profile = await client.scrape_user_profile(user_id)
            username = profile.get('username', f'User_{user_id}')

            # Scrape basic post history (snippets) to get thread links
            posts = await client.scrape_user_post_history(user_id, username, max_pages=20)

            # visit top threads for FULL context (Deep Crawl)
            await msg.channel.send(f"```\ndeep-crawling threads for full content...\n```")
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
                await msg.channel.send(f"```\ngenerating AI personality profile...\n```")
                await client.generate_personality_profile(username, user_id, all_results, profile)
                
                # Save the big history file
                filepath = client.save_user_post_history(username, user_id, profile, all_results)
                Path("./knowledge_base/.trigger_reindex").touch()

        # Report
        total = profile.get('total_posts', '?')
        rank = profile.get('rank', '?')
        joined = profile.get('join_date', '?')

        # IDENTITY LINKING: Check for linked Discord ID
        from utils.social.kaia_identities import registry
        linked_discord = registry.get_discord_id(user_id)
        linked_info = f"  linked discord: {linked_discord}\n" if linked_discord else ""

        await msg.channel.send(
            f"```\n"
            f"user: {username}\n"
            f"  rank: {rank}\n"
            f"  total forum posts: {total}\n"
            f"  joined: {joined}\n"
            f"{linked_info}"
            f"  posts scraped: {len(posts)}\n"
            f"  saved to: knowledge_base/user_logs/forum_{username}_{user_id}/\n"
            f"```"
        )

    except Exception as e:
        log_error(f"Forum user scrape error: {e}")
        await msg.channel.send(f"```\nuser scrape failed: {e}\n```")


async def _handle_link(ctx, msg, forum_id: int):
    """Link a Discord account to a Forum ID."""
    from utils.social.kaia_identities import registry
    from utils.social.kaia_forum import get_forum_client

    discord_id = f"{msg.author.name}_{msg.author.id}"
    
    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send("```\nforum client failure\n```")
            return

        # Optional: Verify user exists on forum
        profile = await client.scrape_user_profile(forum_id)
        forum_name = profile.get('username', 'Unknown')
        
        registry.link_discord_to_forum(discord_id, forum_id)
        
        await msg.channel.send(
            f"```\n"
            f"identity linked:\n"
            f"  discord: {discord_id}\n"
            f"  forum: {forum_name} ({forum_id})\n"
            f"```"
        )
    except Exception as e:
        log_error(f"Identity link error: {e}")
        await msg.channel.send(f"```\nlink failed: {e}\n```")


async def _handle_post(ctx, msg, parts):
    """Post a reply to a forum thread."""
    from utils.social.kaia_forum import get_forum_client

    # Parse: !forum post <thread_id> <message>
    if len(parts) < 3:
        await msg.channel.send("```\nusage: !forum post <thread_id> <message>\n```")
        return

    # Re-split to get thread_id and message properly
    remainder = msg.content.strip()
    # Strip "!forum post "
    remainder = remainder.split(None, 2)[-1] if len(remainder.split(None, 2)) > 2 else ''

    post_parts = remainder.split(None, 1)
    if len(post_parts) < 2 or not post_parts[0].isdigit():
        await msg.channel.send("```\nusage: !forum post <thread_id> <message>\n```")
        return

    thread_id = int(post_parts[0])
    message = post_parts[1]

    try:
        client = await get_forum_client()
        if not client:
            await msg.channel.send("```\nforum not configured or login failed.\n```")
            return

        async with msg.channel.typing():
            success = await client.post_reply(thread_id, message)

        if success:
            await msg.channel.send(f"```\nposted to thread {thread_id}.\n```")
        else:
            await msg.channel.send(f"```\nfailed to post. check rate limits or thread permissions.\n```")

    except Exception as e:
        log_error(f"Forum post error: {e}")
        await msg.channel.send(f"```\npost failed: {e}\n```")
