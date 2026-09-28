# 📖 Kaiacord Documentation

Design specifications, system architecture, maintenance procedures, and development guides for the Kaia persona and the Aethelgard TTRPG engine.

---

## 📂 Documentation Taxonomy

### 🚀 [01 — Getting Started](01-getting-started/)
*   [Installation Guide](01-getting-started/installation.md) — Step-by-step platform setup.
*   [Quick Start Spec](01-getting-started/quick-start.md) — Launch procedures, environment tuning, and initialization testing.

### 📘 [02 — User Guide](02-user-guide/)
*   [Command Reference](02-user-guide/commands.md) — Detailed specifications for all user-facing and administrator-only commands.
*   [Dashboard Manual](02-user-guide/dashboard.md) — Curses-based real-time terminal UI monitoring dashboard guide.
*   [Persona & Styling Guidelines](02-user-guide/persona.md) — Guidelines shaping Kaia's tone, character constraints, and vocabulary.
*   [News Briefs Engine](02-user-guide/news-system.md) — Daily tech briefs generation, retention thresholds, and categorization.
*   [Social Integrations](02-user-guide/social-media.md) — Multi-platform setup guide for Bluesky and X/Twitter posting.
*   [Forum Integration](02-user-guide/forum-integration.md) — Deep-scraping and thread-reply architectures.
*   [User Profiling & Identity](02-user-guide/user-profiling.md) — Multi-platform identity bridging guidelines.

### 🏗️ [03 — Architecture Spec](03-architecture/)
*   [System Overview](03-architecture/overview.md) — Monolithic overview of the orchestrator and AppContext dependency hub.
*   [GPU & VRAM Management](03-architecture/gpu-management.md) — VRAM budgeting constraints, KV cache limits, and CPU model pinning.
*   [Grounding & RAG Subsystem](03-architecture/rag-system.md) — Ingestion, routing by intent, hybrid search, whose logs a turn may see, and how chunks are labelled in the prompt.
*   [Intelligence & Decision Layer](03-architecture/intelligence-layer.md) — Regex intent matching (no classifier model) and self-healing LLM loops.
*   [Utilities Library](03-architecture/utils-reference.md) — Developer reference to standard helpers and modules.

### 💻 [04 — Development & Testing](04-development/)
*   [Testing Framework](04-development/testing.md) — Running the suite, markers, and the rules that keep a test honest and out of live state.

### 🔒 [04 — Security & API Keys](04-security/)
*   [Twikit Credential Management](04-security/x-twikit-credentials.md) — Local cookie persistence, twikit API handling, and security notices.

### 🔧 [05 — Maintenance Procedures](05-maintenance/)
*   [Standard Operating Procedures](05-maintenance/procedures.md) — Daily tasks, database optimization, and manual cache invalidations.
*   [Fixes & Phase History](05-maintenance/fixes-history.md) — Where the change history lives: `git log` for the public record, the local reports for the rest.

### 🛠️ [06 — Technical Troubleshooting](06-troubleshooting/)
*   [Common Issues & Remedies](06-troubleshooting/common-issues.md) — Setup errors, dependency conflicts, VRAM exceptions, and database lockups.

### 📊 Reports & System Audits — *local only*

Operational audits live in `docs/reports/`, which is **git-ignored**: they quote user transcripts
and runtime telemetry, so they stay on the deployment machine rather than in the public
repository. `docs/reports/README.md` indexes them *(local only — the link would 404
on GitHub, which is why nothing here links into that tree)*.

There are three reports and four supporting folders:

```
reports/
├── master_report.md   Where every subsystem stands, and the roadmap of unbuilt work
├── audit_report.md    The review checklist: every file, the commit that verified it
├── history.md         The engineering log, Phase 1 to now, newest at the bottom
├── subsystems/        Deep write-ups of one part: music, art, the persona LoRA
├── investigations/    Dated one-off audits
├── reference/         Background research (Strudel guide, data curation)
├── templates/         Prompts to hand an agent, such as the code-review directive
└── archive/           Finished or superseded documents
```

### ⚔️ [Aethelgard TTRPG Specifications](ttrpg/)
*   [System Specification](ttrpg/aethelgard_system.md) — Complete game rules, combat formulas, class trees, and item structures.
*   [Lore & World Bible](ttrpg/aethelgard_lore_bible.md) — Canon history and geographic layouts of Aeridor.
*   [Balance & Audit Report](ttrpg/ttrpg_report.md) — Strategic balancing sheets, monster and item budgets, and loot table audits.
*   [Spine Variety Audit](ttrpg/Spine_Variety_Audit.md) — Floor pool variety and mega-dungeon distribution.
*   [Historical Archive](ttrpg/Historical_Archive.md) — TTRPG progression change logs and historical records.

---

## 🔗 Navigation Quick Links

| Objective | Target Document |
| :--- | :--- |
| **I want to deploy Kaiacord** | [🚀 Quick Start Guide](01-getting-started/quick-start.md) |
| **I need to add/debug a command** | [📘 Command Reference](02-user-guide/commands.md) |
| **I want to understand the VRAM split** | [🏗️ GPU & VRAM Management](03-architecture/gpu-management.md) |
| **I need to fix a database exception** | [🛠️ Common Issues & Remedies](06-troubleshooting/common-issues.md) |
| **I want to verify Aethelgard balance** | [⚔️ TTRPG Balance & Audit Report](ttrpg/ttrpg_report.md) |
| **I need to see the latest audit status** | `docs/reports/master_report.md`, `audit_report.md` and `history.md` *(local only)* |
| **I want to see all reports** | `docs/reports/README.md` *(local only)* |

