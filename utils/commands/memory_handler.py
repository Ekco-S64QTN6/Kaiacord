import re
from utils.infrastructure.logging.kaia_logger import log_action

async def handle_memory_command(msg, sanitized_content, run_rag, rag):
    """Handle the 'kaia remember' command"""
    # This regex ensures that only explicit "kaia remember [this/that]:" triggers the log
    # It prevents "remember when..." questions from being logged.
    remember_match = re.match(r"kaia remember (?:this|that|to|the following)?:?\s*(.*)", sanitized_content, re.IGNORECASE)
    if remember_match and not re.search(r"\bwhen\b|\bif\b|\bhow\b", sanitized_content, re.IGNORECASE):
        memory_content = remember_match.group(1).strip()
        if memory_content:
            log_action(f"Storing memory: {memory_content}")
            if run_rag and rag:
                success = await run_rag(rag.add_memory, msg.author.id, msg.author.display_name, memory_content)
                if success:
                    await msg.channel.send("```\nLogged it.\n```")
                else:
                    await msg.channel.send("```\nMemory buffer error. Try again.\n```")
        else:
            await msg.channel.send("```\nRemember what? I'm not a mind reader.\n```")
        return True
    return False
