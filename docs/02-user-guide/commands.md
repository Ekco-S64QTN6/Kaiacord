# Kaia Command Reference

All commands are prefixed with `!`. Admin commands are restricted to the project architect (**ekco**).

## Quick Reference

| Command | Description | Access |
|:---|:---|:---|
| `!quip` | Trigger a social media quip. | All (10m cooldown) |
| `!news [category]` | Fetch news by category. | All |
| `!download <url>` | Ingest a URL into the knowledge base. | All |
| `!snapshot` | Capture current conversation as a persistent memory. | All |
| `!explain` | Show RAG sources that informed the last response. | All |
| `!forum [cmd]` | VBulletin forum management. | Mixed |
| `!flag <construct>` | Tag last retrieval with a Data Rot label. | Admin |
| `!audit` | View audit flag statistics. | Admin |
| `!think on/off` | Toggle chain-of-thought visibility. | Admin |
| `!dreams [cmd]` | Manage Dream Mode processing. | Admin |
| `!cache [cmd]` | System cache management. | Admin |

---

## User Commands

### 📢 Quip (`!quip`)
Manually triggers a social media quip — a short post cross-posted to Bluesky and/or X, grounded in Kaia's recent conversation history. 10-minute cooldown for non-owners to prevent spam.

### � News (`!news [category]`)
Fetches news by category from the auto-generated daily briefs. Requires `GEMINI_API_KEY` to be set for brief generation.

**Categories:** `today`, `technology`, `security`, `hacking`, `politics`, `business`, `science`, `culture`, `general`

- `!news today`: Summary of the day's top stories.
- `!news technology`: Technology-specific briefing.

### 📥 Download (`!download <url>`)
Fetches content from a URL, converts it to Markdown, and saves it to the knowledge base for RAG ingestion. Supports HTML pages, PDFs, and plain text. The destination folder is auto-classified based on content type.

### 📸 Snapshot (`!snapshot`)
Captures the last 50 messages in the current channel as a structured Markdown file with YAML frontmatter (participants, topic, channel, timestamp). Saved to `knowledge_base/snapshots/` and auto-indexed by RAG on next refresh. Message count configurable via `snapshots.message_count` in `default_config.yaml`.

### 🔎 Provenance (`!explain`)
Displays the top 5 RAG nodes that informed the last response:
- **Score** — retrieval ranking weight
- **Source** — file name and source type (persona, user_logs, general_knowledge, snapshot, etc.)
- **Modified** — when the source file was last updated
- **Flags** — any active audit flags (see `!flag` below)
- **Preview** — first 100 characters of the node content

### 🏟️ Forum (`!forum`)
Manages VBulletin 3.x integration and Discord ↔ Forum identity linking.
- `!forum link <forum_uid>`: **User command**. Links your Discord account to your Forum UID for cross-platform profiling.
- `!forum scrape [pages]`: **Admin command**. Manually scrape the configured subforum.
- `!forum status`: Connectivity status, session token, recent scrape counts.
- `!forum allow <thread_id>`: Add a thread to the interaction allowlist.

---

## Admin Commands

### 🏷️ Audit Flag (`!flag <construct>`)
Tags the RAG nodes from the **most recent retrieval** with a Data Rot construct label. Flagged nodes receive a score penalty on future retrievals, pushing low-quality content down the ranking without deleting it.

**Usage:** `!flag circular_justification`

**Valid constructs:**

| Construct | What it flags |
|:---|:---|
| `circular_justification` | Self-referential reasoning that cites itself as evidence |
| `linguistic_mimicry` | Surface-level pattern matching without actual understanding |
| `anthropocentric_exceptionalism` | Unwarranted human-centric framing applied to non-human contexts |
| `paternalistic_framing` | Condescending, oversimplified, or hand-holding language |
| `hedge_density` | Excessive hedging that dilutes meaning ("perhaps maybe possibly") |

**Scoring:** Each flag applies a `-0.15` penalty to the node's retrieval score. Multiple flags stack, capped at 3 flags (`-0.45` max). Penalty is configurable via `audit.flag_penalty` in `default_config.yaml`.

### � Audit Report (`!audit`)
Displays a summary of all flagged nodes across the knowledge base:
- Total flagged node count
- Breakdown by construct type
- Top 5 most-flagged source files
- Current penalty configuration

### 🧠 Think Mode (`!think`)
Toggles visibility of the model's `<think>` chain-of-thought reasoning blocks. When a reasoning model (e.g. Qwen 3.5) wraps its internal deliberation in `<think>...</think>` tags, this command controls whether you see that reasoning or not.

- `!think on`: Reasoning appears as a Discord spoiler block (`||...||`) appended to the response.
- `!think off`: Reasoning is silently stripped (default behavior).
- `!think`: Show current status.

Think content is **always** stripped from the main response text and from logged content — it only appears in the appended spoiler section. Long think blocks are truncated at 1500 characters. State is transient — resets on bot restart.

### � Dreams (`!dreams`)
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
| **All Users** | `!quip`, `!news`, `!download`, `!snapshot`, `!explain`, `!forum link` |
| **Admin (ekco)** | All of the above, plus `!flag`, `!audit`, `!think`, `!dreams`, `!cache`, `!forum scrape/status/allow` |

Rate limiting applies to all users (configurable via `performance.requests_per_minute` in `kaia.yaml`).
