# Intelligence Layer
The Intelligence Layer is a suite of advanced features designed to make Kaia faster, smarter, and more stable.

## 1. Improved Semantic Cache
Kaia uses an enhanced caching system to provide near-instant responses while preventing keyword pollution.
- **Normalization**: Queries are normalized by removing extra whitespace and replacing dates/numbers with placeholders (e.g., `[DATE]`, `[YEAR]`).
- **Keyword Blacklist**: Automatically bypasses caching for queries containing high-risk keywords (e.g., "68k.news", "Elena").
- **Contextual Differentiation**: Detects if two news queries are about different dates, even if they share similar keywords, preventing stale news from being served.
- **Adaptive Expiry**: News-related queries expire in 24 hours, while general queries last for 7 days.
- **Bypass**: Identity-related queries (e.g., "who are you") automatically bypass the cache.

## 2. Intent Analysis (`IntentParser`)
Before processing a query, Kaia's `IntentParser` (Advanced Intent Understanding Engine) analyzes the intent:
- **Rule-Based (Fast)**: Uses regex patterns for instant parsing of common intents (Greetings, Identity, News, Commands).
- **Model-Based (Accurate)**: Falls back to the `gemma2:2b` model running on **CPU** (`num_gpu: 0`) for deep cognitive analysis of emotional context, implied needs, and relational cues. Runs via `ThreadPoolExecutor` with a configurable timeout.
- **Output**: Generates a structured `Intent` object with specific strategies (e.g., `DIAGNOSTIC_DEEP_DIVE`, `DREAM_RECALL`).
- **Lazy Initialization**: The `IntentParser` is lazily initialized on first use to avoid blocking startup.

This analysis allows the bot to optimize retrieval and choose the best persona-aligned response strategy.

## 3. Context Optimization
The `ContextOptimizer` dynamically manages the limited context window of the LLM:
- **Persona**: Always prioritized (non-truncating identity anchor).
- **RAG Context**: Filtered and ranked by relevance and source priority.
- **Conversation History**: Summarized or truncated to fit within the token limit while maintaining continuity.
- **Config-Driven**: Context window size controlled by `config.max_context_tokens` (default: 20,000).

## 4. Self-Healing System
To ensure reliability, the `SelfHealingSystem` wraps LLM calls:
- **Automatic Retries**: If a call fails or produces garbage, it retries with a simplified prompt.
- **Context Reduction**: If the context is too large, it automatically prunes less relevant nodes.
- **Temperature Scaling**: On retry, temperature is adjusted to encourage different outputs.
- **Fallback Responses**: Provides a grounded, persona-aligned fallback if all else fails.

## 5. Model Warm Pool
Maintains a "warm" state for the primary chat model to reduce first-token latency.
- **Pre-Warm Timeout**: Wrapped in a strict 300s `asyncio.wait_for` during startup. If the model takes >5 minutes to load, it's logged as a CRITICAL FAILURE.
- **Keep-Alive**: Periodically pings the model to keep it loaded in VRAM when the bot is active.

## 6. Knowledge Boundary
The `KnowledgeBoundary` prevents Kaia from hallucinating about entities she doesn't know:
- **Entity Extraction**: Identifies capitalized names and acronyms from user queries.
- **Known Entity Database**: Pre-loads entities from user logs, knowledge base files, and identity registry.
- **Common Words Filter**: Filters out common English words and acronyms (externalized to `config/common_entities.json`).
- **Fuzzy Matching**: Levenshtein-distance matching for typos, with a configurable performance guard (`fuzzy_max_context_words`) to skip excessively large contexts.
- **Boundary Response**: When unknown entities are detected, Kaia admits lack of knowledge rather than fabricating information.
