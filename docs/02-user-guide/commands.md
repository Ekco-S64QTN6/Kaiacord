# Kaia Command Reference

This document provides a comprehensive list of all commands and conversational triggers available in the Kaia system.

## 🕹️ Interaction Commands (Manual)

These commands are prefixed with `!` and are typically used for manual control or testing.

| Command | Description | Notes |
|:---|:---|:---|
| `!quip` | Manually trigger a social media "skeet"/quip. | 10 minute cooldown for non-owners. |
| `!news [category]` | Fetch news by category (technology, security, hacking, etc.). | `!news today` for a daily summary. |
| `!dreams [cmd]` | Manage associative memory (Dream Mode). | Admin only. |
| `!cache [cmd]` | System cache management. | Admin only. |
| `!forum [cmd]` | VBulletin forum management. | Admin only (mostly). |

---

## 🛠️ Admin Commands

These commands are restricted to the project architect (**ekco**).

### 💭 Dreams (`!dreams`)
Manages her autonomous "Dream Mode" processing.
- `!dreams list`: Displays the 5 most recent deep reflections / summaries.
- `!dreams generate`: Forces a "nightly" dream cycle (processes archived knowledge into new dreams).
- `!dreams stats`: Shows total reflections, usage counts, and category distribution.
- `!dreams test [trigger]`: Simulates a blended memory trigger to check prompt construction.

### ⚡ Cache (`!cache`)
Manages the semantic and exact response caches.
- `!cache stats`: Shows the current size of semantic and exact caches.
- `!cache clear`: Wipes all cached responses. Use this if she gets stuck in a "stale" conversation loop or if you've updated her persona and want immediate variety.

---

## 🏟️ Forum Commands (`!forum`)
Manages her VBulletin 3.x integration and identity linking.
- `!forum link <forum_uid>`: **User command**. Links your current Discord account to your Forum UID for cross-platform profiling.
- `!forum scrape [pages]`: **Admin command**. Manages manual scraping of the configured subforum.
- `!forum status`: Displays connectivity status, current session token, and recent scrape counts.
- `!forum allow <thread_id>`: Adds a thread to the interaction allowlist.

---

## 🗣️ Conversational Triggers (Natural Language)

Kaia responds naturally to specific phrases when mentioned or addressed.

| Trigger | Description | Variations |
|:---|:---|:---|
| **System Status** | Provides real-time GPU/VRAM health and Ollama status. | "status", "stats", "info", "how are you" |
| **Natural Mention** | Discusses recently ingested documents or news briefings. | "what's new?", "what's up?", "what have you been reading?" |
| **Dream Recall** | Triggers direct reflections from the associative memory cache. | "what did you dream?", "tell me about your dreams" |

---

## 📰 News Categories
When using `!news`, you can specify these categories:
- `today` (Summary of the day)
- `technology`
- `security`
- `hacking`
- `politics`
- `business`
- `science`
- `culture`
- `general`

---

## 🔑 Permissions
- **Admin Commands**: `!dreams` and owner-exemptions for `!quip` are restricted to the project architect (**ekco**).
- **Rate Limiting**: Users are subject to a requests-per-minute limit (configured in `kaia.yaml`).
