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
