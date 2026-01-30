# Hallucination Prevention & Feedback Loop Protection (Kaia 2.5)
Kaia 2.5 introduces critical safeguards to prevent "phantom" hallucinations and recursive feedback loops.

## 1. Hallucination Detector
The `HallucinationDetector` is a real-time monitoring system that scans all inputs and outputs for known hallucination patterns.
- **Patterns**: Targets specific names and phrases (e.g., "Juanita", "Deane", "the agency") that have historically caused issues.
- **Query Blocking**: If a user's query contains hallucination triggers, the bot blocks it to prevent the LLM from engaging with contaminated data.
- **Response Sanitization**: If the LLM generates a hallucinated response, the detector automatically cleans it or provides a grounded fallback before it reaches the user or the logs.

## 2. Feedback Loop Protection
One of the most dangerous failure modes is when a hallucination is logged, retrieved via RAG, and then repeated—creating a reinforcement loop.
- **Sanitized Logging**: The `log_user_interaction` method now sanitizes responses *before* they are written to disk.
- **Cache Bypass**: Identity queries bypass the semantic cache to prevent "stale" hallucinations from being served.
- **Nuclear Option**: The `quick_fix.py` and `stop_hallucination_feedback.py` scripts provide an emergency way to purge all contaminated data from logs and the knowledge base.

## 3. Strict Identity Filtering
When asked about her own identity or the user's identity, Kaia now uses a `strict_identity` retrieval mode:
- **Source Restriction**: Only allows nodes from `kaia_persona.md` and the current user's specific log directory.
- **Exclusion**: Completely ignores the general knowledge base and other users' logs to prevent cross-contamination.

## 4. Priority Metadata & Scoring
RAG results are now scored based on their source type:
1. **Persona**: Highest priority (1.5x boost).
2. **User Logs**: High priority (1.2x boost).
3. **User Profiles**: Medium priority (1.0x).
4. **General Knowledge**: Standard priority (0.8x).

## 5. Emergency Contamination Filter
The `EmergencyContaminationFilter` acts as a final safety net before any response is sent to Discord or logged.
- **Line-by-Line Scanning**: Every response is split into lines and scanned for high-risk patterns (e.g., "Elena", "Juanita").
- **Surgical Removal**: Contaminated lines are removed while preserving the rest of the response.
- **Fallback Mechanism**: If the entire response is contaminated, it is replaced with a clean, persona-appropriate fallback.

## 6. Nuclear Reset Process
When hallucinations become deeply embedded in the conversation context, a "Nuclear Reset" can be performed using `tools/nuclear_reset.py`:
- **Log Purging**: Surgically removes hallucinated blocks from all user logs.
- **Index Reset**: Deletes all RAG indices to force a clean rebuild.
- **Profile Reset**: Deletes all user profiles to prevent "stale" identity hallucinations.
- **Cache Clearing**: Wipes the semantic cache to prevent keyword pollution.
