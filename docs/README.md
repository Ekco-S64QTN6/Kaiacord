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
*   [Grounding & RAG Subsystem](03-architecture/rag-system.md) — BM25, dense vector search, Reciprocal Rank Fusion, and custom index storage.
*   [Intelligence & Decision Layer](03-architecture/intelligence-layer.md) — Regex intent matching (no classifier model) and self-healing LLM loops.
*   [Utilities Library](03-architecture/utils-reference.md) — Developer reference to standard helpers and modules.

### 💻 [04 — Development & Testing](04-development/)
*   [Testing Framework](04-development/testing.md) — Async pytest setups, mock engines, and verification suites.

### 🔒 [04 — Security & API Keys](04-security/)
*   [Twikit Credential Management](04-security/x-twikit-credentials.md) — Local cookie persistence, twikit API handling, and security notices.

### 🔧 [05 — Maintenance Procedures](05-maintenance/)
*   [Standard Operating Procedures](05-maintenance/procedures.md) — Daily tasks, database optimization, and manual cache invalidations.
*   [Fixes & Phase History](05-maintenance/fixes-history.md) — Chronological history of software patches and version releases.

### 🛠️ [06 — Technical Troubleshooting](06-troubleshooting/)
*   [Common Issues & Remedies](06-troubleshooting/common-issues.md) — Setup errors, dependency conflicts, VRAM exceptions, and database lockups.

### 📊 Reports & System Audits — *local only*

Operational audits live in `docs/reports/`, which is **git-ignored**: they quote user transcripts
and runtime telemetry, so they stay on the deployment machine rather than in the public
repository. `docs/reports/README.md` indexes them *(local only — the link would 404
on GitHub, which is why nothing here links into that tree)*.

Reports are organised by purpose:

```
reports/
├── 01-status/      Living documents: master report, audit log, roadmap, history
├── 02-decisions/   Open questions waiting on a call from Ekco
├── 03-subsystems/  Per-subsystem design docs (music engine, art, LoRA)
├── 04-audits/      Point-in-time investigations (grounding, sycophancy, probing)
├── 05-reference/   External research (Strudel guide, data-curation strategy)
├── templates/      Prompts and scaffolding — not reports
└── archive/        Fully actioned or superseded
```

| Report | Contents |
| :--- | :--- |
| `01-status/master_report.md` | System status, metrics, strategic roadmap |
| `01-status/audit_report.md` | Phase-by-phase production audits (cognitive pipeline, RAG, safety, GPU) |
| `01-status/history.md` | Development history, Phase 1 onward |
| `01-status/evolution_proposals.md` | Proposals and backlog |
| `03-subsystems/music_engine.md` | `!music` — Strudel-backed live-coded performance engine |
| `03-subsystems/art_report.md` | Fractal flame renderer and Mandelbrot rebuild |
| `03-subsystems/lora.md` | LoRA fine-tuning pipeline |
| `04-audits/response_accuracy_audit_report.md` | Grounding and persona-fidelity audit |
| `04-audits/consistency_watchdog_sycophancy_report.md` | Epistemic stability and anti-sycophancy analysis |
| `04-audits/cryptographic_inventory_for_kaia.md` | Cryptographic dependency inventory |
| `04-audits/jspace.md` · `04-audits/noon_events_mechanical_audit.md` | Behavioural probing, world-event mechanics |
| `05-reference/strudel-coding-guide.md` | Strudel syntax reference for pattern authoring |
| `05-reference/local-ai-data-curation-strategy.md` | RAG data-curation research |

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

