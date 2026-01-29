"""
Bot State Manager
=================

Encapsulates global bot state and persistence.

Extracted from Kaiacord.py to improve modularity.
"""

import os
import json
import time
from typing import Dict, Deque, Optional
from collections import deque
from utils.kaia_logger import log_info, log_warning


class BotState:
    """Encapsulates global bot state and persistence"""
    def __init__(self, state_file: str = "storage/bot_state.json"):
        self.state_file = state_file
        self.channel_memory: Dict[int, Deque[Dict[str, str]]] = {}
        self.last_interaction_time: float = time.time()
        self.last_active_channel_id: Optional[int] = None
        self.consecutive_quips: int = 0
        self.is_generating_image: bool = False
        self.load()

    def load(self):
        """Load persisted bot state from JSON file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.last_active_channel_id = state.get('last_active_channel_id')
                    self.consecutive_quips = state.get('consecutive_quips', 0)
                    log_info(f"Loaded last_active_channel_id: {self.last_active_channel_id}, quips: {self.consecutive_quips}")
        except Exception as e:
            log_warning(f"Failed to load bot state: {e}")

    def save(self):
        """Save bot state to JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            
            state = {
                'last_active_channel_id': self.last_active_channel_id,
                'consecutive_quips': self.consecutive_quips,
                'saved_at': time.time()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f)
        except Exception as e:
            log_warning(f"Failed to save bot state: {e}")

    def reset_quips(self):
        """Reset consecutive quips counter"""
        self.consecutive_quips = 0
        self.save()

    def increment_quips(self):
        """Increment consecutive quips counter"""
        self.consecutive_quips += 1
        self.save()

    def update_interaction(self, channel_id: int):
        """Update last interaction time and channel"""
        self.last_interaction_time = time.time()
        if self.last_active_channel_id != channel_id:
            self.last_active_channel_id = channel_id
            self.save()


# Global bot_state instance for backward compatibility
bot_state = BotState()
