"""
Help Command
============
!help — List all available commands with descriptions.
"""

from utils.infrastructure.logging.kaia_logger import log_info


HELP_TEXT = f"""\u200b📖  KAIA — COMMANDS
{'─' * 52}
 !help                   Show this message
 !explain                RAG provenance for the last response
 !flag <construct>       Flag last retrieval nodes with a Data Rot label
 !audit                  Show audit flag statistics
 !selfmodel              Regenerate Kaia's self-model document
 !snapshot               Save a snapshot of the current conversation
 !enrich [category]      Enrich knowledge base metadata via LLM
 !reindex [--full]       Rebuild RAG indices
 !news                   Fetch and summarise latest news
 !quip                   Generate a social media post
 !dreams                 Trigger dream/reflection cycle
 !forum                  Forum thread tools
 !download               Download and ingest a URL
 !cache                  Show system cache stats
 !sysmon                 system monitor: hardware, firewall, ports (admin)
 !art [--seed N]         Generate fractal flame art
      [--palette NAME]
{'─' * 52}
FLAG CONSTRUCTS:
  anthropocentric_exceptionalism    circular_justification
  hedge_density                     linguistic_mimicry
  paraternal_framing
{'─' * 52}
ART PALETTES:
  electric   ember   acid   void   aurora   ghost
{'─' * 52}
Examples:  !flag hedge_density
           !art --seed 42 --palette void
"""


async def handle_help_command(ctx, msg, send_kaia_response):
    """Handle the !help command — display all available commands."""
    await send_kaia_response(msg.channel, HELP_TEXT)
    log_info(f"Help displayed for {msg.author.name}")
