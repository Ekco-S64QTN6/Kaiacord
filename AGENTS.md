# AGENTS.md

> Instructions for AI coding agents working on this repository.
> **Canonical agent directive.** `GEMINI.md` and `CLAUDE.md` point here; do not duplicate content into them.

---

## 1. Project Overview

**Kaiacord** is a self-hosted Discord bot: `discord.py 2.6.4`, Python 3.12, Ollama for local
inference on a single RTX 3060 12 GB.

| Subsystem | Where | Summary |
|:--|:--|:--|
| **Kaia** | `utils/core/` | AI persona. 28-feature cognitive pipeline in `message_processor.py`, post-generation safety pipeline in `safety_pipeline.py` + `response_filter.py`, hybrid BM25 + vector RAG. |
| **Aethelgard TTRPG** | `utils/ttrpg/` | Deterministic turn-based RPG, 77-floor mega-dungeon. |
| **Fractal art** | `utils/core/kaia_art.py` | Electric Sheep flame renderer, CPU-only NumPy/SciPy. |
| **Social & forum** | `utils/social/` | Project 1999 forum client, moderation queue, Bluesky/X (both disabled by default). |
| **Monitoring** | `utils/infrastructure/monitoring/` | Curses dashboard (`btop_dashboard_v2.py`). |

Models: `gemma3:12b` (GPU), `gemma2:2b` (CPU classifier), `nomic-embed-text-cpu` (CPU embeddings).

---

## 2. Running and Validating Code

Use the virtualenv interpreter. It has the project's dependencies; the system interpreter does
not.

```bash
venv/bin/python3 -m pytest tools/tests/unit/ tools/tests/integration/ -q
venv/bin/python3 -c "from utils.core.message_processor import MessageProcessor"
venv/bin/python3 -c "import ast, io; ast.parse(io.open('utils/core/message_processor.py').read())"
```

> [!NOTE]
> **Correction (Sept 2026).** Earlier versions of this file claimed that importing anything from
> `utils/` would "hang indefinitely" and that agents must restrict themselves to `ast.parse` and
> `exec()`. **That is not true.** Importing `utils.core.message_processor`, `utils.ttrpg.
> combat_engine`, and every other module completes normally, on both the venv and system
> interpreter. The claim pushed agents away from the fastest and strongest verification method
> available — actually importing the code and calling it — toward weaker substitutes.
>
> The real constraint is narrower: use `venv/bin/python3`, because the system interpreter lacks
> the dependencies (`python3 -m pytest` collects zero tests rather than hanging). Wrapping
> commands in `timeout` is still good hygiene, not a workaround for a hang.

**Do not** run `python Kaiacord.py` to test a change — that starts a real Discord client against
the live token. Import the module and call the function instead.

### Verify behaviour, not just syntax

The strongest check is exercising the code path with real inputs:

```bash
venv/bin/python3 -c "
from utils.core.response_filter import BotSpeakFilter as B
print(repr(B.harden(\"ekco,\n\nyou're right; the cron job was the culprit.\")))"
```

---

## 3. Registry Integrity (TTRPG)

Registry files hold large data dicts **and** critical helper functions in the same file. Bulk
edits have previously truncated files and silently deleted helpers, causing outages.

**After any bulk edit to a registry, run all five:**

```bash
F=utils/ttrpg/equipment_registry.py
grep -n "^def " $F                                     # 1. helpers still present
grep -c "^}" $F                                        # 2. dict closures intact
venv/bin/python3 -c "import ast,io;ast.parse(io.open('$F').read())"   # 3. syntax
tail -20 $F                                            # 4. no truncation
timeout 10 venv/bin/python3 -c "exec(open('$F').read()); print(len(WEAPONS))"  # 5. counts
```

`equipment_registry.py` must always export `get_equipment` and `get_caravan_stock`.

**8-space indent rule:** item properties live at 8-space indent inside their sub-dict. A
property at 4-space indent (`"droppable_only": True` is the recurring offender) silently
attaches to the wrong parent and corrupts data without raising.

### Current counts — verify, don't trust

These drift every phase, and stale numbers in this file have misled agents before. Compute them:

```bash
timeout 10 venv/bin/python3 -c "
exec(open('utils/ttrpg/monster_registry.py').read()); print('monsters', len(MONSTERS))"
timeout 10 venv/bin/python3 -c "
exec(open('utils/ttrpg/equipment_registry.py').read())
print('gear', sum(len(d) for d in (WEAPONS,ARMOR,HEADGEAR,BOOTS,ACCESSORIES)), '+ consumables', len(CONSUMABLES))"
```

At time of writing: **369 monsters**, **395 gear + 58 consumables = 453 items**, 253 fish,
12 quests, 10 classes.

---

## 4. Architecture Rules

- **Python owns deterministic state.** Combat resolution, stat maths, inventory, and budgets are
  plain Python. The LLM narrates outcomes; it never computes them.
- **Defence soft-cap** `min(10, raw) + max(0, raw - 10) // 2` and **global DEF cap**
  `level * 1.5 + 12` are intentional. Do not remove or bypass.
- **Character sheets** go through `character_manager.load()` / `.save()` only, never direct file
  access. It uses per-user async locks.
- **Atomic writes everywhere**: write `.tmp`, then `os.replace()`.
- **Blocking work off the event loop.** File I/O, PIL, and CPU rendering must be wrapped in
  `asyncio.to_thread()`. This is not theoretical — vision image preparation was found running
  full-resolution PIL decode and base64 synchronously on the loop, stalling every other
  coroutine.
- **GPU is reserved for Ollama.** No CUDA, Numba, or PyCUDA for non-LLM work. CPU + NumPy only.
  All Ollama calls go through `gpu_memory_manager` with an appropriate `GPUTaskPriority`
  (`grep -rc run_with_gpu_guard utils/` for current call sites).
- **`secrets` for security-relevant randomness** (combat rolls, loot, tokens). `random` is fine
  for flavour (dream shuffling, world-event variety).

---

## 5. Kaia Cognitive Pipeline

- All 28 behavioural injections in `message_processor.py` are **pure Python heuristics** — no LLM
  calls. Each is wrapped in `try/except Exception: pass` so a non-critical feature can never
  break the response path. This is mandatory for new injections.
- **Pre-initialise variables before `try` blocks.** A production `UnboundLocalError` came from a
  local bound in only one branch of an `if/else` and read unconditionally afterwards.
- **Trace the actual call path before editing.** Several paths bypass `MessageProcessor`
  entirely — see §6. Modifying `message_processor.py` will not change forum, social, dream, or
  monologue behaviour.

### Token budget

The context window is 16,384 tokens. `optimize_context()` in `context_optimizer.py` reserves
`system_reserve_tokens` + `max_response_tokens` + the user message, then splits the remainder
between RAG and history. **Anything you add to the system prompt comes out of retrieval.**

Two toggles exist because those blocks are expensive:

| Key | Default | Cost |
|:--|:--|:--|
| `features.self_model_injection` | `false` | ~900 tokens/turn |
| `features.constitution_injection` | `true` | ~2,400 tokens/turn |

Persona (`knowledge_base/kaia_persona.md`) is never truncated, so additions there are permanent
per-turn cost. Keep new rules terse.

### Generation temperature

`base_temperature` 0.70 for conversation, `rag_temperature` 0.35 for document-grounded work.
The `is_grounded` predicate that selects between them must key on the *source* being reference
material — an earlier version matched any `retrieval_method in (vector, bm25, hybrid)`, which is
true for nearly every turn and silently ran all conversation at 0.35, producing flat and
sycophantic prose.

### Output filters

`response_filter.py` guards run in two modes and the distinction matters:

- `mode="clause"` — the offence is a *prefix* on real content (`"you're right; <substance>"`).
  Excise the clause, keep the substance.
- `mode="sentence"` — the whole sentence is the artefact (bot-speak, prompt echo). Drop it.

Using sentence mode on concessional prefixes deleted entire valid answers and forced
regenerations; using clause mode on mid-sentence patterns left grammar rubble
(`"the and i'll investigate."`). When adding a pattern, decide which shape it is.

**Never let a filter empty a good response.** An empty return triggers a full regeneration,
which costs a whole inference round-trip.

### Persona grounding facts

- Ekco's **Lucky**, Starkind's **Nala** and **Marley** are living biological cats. Kaia's
  **Pixel** is a vintage-modded robotic cat. Never apply hardware jargon ("sensor readings",
  "thermal equilibrium", "battery swap") to biological pets.
- Kaia lives in a small apartment. She has no server racks, datacenter, remote access to user
  machines, or readouts of her own processing load.
- "Kaia" = "Kaia Artificial Intelligence Agent" (recursive).
- If asked about an image with no attachment present, say no image is visible.
- If asked for a quote's source with no verified RAG document, say the source is unverified.

---

## 6. LLM Call Paths

Not everything goes through `MessageProcessor`. Trace the real `ollama_client` call before
editing.

| Path | Entry point | Pipeline |
|:--|:--|:--|
| **Discord chat** | `MessageProcessor.process()` | Full cognitive pipeline, RAG, intent classification, full safety pipeline |
| **Proactive opener** | `kaia_proactive.py` → `generate_opener()` | Selective injections; `harden()` + contamination filter + style collapsers |
| **Afterthought** | `background_tasks.py` | Emotional arc + channel memory; full post-generation pipeline |
| **Forum auto-post** | `background_tasks.py` → `_make_forum_auto_post_task()` | Direct Ollama call, bypasses `MessageProcessor`; `harden()` only |
| **Forum tech support** | `background_tasks.py` → `_make_forum_support_task()` | Direct call, BM25/hybrid grounded, mandatory disclaimer footer |
| **Social responder** | `kaia_social_responder.py` | Direct call, bypasses `MessageProcessor` |
| **Dream engine** | `kaia_dream.py` | Direct call, dream summary + belief extraction |
| **Inner monologue** | `kaia_monologue.py` | Direct call, background thought generation |

---

## 7. Forum & Social Operations

- **Moderation queue**: all auto-generated forum posts and support replies go to `#kaia-opolis`
  as drafts with Accept/Reject buttons before submission.
- **Zero-hallucination support**: technical replies must be BM25/hybrid grounded in
  `knowledge_base/wiki/` and `knowledge_base/troubleshooting/`, hallucination-checked, and end
  with the disclaimer footer.
- **Capped scraping**: 6-hour interval, 2–3 drafts per run; profile scrapes limited to 20 post
  pages / 10 thread pages, cached 4 h (history) and 1 h (profile).
- **Bluesky and X are disabled** (`bluesky.enabled`, `x_twitter.enabled` = `false`). Credentials
  alone do not re-enable them; the flag gates the integration and the mention poller is not
  started when both are off.

---

## 8. Logging

- Production telemetry is `logs/kaiacord.log`. **Test runs go to `logs/kaiacord.test.log`** —
  `UnifiedLogger._resolve_log_file()` detects pytest. Do not remove this: mock artifacts in the
  shared log were previously indistinguishable from production incidents and cost real
  debugging time.
- Elevate core cognitive actions (monologue, dream summaries, belief shifts, anchor formation),
  scraper operations, and mood changes to `log_info`/`log_warning` so they surface in the
  dashboard.
- When auditing the log, **separate production runs from test runs first**. Segment by the
  "Unified logging system initialized" boot marker and discard segments containing `MagicMock`,
  `test-model`, or `(case test)`.

---

## 9. Knowledge Base

- Ingest with `tools/maintenance/ebook_to_kb_md.py` (EPUB/PDF/TXT/HTML) or the
  `knowledge_base/epub-to-md.sh` picker. Never drop raw `pandoc` output into the tree — it
  carries fenced divs, empty anchors, style spans, and Calibre frontmatter that degrade
  retrieval.
- Naming: `books/` uses `Book - <Title> by <Author>.md`; `documents/` uses `<Topic> - <Title>.md`.
- Frontmatter schema: `title`, `category`, `document_type`, `summary`, `keywords`. A hand-written
  summary substantially outperforms the auto-extracted fallback.
- `tools/maintenance/repair_kb_book_structure.py` repairs already-converted files (dry run by
  default).
- **Do not fabricate chapter headings.** Several books have no chapter markers in their text; a
  heading at a guessed position attaches a chapter name to the wrong passage and retrieves worse
  than no heading at all.

---

## 10. Working Practice

**Measure before optimising.** Numbers from this codebase that changed decisions:

- `harden()` costs ~1 ms against ~14,900 ms of inference — filter micro-optimisation is noise.
- RAG retrieval is ~0.65 s (p50); inference is ~91% of turn latency.
- Prompt size costs ~0.65 s per 1,000 tokens.
- Response length p99 is 265 tokens, max 852 — reserving 2,048 wasted ~1,200 tokens of RAG
  budget every turn.

**Verify claims against the code.** Several long-standing statements in this file were simply
false (see §2). If a doc and the code disagree, the code wins, and the doc should be fixed.

**Preserve content when cleaning.** Any transform that removes text should be checked for
retention. A page-number stripper compiled with `re.IGNORECASE` silently deleted prose lines;
word-count comparison caught it.

**Scope containment.** If asked to update a specific file (e.g. a report), do not modify other
files. Document proposed fixes in the report; apply them only when asked.

**Don't stack prompt instructions.** Adding another negative constraint on top of a contradictory
one causes instruction leakage into output. Fix the prompt architecture instead.

**Take correction seriously.** If the user says a fix did not work, re-verify the active call
path before assuming the bot needs restarting.

---

## 11. Do Not Touch

| Path | Why |
|:--|:--|
| `.env` | Tokens and API keys |
| `memory/` | Live runtime state; never commit |
| `Kaiacord.py` | Orchestrator; read fully before any change |
| `knowledge_base/kaia_persona.md` | Changes alter Kaia's entire behavioural baseline |
| `config/` | Downstream effects across all subsystems |
| `knowledge_base/user_logs/` | Real user messages. Kaia's turns may be corrected; **user turns never** |

---

## 12. Commits

- Format: `[area] Brief description` — e.g. `[ttrpg] Add missing owlbear stat block`
- Areas: `ttrpg`, `fishing`, `combat`, `housing`, `alchemy`, `core`, `docs`, `config`, `kaia`,
  `art`, `infra`, `social`
- One logical change per commit; don't mix balance changes with bug fixes.

---

## 13. Reference

| Topic | File |
|:--|:--|
| Architecture | `docs/03-architecture/overview.md` |
| RAG system | `docs/03-architecture/rag-system.md` |
| GPU management | `docs/03-architecture/gpu-management.md` |
| Testing | `docs/04-development/testing.md` |
| TTRPG spec | `docs/ttrpg/aethelgard_system.md` — **read before touching combat** |
| TTRPG balance | `docs/ttrpg/ttrpg_report.md` |

> `docs/reports/` (audit reports, master report, history) is **git-ignored** — it contains
> transcript excerpts and runtime telemetry. It exists in a working checkout but not on GitHub,
> so do not link it from tracked documentation.
