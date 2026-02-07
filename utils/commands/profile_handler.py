import re
from pathlib import Path
from typing import List
from utils.infrastructure.logging.kaia_logger import log_info

def get_known_users() -> List[str]:
    """Scan knowledge base for actual user profiles to prevent hallucinations"""
    users = []
    
    # Check logs (primary source of truth)
    logs_dir = Path("./knowledge_base/user_logs")
    if logs_dir.exists():
        # user_logs contains directories like "Username_123456789/"
        for d in logs_dir.iterdir():
            if d.is_dir():
                # Extract name part (everything before the last underscore usually, but ID is long digits)
                # Format is usually Name_ID
                parts = d.name.split('_')
                if len(parts) > 1 and parts[-1].isdigit():
                    name = "_".join(parts[:-1]).replace("_", " ")
                else:
                    name = d.name.replace("_", " ")
                
                # Try to read profile summary
                profile_path = d / "user_profile.md"
                summary = "No profile available."
                if profile_path.exists():
                    try:
                        with profile_path.open('r', encoding='utf-8') as f:
                            content = f.read()
                            # Extract QUICK REFERENCE section
                            if "QUICK REFERENCE" in content:
                                start = content.find("QUICK REFERENCE")
                                end = content.find("\n\n", start + 20) # Find next double newline
                                if end == -1: end = len(content)
                                summary = content[start:end].replace("QUICK REFERENCE", "").strip()
                            else:
                                # Fallback to first few lines
                                summary = "\n".join(content.split('\n')[:5])
                    except Exception:
                        pass
                
                # Check if we already have this user (by name)
                users.append(f"👤 **{name}**\n*\"{summary}\"*")
                
    return sorted(list(set(users))) # Deduplicate and sort

async def handle_profile_query(msg, sanitized_content, send_kaia_response, run_rag, rag):
    """Handle explicit user list/profile queries"""
    q_lower = sanitized_content.lower().strip()
    
    # Stricter user list detection
    is_user_list_query = False
    if len(q_lower) < 100:
        user_list_patterns = [
            r"kaia\s+(list|show|display)\s+(all\s+)?(users?|profiles?|known users?)",
            r"kaia\s+who\s+do\s+you\s+know",
            r"kaia\s+who\s+is\s+(on\s+this\s+server|here)",
            r"kaia\s+list\s+profiles"
        ]
        is_user_list_query = any(re.search(p, q_lower) for p in user_list_patterns)

    if is_user_list_query:
        log_info("Detected explicit user list query - fetching known users")
        known_users_formatted = get_known_users()
        log_info(f"Found {len(known_users_formatted)} known users")
        
        # Direct response construction
        if known_users_formatted:
            response_text = "Here are the users I'm aware of:\n\n" + "\n\n".join(known_users_formatted)
        else:
            response_text = "I'm aware of you, but I can't seem to access the full user database right now."
        
        # Send directly
        await send_kaia_response(msg.channel, response_text)
        
        # Log interaction
        if run_rag and rag:
            await run_rag(rag.log_user_interaction, msg.author.id, msg.author.display_name, sanitized_content, response_text)
        return True
    return False
