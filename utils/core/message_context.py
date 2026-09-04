from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import discord
import time
from utils.core.kaia_intelligence import Intent

@dataclass
class MessageContext:
    """Holds the state of a single message being processed through the pipeline."""
    message: discord.Message
    sanitized_content: str
    is_social: bool = False
    is_mention: bool = False
    is_dm: bool = False
    category: str = "GENERAL"
    root_context: Optional[str] = None
    parent_context: Optional[str] = None
    intent: Optional[Intent] = None
    fast_intent_strategy: Optional[str] = None  # Stashed from fast-path, immune to async overwrite
    history: List[Dict[str, str]] = field(default_factory=list)
    
    # Retrieval & Intelligence
    cached_response: Optional[str] = None
    retrieved_context: str = ""
    status_context: str = ""
    retrieval_confidence: float = 0.0   # 0.0–1.0 avg score of retrieved nodes; 0 = nothing found
    retrieval_node_count: int = 0       # How many nodes passed the threshold
    raw_nodes: List[Any] = field(default_factory=list)
    context_nodes: List[Any] = field(default_factory=list)
    system_prompt: str = ""
    user_traits: Dict[str, Any] = field(default_factory=dict)
    knowledge_boundary_check: Dict[str, Any] = field(default_factory=dict)
    classification_task: Optional[Any] = None
    _is_channel_recall: bool = False
    _channel_refs: Optional[List[str]] = None
    
    # Timing & Performance
    start_time: float = field(default_factory=time.time)
    # Timings dict is unused in core flow, kept for telemetry if needed but removed logic from processor
    
    # Result
    response_text: Optional[str] = None
    
    @property
    def author_id(self) -> str:
        author = getattr(self.message, 'author', None) if self.message else None
        return str(getattr(author, 'id', '0')) if author else "0"
        
    @property
    def author_name(self) -> str:
        author = getattr(self.message, 'author', None) if self.message else None
        if not author:
            return "unknown"
        return getattr(author, 'display_name', getattr(author, 'name', 'unknown')) or "unknown"
        
    @property
    def channel_id(self) -> int:
        channel = getattr(self.message, 'channel', None) if self.message else None
        return getattr(channel, 'id', 0) if channel else 0
