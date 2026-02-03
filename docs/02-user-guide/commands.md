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

## 🗣️ Conversational Triggers (Natural Language)

Kaia responds naturally to specific phrases when mentioned or addressed.

| Trigger | Description | Variations |
|:---|:---|:---|
| **System Status** | Provides real-time GPU/VRAM health and Ollama status. | "status", "stats", "info", "how are you" |
| **Natural Mention** | Discusses recently ingested documents or news briefings. | "what's new?", "what's up?", "what have you been reading?" |
| **Dream Recall** | Triggers direct reflections from the associative memory cache. | "what did you dream?", "tell me about your dreams" |
| **Image Generation** | Generates high-fidelity images using FLUX.1-schnell. | "draw a cat", "generate a cyberpunk city", "sketch a..." |

---

## 🎨 Creative Commands

### Image Generation
Instead of a strict `!draw` command, Kaia detects creative intent in natural language.
- **Syntax**: `kaia draw [prompt]` or `will you paint [prompt] please?`
- **Supported Intents**: `draw`, `paint`, `generate`, `create`, `sketch`, `render`.
- **Supported Shapes**: `portrait`, `landscape`, `square`, `circle`, etc.

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
