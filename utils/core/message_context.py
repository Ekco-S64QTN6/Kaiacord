from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import discord
from utils.core.kaia_intelligence import Intent

@dataclass
class MessageContext:
    """Holds the state of a single message being processed through the pipeline."""
    message: discord.Message
    sanitized_content: str
    is_social: bool = False
    is_mention: bool = False
    category: str = "GENERAL"
    intent: Optional[Intent] = None
    parent_context: Optional[str] = None
    
    # Retrieval & Intelligence
    cached_response: Optional[str] = None
    retrieved_context: str = ""
    status_context: str = ""
    
    # Timing & Performance
    start_time: float = field(default_factory=float)
    timings: Dict[str, float] = field(default_factory=dict)
    
    # Result
    response_text: Optional[str] = None
    
    @property
    def author_id(self) -> str:
        return str(self.message.author.id)
        
    @property
    def author_name(self) -> str:
        return self.message.author.display_name
        
    @property
    def channel_id(self) -> int:
        return self.message.channel.id
