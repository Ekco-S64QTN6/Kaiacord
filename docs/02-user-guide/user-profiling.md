# User Profiling & Relationship Tracking

Kaia builds persistent user profiles and tracks per-user relationships to create a personalized, evolving social presence.

## 1. Relationship Tracking
The `relationship_manager.py` module maintains per-user relationship event stores:
- **Relationship Stages**: `stranger` → `acquaintance` → `familiar` → `friend` → `close_friend` → `inner_circle` — each stage unlocks different behavioral gating.
- **Event Store**: Up to 100 events per user with atomic writes, stored in `memory/relationships/`.
- **Behavioral Gating**: Kaia adjusts tone, depth, and proactivity based on the current relationship stage.

## 2. Automated Profiling
The `generate_user_profiles.py` script performs multi-layered analysis of each user's interaction logs:
- **Topic Analysis**: Identifies recurring themes and interests.
- **Communication Style**: Analyzes tone, verbosity, and vocabulary.
- **Interaction Stats**: Tracks frequency, timing, and engagement levels.
- **LLM Synthesis**: Uses a specialized LLM prompt to synthesize data into a structured `user_profile.md`.

## 3. Unified Identity Linking
Kaia bridges a user's presence across multiple platforms for comprehensive profiling.
- **Discord ↔ Forum**: By linking a Discord ID to a VBulletin UID, Kaia merges interaction data from both sources.
- **Linked Dossiers**: The user's `user_profile.md` explicitly references linked identities.
- **Command**: `!forum link <uid>` (See [Commands Guide](commands.md)).

## 4. Integration with RAG
Profiles are stored in the user's log directory and indexed by the RAG system.
- **Identity Retrieval**: When a user asks "who am i?", Kaia retrieves their profile for a personalized summary.
- **Contextual Awareness**: Profile data tailors responses to the user's known preferences.

## 5. Maintenance
Profiles are regenerated periodically or can be triggered manually via `tools/maintenance/generate_user_profiles.py`.
