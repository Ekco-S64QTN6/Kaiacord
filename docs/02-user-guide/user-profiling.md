# User Profiling & Relationship Tracking

Kaia builds persistent user profiles and tracks per-user relationships to create a personalized, evolving social presence.

## 1. Relationship Tracking
`relationship_manager.py` maintains a per-user event store; `!scores` reads it.

- **Familiarity is a float, not a ladder.** There are no discrete stages to
  unlock. `scores_handler._get_stage_badge` turns the score into a label at
  four thresholds:

  | Familiarity | Shown as |
  |:--|:--|
  | < 0.15 | 👤 Stranger |
  | ≥ 0.15 | 📜 Acquaintance |
  | ≥ 0.40 | 🗡️ Familiar |
  | ≥ 0.65 | 🛡️ Confidant |
  | ≥ 0.85 | 👑 Inner Circle |

  The label is display only. What actually varies with familiarity is tone,
  depth and how readily she speaks first.
- **Event Store**: Up to 100 events per user with atomic writes, stored in
  `memory/relationships/`.

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
Profiles are regenerated periodically or triggered manually with
`venv/bin/python3 tools/maintenance/generate_user_profiles.py`.

Each profile is written to `knowledge_base/user_logs/<Name>_<id>/user_profile.md`
— there is no `knowledge_base/user_profiles/` folder. Two tools write that file
(`generate_user_profiles.py` and `compact_forum_profiles.py`) and both must
consult `kaia_identities.registry` first; see CLAUDE.md §12.
