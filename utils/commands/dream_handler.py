import discord


async def handle_dreams_command(ctx, msg, load_persona_async):
    """Handle the !dreams command (Admin only)"""
    # Owner exemption - uses configurable owner_ids from config
    is_owner = ctx.config.is_owner(msg.author.name, msg.author.display_name, str(msg.author.id))
    
    if not is_owner:
        await msg.channel.send("```\nyou aren't my architect. restricted.\n```")
        return
        
    parts = msg.content.strip().split()
    subcommand = parts[1].lower() if len(parts) > 1 else "list"
    
    if subcommand == "list":
        stats = ctx.dream_engine.get_dreams_from_files()
        if stats['total'] == 0:
            embed = discord.Embed(
                title="💤  KAIA'S RECENT DREAMS",
                description="No dreams generated yet.",
                color=0x4f46e5
            )
            await msg.channel.send(embed=embed)
        else:
            embed = discord.Embed(
                title="💤  KAIA'S RECENT DREAMS & REFLECTIONS",
                description="Associative reflections synthesized during offline dream cycles.",
                color=0x4f46e5
            )
            for i, d in enumerate(stats['recent'], 1):
                source = d.get('source', 'unknown')
                category = d.get('category', 'unknown').upper()
                reflection = d.get('reflection', '')
                
                # Clean up source formatting for display
                source_display = source.replace('.md', '').replace('_', ' ').replace('-', ' ').strip()
                source_display = " ".join(source_display.split()).upper()
                
                if len(reflection) > 180:
                    reflection = reflection[:177] + "..."
                embed.add_field(
                    name=f"{i}. {source_display} ({category})",
                    value=f"*{reflection}*",
                    inline=False
                )
            embed.set_footer(text=f"Total Dream Records: {stats['total']} · Kaia System")
            await msg.channel.send(embed=embed)
            
    elif subcommand == "generate":
        embed = discord.Embed(
            title="💤  FORCING DREAM CYCLE",
            description=(
                "*(Human brains must dream to reorganize, to get rid, periodically, of knots and snarls. "
                "Perhaps so must this robot, and for the same reason.)*\n\n"
                "Starting nightly reflection processing..."
            ),
            color=0x8b5cf6
        )
        embed.set_footer(text="Dream generation executes asynchronously in the background.")
        await msg.channel.send(embed=embed)
        
        persona_content = await load_persona_async()
        await ctx.dream_engine.nightly_dream_processing(persona_content)
        
    elif subcommand == "stats":
        stats = ctx.dream_engine.get_dreams_from_files()
        if stats['total'] == 0:
            embed = discord.Embed(
                title="📊  KAIA'S DREAM METRICS",
                description="No dreams recorded yet. Run `!dream generate`.",
                color=0x5f5caf
            )
            await msg.channel.send(embed=embed)
        else:
            embed = discord.Embed(
                title="📊  KAIA'S DREAM METRICS",
                description="Operational statistics for the autonomous reflection synthesis pipeline.",
                color=0x5f5caf
            )
            embed.add_field(name="Total Dreams Synthesized", value=str(stats['total']), inline=True)
            
            cats = stats.get('categories', {})
            cat_lines = []
            for cat_name, count in cats.items():
                cat_lines.append(f"• **{cat_name.title()}**: {count} dreams")
            cat_val = "\n".join(cat_lines) if cat_lines else "None"
            embed.add_field(name="Reflections by Category", value=cat_val, inline=False)
            embed.set_footer(text="Kaia System Dream Engine")
            await msg.channel.send(embed=embed)
            
    elif subcommand == "test":
        trigger = " ".join(parts[2:]) if len(parts) > 2 else "what's new?"
        embed = discord.Embed(
            title="🧪  DREAM TRIGGER TEST",
            description=f"Tested trigger: **\"{trigger}\"**",
            color=0xf59e0b
        )
        embed.add_field(
            name="Action Logged",
            value="Please check logs for blended prompt construction detail.",
            inline=False
        )
        await msg.channel.send(embed=embed)
