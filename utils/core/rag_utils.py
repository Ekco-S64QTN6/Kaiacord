def extract_node_content(node) -> str:
    """Extract text content from RAG node regardless of format (DRY helper)."""
    if hasattr(node, 'text'):
        return node.text
    if hasattr(node, 'content'):
        return node.content
    if isinstance(node, dict):
        return node.get('text') or node.get('content') or str(node)
    return str(node)
