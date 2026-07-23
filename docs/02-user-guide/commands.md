# Kaia Command Reference

All commands are prefixed with `!`. Admin commands are restricted to the project architect (**ekco**).

## Quick Reference

| Command | Description | Access |
|:---|:---|:---|
| `!scores` | Gamified memory analytics & affinity leaderboards | All |
| `!art` | Generate a fractal flame artwork with Kaia commentary | All |
| `!rpg` | Open the Aethelgard TTRPG HUD and play | All |
| `!news [category]` | Fetch news by category | All |
| `!download <url>` | Ingest a URL into the knowledge base | All |
| `!quip` | Trigger a social media quip (10m cooldown) | All |
| `!forum [cmd]` | VBulletin forum management | Mixed |
| `!dream [cmd]` | Dream engine management | Admin |
| `!memory [cmd]` | Memory and beliefs management | Admin |
| `!selfmodel` | Regenerate Kaia's self-model | Admin |
| `!sysmon` | System monitoring dashboard | Admin |
| `!explain` | Deep-dive into RAG retrieval logic | Admin |

---

## User Commands

### 🏆 Gamified Memory Analytics & Affinity (`!scores` / `!score` / `!stats`)
Displays Kaia's gamified memory analytics, affinity bond scores, active beliefs, episodic memory anchors, and emotional vector telemetry via an interactive Discord Embed with category selection dropdowns:
- **Kaia's Inner Circle**: Ranks user affinity bonds, familiarity stages, interaction milestones, and relationship stats.
- **Beliefs & Memory Anchors**: Displays memory capacity overview (100 active beliefs / 100 memory anchors), most salient beliefs with recall counts, and top episodic anchor callbacks.
- **System Telemetry**: Displays emotional vector (`valence`, `arousal`, `energy`), RAG retrieval confidence, forum activity, and operational statistics.

### 🎨 Art (`!art`)
Generates a fractal flame artwork using the Electric Sheep algorithm (CPU-rendered, NumPy/SciPy). Kaia provides commentary on each piece. Features 20 variation functions, 10 color palettes, and adaptive density estimation.

### ⚔️ RPG (`!rpg`)
Opens the Aethelgard TTRPG interface — a full persistent RPG with turn-based combat, 10 advanced classes, a 77-floor mega-dungeon, housing, farming, pets, and alchemy. Python handles all game math; Kaia narrates outcomes.

Key subcommands:
- `!rpg new <Name> <Class>` — Create a character (Warrior/Ranger/Mage/Rogue/Cleric)
- `!rpg sheet` — View character sheet
- `!rpg hunt` — Hunt for monsters in current region
- `!rpg move <direction>` — Travel the world map
- `!rpg dungeon enter` — Enter a dungeon
- `!rpg buy/sell` — Shop interactions
- `!rpg home/farm/pet` — Estate management

### 📰 News (`!news [category]`)
Fetches news by category from auto-generated daily briefs. Requires `GEMINI_API_KEY` for brief generation.

**Categories:** `today`, `technology`, `security`, `hacking`, `politics`, `business`, `science`, `culture`, `general`

### 📥 Download (`!download <url>`)
Fetches content from a URL, converts it to Markdown, and saves it to the knowledge base for RAG ingestion. Supports HTML pages, PDFs, and plain text.

### 📢 Quip (`!quip`)
Triggers a social media quip — a short post cross-posted to Bluesky and/or X, grounded in Kaia's recent conversation history. 10-minute cooldown for non-owners.

### 🏟️ Forum (`!forum`)
Manages VBulletin 3.x integration and Discord ↔ Forum identity linking.
- `!forum link <forum_uid>` — **User command**. Links your Discord account to your Forum UID.
- `!forum scrape [pages]` — **Admin**. Manually scrape the configured subforum.
- `!forum status` — Connectivity status and recent scrape counts.

---

## Admin Commands

### 💤 Dream (`!dream`)
Manages Kaia's autonomous Dream Mode — nightly processing of daily interaction logs into associative reflections.
- `!dream list` — Recent reflections
- `!dream generate` — Force a dream cycle
- `!dream stats` — Reflection counts and category distribution

### 🧠 Memory (`!memory`)
Manages Kaia's persistent memory systems.
- `!memory beliefs` — View current beliefs (50-cap)
- `!memory anchors` — View episodic memory anchors (50-cap)

### 🪞 Self-Model (`!selfmodel`)
Regenerates Kaia's self-model — a 30-day synthesis of interaction logs into `kaia_self_model.md`.

### 📊 Sysmon (`!sysmon`)
System monitoring — VRAM usage, response times, active users, and cognitive pipeline metrics.

### 🔍 Explain (`!explain`)
Deep-dive into the RAG retrieval logic for the last response — shows the top 8 sources with scores and audit flags.

---

## Conversational Triggers

Kaia responds naturally to specific phrases when mentioned or addressed — no `!` prefix needed.

| Trigger | What it does |
|:---|:---|
| **Status** | Real-time GPU/VRAM health and Ollama status |
| **What's new** | Discusses recently ingested documents or news |
| **Dream recall** | Reflections from associative memory |

---

## Permissions Summary

| Role | Commands |
|:---|:---|
| **All Users** | `!art`, `!rpg`, `!news`, `!download`, `!quip`, `!forum link` |
| **Admin (ekco)** | All of the above, plus `!dream`, `!memory`, `!selfmodel`, `!sysmon`, `!explain`, `!forum scrape/status` |

Rate limiting applies to all users (configurable via `performance.requests_per_minute` in `kaia.yaml`).
