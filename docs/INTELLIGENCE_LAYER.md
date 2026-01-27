# Intelligence Layer
The Intelligence Layer is a suite of advanced features designed to make Kaia faster, smarter, and more stable.

## 1. Improved Semantic Cache
Kaia uses an enhanced caching system to provide near-instant responses while preventing keyword pollution.
- **Normalization**: Queries are normalized by removing extra whitespace and replacing dates/numbers with placeholders (e.g., `[DATE]`, `[YEAR]`).
- **Keyword Blacklist**: Automatically bypasses caching for queries containing high-risk keywords (e.g., "68k.news", "Elena").
- **Contextual Differentiation**: Detects if two news queries are about different dates, even if they share similar keywords, preventing stale news from being served.
- **Adaptive Expiry**: News-related queries expire in 24 hours, while general queries last for 7 days.
- **Bypass**: Identity-related queries (e.g., "who are you") automatically bypass the cache.

## 2. Query Classification (Consolidated)
Before processing a query, Kaia's consolidated `QueryClassifier` categorizes the intent using a hybrid approach:
- **Rule-Based (Fast)**: Uses regex patterns for instant classification of common intents (Greetings, Identity, News, Commands).
- **Model-Based (Accurate)**: Falls back to the main LLM (`gemma3:12b`) for complex queries, with a **5.0s timeout protection** to prevent hanging.
- **Categories**: GREETING, IDENTITY, NEWS, POLITICS, TECH, SECURITY, COMMAND, GENERAL, KNOWLEDGE, PERSONAL, CASUAL.

This classification allows the bot to optimize retrieval (e.g., using `strict_identity` for identity queries) and choose the best system prompt or news category.

## 3. Context Optimization
The `ContextOptimizer` dynamically manages the limited context window of the LLM:
- **Persona**: Always prioritized.
- **RAG Context**: Filtered and ranked by relevance and source priority.
- **Conversation History**: Summarized or truncated to fit within the token limit while maintaining continuity.

## 4. Self-Healing System
To ensure reliability, the `SelfHealingSystem` wraps LLM calls:
- **Automatic Retries**: If a call fails or produces garbage, it retries with a simplified prompt.
- **Context Reduction**: If the context is too large, it automatically prunes less relevant nodes.
- **Fallback Responses**: Provides a grounded, persona-aligned fallback if all else fails.

## 5. Model Warm Pool
Maintains a "warm" state for the primary chat model to reduce first-token latency. It periodically pings the model to keep it loaded in VRAM when the bot is active.
