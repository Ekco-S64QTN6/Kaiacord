import re
import time
import threading
import asyncio
from ollama import Client
from typing import Optional, Dict, Any

class FixedQueryClassifier:
    """Query classifier with timeout and improved performance"""
    
    def __init__(self, ollama_client=None, model="gemma3:12b", logger=None, host="http://localhost:11434", timeout=5.0):
        # Note: ollama_client arg kept for compatibility but we create a new sync client for the thread
        self.model = model
        self.logger = logger or print
        self.timeout = 2.0 # Reduced from 5.0 for better responsiveness
        self.host = host
        
        # Create Ollama client with shorter timeout for the synchronous thread
        self.sync_client = Client(host=host, timeout=timeout)
        
        # Lighter model for classification (faster response)
        self.classification_model = "gemma2:2b"  # Smaller, faster model
        
        # Define classification options - CPU ONLY for speed
        self.classification_options = {
            "num_gpu": 0,           # CPU only for classification
            "num_thread": 4,        # Reduced from 8 to avoid contention
            "num_ctx": 1024,        # Smaller context for classification
            "temperature": 0.1,     # Low temperature for consistent classification
            "top_p": 0.9,
            "top_k": 40,
        }
        
        # Enhanced rule-based patterns (fast, no model needed)
        self.patterns = {
            "GREETING": [
                r"^\s*(hi|hello|hey|greetings|sup|yo)\s*$",
                r"^\s*(hi|hello|hey)\s+kaia",
                r"^\s*kaia\s*(hi|hello|hey)"
            ],
            "IDENTITY": [
                r"^\s*(who\s*(are\s*you|am\s*i|is\s*this))\s*[?]?\s*$",
                r"^\s*tell\s+me\s+about\s+(yourself|you)\s*[?]?\s*$",
                r"^\s*what\s+are\s+you\s*[?]?\s*$"
            ],
            "ENTITY": [  # NEW: Entity/identity queries
                r"^\s*who (is|are|was|were) ",
                r"^\s*tell me about ",
                r"^\s*what do you know about ",
                r"^\s*who the (hell|fuck) is ",
                r"^\s*who's ",
                r"^\s*explain ",
                r"^\s*describe ",
                r"^\b(mark|elara|thorne|jules|elias)\b"  # Specific names mentioned
            ],
            "NEWS": [  # NEW: Direct news pattern matching
                r"news\s+(about|on|regarding)",
                r"what('?s| is) the (latest|recent|current|today'?s) news",
                r"tell\s+me\s+(the\s+)?news",
                r"any\s+(new|recent)\s+updates",
                r"what'?s\s+happening",
                r"current\s+events",
                r"headlines",
                r"breaking\s+news"
            ],
            "POLITICS": [
                r"politics|political|election|government|senate|congress",
                r"president|prime minister|minister|policy|legislation"
            ],
            "TECH": [
                r"tech(nology)?|software|hardware|ai\s+news|llm|gpt",
                r"openai|google|meta|microsoft|apple|tesla|spacex",
                r"quantum|computer|chip|processor|gpu|cpu",
                r"starkind|architecture|mitigate"
            ],
            "SECURITY": [
                r"security|hack|breach|cyber|attack|vulnerability|cve",
                r"ransomware|malware|phishing|zero.?day|exploit"
            ],
            "COMMAND": [
                r"^\s*(status|statistics|stats|info|ping|uptime)\s*$",
                r"^\s*(list|show|display)\s+users?\s*$",
                r"^\s*(clear|reset|clean|refresh)\s*$"
            ],
            "PERSONAL": [
                r"how (are|is) you",
                r"how'?s it going",
                r"how are you feeling",
                r"you okay",
                r"what'?s up",
                r"feeling now"
            ],
            "CASUAL": [
                r"^(yeah|no|maybe|ok|okay|sure|cool|nice|thanks|thank you|thx)$",
                r"^(lol|lmao|haha|wow|interesting)$"
            ]
        }
        
        self.category_descriptions = {
            "GREETING": "Greeting or casual conversation",
            "IDENTITY": "Questions about identity",
            "NEWS": "News and current events",
            "POLITICS": "Political news and discussions",
            "TECH": "Technology news and developments",
            "SECURITY": "Security and cybersecurity topics",
            "COMMAND": "Bot commands and status requests",
            "GENERAL": "General conversation and questions",
            "KNOWLEDGE": "Knowledge-based questions",
            "PERSONAL": "Personal or emotional topics",
            "CASUAL": "Casual short responses"
        }
        
        self.logger(f"✅ QueryClassifier initialized with timeout: {timeout}s")
    
    def fast_classify(self, query: str) -> str:
        """Rule-based ONLY classification (extremely fast)"""
        return self._classify_rules(query).lower()

    def classify_with_timeout(self, query: str) -> str:
        """Classify query with timeout protection"""
        # First, try rule-based classification
        rule_based_result = self._classify_rules(query)
        if rule_based_result != "GENERAL":
            return rule_based_result.lower() # Return lowercase to match existing code expectations
        
        # If no rule matches, use model with timeout
        return self._classify_with_model_timeout(query).lower()
    
    def _classify_rules(self, query: str) -> str:
        """Rule-based classification (fast, no model)"""
        query_lower = query.lower().strip()
        
        # Check each pattern category
        for category, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    self.logger(f"📋 Rule-based classification: {category}")
                    return category
        
        return "GENERAL"
    
    def _classify_with_model_timeout(self, query: str) -> str:
        """Classify using model with timeout protection"""
        classification_result = {"result": "GENERAL"}  # Default
        
        def run_classification():
            try:
                # Simple prompt for classification
                prompt = f"""Classify this user query into ONE category:

Query: "{query}"

Categories:
- GREETING: Casual greetings like "hi", "hello"
- IDENTITY: Questions about identity like "who are you", "who am i"
- NEWS: Questions about news, current events, headlines
- POLITICS: Political discussions, elections, government
- TECH: Technology, software, hardware, AI
- SECURITY: Cybersecurity, hacks, vulnerabilities
- COMMAND: Bot commands like "status", "list users"
- GENERAL: General conversation, other topics

Return ONLY the category name, nothing else."""

                response = self.sync_client.chat(
                    model=self.classification_model,
                    messages=[{"role": "user", "content": prompt}],
                    stream=False,
                    options=self.classification_options
                )
                
                result = response['message']['content'].strip().upper()
                
                # Map to known categories
                for category in self.category_descriptions.keys():
                    if category in result:
                        classification_result["result"] = category
                        return
                
                classification_result["result"] = "GENERAL"
                
            except Exception as e:
                self.logger(f"⚠️ Classification error: {e}")
                classification_result["result"] = "GENERAL"
        
        # Run in thread with timeout
        thread = threading.Thread(target=run_classification)
        thread.daemon = True
        thread.start()
        thread.join(timeout=self.timeout)
        
        if thread.is_alive():
            self.logger(f"⏱️ Classification timeout after {self.timeout}s")
            return "GENERAL"  # Fallback
        
        return classification_result["result"]
    
    async def classify(self, query: str) -> str:
        """Main classification method (Async wrapper)"""
        # Run the synchronous timeout logic in a thread to avoid blocking the event loop
        return await asyncio.to_thread(self.classify_with_timeout, query)
