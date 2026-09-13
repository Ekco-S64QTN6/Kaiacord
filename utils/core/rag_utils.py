def get_node_text(node) -> str:
    """Extract text content from RAG node regardless of format (DRY helper)."""
    if not node: return ""
    
    # Handle NodeWithScore wrapper
    if hasattr(node, 'node'):
        node = node.node
        
    if hasattr(node, 'get_content'):
        return node.get_content()
    if hasattr(node, 'text'):
        return node.text
    if isinstance(node, dict):
        return node.get('text', node.get('content', ''))
    return str(node)

def get_node_metadata(node) -> dict:
    """Extract metadata from RAG node regardless of format."""
    if not node: return {}
    
    # Handle NodeWithScore wrapper
    if hasattr(node, 'node'):
        node = node.node
        
    if hasattr(node, 'metadata'):
        return node.metadata
    if isinstance(node, dict):
        return node.get('metadata', {})
    return {}


def speaker_from_log_path(path: str) -> str:
    """The display name of whoever owns a user_logs path, or ''.

    `knowledge_base/user_logs/Starkind_519557167779676160/interactions_20260912.md`
    -> `Starkind`. The directory is the only thing that identifies whose log a
    chunk came from: every user's daily file is named `interactions_<date>.md`,
    so a basename is not an identity.

    Exists because `search_recent_events` rebuilt its result metadata from
    scratch with only source_type/file_path/retrieval_method, dropping the
    `user_name` the indexer had set — so every node a recap injected reached the
    prompt unattributed. Starkind posted a fractal URL and wrote "forwarding the
    url to @Ekco he likes fractals"; with no speaker on the node, the only name
    in the text won, and the recap credited the link to Ekco.
    """
    p = (path or "").replace("\\", "/")
    if "/user_logs/" not in p:
        return ""
    try:
        folder = p.split("/user_logs/")[1].split("/")[0]
    except Exception:
        return ""
    if not folder:
        return ""
    # Folders are `<DisplayName>_<discord id>`; the id is a long digit run.
    import re as _re
    name = _re.sub(r"_\d{5,}$", "", folder)
    return name.replace("_", " ").strip()
