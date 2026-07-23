from utils.commands.help_handler import handle_help_command
from utils.commands.news_handler import handle_news_command
from utils.commands.social_handler import handle_quip_command
from utils.commands.dream_handler import handle_dreams_command
from utils.commands.system_handler import handle_cache_command
from utils.commands.download_handler import handle_download_command
from utils.commands.forum_handler import handle_forum_command
from utils.commands.audit_handler import handle_flag_command, handle_audit_command
from utils.commands.snapshot_handler import handle_snapshot_command
from utils.commands.explain_handler import handle_explain_command
from utils.commands.selfmodel_handler import handle_selfmodel_command
from utils.commands.enrich_handler import handle_enrich_command
from utils.commands.reindex_handler import handle_reindex_command
from utils.commands.art_handler import handle_art_command
from utils.commands.sysmon_handler import handle_sysmon_command
from utils.commands.rpg_handler import handle_rpg_command
from utils.commands.memory_handler import handle_memory_cmd
from utils.commands.scores_handler import handle_scores_command

async def dispatch_command(ctx, msg, load_persona_async, send_kaia_response):
    """Route commands to the appropriate handler"""
    content = msg.content.strip()

    if content.startswith("!scores") or content.startswith("!score") or content.startswith("!leaderboard") or content.startswith("!halloffame") or content.startswith("!stats"):
        await handle_scores_command(ctx, msg)
        return True
    
    if content.startswith("!help"):
        await handle_help_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!news"):
        await handle_news_command(ctx, msg, send_kaia_response)
        return True
        
    if content.startswith("!quip"):
        await handle_quip_command(ctx, msg)
        return True
        
    if content.startswith("!dreams") or content.startswith("!dream"):
        await handle_dreams_command(ctx, msg, load_persona_async)
        return True

    if content.startswith("!memory"):
        await handle_memory_cmd(ctx, msg, send_kaia_response)
        return True
        
    if content.startswith("!cache"):
        await handle_cache_command(ctx, msg)
        return True
    
    if content.startswith("!download"):
        await handle_download_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!forum"):
        await handle_forum_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!flag"):
        await handle_flag_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!audit"):
        await handle_audit_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!snapshot"):
        await handle_snapshot_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!explain"):
        await handle_explain_command(ctx, msg, send_kaia_response)
        return True
        
    if content.startswith("!selfmodel"):
        await handle_selfmodel_command(ctx, msg, send_kaia_response)
        return True
        
    if content.startswith("!enrich"):
        await handle_enrich_command(ctx, msg, send_kaia_response)
        return True
        
    if content.startswith("!reindex"):
        await handle_reindex_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!sysmon"):
        await handle_sysmon_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!art"):
        await handle_art_command(ctx, msg, send_kaia_response)
        return True

    if content.startswith("!rpg"):
        await handle_rpg_command(ctx, msg, send_kaia_response)
        return True

    return False
