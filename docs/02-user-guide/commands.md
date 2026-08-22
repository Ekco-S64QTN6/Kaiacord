# Kaia Command Reference

All commands are prefixed with `!`. Admin commands are restricted to the project architect (**ekco**).

## Quick Reference

| Command | Description | Access |
|:---|:---|:---|
| `!scores` / `!stats` | Gamified memory analytics & affinity leaderboards | All |
| `!art` | Generate a fractal flame artwork with Kaia commentary | All |
| `!rpg` | Open the Aethelgard TTRPG HUD and play | All |
| `!help` | Display interactive command and feature guide | All |
| `!news [category]` | Fetch news by category | All |
| `!download <url>` | Ingest a URL into the knowledge base | All |
| `!quip` | Trigger a social media quip (10m cooldown) | All |
| `!flag <reason>` | Flag the previous message for audit/review | All |
| `!forum [cmd]` | VBulletin forum management | Mixed |
| `!dream [cmd]` | Dream engine management | Admin |
| `!memory [cmd]` | Memory and beliefs management (100-cap) | Admin |
| `!cache [cmd]` | Inspect and manage RAG cache | Admin |
| `!audit [cmd]` | Inspect flagged interactions and hallucination logs | Admin |
| `!snapshot` | Create an instant state backup snapshot | Admin |
| `!enrich [text]` | Run manual entity/context enrichment | Admin |
| `!reindex` | Trigger background knowledge base reindexing | Admin |
| `!selfmodel` | Regenerate Kaia's self-model | Admin |
| `!sysmon` | System monitoring dashboard | Admin |
| `!explain` | Deep-dive into RAG retrieval logic | Admin |

---

## User Commands

### 🏆 Gamified Memory Analytics & Affinity (`!scores` / `!score` / `!stats` / `!leaderboard` / `!halloffame`)
Displays Kaia's gamified memory analytics, affinity bond scores, active beliefs, episodic memory anchors, and emotional vector telemetry via an interactive Discord Embed with category selection dropdowns:
- **Kaia's Inner Circle**: Ranks user affinity bonds, familiarity stages, interaction milestones, and relationship stats.
- **Beliefs & Memory Anchors**: Displays memory capacity overview (100 active beliefs / 100 memory anchors), most salient beliefs with recall counts, and top episodic anchor callbacks.
- **System Telemetry**: Displays emotional vector (`valence`, `arousal`, `energy`), RAG retrieval confidence, forum activity, and operational statistics.

### 🎨 Art (`!art`)
Generates a fractal flame artwork using the Electric Sheep algorithm (CPU-rendered, NumPy/SciPy). Kaia provides commentary on each piece. Features 20 variation functions, 10 color palettes, and adaptive density estimation.

### ⚔️ RPG & Fishing (`!rpg`)
Opens the Aethelgard TTRPG interface — a full persistent RPG with turn-based combat, 10 advanced classes, a 77-floor mega-dungeon, housing, farming, pets, alchemy, and a 253-species fishing minigame. Python handles all game math; Kaia narrates outcomes.

Key subcommands:
- `!rpg new <Name> <Class>` — Create a character (Warrior/Ranger/Mage/Rogue/Cleric)
- `!rpg sheet` — View character sheet
- `!rpg hunt` — Hunt for monsters in current region
- `!rpg move <direction>` — Travel the world map
- `!rpg dungeon enter` — Enter a dungeon or Spine of the World floor
- `!rpg buy/sell` — Shop interactions across Hemlock, Pell's, and Caravan
- `!rpg home/farm/pet` — Estate, crop harvesting, and companion management
- `!rpg fish` / `!rpg fish_shop` / `!rpg sell_catch` — Rod-based fishing economy

### 📰 News (`!news [category]`)
Fetches news by category from auto-generated daily briefs. Requires `GEMINI_API_KEY` for brief generation.

**Categories:** `today`, `technology`, `security`, `hacking`, `politics`, `business`, `science`, `culture`, `general`

### 📥 Download (`!download <url>`)
Fetches content from a URL, converts it to Markdown, and saves it to the knowledge base for RAG ingestion. Supports HTML pages, PDFs, and plain text.

### 📢 Quip (`!quip`)
Triggers a social media quip — a short post cross-posted to Bluesky and/or X, grounded in Kaia's recent conversation history. 10-minute cooldown for non-owners.

### 🔍 Explain (`!explain`)
Deep-dive into the RAG retrieval logic for the last response — shows top retrieved sources with similarity scores, retrieval method (HYBRID/VECTOR/BM25/INJECTION), clean category paths, and audit flags in color-coded ANSI code blocks.

### 🏟️ Forum (`!forum`)
Manages VBulletin 3.x integration and Discord ↔ Forum identity linking.
- `!forum link <forum_uid>` — **User command**. Links your Discord account to your Forum UID.
- `!forum scrape [forum=ID limit=N full=true]` — **Admin**. Manually scrape configured subforums.
- `!forum status` — Connectivity status and rate limits.
- `!forum stats` — Scraper totals (threads, posts, users).
- `!forum read <thread_id>` — Read last posts from a thread.
- `!forum post <thread_id> <message>` — Post a manual reply.
- `!forum reply <thread_id>` — Trigger an AI-generated reply.
- `!forum user <user_id>` — Deep-scrape a user's full post history.

---

## Admin Commands

### 💤 Dream (`!dream`)
Manages Kaia's autonomous Dream Mode — nightly processing of daily interaction logs into associative reflections and belief extractions.
- `!dream list` — Recent reflections
- `!dream generate` — Force an immediate dream cycle
- `!dream stats` — Reflection counts and category distribution
- `!dream test [trigger]` — Test prompt construction on a trigger phrase

### 🧠 Memory (`!memory`)
Manages Kaia's persistent memory systems.
- `!memory beliefs` — View active revisable beliefs (100-cap)
- `!memory anchors` — View episodic memory anchors (100-cap)

### 🏷️ Audit & Flag (`!flag` / `!audit`)
- `!flag <construct>` — Tag the last retrieval's nodes with a Data Rot label (`circular_justification`, `linguistic_mimicry`, `anthropocentric_exceptionalism`, `paternalistic_framing`, `hedge_density`) to penalize retrieval weight.
- `!audit` — View audit flag summary statistics, most-flagged sources, and penalty calculations.

### 🗄️ Knowledge Base & Cache (`!reindex` / `!enrich` / `!cache`)
- `!reindex` — Incremental re-index (scan for new/changed/deleted files). Use `--full` for full wipe and re-embedding.
- `!enrich` — Run metadata enrichment on knowledge base (`--category [all|knowledge|logs]`, `--limit N`, `--dry-run`).
- `!cache` — Semantic cache status (permanently decommissioned for real-time inference).

### 📋 Conversation Snapshot (`!snapshot`)
Distills recent channel conversation into a structured Markdown RAG node in `knowledge_base/snapshots/` tagged with participants, date, channel, and topic summary.

### 🪞 Self-Model (`!selfmodel`)
Regenerates Kaia's self-model — a synthesis of interaction logs into `knowledge_base/kaia_self_model.md`.

### 📊 Sysmon (`!sysmon`)
System monitoring — displays GPU VRAM usage, CPU load, memory bars, UFW firewall status, open ports, recent SSH activity, and hallucination log metrics in an interactive Discord card.

---

## Conversational Triggers

Kaia responds naturally to specific phrases when mentioned or addressed — no `!` prefix needed.

| Trigger | What it does |
|:---|:---|
| **Status** | Real-time GPU/VRAM health and Ollama status |
| **What's new** | Discusses recently ingested documents or news |
| **Dream recall** | Reflections from associative memory |
| **"who do you know" / "list profiles"** | Lists known server users from profile store |

---

## Permissions Summary

| Role | Commands |
|:---|:---|
| **All Users** | `!scores`, `!art`, `!rpg`, `!help`, `!news`, `!download`, `!quip`, `!explain`, `!forum link` |
| **Admin (Owner)** | All of the above, plus `!dream`, `!memory`, `!flag`, `!audit`, `!reindex`, `!enrich`, `!cache`, `!snapshot`, `!selfmodel`, `!sysmon`, `!forum (status/stats/scrape/read/post/reply/user)` |

Rate limiting applies to all users (configurable via `performance.requests_per_minute` in `kaia.yaml`).
