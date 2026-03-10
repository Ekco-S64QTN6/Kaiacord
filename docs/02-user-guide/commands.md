# Kaia Command Reference

All commands are prefixed with `!`. Admin commands are restricted to the project architect (**ekco**).

## Quick Reference

| Command | Description | Access |
|:---|:---|:---|
| `!quip` | Trigger a social media quip. | All (10m cooldown) |
| `!news [category]` | Fetch news by category. | All |
| `!download <url>` | Ingest a URL into the knowledge base. | All |
| `!forum [cmd]` | VBulletin forum management. | Mixed |
| `!dreams [cmd]` | Manage Dream Mode processing. | Admin |
| `!snapshot` | Capture current context for diagnostics. | Admin |
| `!flag` / `!audit` | Path to response review / auditing. | Admin |
| `!explain` | Deep-dive into RAG retrieval logic for last response. | Admin |
| `!cache [cmd]` | System cache management. | Admin |

---

## User Commands

### 📢 Quip (`!quip`)
Manually triggers a social media quip — a short post cross-posted to Bluesky and/or X, grounded in Kaia's recent conversation history. 10-minute cooldown for non-owners to prevent spam.

### 📰 News (`!news [category]`)
Fetches news by category from the auto-generated daily briefs. Requires `GEMINI_API_KEY` to be set for brief generation.

**Categories:** `today`, `technology`, `security`, `hacking`, `politics`, `business`, `science`, `culture`, `general`

- `!news today`: Summary of the day's top stories.
- `!news technology`: Technology-specific briefing.

### 📥 Download (`!download <url>`)
Fetches content from a URL, converts it to Markdown, and saves it to the knowledge base for RAG ingestion. Supports HTML pages, PDFs, and plain text. The destination folder is auto-classified based on content type.

### 🏟️ Forum (`!forum`)
Manages VBulletin 3.x integration and Discord ↔ Forum identity linking.
- `!forum link <forum_uid>`: **User command**. Links your Discord account to your Forum UID for cross-platform profiling.
- `!forum scrape [pages]`: **Admin command**. Manually scrape the configured subforum.
- `!forum status`: Connectivity status, session token, recent scrape counts.
- `!forum allow <thread_id>`: Add a thread to the interaction allowlist.

---

## Admin Commands

### 💤 Dreams (`!dreams`)
Manages Kaia's autonomous "Dream Mode" — nightly (3–5 AM) processing of daily interaction logs into associative reflections that feed back into RAG.
- `!dreams list`: Displays the 5 most recent reflections.
- `!dreams generate`: Forces a dream cycle manually.
- `!dreams stats`: Total reflections, usage counts, category distribution.
- `!dreams test [trigger]`: Simulates a blended memory trigger to check prompt construction.

### ⚡ Cache (`!cache`)
Manages the response caches.
- `!cache stats`: Current size of semantic and exact caches.
- `!cache clear`: Wipes all cached responses. Use when stuck in a stale conversation loop or after persona updates.

---

## Conversational Triggers

Kaia responds naturally to specific phrases when mentioned or addressed — no `!` prefix needed.

| Trigger | What it does | Example phrases |
|:---|:---|:---|
| **System Status** | Real-time GPU/VRAM health and Ollama status | "status", "stats", "how are you" |
| **What's New** | Discusses recently ingested documents or news | "what's new?", "what's up?" |
| **Dream Recall** | Reflections from associative memory | "what did you dream?", "tell me about your dreams" |

---

## Permissions Summary

| Role | Commands |
|:---|:---|
| **All Users** | `!quip`, `!news`, `!download`, `!forum link` |
| **Admin (ekco)** | All of the above, plus `!dreams`, `!cache`, `!forum scrape/status/allow` |

Rate limiting applies to all users (configurable via `performance.requests_per_minute` in `kaia.yaml`).
