# User Profiling & Relationship Tracking (Kaia 2.4)
Kaia 2.4 enhances the bot's social intelligence by analyzing historical interactions to build deep, persistent user profiles.

## 1. Automated Profiling
The `generate_user_profiles.py` script performs a multi-layered analysis of each user's interaction logs:
- **Topic Analysis**: Identifies recurring themes and interests.
- **Communication Style**: Analyzes tone, verbosity, and vocabulary.
- **Interaction Stats**: Tracks frequency, timing, and engagement levels.
- **LLM Synthesis**: Uses a specialized LLM prompt to synthesize these data points into a structured `user_profile.md`.

## 2. Relationship Tracking
The `relationship_tracker.py` module quantifies the social bond between Kaia and each user:
- **Trust Score**: A dynamic metric based on positive interactions and shared history.
- **Evolution Visualization**: Generates `relationship_evolution.png` charts showing how the relationship has changed over time.
- **Actionable Insights**: Provides Kaia with specific advice on how to interact with a user (e.g., "User prefers blunt technical talk", "User is sensitive about X").

## 3. Unified Identity Linking
Kaia can bridge a user's presence across multiple platforms to create a more accurate and comprehensive personality profile.
- **Discord <-> Forum**: By linking a Discord ID to a VBulletin UID, Kaia merges interaction data from both sources.
- **Linked Dossiers**: The frontmatter of the user's `user_profile.md` explicitly references their linked identities, allowing Kaia to recognize them as the same entity across the ecosystem.
- **Command**: `!forum link <uid>` (See [Commands Guide](commands.md)).

## 4. Integration with RAG
These profiles are stored in the user's log directory and indexed by the RAG system.
- **Identity Retrieval**: When a user asks "who am i?", Kaia retrieves their `user_profile.md` to provide a nuanced, personalized summary.
- **Contextual Awareness**: Even in general conversation, Kaia can use profile data to tailor her responses to the user's known preferences.

## 4. Maintenance
Profiles are regenerated periodically or can be triggered manually. The `emergency_fix.py` script can be used to reset all profiles if a user's history becomes contaminated or if a fresh start is needed.
