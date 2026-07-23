# Kaiacord Tools Directory

Production maintenance, diagnostic, development, simulation, and test automation suite for Kaiacord.

---

## 📁 Directory Structure

```
tools/
├── maintenance/     # Production maintenance, health validation & KB cleaner tools
├── diagnostics/     # RAG index diagnostics, knowledge base & model probes
├── development/     # World build generators (Spine layouts), self-model & profile utilities
├── social/          # Project 1999 Forum scrapers, wiki indexers & social cookie managers
├── simulation/      # Aethelgard TTRPG game balance simulation & audit tools
└── tests/           # Automated test suite (unit & integration)
    ├── unit/        # Isolated unit tests for core & TTRPG subsystems
    └── integration/ # End-to-end integration & boot verification
```

---

## 🛠️ Key Utilities & Execution Guide

### 1. System Health & Maintenance (`tools/maintenance/`)

| Script | Purpose | Execution |
|:-------|:--------|:----------|
| `health_check.py` | Validates Ollama models, GPU VRAM, RAG indices, and config | `python3 tools/maintenance/health_check.py` |
| `reindex_rag.py` | Rebuilds BM25 and vector RAG indices | `python3 tools/maintenance/reindex_rag.py` |
| `update_kaia_news.py` | Fetches, synthesizes, and indexes daily news briefs | `python3 tools/maintenance/update_kaia_news.py` |
| `generate_user_profiles.py` | Synthesizes episodic user profile summaries | `python3 tools/maintenance/generate_user_profiles.py` |
| `clean_hallucinations.py` | Cleans hallucinated logs and sanitizes memory streams | `python3 tools/maintenance/clean_hallucinations.py` |
| `enrich_metadata.py` | Auto-enriches document metadata using LLM tagging | `python3 tools/maintenance/enrich_metadata.py` |

### 2. Diagnostics (`tools/diagnostics/`)

| Script | Purpose | Execution |
|:-------|:--------|:----------|
| `diagnose_rag.py` | Deep diagnostic of RAG document retrieval & node scoring | `python3 tools/diagnostics/diagnose_rag.py` |
| `check_indexing_health.py` | Validates document manifest integrity and file counts | `python3 tools/diagnostics/check_indexing_health.py` |
| `check_gemini_models.py` | Queries active Gemini API endpoint models and quotas | `python3 tools/diagnostics/check_gemini_models.py` |

### 3. Development Utilities (`tools/development/`)

| Script | Purpose | Execution |
|:-------|:--------|:----------|
| `generate_spine_layouts.py` | Pre-computes 77-floor Spine of the World mega-dungeon layouts | `python3 tools/development/generate_spine_layouts.py` |
| `generate_self_model.py` | Auto-regenerates Kaia's 30-day identity self-model document | `python3 tools/development/generate_self_model.py` |
| `profile_imports.py` | Analyzes module import performance & boot latency | `python3 tools/development/profile_imports.py` |

### 4. Social & Forum Integrations (`tools/social/`)

| Script | Purpose | Execution |
|:-------|:--------|:----------|
| `scrape_p99_wiki.py` | Crawls & indexes Project 1999 Wiki knowledge base | `python3 tools/social/scrape_p99_wiki.py` |
| `scrape_technical_discussion.py` | Scrapes P99 technical discussion forums for troubleshooting | `python3 tools/social/scrape_technical_discussion.py` |
| `synthesize_technical_knowledge.py` | Synthesizes tech support troubleshooting cheatsheets | `python3 tools/social/synthesize_technical_knowledge.py` |
| `export_x_cookies.py` | Export and format headless browser cookies for X social post dispatch | `python3 tools/social/export_x_cookies.py` |

### 5. Automated Test Suite (`tools/tests/`)

```bash
# Run unit test suite (Safe for live environment)
venv/bin/python3 -m pytest tools/tests/unit/ -v

# Run integration test suite
venv/bin/python3 -m pytest tools/tests/integration/ -v
```
