# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **This is the canonical agent directive.** It is the only one. `AGENTS.md` and `GEMINI.md` used
> to exist alongside it and were removed in September 2026 — see [§14](#14-why-one-file).

---

## 1. Project Overview

**Kaiacord** is a self-hosted Discord bot: `discord.py 2.6.4`, Python 3.12, Ollama for local
inference on a single RTX 3060 12 GB.

| Subsystem | Where | Summary |
|:--|:--|:--|
| **Kaia** | `utils/core/` | AI persona. 28-feature cognitive pipeline in `message_processor.py`, post-generation safety pipeline in `safety_pipeline.py` + `response_filter.py`, hybrid BM25 + vector RAG. |
| **Aethelgard TTRPG** | `utils/ttrpg/` | Deterministic turn-based RPG, 77-floor mega-dungeon. |
| **Fractal art** | `utils/core/kaia_art.py` | Electric Sheep flame renderer, CPU-only NumPy/SciPy. |
| **Music** | `utils/audio/` | Live-coded sets in a voice channel, driving Strudel in a real browser. No LLM, no GPU — see [§7](#7-music-engine). |
| **Social & forum** | `utils/social/` | Project 1999 forum client, moderation queue, Bluesky/X (both disabled by default). |
| **Monitoring** | `utils/infrastructure/monitoring/` | Curses dashboard (`btop_dashboard_v2.py`). |

Models: `gemma3:12b` (GPU), `nomic-embed-text-cpu` (CPU embeddings). **There is no classifier
model.** Intent is matched by regex in `IntentParser.fast_parse`. A `gemma2:2b` second pass used
to run on every ambiguous message and its verdict was never read — `ctx.intent` only ever came
from the fast path — so the dispatch, the model, its warm-up and its config were removed in
September 2026. Do not re-add a classification model without also consuming its result.

Configuration resolves **environment variables → `config/kaia.yaml` (your overrides) →
`config/default_config.yaml` (defaults)**. Edit `kaia.yaml`; leave the defaults file alone.

---

## 2. Running and Validating Code

Use the virtualenv interpreter. It has the project's dependencies; the system interpreter does
not.

```bash
venv/bin/python3 -m pytest -q                                            # whole suite; pytest.ini sets testpaths
venv/bin/python3 -m pytest -q -m "not ollama and not gpu and not slow"   # no external services
venv/bin/python3 -m pytest tools/tests/unit -q                           # just the fast ones
venv/bin/python3 -m pytest tools/tests/unit/test_response_filters.py -q  # one file
venv/bin/python3 -m pytest tools/tests/unit/test_response_filters.py::test_harden_is_idempotent   # one test
venv/bin/python3 -c "from utils.core.message_processor import MessageProcessor"
venv/bin/python3 -c "import ast, io; ast.parse(io.open('utils/core/message_processor.py').read())"
```

Baseline for the no-external-services run, verified 2026-09-15: **1,347 passed, 10 skipped,
3 deselected, 2 xfailed** in ~107 s. Only three tests in the whole suite need Ollama or a GPU, so
that invocation is the one to use by default — the full `pytest -q` additionally loads
`gemma3:12b`, which evicts the production model from VRAM.

**There is no linter or formatter.** No `ruff`, `black`, `pyproject.toml`, `setup.cfg`, or
pre-commit hook exists, and none is in `requirements.txt`. Don't go looking for one, and don't
introduce one without asking. Validation is the test suite plus exercising the code you changed.

> [!NOTE]
> **Correction (Sept 2026).** Earlier agent docs claimed that importing anything from `utils/`
> would "hang indefinitely" and that agents must restrict themselves to `ast.parse` and `exec()`.
> **That is not true.** Importing `utils.core.message_processor`, `utils.ttrpg.combat_engine`, and
> every other module completes normally, on both the venv and system interpreter. The claim pushed
> agents away from the fastest and strongest verification method available — actually importing the
> code and calling it — toward weaker substitutes.
>
> The real constraint is narrower: use `venv/bin/python3`, because the system interpreter lacks
> the dependencies (`python3 -m pytest` collects zero tests rather than hanging). Wrapping
> commands in `timeout` is still good hygiene, not a workaround for a hang.

> **Why this matters more than it looks (Sept 12, 2026).** A system update moved `/usr/bin/python`
> from 3.12 to 3.14, and the bot was started as `python Kaiacord.py` without the venv active. It
> *ran* — a stray set of packages under `~/.local/lib/python3.14` was enough to boot it — and then
> failed hours later inside two unrelated subsystems: `No module named 'bs4'` in forum scraping,
> and `cannot import name 'genai' from 'google'` in news. Neither traceback pointed anywhere near
> the cause, and reinstalling `beautifulsoup4` "fixed" one of them by landing in that same stray
> directory, which hid the real fault for another day.
>
> `Kaiacord.py` now re-execs into `venv/bin/python` when started under anything else
> (`KAIA_NO_REEXEC=1` opts out), and `kaia-tools.sh` says so loudly when it falls back to the
> system interpreter. The guard means a wrong-interpreter launch can no longer half-work — but the
> rule stands for anything you run by hand, because nothing re-execs a bare `python3 -c`.

**Do not** run `python Kaiacord.py` to test a change — that starts a real Discord client against
the live token. Import the module and call the function instead.

Operational entry points — health checks, RAG re-indexing, knowledge-base ingestion — are behind
`bash scripts/kaia-tools.sh`. The README's *Operations* section lists the direct invocations.

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

These drift every phase, and stale numbers in agent docs have misled agents before. Compute them:

```bash
timeout 10 venv/bin/python3 -c "
exec(open('utils/ttrpg/monster_registry.py').read()); print('monsters', len(MONSTERS))"
timeout 10 venv/bin/python3 -c "
exec(open('utils/ttrpg/equipment_registry.py').read())
print('gear', sum(len(d) for d in (WEAPONS,ARMOR,HEADGEAR,BOOTS,ACCESSORIES)), '+ consumables', len(CONSUMABLES))"
```

Verified 2026-09-14: **369 monsters**, **395 gear + 58 consumables = 453 items**, 253 fish,
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
  entirely — see [§6](#6-llm-call-paths). Modifying `message_processor.py` will not change forum,
  social, dream, or monologue behaviour.

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

**There is a third shape, and it is the one that keeps getting shipped: a *substring*
excision inside a clause.** The removed span is usually carrying the grammar, so taking it
leaves the sentence without its subject. Two guards did this in one week:

| Guard | Wrote | Shipped |
|:--|:--|:--|
| `PROMPT_ECHO_GUARD` | `the "dead internet theory" is… concerning.` | `the is… concerning.` |
| `DIRECTIVE_LEAK_GUARD` | `the system warning is unhelpful on its own.` | `theis unhelpful on its own.` |

The first was queued to the Project 1999 forum for review before anyone noticed. Any guard
that excises inside a sentence must call `response_filter.excision_broke_grammar(before,
after)` and keep the original when it returns True — shipping the offence beats shipping a
sentence with a hole in it. `strip_prompt_echo` additionally declines outright when the span
is the subject of its sentence: quoting someone's term to refer to the thing is how you
refer to a thing, and was never the fault that guard was written for.

**Never let a filter empty a good response.** An empty return triggers a full regeneration,
which costs a whole inference round-trip — and if every attempt is rejected she says nothing at
all. That happened: three contemplative replies to a question about her own code were each
rejected for ellipsis-affect drift, 35 s of inference discarded, silence delivered. Exhaustion is
now recoverable — `_generate_with_retries` retains rejected attempts, defuses the cadence with
`EmergencyContaminationFilter.defuse_ellipsis_affect`, and **re-runs the full pipeline** on the
result. Salvaged text is used only if it passes on its own merits; the guards are unchanged.

**The reply must have room to exist.** `optimize_context` budgets with
`performance.token_multiplier` (1.6), which is the *median* tokens-per-word — measured against 147
real prompts the ratio runs 1.55 median, 1.66 p90, 2.04 worst. A median used as a bound
underestimates half of all prompts, and four production turns overran the response reserve badly
enough that the reply shrank to 21 tokens. `_clamp_to_context_window` is a hard clamp after
assembly using the observed worst ratio: it drops history oldest-first, never the system prompt or
the user's message, and logs `[CONTEXT_CLAMP]`.

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

Not everything goes through `MessageProcessor`, and **the rows below have been wrong before** —
three of them still claimed "bypasses `MessageProcessor`" months after those paths were unified,
and one named a function that does not exist. Trace the real `ollama_client` call before editing,
and fix this table when it disagrees with the code.

| Path | Entry point | Pipeline |
|:--|:--|:--|
| **Discord chat** | `MessageProcessor.process()` | Full cognitive pipeline, RAG, intent classification, full safety pipeline |
| **Proactive opener** | `kaia_proactive.py` → `generate_opener()` | Selective injections; `harden()` + contamination filter + style collapsers |
| **Afterthought** | `background_tasks.py` | Emotional arc + channel memory; full post-generation pipeline |
| **Forum auto-post** | `background_tasks.py` → `_make_forum_auto_post_task()` | **Through the pipeline**: `forum_drafting.draft_forum_reply()` → `process_external_mention()`. The thread is seeded into `channel_memory` as conversation history — under an **int** key, because that is what `ctx.channel_id` is. It was `str()`-wrapped until Sept 18, so no forum draft ever had history and every one was generated cold. |
| **Forum tech support** | `background_tasks.py` → `_make_forum_tech_support_task()` | Direct call, BM25/hybrid grounded, mandatory disclaimer footer |
| **Social responder** | `kaia_social_responder.py` → `mock_external_mention()` | **Through the pipeline**: builds a `MockMessage` and hands it to the normal `on_message` handler |
| **Quip / social thread** | `social_response_generator.py` | **Through the pipeline** via `process_external_mention(platform="broadcast")` |
| **Observation digest** | `background_tasks.py` → `_make_observation_digest_task()` | Direct call to summarise; the digest text is then spoken verbatim, not re-generated |
| **Dream engine** | `kaia_dream.py` | Direct call, dream summary + belief extraction |
| **Inner monologue** | `kaia_monologue.py` | Direct call, background thought generation |

`utils/audio/` is deliberately **not** in this table: the music engine makes no LLM call at all.

---

## 7. Music Engine

`!music` puts Kaia in a voice channel performing a live-coded set. The arrangement is a scripted
performance in `strudel_patterns.py` / `performance.py` — **no model is involved and no VRAM is
used**, so it is safe to run alongside inference.

```
local HTTP server (assets/strudel/)
    -> Chromium via Playwright, audio routed to a PipeWire null sink
        -> ffmpeg captures the sink monitor as s16le
            -> StrudelAudioSource hands 20 ms frames to discord.py
```

Two behaviours here look like bugs and are not — the module docstring in `strudel_engine.py` is
the authority, but they are the ones most likely to be "fixed" by mistake:

- **The browser runs headed.** Headless Chromium opens an audio stream and emits pure silence:
  routing looks perfect, the sink-input is present, uncorked and at full volume, and the capture
  is 0.0 RMS. Only headed mode makes sound. The window is parked off-screen unless
  `music.show_window` is set.
- **Patterns are applied by clicking a real button.** `evaluate()` through Playwright is not a
  user gesture: it returns true, logs `[cyclist] start`, reports a running AudioContext, and
  produces nothing.

Strudel is AGPL-3.0 and is **not vendored**. `tools/maintenance/fetch_music_assets.py` fetches it
as its own unmodified bundle at install time (needs `ffmpeg` and `pactl`), and this project only
drives it, so the copyleft does not reach Kaiacord. Do not copy Strudel source into the tree.

---

## 8. Forum & Social Operations

- **Moderation queue**: all auto-generated forum posts and support replies go to `#kaia-opolis`
  as drafts with Accept/Reject buttons before submission.
- **Zero-hallucination support**: technical replies must be BM25/hybrid grounded in
  `knowledge_base/wiki/` and `knowledge_base/troubleshooting/`, hallucination-checked, and end
  with the disclaimer footer.
- **Capped scraping**: 6-hour interval, 2–3 drafts per run; profile scrapes limited to 20 post
  pages / 10 thread pages, cached 4 h (history) and 1 h (profile).
- **Bluesky is on, X is off.** As of Sept 2026 `bluesky.enabled` and `bluesky.cross_post_quips`
  are `true` in `kaia.yaml`, so idle quips mirror to her feed; `x_twitter.enabled` is `false`.
  Credentials alone never enable either — the flag gates the integration, and the mention poller
  is not started when both are off.
- **Forum posting is on** (`forum.enabled: true`), behind the Accept/Reject queue above.
  `forum.tech_support_enabled` stays **off**: it answered strangers without staying grounded in
  the wiki, and confidently wrong EQ advice is worse than silence. Do not enable it without
  fixing the grounding.

### Speaking unprompted

Three separate things reach chat without being asked, on **separate** switches so one can be
silenced without the others:

| What | Switch | Where | Notes |
|:--|:--|:--|:--|
| Observation digest | `observation.broadcast_digest` | `#kaia-opolis` | The summary is spoken **verbatim**. It used to be handed to `generate_opener` as hidden context and an unrelated one-liner was sent instead, while the log claimed the digest had aired. |
| Inner monologue | `monologue.broadcast_to_chat` | `#kaia-opolis` | Capped at 6/day, 90-minute gap. `monologue.respect_quiet_hours` is **false**: a thought in her own channel is not the interruption a proactive opener is. |
| Proactive opener | the desire gate + rate limiter | most recent channel | Obeys `proactive.quiet_hour_start`/`quiet_hour_end` (9–22). |
| Idle quip | the idle timer | most recent channel | `quip.broadcast_prefix`. Was posted in a bare ``` block with no label, which is why it read as a stray fragment rather than a thought. |

Both broadcasts are prefixed (`monologue.broadcast_prefix`, `observation.broadcast_prefix`) so
they read as a thought and an observation rather than as remarks aimed at someone.

**The desire gate must not be able to silence her.** `INITIATE_THRESHOLD` was 0.55 while
`observe_exchange` pinned the intellectual need at 0.0 on any active server, capping pressure at
0.16 — she spoke first **once in 102 evaluations**. It is 0.12 now and configurable
(`desires.initiate_threshold`, `desires.gate_enabled`). A chat bot that cannot chat first is not
the point.

---

## 9. Logging

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
- **Never interpolate a document into a log message.** `UnifiedLogger.log()` compacts multi-line
  payloads, but the right fix is at the call site: use
  `log_sanitize.summarize_payload("label", text)`, which reports size instead of content. A
  150-character slice is not a workaround — it lands mid-document and carries its newlines, which
  is how the constitution came to appear in full 771 times in one log.
- Tracebacks are deliberately exempt from compaction; their line structure is the information.
  Pass them through as-is.
- Consecutive repeats of the same message *shape* are collapsed with a suppressed-count tally, so
  a varying number in the text no longer defeats deduplication.

### Telemetry that lies

**Do not trust a success line. Check what was actually transmitted.** This is the single most
productive check in this codebase; a September 2026 review found seven instances, every one of which
had misled someone:

- `"Observation digest broadcast to chat"` fired after sending an unrelated one-liner the opener
  generator had produced *from* the digest. The digest itself had never once been spoken.
- `"Proactive trigger evaluation: no active triggers"` covered five distinct exits, four of which
  never consulted a trigger source. 101 of 102 evaluations said it.
- `"Batch persistence complete for: …"` named every index it *attempted*, including ones that had
  logged `"Failed to persist"` one line above.
- `RAGPersistenceMixin.persist()` cleared `persist_needed` even when every write threw, so the
  retry never happened and the index changes were lost silently.
- `_dispatch_proactive` returned `False` with no log at all when the channel id did not resolve.
  `"Proactive message sent"` appeared once in the entire log.
- `[ELLIPSIS_COLLAPSE]` could not match a lone `…`, so it fired on 0 responses ever.
- `[APOLOGY_GUARD] Trimmed offending clause, kept substance` logged eight times on 2026-09-18
  while emitting `'starkind,  to point that out.'` and `'lune,  to call me out.'` The dangling-tail
  repair ran only when the excised clause had *nothing* in front of it, so every sentence with a
  name, an "and", or a preceding clause shipped the fragment — announced as substance kept.

The pattern behind the first six: **success is logged where the attempt happens, not where the
outcome lands.** The seventh is a variant worth naming separately — **a guard that reports what it
intended rather than what it produced** — and the fix for it is the same shape: when a guard
rewrites text, log the result. When adding a log line that asserts an outcome, make it reachable
only when that outcome occurred, and return what actually succeeded rather than what was tried.

**Two sweeps worth repeating.** Enumerate every bracketed guard tag in `utils/` and count its
occurrences in the production log — a tag with zero hits is either well-calibrated or dead code,
and telling those apart means exercising the guard directly. And pair any claimed number against
an independent measurement: estimated tokens against `prompt_eval_count`, a log line against the
message actually sent, a guard's verdict against its own return value.

---

## 10. Knowledge Base

- Ingest with `tools/maintenance/ebook_to_kb_md.py` (EPUB/PDF/TXT/HTML), reachable from
  `kaia-tools.sh` → Documents & Ingestion. Never drop raw `pandoc` output into the tree — it
  carries fenced divs, empty anchors, style spans, and Calibre frontmatter that degrade
  retrieval.
- **Layout is documented in `knowledge_base/README.md`** — read it before adding a folder. The
  top level was flattened from sixteen folders to twelve in September 2026 (`corrupt_files` +
  `quarantine` → `_quarantine`, `snapshots` + `system_logs` → `runtime`, `blogs` and
  `deep_dive_reports` → `documents`, `documents/tech_updates` → `news/tech_updates`). A new folder
  has to be named in `process_ingress.ALLOWED_FOLDERS`, `knowledge_boundary` and
  `enrich_metadata.knowledge_dirs` or it half-works silently — a sidecar naming a folder absent
  from the allow-list is discarded and the file is filed as a document instead. That is not
  hypothetical: `_classify_folder` returned `"Books"` against an allow-list holding `"books"`, so
  every long PDF `!download` fetched lost its folder hint.
- **A leading underscore means not indexed** (`_ingress`, `_quarantine`), and so does a leading
  dot. The dot rule replaced a named exclusion for `.test` alone, which had left
  `.compacted_backup` (474 files, the raw forum histories compaction had just replaced) and
  `.dream_archive` being walked into the index — handing her the summary *and* everything it
  summarised.
- **An exclusion has two ends, and both must use `RAGIndexerMixin._is_excluded_path`.** The scan
  decides what gets *added*; `_prune_deleted_files` decides what gets *removed*, and it only ever
  removed entries whose file had vanished from disk. So adding the dot rule to the scan alone left
  475 `.compacted_backup` entries in `file_manifest.json` — blocked from being re-added, never
  removed, still retrievable. A new exclusion takes effect on the next sweep only because both
  ends now call the same predicate. Note the prune runs **in the live bot**, so a rule added here
  reaches the index at her next restart, not on a `--trigger`.
- Naming: `books/` uses `Book - <Title> by <Author>.md`; `documents/` uses `<Topic> - <Title>.md`.
- Frontmatter schema: `title`, `category`, `document_type`, `summary`, `keywords`. A hand-written
  summary substantially outperforms the auto-extracted fallback.
- `tools/maintenance/repair_kb_book_structure.py` repairs already-converted files (dry run by
  default).
- **Do not fabricate chapter headings.** Several books have no chapter markers in their text; a
  heading at a guessed position attaches a chapter name to the wrong passage and retrieves worse
  than no heading at all.
- `knowledge_base/_ingress/` is a **staging area**, excluded from RAG indexing. `!download` and
  `!youtube` write there with a `.meta.json` sidecar; `tools/maintenance/process_ingress.py` (hourly, and from
  `kaia-tools.sh` → Documents & Ingestion) normalises, adds frontmatter and provenance, and files
  each document into an allow-listed folder. Do not index `_ingress` — that exclusion is what
  makes it safe for `!download` and `!youtube` to be open to every user.
- A sidecar carrying `"preformatted": true` is filed **without normalisation**. `!youtube` emits
  finished Markdown with timestamp anchors; running the reflow over it would destroy them.
- Maintenance tools that write across the corpus must default to a dry run and require `--apply`.
  `enrich_kb_metadata.py` had no argument parsing at all, so probing it with `--help` rewrote
  frontmatter on 124 files.

### Dreams

`knowledge_base/kaia_dreams/` is its own RAG index, and `context_optimizer` labels anything
retrieved from it **INTERNAL REFLECTION (DREAM)** — as something Kaia thought. Two consequences
follow, and both had already gone wrong by September 2026:

- **Only reflections belong in it.** 868 of 2,399 files were cleaned chat transcripts and scraped
  prose written there by an older pipeline, one of them an American Express advertisement,
  retrievable as a thing Kaia dreamt about credit cards. `tools/maintenance/triage_dreams.py`
  sorts the folder (deterministic, no model) and quarantines the rest.
- **`kaia_dreams` is itself a valid dream source** (`dream_source_type = 'prior_dream'`), so
  anything wrong in there teaches the next night. 250 reflections are reflections on earlier
  dreams; that is how transcript-shaped files came to produce `User:`-prefixed fragments inside a
  reflection about a novel whose own file has no such prefixes.

One file per night is right for *writing* a dream and wrong for retrieving one — forty-two
separate reflections on *Do Androids Dream* retrieve as three fragments chosen by similarity.
`tools/maintenance/consolidate_dreams.py` groups them (by book, by person, by topic, all in
Python) and writes one document per subject. It **extends** an existing document rather than
replacing it; without that, a weekly run would overwrite a 229-reflection synthesis with one built
from the week's seven. Both tools run weekly from `_make_dream_curation_task`
(`dream_mode.auto_curate`).

The synthesis is the fragile half. Asked to merge twelve passages about a person, gemma3 returns
`**1. Key Themes & Recurring Ideas:**` and bullets analysing "the narrator" — a literary essay
about Kaia instead of Kaia. `reads_as_essay()` rejects that shape and retries; do not remove it
without a better check. "the user" is deliberately *not* treated as third person — she uses it
constantly and correctly about the people in her logs.

---

## 11. Working Practice

**Measure before optimising.** Numbers from this codebase that changed decisions:

- `harden()` costs ~1 ms against ~14,900 ms of inference — filter micro-optimisation is noise.
- RAG retrieval is ~0.65 s (p50); inference is ~91% of turn latency.
- Prompt size costs ~0.65 s per 1,000 tokens.
- Response length p99 is 265 tokens, max 852 — reserving 2,048 wasted ~1,200 tokens of RAG
  budget every turn.

**Verify claims against the code.** Several long-standing statements in the old agent docs were
simply false (see [§2](#2-running-and-validating-code)). If a doc and the code disagree, the code
wins, and the doc should be fixed. The §6 call-path table was wrong in four rows at once, so
check it rather than trusting it.

**Segment the log before counting anything.** A decision brief once reported the hallucination
detector had "fired 42 times in the current production log". All 368 entries were unit-test
fixtures; it has never fired on real input. `grep -c` over `logs/kaiacord.log` without splitting
production from test runs (see [§9](#9-logging)) has now produced a wrong conclusion twice.

**Exercise the code, do not just parse it.** `ast.parse` passes happily on a `NameError` waiting
to happen — a config read added to `kaia_proactive` referenced a `config` that module never
imported, and only calling the function found it. Three separate defects this September were
caught by running the changed path and none by reading it.

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

## 12. Do Not Touch

| Path | Why |
|:--|:--|
| `.env` | Tokens and API keys |
| `memory/` | Live runtime state; never commit |
| `Kaiacord.py` | Orchestrator; read fully before any change |
| `knowledge_base/kaia_persona.md` | Changes alter Kaia's entire behavioural baseline |
| `config/` | Downstream effects across all subsystems |
| `knowledge_base/user_logs/` | Real user messages. Kaia's turns may be corrected; **user turns never** |

**`user_profile.md` has more than one writer.** `compact_forum_profiles.py` and
`generate_user_profiles.py` both rebuild it from a fixed key list, and neither consulted
`kaia_identities.registry`. Making one of them identity-aware on Sept 18 was undone at 03:41 the
next morning by the other, which replaced Kaia's own self-reference document with a third-person
personality profile assembled from her own posts. Anything that writes this file has to ask the
registry who the account belongs to first; `test_every_writer_of_user_profile_consults_the_identity_registry`
enforces it.

---

## 13. Commits

- Format: `[area] Brief description` — e.g. `[ttrpg] Add missing owlbear stat block`
- Areas: `ttrpg`, `fishing`, `combat`, `housing`, `alchemy`, `core`, `docs`, `config`, `kaia`,
  `art`, `music`, `infra`, `social`
- One logical change per commit; don't mix balance changes with bug fixes.

---

## 14. Why One File

`AGENTS.md`, `GEMINI.md`, and `CLAUDE.md` were maintained as parallel documents. They drifted, and
by September 2026 they disagreed with each other and with the code:

- Both claimed importing from `utils/` "hangs indefinitely". It does not — verified on the venv
  and system interpreters. The claim steered agents away from the strongest verification method
  they had.
- Both specified Python 3.14+; the project venv runs 3.12.
- `AGENTS.md` gave two different monster counts in the same file (366 and 369; the real number
  was 369) and two different safety-pipeline layer counts.

They were collapsed into pointers, and then into this single file. Duplicated instructions rot
independently. **Do not create `AGENTS.md`, `GEMINI.md`, or a `.agents/` rules tree again** — put
it here.

---

## 15. Reference

| Topic | File |
|:--|:--|
| Architecture | `docs/03-architecture/overview.md` |
| RAG system | `docs/03-architecture/rag-system.md` |
| GPU management | `docs/03-architecture/gpu-management.md` |
| Testing | `docs/04-development/testing.md`, `tools/tests/README.md` |
| TTRPG spec | `docs/ttrpg/aethelgard_system.md` — **read before touching combat** |
| TTRPG balance | `docs/ttrpg/ttrpg_report.md` |
| Contributing | `CONTRIBUTING.md` — human-facing PR workflow |

> `docs/reports/` (audit reports, master report, history) is **git-ignored** — it contains
> transcript excerpts and runtime telemetry. It exists in a working checkout but not on GitHub,
> so do not link it from tracked documentation.
