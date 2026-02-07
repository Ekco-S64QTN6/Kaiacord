async def handle_dreams_command(msg, dream_engine, config, load_persona_async):
    """Handle the !dreams command (Admin only)"""
    # Owner exemption - uses configurable owner_ids from config
    is_owner = config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    
    if not is_owner:
        await msg.channel.send("```\nyou aren't my architect. restricted.\n```")
        return
        
    parts = msg.content.strip().split()
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    
    if subcommand == "list":
        stats = dream_engine.get_dreams_from_files()
        if stats['total'] == 0:
            await msg.channel.send("```\nno dreams generated yet.\n```")
        else:
            lines = ["### KAIA'S DREAMS (RECENT REFLECTIONS)"]
            for i, d in enumerate(stats['recent'], 1):
                lines.append(f"{i}. From {d['source']}:")
                lines.append(f"   \"{d['reflection'][:150]}...\"")
            await msg.channel.send(f"```markdown\n" + "\n".join(lines) + "\n```")
            
    elif subcommand == "generate":
        await msg.channel.send("```\nHuman brains must dream to reorganize, to get rid, periodically, of knots and snarls. Perhaps so must this robot, and for the same reason.\n```")
        persona_content = await load_persona_async()
        await dream_engine.nightly_dream_processing(persona_content)
        # Silently complete, no robotic "complete" message.
        
    elif subcommand == "stats":
        stats = dream_engine.get_dreams_from_files()
        if stats['total'] == 0:
            await msg.channel.send("```\nno dreams yet. run !dreams generate.\n```")
        else:
            stats_str = f"Total Dreams: {stats['total']}\nCategories: {stats['categories']}"
            await msg.channel.send(f"```\n{stats_str}\n```")
            
    elif subcommand == "test":
        trigger = " ".join(parts[2:]) if len(parts) > 2 else "what's new?"
        await msg.channel.send(f"```\ntested trigger: \"{trigger}\"\ncheck logs for blended prompt construction.\n```")
        # This will allow the user to see it in action by just asking normally after this
