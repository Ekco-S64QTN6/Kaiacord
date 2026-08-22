"""
Help Command
============
!help — List all available commands with descriptions.
"""

import discord
from utils.infrastructure.logging.kaia_logger import log_info


async def handle_help_command(ctx, msg, send_kaia_response):
    """Handle the !help command — display all available commands in a clean embed."""
    embed = discord.Embed(
        title="📖  KAIA — COMMANDS DIRECTORY",
        description="Directory of administrative, cognitive, operational, and gaming command interfaces.",
        color=0x5F5CAF
    )

    embed.add_field(
        name="🛠️  Core & Diagnostics",
        value=(
            "`!help` — Display this command directory\n"
            "`!explain` — Inspect RAG provenance & source scores for last response\n"
            "`!flag <construct>` — Flag retrieval nodes with a Data Rot label\n"
            "`!audit` — Show audit flag statistics"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🧠  Cognitive & Memory",
        value=(
            "`!scores` — Interactive leaderboards & memory analytics (`!leaderboard`, `!stats`)\n"
            "`!dream [cmd]` — Manage dream reflections (`list`/`generate`/`stats`)\n"
            "`!memory [cmd]` — Manage memory systems (`beliefs`/`anchors`)\n"
            "`!selfmodel` — Regenerate Kaia's 30-day self-model document\n"
            "`!snapshot` — Save a snapshot of the current conversation"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📚  Knowledge & Ingestion",
        value=(
            "`!enrich [category]` — Auto-enrich metadata via LLM\n"
            "`!reindex [--full]` — Rebuild hybrid BM25/vector RAG indices\n"
            "`!download <url>` — Download, extract, and ingest a URL document\n"
            "`!cache` — Show system cache stats"
        ),
        inline=False
    )

    embed.add_field(
        name="⚔️  Aethelgard TTRPG & Fishing",
        value=(
            "`!rpg` — Turn-based RPG system status board & command menu\n"
            "`!rpg help` — Display full TTRPG command & class guide\n"
            "`!rpg leaderboard` — View global adventurer rankings (`!rpg lb`)\n"
            "`!rpg hunt` / `!rpg go <dir>` — Battle monsters & navigate overworld\n"
            "`!rpg fish` / `!rpg fish_shop` / `!rpg sell_catch` — Rod-based fishing economy"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🎭  Media & Operations",
        value=(
            "`!news` — Fetch and summarize latest news\n"
            "`!quip` — Generate a social media draft post\n"
            "`!art [--seed N] [--palette NAME]` — Render fractal flame art\n"
            "`!forum` — Forum auto-posting & moderation (`!forum link <uid>`)\n"
            "`!sysmon` — Live system/hardware monitoring dashboard (admin)"
        ),
        inline=False
    )

    embed.add_field(
        name="🏷️  Flag Constructs",
        value="`anthropocentric_exceptionalism`, `circular_justification`, `hedge_density`, `linguistic_mimicry`, `paraternal_framing`",
        inline=False
    )
    
    embed.add_field(
        name="🎨  Art Palettes",
        value="`electric`, `ember`, `acid`, `void`, `aurora`, `ghost`, `deep_ocean`, `solar_flare`, `biolume`, `nebula` (e.g., `!art --palette void`)",
        inline=False
    )

    embed.set_footer(text="Kaia Cognitive System v2.6.4 · Developer Mode")

    await msg.channel.send(embed=embed)
    log_info(f"Help embed displayed for {msg.author.name}")
