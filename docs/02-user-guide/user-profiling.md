# User Profiling & Relationship Tracking

Kaia builds persistent user profiles and tracks per-user relationships to create a personalized, evolving social presence.

## 1. Relationship Tracking
`relationship_manager.py` maintains a per-user event store; `!scores` reads it.

- **Familiarity is a float, not a ladder.** There are no discrete stages to
  unlock. `scores_handler._get_stage_badge` turns the score into one of five
  labels at four thresholds:

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
Profiles are stored in the user's log directory and indexed on their own (`user_profiles`).
- **Whose profile**: a profile reaches a turn only when it is about the person asking or about
  someone the message names — "who am i?" gets the asker's, "who is starkind?" gets Starkind's
  (and the forum accounts linked to them). A stranger's profile never reaches an unrelated turn.
- **Contextual Awareness**: Profile data tailors responses to the user's known preferences.
- In the prompt a profile is labelled `USER PROFILE SUMMARY`, so she knows it is her summary of a
  person, not something they said.

## 5. Maintenance
Discord profiles are refreshed by the nightly dream cycle when they go stale (new logs a week
newer than the profile, or 15 KB of them), and on demand with
`venv/bin/python3 tools/maintenance/generate_user_profiles.py`. Forum profiles are built by the
forum scraper when it meets someone, and on demand with
`tools/maintenance/refresh_forum_profiles.py --apply` (see
[forum-integration](forum-integration.md)).

Each profile is written to `knowledge_base/user_logs/<Name>_<id>/user_profile.md`
— there is no `knowledge_base/user_profiles/` folder. Two tools write that file
(`generate_user_profiles.py` and `compact_forum_profiles.py`) and both must
consult `kaia_identities.registry` first; see CLAUDE.md §12.
