# 📖 Kaiacord Documentation Portal

Welcome to the official **Kaiacord** documentation directory. This portal contains comprehensive design specifications, system architectures, maintenance procedures, and development guides for the local AI persona and the Aethelgard TTRPG engine.

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
*   [Intelligence & Decision Layer](03-architecture/intelligence-layer.md) — Dual-path intent classification and self-healing LLM loops.
*   [Utilities Library](03-architecture/utils-reference.md) — Developer reference to standard helpers and modules.

### 💻 [04 — Development & Testing](04-development/)
*   [Testing Framework](04-development/testing.md) — Async pytest setups, mock engines, and verification suites.

### 🔒 [05 — Security & API Keys](04-security/)
*   [Twikit Credential Management](04-security/x-twikit-credentials.md) — Local cookie persistence, twikit API handling, and security notices.

### 🔧 [06 — Maintenance Procedures](05-maintenance/)
*   [Standard Operating Procedures](05-maintenance/procedures.md) — Daily tasks, database optimization, and manual cache invalidations.
*   [Fixes & Phase History](05-maintenance/fixes-history.md) — Chronological history of software patches and version releases.

### 🛠️ [07 — Technical Troubleshooting](06-troubleshooting/)
*   [Common Issues & Remedies](06-troubleshooting/common-issues.md) — Setup errors, dependency conflicts, VRAM exceptions, and database lockups.

### 📊 [Reports & System Audits](reports/README.md)
*   [Master System Status](reports/MASTER_REPORT.md) — Core metrics, system health logs, and current operational reports.
*   [Claude Production Audit](reports/Claude_Report.md) — Deep architectural audit of software patterns.
*   [Phase 1–50 Archive](reports/Phase_1_50_History.md) — Archive of historical development records.
*   [Phase 51–53 Milestones](reports/Phase_51_53_Report.md) — Record of cognitive pipeline implementation phases.
*   [Strategic Roadmap](reports/roadmap.md) — Future feature specifications and development priorities.

### ⚔️ [Aethelgard TTRPG Specifications](ttrpg/)
*   [System Specification](ttrpg/aethelgard_system.md) — Complete game rules, combat formulas, class trees, and item structures.
*   [Lore & World Bible](ttrpg/aethelgard_lore_bible.md) — Canon history and geographic layouts of Aeridor.
*   [Balance & Audit Report](ttrpg/CLAUDE_REPORT.md) — Strategic balancing sheets and loot table audits.

---

## 🔗 Navigation Quick Links

| Objective | Target Document |
| :--- | :--- |
| **I want to deploy Kaiacord** | [🚀 Quick Start Guide](01-getting-started/quick-start.md) |
| **I need to add/debug a command** | [📘 Command Reference](02-user-guide/commands.md) |
| **I want to understand the VRAM split** | [🏗️ GPU & VRAM Management](03-architecture/gpu-management.md) |
| **I need to fix a database exception** | [🛠️ Common Issues & Remedies](06-troubleshooting/common-issues.md) |
| **I want to verify Aethelgard balance** | [⚔️ TTRPG Balance & Audit Report](ttrpg/CLAUDE_REPORT.md) |
| **I need to see the latest audit status** | [📊 Master System Status](reports/MASTER_REPORT.md) |
