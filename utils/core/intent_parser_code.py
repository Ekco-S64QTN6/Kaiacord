class IntentParser:
    """
    Advanced Intent Understanding Engine. 
    Replaces simple classification with cognitive intent parsing.
    """
    
    def __init__(self, ollama_client=None, model="gemma3:12b", logger=None, host="http://localhost:11434", timeout=15.0):
        self.ollama_client = ollama_client
        self.model = model
        self.logger = logger or log_info
        self.timeout = timeout
        
        # Use main model for intelligence
        self.classification_model = model
        
        # Optimized options for analysis
        from utils.infrastructure.system.yaml_config import config
        self.classification_options = {
            "num_gpu": -1,
            "num_ctx": getattr(config, 'max_context_tokens', 28000),
            "temperature": 0.1,  # Low temp for structured analysis
            "top_p": 0.9,
            "num_predict": 256   # Allow enough tokens for JSON/Structured output
        }
        
        # LAYER 1: Fast Pattern Triggers (Regex)
        # Used for immediate responses or obvious routing
        self.fast_triggers = {
            "SOCIAL_GREETING": [
                r"^\s*(hi|hello|hey|greetings|sup|yo|hi there|hello there)\s*$",
                r"^\s*(hi|hello|hey|greetings|sup|yo)\s+kaia",
                r"^\s*kaia\?$"
            ],
            "COMMAND_EXECUTION": [
                r"^\s*(status|stats|ping|uptime|clear|reset|quip)\b",
                r"^\s*[!/](quip|news|dreams|cache)\b"
            ],
            "PRECISE_RECALL": [
                r"^\s*who (is|are|was|were) ",
                r"^\s*what (is|are|was|were) ",
                r"\b(mark|elara|thorne|jules|elias)\b"
            ],
             "DIAGNOSTIC_DEEP_DIVE": [
                r"\b(error|bug|fail|crash|exception|traceback|fix|broken|dogshit)\b"
            ]
        }

        log_success(f"IntentParser initialized (Model: {model})")
    
    def fast_parse(self, query: str) -> Optional[Intent]:
        """Layer 1: Fast Pattern Detection"""
        query_lower = query.lower().strip()
        
        for strategy, patterns in self.fast_triggers.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    log_info(f"Fast-path trigger: {strategy} (Matched: {pattern})")
                    
                    # Construct a basic Intent object from the trigger
                    return Intent(
                        explicit_intent=query,
                        implied_needs=["immediate_response"],
                        emotional_context="neutral",
                        temporal_focus="present_immediate",
                        relational_context="direct_command" if "COMMAND" in strategy else "social_casual",
                        suggested_strategy=strategy,
                        confidence=1.0
                    )
        return None

    async def parse_intent(self, query: str, context: Optional[ContextCtx] = None) -> Intent:
        """Main Entry Point: Analyze query into Intent Object"""
        
        # 1. Fast Path
        fast_intent = self.fast_parse(query)
        # If it's a Greeting or Command, return immediately.
        # For Precise/Diagnostic triggers, we MIGHT still want LLM analysis 
        # to get implied needs, but for now let's trust the fast path 
        # for speed if confidence is high.
        if fast_intent and fast_intent.suggested_strategy in ["SOCIAL_GREETING", "COMMAND_EXECUTION"]:
             return fast_intent

        # 2. Layer 2: LLM Intent Analysis
        return await self._analyze_with_llm(query, context)

    async def _analyze_with_llm(self, query: str, context: Optional[ContextCtx]) -> Intent:
        """Layer 2: Deep Analysis via LLM"""
        try:
            # Context string construction
            ctx_str = ""
            if context:
                ctx_str = f"Active Entities: {', '.join(context.active_entities)}\nLast Topic: {context.last_turns[-1] if context.last_turns else 'None'}"

            prompt = (
                "SYSTEM: You are an Intent Analysis Engine. Analyze the user query.\n"
                "OUTPUT FORMAT: JSON ONLY.\n"
                "{\n"
                "  \"explicit_intent\": \"literal meaning\",\n"
                "  \"implied_needs\": [\"underlying need 1\", \"need 2\"],\n"
                "  \"emotional_context\": \"frustrated|curious|neutral|urgent\",\n"
                "  \"temporal_focus\": \"past|present_immediate|future|theoretical\",\n"
                "  \"relational_context\": \"admin|social|knowledge_seeking\",\n"
                "  \"suggested_strategy\": \"PRECISE_RECALL|DIAGNOSTIC_DEEP_DIVE|ASSOCIATIVE_WANDERING|RELATIONAL_MIRROR|SYNTHESIS_SCAN|EXPLORATORY_DIALOGUE\"\n"
                "}\n\n"
                "STRATEGIES:\n"
                "- PRECISE_RECALL: Specific facts, names, dates, definitions.\n"
                "- DIAGNOSTIC_DEEP_DIVE: Errors, troubleshooting, bugs, system health.\n"
                "- ASSOCIATIVE_WANDERING: Dreams, stories, creative, 'what if'.\n"
                "- RELATIONAL_MIRROR: User identity, 'who am i', self-reflection.\n"
                "- SYNTHESIS_SCAN: News, updates, 'what happened recently'.\n"
                "- EXPLORATORY_DIALOGUE: General conversation, open-ended.\n\n"
                f"CONTEXT:\n{ctx_str}\n\n"
                f"USER QUERY: \"{query}\"\n\nJSON:"
            )

            response = await self.ollama_client.chat(
                model=self.classification_model,
                messages=[{"role": "user", "content": prompt}],
                options=self.classification_options
            )
            
            raw_json = response['message']['content'].strip()
            # Clean markdown code blocks if present
            raw_json = raw_json.replace("```json", "").replace("```", "").strip()
            
            data = json.loads(raw_json)
            
            # Fallback for confidence (not usually in LLM output unless asked)
            confidence = 0.85
            
            return Intent(
                explicit_intent=data.get('explicit_intent', query),
                implied_needs=data.get('implied_needs', []),
                emotional_context=data.get('emotional_context', 'neutral'),
                temporal_focus=data.get('temporal_focus', 'present_immediate'),
                relational_context=data.get('relational_context', 'general'),
                suggested_strategy=data.get('suggested_strategy', 'EXPLORATORY_DIALOGUE'),
                confidence=confidence
            )

        except Exception as e:
            log_error(f"Intent Analysis Failed: {e}")
            import traceback
            traceback.print_exc()
            # Fallback Intent
            return Intent(
                explicit_intent=query,
                implied_needs=["general chat"],
                emotional_context="neutral",
                temporal_focus="present_immediate",
                relational_context="general",
                suggested_strategy="EXPLORATORY_DIALOGUE",
                confidence=0.5
            )

    async def pre_warm(self):
        """Pre-warm the model"""
        log_action("Pre-warming IntentParser...")
        try:
            from utils.infrastructure.system.yaml_config import config
            original_timeout = self.timeout
            self.timeout = config.prewarm_timeout
            
            await self.parse_intent("System check")
            
            self.timeout = original_timeout
            log_success("IntentParser warmed up.")
        except Exception as e:
            log_error(f"Pre-warm failed: {e}")
