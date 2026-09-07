"""
Command Registry
================

Single source of truth for Kaia's ``!`` commands: one table describing every
command, its aliases, its handler and the arguments that handler wants. The
dispatcher and ``!help`` both read from it, so a command cannot be added to
one and forgotten in the other.

Matching is on the whole first word. The previous implementation was a chain
of ``content.startswith("!news")`` tests, which routed ``!newsletter`` to the
news handler, ``!artist`` to the art renderer and ``!helper`` to help.
"""

from utils.commands.art_handler import handle_art_command
from utils.commands.audit_handler import handle_flag_command, handle_audit_command
from utils.commands.download_handler import handle_download_command
from utils.commands.dream_handler import handle_dreams_command
from utils.commands.enrich_handler import handle_enrich_command
from utils.commands.explain_handler import handle_explain_command
from utils.commands.forum_handler import handle_forum_command
from utils.commands.help_handler import handle_help_command
from utils.commands.memory_handler import handle_memory_cmd
from utils.commands.news_handler import handle_news_command
from utils.commands.reindex_handler import handle_reindex_command
from utils.commands.rpg_handler import handle_rpg_command
from utils.commands.scores_handler import handle_scores_command
from utils.commands.selfmodel_handler import handle_selfmodel_command
from utils.commands.snapshot_handler import handle_snapshot_command
from utils.commands.social_handler import handle_quip_command
from utils.commands.sysmon_handler import handle_sysmon_command
from utils.commands.system_handler import handle_cache_command
from utils.infrastructure.logging.kaia_logger import log_debug, log_error


# Which extra arguments a handler takes beyond (ctx, msg). Handlers were
# written with three different signatures; naming them here keeps the
# dispatcher from having to know which is which.
RESPONDER = "send_kaia_response"
PERSONA = "load_persona_async"


class Command:
    """One command: how it is invoked, what runs it, and how it is documented.

    ``group`` and ``usage`` exist so ``!help`` renders from this table rather
    than from a hand-maintained copy that drifts out of sync.
    """

    __slots__ = ("name", "aliases", "handler", "extra", "group", "usage", "summary", "owner_only")

    def __init__(self, name, handler, group, summary, usage=None, aliases=(),
                 extra=None, owner_only=False):
        self.name = name
        self.aliases = tuple(aliases)
        self.handler = handler
        self.extra = extra
        self.group = group
        self.usage = usage or f"!{name}"
        self.summary = summary
        self.owner_only = owner_only

    @property
    def invocations(self):
        return (self.name,) + self.aliases


# Groups render in this order in !help.
GROUP_CORE = "🛠️  Core & Diagnostics"
GROUP_MEMORY = "🧠  Cognitive & Memory"
GROUP_KNOWLEDGE = "📚  Knowledge & Ingestion"
GROUP_RPG = "⚔️  Aethelgard TTRPG & Fishing"
GROUP_MEDIA = "🎭  Media & Operations"

GROUP_ORDER = (GROUP_CORE, GROUP_MEMORY, GROUP_KNOWLEDGE, GROUP_RPG, GROUP_MEDIA)


COMMANDS = (
    # ── Core & Diagnostics ───────────────────────────────────────────
    Command("help", handle_help_command, GROUP_CORE, extra=RESPONDER,
            summary="Display this command directory"),
    Command("explain", handle_explain_command, GROUP_CORE, extra=RESPONDER,
            owner_only=True,
            summary="Inspect RAG provenance & source scores for the last response"),
    Command("flag", handle_flag_command, GROUP_CORE, extra=RESPONDER,
            owner_only=True, usage="!flag <construct>",
            summary="Flag retrieval nodes with a Data Rot label"),
    Command("audit", handle_audit_command, GROUP_CORE, extra=RESPONDER,
            owner_only=True,
            summary="Show audit flag statistics"),

    # ── Cognitive & Memory ───────────────────────────────────────────
    Command("scores", handle_scores_command, GROUP_MEMORY,
            aliases=("score", "leaderboard", "halloffame", "stats"),
            usage="!scores",
            summary="Interactive leaderboards & memory analytics "
                    "(`!leaderboard`, `!stats`, `!halloffame`)"),
    Command("dream", handle_dreams_command, GROUP_MEMORY, extra=PERSONA,
            aliases=("dreams",), owner_only=True, usage="!dream [list|generate|stats]",
            summary="Manage dream reflections"),
    Command("memory", handle_memory_cmd, GROUP_MEMORY, extra=RESPONDER,
            owner_only=True, usage="!memory [beliefs|anchors]",
            summary="Inspect belief and anchor stores"),
    Command("selfmodel", handle_selfmodel_command, GROUP_MEMORY, extra=RESPONDER,
            owner_only=True,
            summary="Regenerate the 30-day self-model document "
                    "(not injected into prompts by default — see "
                    "`features.self_model_injection`)"),
    Command("snapshot", handle_snapshot_command, GROUP_MEMORY, extra=RESPONDER,
            owner_only=True,
            summary="Save a snapshot of the current conversation"),

    # ── Knowledge & Ingestion ────────────────────────────────────────
    Command("enrich", handle_enrich_command, GROUP_KNOWLEDGE, extra=RESPONDER,
            owner_only=True, usage="!enrich [category]",
            summary="Auto-enrich knowledge-base metadata via LLM"),
    Command("reindex", handle_reindex_command, GROUP_KNOWLEDGE, extra=RESPONDER,
            owner_only=True, usage="!reindex [--full]",
            summary="Rebuild hybrid BM25/vector RAG indices"),
    # Open to everyone: downloads are staged in knowledge_base/_ingress/, which
    # the RAG indexer skips, so nothing is retrievable until process_ingress.py
    # has cleaned and filed it.
    Command("download", handle_download_command, GROUP_KNOWLEDGE, extra=RESPONDER,
            usage="!download <url>",
            summary="Submit a URL for the knowledge base (filed on the next hourly pass)"),
    Command("cache", handle_cache_command, GROUP_KNOWLEDGE,
            owner_only=True,
            summary="Show system cache stats"),

    # ── Aethelgard TTRPG & Fishing ───────────────────────────────────
    Command("rpg", handle_rpg_command, GROUP_RPG, extra=RESPONDER,
            usage="!rpg [subcommand]",
            summary="Turn-based RPG status board & command menu "
                    "(`!rpg help` for the full class guide)"),

    # ── Media & Operations ───────────────────────────────────────────
    Command("news", handle_news_command, GROUP_MEDIA, extra=RESPONDER,
            summary="Fetch and summarize latest news"),
    Command("quip", handle_quip_command, GROUP_MEDIA,
            summary="Generate a social media draft post "
                    "(10-minute cooldown; owners are exempt)"),
    Command("art", handle_art_command, GROUP_MEDIA, extra=RESPONDER,
            usage="!art [--seed N] [--palette NAME]",
            summary="Render fractal flame art"),
    # Not owner_only: `!forum link <uid>` returns before the owner gate, so any
    # user can link their account. Every other subcommand is admin. Marking the
    # whole command admin hid the one part users are meant to reach.
    Command("forum", handle_forum_command, GROUP_MEDIA, extra=RESPONDER,
            usage="!forum link <uid>",
            summary="Link your forum account "
                    "(other `!forum` subcommands are admin-only)"),
    Command("sysmon", handle_sysmon_command, GROUP_MEDIA, extra=RESPONDER,
            owner_only=True,
            summary="Live system/hardware monitoring dashboard"),
)


def _build_lookup():
    """Map every invocation to its command, rejecting duplicates at import."""
    table = {}
    for cmd in COMMANDS:
        for word in cmd.invocations:
            key = f"!{word}"
            if key in table:
                raise ValueError(
                    f"Duplicate command invocation {key!r}: "
                    f"{table[key].name} and {cmd.name}"
                )
            table[key] = cmd
    return table


LOOKUP = _build_lookup()


def resolve(content: str):
    """Return the Command for a message, or None.

    Only the first whitespace-delimited word is considered, so ``!news`` and
    ``!news tech`` both resolve while ``!newsletter`` does not.
    """
    if not content:
        return None
    stripped = content.strip()
    if not stripped.startswith("!"):
        return None
    return LOOKUP.get(stripped.split(maxsplit=1)[0].lower())


async def dispatch_command(ctx, msg, load_persona_async, send_kaia_response):
    """Route a message to its command handler.

    Returns True if the message was a command (whether or not the handler
    succeeded), so the caller knows not to treat it as conversation.
    """
    cmd = resolve(msg.content)
    if cmd is None:
        return False

    extras = {RESPONDER: send_kaia_response, PERSONA: load_persona_async}
    args = (ctx, msg) if cmd.extra is None else (ctx, msg, extras[cmd.extra])

    try:
        await cmd.handler(*args)
    except Exception as e:
        # A failing command must not fall through to the chat pipeline, which
        # would answer "!reindex --full" as if it were conversation.
        import traceback
        log_error(f"Command !{cmd.name} raised: {e}\n{traceback.format_exc()}")
        try:
            await msg.channel.send(f"```\n!{cmd.name} failed. check the logs.\n```")
        except Exception:
            pass
    else:
        log_debug(f"Dispatched !{cmd.name} for {msg.author.name}")
    return True
