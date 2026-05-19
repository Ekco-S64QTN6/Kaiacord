"""
Theory of Mind Lite — Session-Based User State Modeling
======================================================

Maintains a lightweight, ephemeral representation of the user's apparent
emotional state, conversational energy, and intent.
"""

import time
import re
from typing import Dict, Any

class KaiaUserModel:
    """Session-based Theory of Mind tracker for active users."""
    
    def __init__(self):
        # Ephemeral session states format:
        # { user_id: { "apparent_mood": str, "energy": str, "likely_intent": str, "last_updated": float } }
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self.SESSION_TTL = 7200.0  # 2 hours session boundary

    def get_user_state(self, user_id: str, author_name: str, message_text: str) -> Dict[str, Any]:
        """Fetch and update user's session-based Theory of Mind state."""
        uid = str(user_id)
        now = time.time()
        
        # Check if session exists and is fresh
        session = self._sessions.get(uid)
        if not session or (now - session.get("last_updated", 0.0) > self.SESSION_TTL):
            # Start fresh session state
            session = {
                "apparent_mood": "neutral",
                "energy": "moderate",
                "likely_intent": "conversational",
                "last_updated": now
            }
            self._sessions[uid] = session

        # Analyze current message to update session
        self._update_session_heuristics(session, message_text)
        session["last_updated"] = now
        return session

    def _update_session_heuristics(self, session: Dict[str, Any], text: str):
        """Parse text for indicators of mood, energy, and intent (heuristics only, low overhead)."""
        text_lower = text.lower()
        
        # 1. APPARENT MOOD CLASSIFICATION
        mood_words = {
            "playful": ["haha", "lol", "lmao", "rofl", "xd", "joke", "funny", "pog", "hype"],
            "positive": ["happy", "excited", "good", "great", "awesome", "glad", "hyped", "wonderful", "love", "perfect"],
            "venting/frustrated": ["frustrated", "annoyed", "angry", "mad", "upset", "terrible", "awful", "bad", "hate", "shit", "fuck", "sucks"],
            "anxious/stressed": ["anxious", "worried", "nervous", "stressed", "scared", "afraid", "panic"],
            "reflective/somber": ["sad", "depressed", "lonely", "miss", "grief", "sorry", "hurt", "thinking", "pondering"],
            "tired": ["tired", "sleepy", "exhausted", "fatigued", "groggy", "drained", "yawning"]
        }
        
        detected_moods = []
        for mood, indicators in mood_words.items():
            if any(ind in text_lower for ind in indicators):
                detected_moods.append(mood)
                
        if detected_moods:
            # Shift towards the most prominent/recent detected mood (EMA-style preference)
            session["apparent_mood"] = detected_moods[0]
            
        # 2. ENERGY LEVEL CLASSIFICATION
        words = text_lower.split()
        word_count = len(words)
        exclamation_count = text.count("!")
        emoji_count = len(re.findall(r'<a?:[a-zA-Z0-9_]+:[0-9]+>|[\u263a-\u1f999]', text))
        
        # High energy indicators
        if exclamation_count >= 2 or emoji_count >= 2 or word_count > 45 or any(w in text_lower for w in ["hype", "hyped", "lfg", "omg", "woot"]):
            session["energy"] = "high"
        # Low energy indicators
        elif word_count < 4 or any(w in text_lower for w in ["tired", "yawn", "sleepy", "sigh", "meh", "bored"]):
            session["energy"] = "low"
        else:
            session["energy"] = "moderate"
            
        # 3. LIKELY INTENT CLASSIFICATION
        if any(text_lower.startswith(w) for w in ["why", "how", "what", "who", "where", "can you", "should i"]) or "?" in text_lower:
            # Check for seeking advice vs straight asking
            if any(w in text_lower for w in ["should i", "do you think i", "how do i", "advice", "suggest"]):
                session["likely_intent"] = "seeking advice"
            else:
                session["likely_intent"] = "seeking answers"
        elif any(w in text_lower for w in ["haha", "lol", "joke", "troll", "meme"]):
            session["likely_intent"] = "humorous bantering"
        elif any(w in text_lower for w in ["sucks", "annoyed", "frustrated", "so bad", "hate"]):
            session["likely_intent"] = "venting emotions"
        elif any(text_lower.startswith(w) for w in ["i did", "i made", "i have", "i built", "look at"]):
            session["likely_intent"] = "sharing accomplishments"
        else:
            session["likely_intent"] = "general discussion"
