# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **This is the canonical agent directive.** It is the only one. `AGENTS.md` and `GEMINI.md` used
> to exist alongside it and were removed in September 2026 — see [§14](#14-why-one-file).

---

## 1. Project Overview

**Kaiacord** is a self-hosted Discord bot: `discord.py 2.7.1`, Python 3.12, Ollama for local
inference on a single RTX 3060 12 GB.

`discord.py >= 2.7` and `davey` are both **required, not optional**. Discord enforced its DAVE
end-to-end-encryption protocol for all non-stage voice on 2 March 2026; a client without it is
refused at the handshake with close code 4017 and can never join a voice channel. 2.6.4 has no
DAVE support at all, so `!music` fails with five retries and "Not connected to voice" whatever
the bot does. This file said 2.6.4 until September 2026 — check `requirements.txt`, not here.

| Subsystem | Where | Summary |
|:--|:--|:--|
| **Kaia** | `utils/core/` | AI persona. Behavioural injections in `message_processor.py`, post-generation safety pipeline in `safety_pipeline.py` + `response_filter.py`, hybrid BM25 + vector RAG. |
| **Aethelgard TTRPG** | `utils/ttrpg/` | Deterministic turn-based RPG, 77-floor mega-dungeon. |
| **Fractal art** | `utils/core/kaia_art.py` | Electric Sheep flame renderer, CPU-only NumPy/SciPy. |
| **Music** | `utils/audio/` | Live-coded sets in a voice channel, driving Strudel in a real browser. No LLM, no GPU — see [§7](#7-music-engine). |
| **Social & forum** | `utils/social/` | Project 1999 forum client, moderation queue, Bluesky/X, each behind its own enable flag. |
| **Monitoring** | `utils/infrastructure/monitoring/` | Curses dashboard (`btop_dashboard_v2.py`). |
| **News** | `utils/news/` | Daily briefs filed into `knowledge_base/news/`. The generator (`tools/maintenance/update_kaia_news.py`) calls the Gemini API with Google Search grounding — the only path that sends anything *of hers* off the machine. `utils/news/` itself only reads what was filed. |
| **Radio** | `utils/radio/` | `!skyking` (military EAMs from eam.watch), `!numbers` (number-station schedule from Priyom), `!radio` (scheduled KiwiSDR recording, CPU transcription, live listening in voice). Feeds polled every `radio.poll_hours` (6); history in `memory/radio/`. See §7. |
| **Sky** | `utils/sky/` | `!iss`, `!nasa`, `!earth`, `!spaceweather`, `!rocks`, `!launch`, `!quake`, `!sky`. Public feeds fetched on request and cached per feed; passes and the night sky computed locally (Skyfield). Every radio/sky box ends with the theme's small print from `utils/commands/nightshift.py`. |
| **LoRA fine-tune** | `finetune/` | Numbered pipeline (`01_convert_logs.py` → `05c_evaluate_persona.py`), driven by `scripts/run_finetune.sh`. Trains a persona adapter on her own logs and exports GGUF for Ollama. Off the runtime path — see [§16](#16-fine-tuning). |

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

**Take the baseline from the suite, not from here.** The pass count moves every phase, and this
number has been stale in three files at once — CLAUDE.md, README and CONTRIBUTING each asserted a
different one. Run it and read the tail; what matters is that nothing *failed*, not that the count
matches a doc.

The no-external-services invocation is the default because only **4** of ~1,790 tests need Ollama
or a GPU. The rest of what it deselects is the 82 marked `slow`. Two of the four were unmarked
until September 2026 and ran on every "no external services" invocation, embedding through the
bot's own live Ollama — Ollama's journal (`journalctl -u ollama`) is where that showed up. A test
that touches the daemon is marked `ollama`, whatever else it does. The full `pytest -q` additionally
loads `gemma3:12b`, which evicts the production model from VRAM.

Markers are declared in `pytest.ini` under `--strict-markers`, so a typo'd marker is an error
rather than a silently ignored one: `slow`, `gpu`, `ollama`, `network`, `integration`.

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

Verified 2026-09-24: **369 monsters**, **395 gear + 58 consumables = 453 items**, 248 fish (`len(FISH)`),
12 quests, 10 classes.

---

## 4. Architecture Rules

- **Python owns deterministic state.** Combat resolution, stat maths, inventory, and budgets are
  plain Python. The LLM narrates outcomes; it never computes them.
- **Defence soft-cap** `min(10, raw) + max(0, raw - 10) // 2` and **global DEF cap**
  `level * 1.5 + 12` are intentional. Do not remove or bypass.
- **Character sheets** go through `character_manager.load()` / `.save()` only, never direct file
  access. It uses per-user async locks.
- **Atomic writes everywhere**: `utils/core/atomic_write.write_atomic()`. Do not call
  `Path.write_text` on anything under `knowledge_base/` or `memory/`. The rule dates from a
  half-written registry that caused an outage, and it was being followed where people remembered
  it: a September 2026 sweep found **35 bare `write_text` calls across 21 modules** that rewrite
  the corpus in place, including the nightly metadata enrichment, the hourly ingress filer and
  the dream engine. An interrupted rewrite there raises nothing anywhere — it leaves a truncated
  document that is indexed on the next sweep, retrievable, and indistinguishable from a file that
  was simply short. The temporary is written beside its destination because `os.replace` is only
  atomic within a filesystem. `test_no_corpus_write_bypasses_the_atomic_helper` enforces it now,
  because two grew back after that sweep — including the forum Off-Topic listing, rewritten on
  every scrape.
- **Blocking work off the event loop.** File I/O, PIL, and CPU rendering must be wrapped in
  `asyncio.to_thread()`. This is not theoretical — vision image preparation was found running
  full-resolution PIL decode and base64 synchronously on the loop, stalling every other
  coroutine.
- **Shared JSON state has one read-modify-write path, under a lock.** `memory/beliefs.json`
  goes through `beliefs_store.update()`; `anchors.json` and `memory/relationships/` hold a
  module lock around load-change-save. Each was being rewritten from two threads (the dream
  engine and a chat turn), and whichever read first put its stale copy back last. Snapshot
  before handing anything to a writer thread: `BotState.save()` serialises on the caller's
  thread, because `json.dump` over live dicts on the writer raised mid-iteration and dropped
  the save. `write_atomic` names its temporary per process *and* thread for the same reason.
- **GPU is reserved for Ollama.** No CUDA, Numba, or PyCUDA for non-LLM work. CPU + NumPy only.
  All Ollama calls go through `gpu_memory_manager` with an appropriate `GPUTaskPriority`
  (`grep -rc run_with_gpu_guard utils/` for current call sites). The bot process itself holds
  no CUDA context: a `torch.cuda` call in it creates one, ~100 MiB on a card the model already
  fills, and `clear_gpu_memory()` was doing exactly that on every boot.
- **Every call to the chat model sends the same runner options.** Ollama keeps one runner per
  model and reloads it whenever a request's `num_ctx`, `num_gpu`, `num_thread` or `main_gpu`
  differ from the loaded one. Build options with `gpu_manager.chat_options(**overrides)` — it
  returns the shared runner options, and overrides are for sampling (`temperature`,
  `num_predict`) only. Six call sites built their own dicts, and the monologue, sending no
  `num_ctx` at all, reloaded gemma3 at 4,096 context every 15 minutes; the next chat turn paid a
  full reload back. `journalctl -u ollama | grep "n_ctx  "` shows every reload and its size.
- **That guard is process-local.** `gpu_semaphore` is a module-level `asyncio.Semaphore(1)`, so a
  standalone tool gets its own and coordinates with nothing the bot is doing. What keeps a batch
  job from colliding with live chat is the Ollama daemon queueing per model — so the cost is
  **latency, not corruption**: a message arriving mid-batch waits for the in-flight generation.
  Run long batches when nobody is talking to her, and keep every one of them resumable.
  `docs/03-architecture/gpu-management.md` said BACKGROUND priority "yields to live chat" and made
  this sound safer than it is; it is true inside the bot and false for every tool in `tools/`.
- **A decay applied on read must advance its own clock.** `kaia_mood._apply_decay` decayed mood
  over the span since the last *interaction* and never moved that mark, so every reader between
  two interactions — the prompt injection, the proactive opener, `update()` itself — applied the
  same span again. Arousal fell twice as fast as its 6-hour half-life and energy overshot its
  regeneration ceiling: her mood depended on how often something asked. `bot_state`'s engagement
  decay had the same shape. `kaia_desires._accrue` is the correct one to copy.
- **`secrets` for security-relevant randomness** (combat rolls, loot, tokens). `random` is fine
  for flavour (dream shuffling, world-event variety).

---

## 5. Kaia Cognitive Pipeline

- Every behavioural injection in `message_processor.py` is a **pure Python heuristic** — no LLM
  calls. The count is deliberately not stated: they are numbered `7`, `8`, `8a`, `8a1`, `8b2`
  in the source, there is no clean total, and "28 features" and "11 safety layers" are both
  numbers that have been asserted in docs and been wrong ([§14](#14-why-one-file)). Each is wrapped in `try/except Exception: pass` so a non-critical feature can never
  break the response path. This is mandatory for new injections.
- **Pre-initialise variables before `try` blocks.** A production `UnboundLocalError` came from a
  local bound in only one branch of an `if/else` and read unconditionally afterwards.
- **Trace the actual call path before editing.** Several paths bypass `MessageProcessor`
  entirely — see [§6](#6-llm-call-paths). Modifying `message_processor.py` will not change forum,
  social, dream, or monologue behaviour.

### Heuristics read the user's words, not the turn

`ctx.sanitized_content` is the *enriched* message: quoted reply context before
`[USER_MESSAGE]`, then any scraped page, embed or linked message. A keyword heuristic run over
it attributes all of that to the speaker. Relationship events did — most of 190 stored
repair/friction events were a fetched article, a forum thread dump, or "actually" in passing,
and repair is the heaviest-weighted line in her relationship notes. Use
`sanitizer.user_authored_text()`, match whole phrases on word boundaries, and check the
result against real data (`memory/relationships/`, `knowledge_base/user_logs/`) before
trusting it. The same audit found the curiosity scanner reading the user's *forum* folder and
quoting Kaia's own lines back as theirs, and memory anchors injecting "you remember None".

The 2000-character cap in `sanitize_prompt` applies to what the user typed. Enricher blocks
carry their own caps (`url_max_content_length`); cutting the whole string cut the page.

### Token budget

The context window is `performance.max_context_tokens` (16,384 by default). `optimize_context()`
in `context_optimizer.py` reserves `system_reserve_tokens` + `max_response_tokens` + the user
message, then splits the remainder between RAG and history. **Anything you add to the system prompt comes out of retrieval.**

Two blocks are expensive enough to be switchable:

| Key | Cost when on |
|:--|:--|
| `features.self_model_injection` | ~900 tokens/turn |
| `features.constitution_injection` | ~2,400 tokens/turn |

Persona (`knowledge_base/kaia_persona.md`) is never truncated, so additions there are permanent
per-turn cost. Keep new rules terse.

### Generation temperature

`base_temperature` 0.70 for conversation, `rag_temperature` 0.35 for document-grounded work.
The `is_grounded` predicate that selects between them must key on the *source* being reference
material — an earlier version matched any `retrieval_method in (vector, bm25, hybrid)`, which is
true for nearly every turn and silently ran all conversation at 0.35, producing flat and
sycophantic prose.

### Output filters

> [!IMPORTANT]
> **Her roleplay is not a bug, and no guard gets to police it.** Kaia plays
> scenes with users on purpose — in-character crises, fictional telemetry
> ("resource consumption has reached 45%", "operating at the edge of
> stability"), sci-fi framing. That is wanted behaviour. Do not add a pattern,
> a persona rule or a filter to suppress it, and do not report it as a finding
> when reviewing logs.
>
> The §5 grounding rules below are about her asserting hardware facts as her own
> in ordinary conversation. A guard cannot tell that apart from a scene, and
> every attempt has cost more than it caught — guards in this file have deleted
> publication titles, stranded sentence fragments, emptied good responses and
> eaten one-word replies. **Before changing anything here, have a real user
> report of the behaviour being wrong.** A log line you find suspicious is not
> that.


`response_filter.py` guards run in two modes and the distinction matters:

- `mode="clause"` — the offence is a *prefix* on real content (`"you're right; <substance>"`).
  Excise the clause, keep the substance.
- `mode="sentence"` — the whole sentence is the artefact (bot-speak, prompt echo). Drop it.

Using sentence mode on concessional prefixes deleted entire valid answers and forced
regenerations; using clause mode on mid-sentence patterns left grammar rubble
(`"the and i'll investigate."`). When adding a pattern, decide which shape it is.

**Whichever mode you pick, check what the excision leaves behind.** This is the failure that
keeps recurring, in both modes: clause mode strands the half of the sentence that depended on
what it removed, and a *substring* excision inside a clause takes the grammar with it, because
the removed span is usually the subject. Four guards shipped it, two of them in more than one shape:

| Guard | Wrote | Shipped |
|:--|:--|:--|
| `APOLOGY_GUARD` | `starkind, you're right to point that out.` | `starkind,  to point that out.` |
| `PROMPT_ECHO_GUARD` | `the "dead internet theory" is… concerning.` | `the is… concerning.` |
| `DIRECTIVE_LEAK_GUARD` | `the system warning is unhelpful on its own.` | `theis unhelpful on its own.` |
| `SYCOPHANCY_GUARD` | `it's a complicated issue, and your observation is astute.` | `it's a complicated issue, and .` |
| `APOLOGY_GUARD` | `i apologize for the unwarranted accusation.` | `the unwarranted accusation.` |
| `SYCOPHANCY_GUARD` | `your observation … is astute and technically sound.` | `and technically sound.` |

The `PROMPT_ECHO` one was queued to the Project 1999 forum for review before anyone noticed.
Every one of them logged **"Trimmed offending clause, kept substance"** or the equivalent while
doing it, which is why they lasted — see [§9](#9-logging).

Rules that follow:

- Any guard that excises inside a sentence must call
  `response_filter.excision_broke_grammar(before, after)` and keep the original when it returns
  True. Shipping the offence beats shipping a sentence with a hole in it. It checks two shapes:
  an article stranded by what followed it, and a token in the output that was not in the input —
  an excision can only remove tokens, so a new one means the cut fused its neighbours
  (`the core directive: understanding` → `theunderstanding`, which has no stranded article in it).
- **A leak pattern must match the diagnostic form, not the English.** `DIRECTIVE_LEAK_PATTERNS`
  made the bracket and the underscore optional on five of nine entries, so `core directive`,
  `system warning`, `safeguard block`, `obs digest` and `could not be scraped` matched ordinary
  speech — and she discusses her own plumbing constantly, which is the conversation the guard
  fires in. Over her whole log corpus the old list altered 5 lines of 62,564 and every one was a
  false positive; the form that requires a bracket, an underscore or a sentence boundary alters
  0. The guard had never once fired in production, so nothing was lost by narrowing it.
- `strip_prompt_echo` declines outright when the span is the subject of its sentence. Quoting
  someone's term to refer to the thing is how you refer to a thing, and was never the fault that
  guard was written for.
- **A pattern must not swallow the word the fragment checks key on.** `i\s+apologi[sz]e\s+for`
  consumed the `for`, so the dangling-tail check — which already treats a tail opening on `for`
  as the rest of the offence — never saw one. Match up to the boundary and leave the connector
  in the tail with a lookahead. The same goes for the praised noun: `that's an astute` stopping
  before `observation` stranded it.
- Punctuation is not survival. `tail.strip()` on a bare `"."` is truthy, so the trailing-connector
  repair never ran when the offence reached the end of the sentence.

**Detect by vocabulary, not by shape — and measure what the marker is actually used for.**
The stage-direction guard classified a span as roleplay if it was multi-word, lowercase and
digit-free. Two things were wrong. The lowercase test was dead (`content.lower()` ran before
`word.islower()`, which can then never be False), so *every* multi-word span matched. And the
premise was never checked: across 618 marked spans in her own output, **not one** was a stage
direction — they are publication titles (`*The Washington Post*`), transliterations
(`*nigi-mitama*`), emphasis (`*what it costs*`), code (`(*args, **kwargs)`) and data (`(50-48)`).
The guard had nothing to catch and was deleting all of it, including the clause a sentence was
built on. Before writing a shape rule, grep the corpus for what the shape actually contains; then
make the rule a membership test against a named vocabulary, so an unrecognised span is kept.

**A delimiter has two halves.** `\([^)]+?\)` cannot cross an inner `)`, so on
`(actions (within actions))` it matches to the *inner* bracket and ships `nested ) should be
fine.` Scan balanced pairs with a stack and leave an unbalanced run alone. The same class of bug
ate the `*` opening an italic span (a leading-divider strip using `[\s\*]*`) and stripped the
markers off `**kwargs` (an "empty pair" pattern that matched any `**`). Assert the property, not
the case: *the filter must not increase the imbalance of its input*.

**Never let a filter empty a good response.** An empty return triggers a full regeneration,
which costs a whole inference round-trip — and if every attempt is rejected she says nothing at
all. That happened: three contemplative replies to a question about her own code were each
rejected for ellipsis-affect drift, 35 s of inference discarded, silence delivered. Exhaustion is
now recoverable — `_generate_with_retries` retains rejected attempts, defuses the cadence with
`EmergencyContaminationFilter.defuse_ellipsis_affect`, and **re-runs the full pipeline** on the
result. Salvaged text is used only if it passes on its own merits; the guards are unchanged.

**`optimize_context` is the only budget. Do not add a second one.** A post-assembly clamp
(`_clamp_to_context_window`) was added in September 2026 because four turns overran the response
reserve and one reply shrank to 21 tokens. It was removed the same month after five bug-fixes,
having spent its whole life cutting history that fit. Every variant of it was wrong in the same
way and none of them were wrong by a little:

| Ratio | Effect |
|:--|:--|
| 2.05 hardcoded | scored the system prompt alone over budget, drained every history turn |
| 1.75 "observed maximum" | overshot by a median of **2,620** tokens; cut history on 30 of 42 turns in one day, when the largest real prompt that day was 15,127 against a 15,360 budget |
| bounded p90 of measured `prompt_eval_count` | still overshot by a median of **1,159** tokens across its last 11 firings; every one of those prompts fit |

The lesson is not "calibrate harder" — the last version *was* calibrated on real counts from the
generation it was budgeting for, and still cut memory it did not need to. A words-to-tokens ratio
is per-turn and content-dependent, so any single number used as a *bound* is wrong for most turns
by construction, and the error falls entirely on her memory. `prompt_eval_count` is still logged
as `[TOKEN_DEBUG]`, which is where to look if reply truncation reappears; the fix then is
`max_response_tokens` or the system prompt's size, not a second budget downstream of the first.

### Vision

Images go inline to `gemma3:12b` as base64 on the `user` message. Three things about that path:

- **It keys off `ctx.message.attachments` and nothing else.** Any platform that wants Kaia to see
  a picture has to populate that list. The forum did not, so `MockMessage.attachments` was always
  empty and she answered image posts blind — a photograph in thread 443378 drew *"those symbols
  again? what are you trying to do?"*. `MockAttachment` supplies the `.filename`/`.url` the branch
  reads, and guesses an extension for `attachment.php?attachmentid=…`, which has none and would
  otherwise fail the suffix test in silence.
- **Downscale before encoding, and do it off the loop.** gemma3's vision encoder works at 896×896;
  a 4032×3024 phone photo is ~49 MB of base64 for no added detail, and the PIL decode was running
  synchronously on the event loop, stalling every other coroutine.
- **The grounding block must match where the picture came from.** It said "The user attached an
  image from their physical environment", which for a public thread invites her to discuss a
  stranger's screenshot as their living room. It varies by platform now.

Certainty is the failure mode, not error. Three confirmed misreads in two days — an origami swan
called a bat, a kintsugi bowl called a globe, a bus emergency hammer called a yellow bulldozer —
each stated with full confidence, and that is what stopped the operator trusting the answer. The
prompt asks her to name only what she can make out and to hedge rather than commit.

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
| **Forum auto-post** | `background_tasks.py` → `_make_forum_auto_post_task()` | **Through the pipeline**: `forum_drafting.draft_forum_reply()` → `process_external_mention()`. The thread is seeded into `channel_memory` as conversation history — under an **int** key, because that is what `ctx.channel_id` is. It was `str()`-wrapped until Sept 18, so no forum draft ever had history and every one was generated cold. Images in the post pass as `image_urls` and reach the vision model through the same `MockMessage.attachments` path Discord uses. `!forum reply <id>` drafts through the same function; its old direct-to-Ollama version had never worked. |
| **Forum tech support** | `background_tasks.py` → `_make_forum_tech_support_task()` | Direct call, BM25/hybrid grounded, mandatory disclaimer footer |
| **Social responder** | `kaia_social_responder.py` → `mock_external_mention()` | **Through the pipeline**: builds a `MockMessage` and hands it to the normal `on_message` handler |
| **Quip / social thread** | `social_response_generator.py` | **Through the pipeline** via `process_external_mention(platform="broadcast")` |
| **Observation digest** | `background_tasks.py` → `_make_observation_digest_task()` | Direct call to summarise; the digest text is then spoken verbatim, not re-generated |
| **Dream engine** | `kaia_dream.py` | Direct call, dream summary + belief extraction |
| **Inner monologue** | `kaia_monologue.py` | Direct call, background thought generation |
| **Overnight log** | `utils/radio/overnight.py` via the radio task | Direct call over facts gathered in Python; a draft with a number no fact contains is rejected; posted through `unprompted.speak` |

`utils/audio/` is deliberately **not** in this table: the music engine makes no LLM call at all.

---

## 7. Music Engine

`!music` puts Kaia in a voice channel performing a live-coded set. Each genre is an arranged
track in `strudel_patterns.py`, played by `tracks.py` — **no model is involved and no VRAM is
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

**A track is arranged, not accumulated.** Every part is in the program from bar one; a
`.mask("<…>")` and per-bar automation sequences (`lpf`, `gain`, roll speed) decide what sounds in
each bar of the form (intro → groove → build → drop → break → build → drop → outro). Sequences are
rotated to an anchor on Strudel's own clock, so a re-render — a DJ request, the next pass — keeps
the song's position. Rules `tracks.check()` and the tests enforce, each learned from silence:

- **No event longer than a bar** (`<a b>/2`, `.slow(2)` on a trigger). It is locked to absolute
  cycles, and one that starts in a masked bar never sounds. Spell it out: `<a a b b>`.
- **Sample URLs go in single quotes.** Strudel parses a double-quoted string as mini-notation, so
  `samples("github:…")` is an eval error — and the REPL swallows it and keeps playing the *old*
  program. The engine now collects `[eval] error` from the console and `play()` returns False.
- **Levels are measured, not guessed.** `audition_tracks.py --calibrate` solos every part, measures
  gated RMS against a per-role target (`ROLE_DB`) and writes `utils/audio/levels.json`, applied as
  `.postgain`. Re-run it for any genre whose parts you change; a part it reports SILENT is broken.
- **Soundfonts and Dirt-Samples load on first use**, which drops the first bar. `warmup_program()`
  plays every sample once, inaudibly, when the engine starts.

**Kaia is the DJ, without a model.** `utils/audio/dj.py` is where she is in the set: with no
genre asked for she picks one from her mood and the hour and says why, her arousal nudges the
tempo a few percent either way, and `!music darker | faster | drop | more bass …` becomes an
edit to the lanes that are playing — the same `set_param` / `live` operations the script uses —
answered in her voice. Every decision reads her *state*; none of it calls a model, so §7's
"no VRAM" still holds. A new request must leave the program balanced and audible on every genre:
`test_every_request_edits_every_genre_cleanly` covers the text, and `audition_tracks.py`
(play it, measure it) covers the sound. When a set ends, `kaia_expression.remember` writes it
into the channel's history and the growth log, so she knows she played and for whom.

**`!art` is decided before it is drawn.** `kaia_art_intent.decide` turns a prompt, her mood or an
attached image into an `ArtIntent` — palette (or a colour ramp from the image), symmetry, lead
shapes, complexity, title. Her own choice comes from one short model call that picks *from the
renderer's menus* and returns JSON; Python drops anything off-menu, and a lexicon and her mood
fill whatever she left open. The renderer still draws the geometry from the seed, and an empty
intent must draw exactly what the seed always drew (`test_an_unsteered_seed_renders_what_it_always_did`).
The piece is remembered the same way a set is.

**Radio is a guest on other people's servers.** `utils/radio/` reads eam.watch's and Priyom's
undocumented JSON endpoints. Poll at most every `radio.poll_hours` (default 6 — Ekco's call: it
is a novelty, not a live feed), one request at a time, with the identifying User-Agent in
`utils/radio/fetch.py`, through `public_only_connector`. A response in an unexpected shape raises
`FeedError` and the command says so; it must never become an empty list, which reads as "no
traffic". EAMs and number-station groups are encrypted: nothing Kaia says may claim to decode
one. Research: `docs/reports/investigations/2026-09-24-shortwave-feasibility.md`.

Kaia also **listens** (`utils/radio/watch.py`): scheduled, squelched recordings from public
KiwiSDRs via `kiwirecorder` (fetched into `assets/kiwiclient/` by
`tools/maintenance/fetch_radio_assets.py`, never vendored — no licence file, GPL parts), CPU-only
faster-whisper `large-v3` on band-passed audio, and `phonetic.parse`, which merges the readbacks
and writes `?` where they disagree. Rules: pick receivers with a free slot and no time limit, hold
a slot only while a job or `!radio` needs it, one listen at a time. **Radio history lives in
`memory/radio/`, never in `knowledge_base/`** — it is noise to retrieval. Accuracy is measured
against eam.watch's human copies (`watch.cross_check`), not claimed. Small and medium Whisper
models, raw audio and the VAD filter all hallucinated on HF audio; don't "optimise" to them
without re-running that comparison.

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
- **A flag gates each integration, never credentials.** `bluesky.enabled`, `x_twitter.enabled`
  and `forum.enabled` decide whether their subsystem runs; `.env` values alone do nothing, and
  the mention poller is not started when both social flags are off. Read `config/kaia.yaml` for
  what is currently set — this file does not track it.
- **`forum.tech_support_enabled` needs grounding work before it is turned on.** It answered
  strangers without staying grounded in the wiki, and confidently wrong EQ advice is worse than
  silence.

### Speaking unprompted

Everything she says without being asked goes through **one system**,
`utils/core/unprompted.py`, configured by one `unprompted:` block. Five sources feed it:

| Source | Decides when to try | Posts to |
|:--|:--|:--|
| `proactive` | every 30 min, then the desire gate (`desires:`) | most recent channel |
| `quip` | the channel has been quiet `performance.idle_quip_timeout_minutes` | most recent channel |
| `observation` | `observation.min_new_turns` new messages watched | `#kaia-opolis` |
| `monologue` | a thought every 15 minutes | `#kaia-opolis` |
| `overnight` | once a morning (`radio.overnight_time`) | `#kaia-opolis` |

A source decides *what* to say and *when to try*. Whether it posts is decided once, for all
four, by `unprompted.gate`: the master switch, `unprompted.sources.<name>`, **one daily limit
and one minimum gap shared by all five**, and one set of posting hours. `unprompted.speak` then
labels the post, sends it, appends it to channel memory, spends the allowance and cross-posts it
to the feeds listed under `unprompted.bluesky` / `unprompted.x`. A source switched off still runs
— the monologue still thinks, the digest is still written — nobody sees it. A manual `!quip`
skips the gate and spends nothing.

**Check the gate before generating, not only before sending.** The proactive engine, the quip
and the digest all call `unprompted.gate` first, so a closed gate costs no model call; `speak`
checks again because other sources may have posted in between.

**Labels rotate, but only honestly.** Nine labels live under `unprompted.labels`. Each source
may wear only the ones in `KIND_LABELS`. The descriptive ones — Unspooling, Down the rabbit
hole, Long thought, Train of thought — are worn only when the post earns them (a revised
belief, something she read, length, a thought built on what someone said), 80% of the time
when it does. Otherwise a post rotates among its home label and the ambient ones, away from
the last label used in that channel. An observation is always an Observation. Tune the cues
against `utils/core/unprompted._leans`, and keep `test_descriptive_labels_are_only_worn_when_earned`
passing: "Unspooling" on a post that questions nothing stops meaning anything.

**An absence check-in is addressed to a person.** It goes out unlabelled and is never
cross-posted. Key that on `trigger_type == "absence"`, not on `target_user` being set —
`conversation_followup`, `personal_memory` and `anchor_callback` populate that field with the
person the thought is *about*.

**Posting to a public feed needs a literal `true`.** `cross_posts` compares with `is True`:
a MagicMock config answers every key with something truthy, and a test reached the real Bluesky
posting function that way. Observations and proactive openers often name or quote people from
the server, which is why the default cross-posts quips only.

**A broadcast gate has to be persisted or a restart resets it.** `BotState` names every saved
field in three places — the attribute, `load()` and `save()` — and the monologue's gate fields
were once in none of them, so she aired a thought two minutes after every restart against a
90-minute minimum. The shared gate's `unprompted_date` / `_count` / `_last_sent` are in all three.

**Name the limit in the skip line.** `gate` returns the reason — `daily limit 16/16`,
`12 min left of the 45 min gap`, `outside the posting hours` — and every caller logs it.
"Rate limited" alone reads like a fault when it is the cap working as written.

**The desire gate must not be able to silence her.** `observe_exchange` pins the intellectual
need at 0.0 on any active server, which caps pressure at 0.16 — so a threshold above that means
she never speaks first, and at 0.55 she did so once in 102 evaluations. Both the threshold and
the gate itself are configurable (`desires.initiate_threshold`, `desires.gate_enabled`).

### Command replies

Every `!` command answers in the embed box `!help` uses — `utils/commands/embed_style.py`
(`box`, `add_field`, `notice`). Text quoted from a user, a document or a scrape goes through
`clean` (one line) or `clean_block` (keeps line breaks) first. A reply built as a code block
around such text is one fence away from breaking: `!explain 1` on a query that contained a
pasted ```` ```ansi ```` block closed the block early and rendered the rest as escape codes.
`test_command_handlers_reply_in_the_box_not_raw_code_blocks` keeps new ones out.

---

## 9. Logging

- Production telemetry is `logs/kaiacord.log`. **Test runs go to `logs/kaiacord.test.log`** —
  `UnifiedLogger._resolve_log_file()` detects pytest. Do not remove this: mock artifacts in the
  shared log were previously indistinguishable from production incidents and cost real
  debugging time.
- **The split only covers pytest.** `_resolve_log_file()` detects the test runner, not you. A
  bare `venv/bin/python3 -c` that imports a guard and calls it writes straight into the
  production log — and a filter exercised over corpus text emits a hundred plausible WARNING
  lines with real user text in them, timestamped today. Export `KAIACORD_LOG_FILE` before any
  ad-hoc run that touches a logging code path. If you forget, segment by timestamp and delete
  your own burst; the file is a record someone reads back as evidence.
- **Everything a test writes must be redirected, and four things needed it.** `telemetry_paths`
  holds all four: `telemetry_path()` for `memory/*.jsonl`, `corpus_dir()` for
  `knowledge_base/`, the logger's own split, and `persist_dir()` for `memory/rag_storage`. The
  last was missing until Sept 19, so every `pytest` run opened the **live** RAG index and wrote
  `{}` over the running bot's `file_manifest.json` — 1,094 entries replaced with two bytes,
  eight times in one day. `reindex_rag.py` refuses to touch that directory while the bot is
  running; the suite had no such guard. If you add a component that persists anything, redirect
  it here first.
- Elevate core cognitive actions (monologue, dream summaries, belief shifts, anchor formation),
  scraper operations, and mood changes to `log_info`/`log_warning` so they surface in the
  dashboard.
- When auditing the log, **separate production runs from test runs first**. Segment by the
  "Unified logging system initialized" boot marker and discard segments containing `MagicMock`,
  `test-model`, or `(case test)`.
- **Check that a boot marker is a boot.** `generate_user_profiles.py` called `replace_all_logging()`
  at import scope and the bot imports `generate_profile` from it nightly, so the marker fired
  mid-run: 6 of 23 in one log, five at the identical point in the profile refresh. The call now
  sits under the `__main__` guard and `test_no_tool_reconfigures_logging_at_import_scope` keeps
  it there, but logs written before that still carry the false markers. A real boot is followed
  by `Ensuring all models are flushed from VRAM`; a spurious one is wedged between two lines of
  whatever was running. Segmenting on the marker alone splits one 1,439-line segment into a
  77-line tail that reads as clean.
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
productive check in this codebase. Every one of these was found in September 2026, and every one
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
- `"desire gate closed (pressure 0.04 < 0.12)"` printed the class default `INITIATE_THRESHOLD`,
  while the gate compared against `desires.initiate_threshold` from config. They agreed only
  because nobody had changed the setting. Anything reporting the gate reads
  `desire_engine.initiate_threshold()`.
- `[APOLOGY_GUARD] Trimmed offending clause, kept substance` logged eight times in one day while
  emitting `'starkind,  to point that out.'` and `'lune,  to call me out.'` The dangling-tail
  repair ran only when the excised clause had *nothing* in front of it, so every sentence with a
  name, an "and", or a preceding clause shipped the fragment — announced as substance kept.
  `SYCOPHANCY_GUARD`, `PROMPT_ECHO_GUARD` and `DIRECTIVE_LEAK_GUARD` each did the same thing in
  their own way ([§5](#5-kaia-cognitive-pipeline)).
- `[CONTEXT_CLAMP] Dropped N history turn(s)` was accurate about what it did and silent about
  whether it should have. Paired against the `prompt_eval_count` that followed each one, the
  estimate ran a median of 2,620 tokens high and cut history on 30 turns that would have fit —
  and after being recalibrated on real counts it still ran 1,159 high. It also logged at WARNING,
  which the dashboard promotes into a ten-line ALERTS pane, so 189 routine lines evicted every
  real alert. The guard is gone ([§5](#5-kaia-cognitive-pipeline)); the lesson is that a line
  reporting an action taken is not evidence the action was warranted.
- `reindex_rag.py --clear` under a live bot correctly refuses to `rmtree` a directory the bot
  holds open, and reported that through `log_error` — which in a standalone script reaches
  neither stdout nor `logs/kaiacord.log`. It printed nothing and exited **0**, so a no-op was
  indistinguishable from a rebuild.
- `"Saved 0 entries to ./memory/rag_storage/file_manifest.json"` in `kaiacord.test.log` was a
  faithful report of the test suite writing over the live index. Nothing was wrong with the log
  line; nobody was reading it.

Three patterns, not one:

1. **Success is logged where the attempt happens, not where the outcome lands.** Make an outcome
   line reachable only when that outcome occurred, and return what succeeded rather than what was
   tried.
2. **A guard reports what it intended rather than what it produced.** When a guard rewrites text,
   log the result. Four separate guards shipped grammar rubble while announcing "kept substance".
3. **A refusal that reports only to the log.** A CLI that declines the job has to say so where the
   person who typed it will see it, and exit non-zero.

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
- **Request a RAG refresh with `rag_utils.request_reindex()`**, never by touching a path. The
  bot watches `knowledge_base/.trigger_reindex` (`reindex_trigger_path()`); writers had
  scattered between that, the repo root and the cwd, and a trigger in the wrong place is
  silently never seen.
- `knowledge_base/_ingress/` is a **staging area**, excluded from RAG indexing. `!download` and
  `!youtube` write there with a `.meta.json` sidecar; `tools/maintenance/process_ingress.py` (hourly, and from
  `kaia-tools.sh` → Documents & Ingestion) normalises, adds frontmatter and provenance, and files
  each document into an allow-listed folder. Do not index `_ingress` — that exclusion is what
  makes it safe for `!download` and `!youtube` to be open to every user.
- A sidecar carrying `"preformatted": true` is filed **without normalisation**. `!youtube` emits
  finished Markdown with timestamp anchors; running the reflow over it would destroy them.
- **`!youtube` corrects misheard names before staging** (`tools/maintenance/transcript_names.py`,
  also a dry-run CLI for transcripts already filed). Auto-captions give "house ATT treaties" for
  House Atreides, and names are what retrieval keys on. The model only supplies a glossary;
  Python applies a pair only if the misheard form is in the excerpt, is a phrase or a non-word,
  and the correction is capitalised and *sounds like* it. Without the sound test gemma3 answered
  confidently and wrongly — "simx" (cymek) became "thinking machines" sixteen times. What was
  changed is recorded in the sidecar's `name_corrections`.
- **Write frontmatter through `utils.core.frontmatter.dump_frontmatter`, never by string
  formatting.** Every corpus
  writer that built a block with an f-string has produced invalid YAML:
  `f"keywords: [{', '.join(keywords)}]"` turns a block-style list into a flow sequence full
  of `- ` entries that no parser will take, and an interpolated summary breaks on the first
  quote or colon it contains. That one line left **1,074 of 6,741 files — 16% of the
  corpus — unparseable**, and nothing noticed for months because the indexer reads
  frontmatter with line regexes rather than a parser. Retrieval kept working; enrichment
  skipped every one of them for good. `tools/maintenance/repair_frontmatter.py` fixes the
  two known shapes and declines anything less regular.
  `test_no_corpus_writer_builds_frontmatter_with_an_f_string` keeps new ones out; it flags an
  f-string that opens with a frontmatter key and interpolates on that line, unless every value
  goes through an escaper. The values here are scraped thread titles, Discord display names
  and book titles — a quote, a colon or a comma in any of them is routine.
- **Broken frontmatter is not absent frontmatter.** `parse_frontmatter` returned the whole
  file as the body on a YAML error, so the caller prepended a *second* block on top of the
  first — 60 files in one pass. A parse failure has to be its own outcome, named in the
  output, not folded into "this file has no metadata yet".
- **`tools/maintenance/audit_knowledge_base.py` checks every fault class that has actually
  occurred** — duplicates, thin pages, disambiguation stubs, baked-in U+FFFD, missing or empty
  frontmatter, a frontmatter fence fused to the body, and anything in `kaia_dreams/` that is not
  a reflection. Read-only, names the tool that fixes each finding, and `--check` exits non-zero.
  Run it after anything that writes across the corpus; that is cheaper than the sweep it replaces.
  Note the two scopes: `NOT_CORPUS` skips `forum_posts` because the *quality* checks do not
  apply to scraped threads, but forum drafting reads those threads directly (they are *not* in
  the RAG index), so `MECHANICAL_ONLY` runs the integrity checks over it. Excluding it outright
  hid 4,516 files from every check — 17 files carrying baked-in U+FFFD among them.
- **A cap must be applied to the eligible set, not to the listing.** `enrich_metadata` capped the
  whole corpus listing in directory order — books first, all already enriched — so a nightly
  `--limit 40` spent its entire budget skipping them and never reached the 369 news files with no
  frontmatter at all. It logged a completed pass every night and moved nothing.
- Maintenance tools that write across the corpus must default to a dry run and require `--apply`.
  `enrich_kb_metadata.py` had no argument parsing at all, so probing it with `--help` rewrote
  frontmatter on 124 files.

### The index

`memory/rag_storage/` holds one llama_index store per index type (`knowledge`, `logs`,
`dreams`, `user_profiles`) plus `file_manifest.json`. Rules that were each broken in a way
retrieval never reported:

- **Delete through `RAGIndexerMixin._delete_nodes`.** `VectorStoreIndex.delete_nodes` defaults
  to `delete_from_docstore=False`: the vector goes, the node stays in the docstore that BM25 is
  built from and the manifest is rebuilt from at boot. By September 2026, 70% of the knowledge
  docstore was old versions and removed files, and 3,852 nodes were superseded persona text.
  `_reconcile_indices()` runs on every refresh and removes any node with no embedding, no
  source file, a deleted or excluded file, or persona text; a second pass should find nothing.
- **Any index change deletes that index's BM25 pickle.** Its freshness check is file mtimes,
  and a deletion changes none.
- **Directory and file exclusions are separate predicates.** `_is_excluded_dir` for walking,
  `_is_excluded_path` for files. Asking the file rule about a forum user's folder excluded the
  whole folder, so their `user_profile.md` was indexed once and never refreshed.
- **Log tails are byte offsets**, with a hash of the indexed prefix. Character offsets against a
  byte size re-indexed turns on any file with a curly quote, and a log rewritten in place
  (a corrected turn, enrichment adding frontmatter) is now re-indexed whole.
- **Only `title` and `user_name` are embedded** (`EMBED_METADATA_KEYS`). Every other metadata
  key — absolute path, offsets, epoch timestamps, scores — was prepended to the text of every
  vector.
- **Not indexed:** the persona (injected whole), `news_summary_*` (a dateless condensed copy of
  the day's brief, kept for `!news`), forum threads and post histories, and anything without a
  source file. `RelevanceFeedback` used to insert synthetic Q/A copies of her own answers; it
  no longer writes.
- **News and dreams are dated by their filename.** `timestamp` was the file mtime, and
  enrichment rewrites old briefs, so recency could not tell February from yesterday.
- **Retrieval, not just indexing, decides what she can know.** Chat always passed
  `include_news=False`, and the scorer drops every news node then — the corpus that costs a
  Gemini call a day was never retrieved. News is included when the turn asks about it; a turn
  asking for what is *current* is also offered the newest briefs on its topic
  (`_latest_news_candidates`), and one that names its period ("in June") is not decayed by age.
  And four words or fewer meant casual, which searches only profiles and logs, so "who wrote
  Neuromancer?" never reached the book — `_is_short_question` keeps real short questions out of
  that bucket. Check a change here by asking the index real questions, not by reading scores.
- **`reindex_rag.py --clear` removes only the index artefacts.** `dream_history.json` and
  `kaia_continuity.md` live in the same directory and are not rebuilt from anything.

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

The synthesis is the fragile half, and it fails in three distinct ways. `reads_as_essay()`
rejects all three and retries; **it runs on every pass, not only on merges** — a group of twenty
reflections or fewer is a single pass and reached no merge, which is how one document went out
unchecked.

| Shape | What it looks like |
|:--|:--|
| essay | `**1. Key Themes & Recurring Ideas:**` and bullets analysing "the narrator" |
| review | *"That's excellent! It flows beautifully… I'd love for you to focus on lost authenticity in the next iteration."* |
| meta | talking about "these passages" and "the prompt to merge" instead of performing it |

The review shape is the one to watch for: it is fluent, first-person and has no bullets, so it
passes every structural test. `knowledge_base/books/Book - Neuromancer by William Gibson.md` was forty-three nights of reflection replaced
by a critique of a draft. **"the user" is deliberately not treated as third person** — she uses it
constantly and correctly about the people in her logs, and an earlier rule rejected the very
reflection it existed to protect.

Two accounting rules that are easy to get wrong:

- Consolidation **extends** an existing document rather than replacing it, but only carries the
  prior count forward when the run archives what it consumed. Re-running a group without
  `--archive` counted the same sources twice and recorded 84 reflections against a group of 42.
- Titles are canonicalised against the real filenames in `knowledge_base/books/`. The engine
  truncates a source stem to 30 characters and a dream-about-a-dream spends 22 of those on the
  parent's timestamp, so one book arrived under three keys and 250 files under the key
  `dream 20`.

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

**A test that runs a tool is a tool run.** `test_tools_runnable` checked that every script in
`tools/` can start, by invoking `python <tool> --help`. Sixteen of them have no argparse, so the
argument is ignored and the script simply **runs** — `sanitize_logs`, `kb_cleanse_user_logs`,
`repair_kb` and `precision_repair_kb` all rewrite `knowledge_base/user_logs/` in place. The suite
stripped the identity frontmatter off eight forum profiles, twice, while claiming to be a
read-only check, and the repair had to be run again afterwards. Exercise a script's *import block*
with `importlib.util.spec_from_file_location` + `exec_module` under any name but `__main__`;
anything guarded by `if __name__ == "__main__":` then stays unexecuted.

**A regex across many files is a change you have not read.** Converting 35 `write_text` calls in
21 modules to the atomic helper looked mechanical. The pattern matched the receiver greedily, so
it swallowed each line's leading indentation, and it turned
`other.with_suffix(other.suffix + ".error")` into `other.suffix +write_atomic(".error")`. Twenty
files stopped parsing. `ast.parse` over the tree caught it, `git checkout` undid it — and took an
uncommitted feature with it, which is the second lesson. If you must sweep:

- anchor the pattern at line start and keep the indentation in its own group
- restrict the receiver to what you expect (a dotted name), not `.+?`
- parse every touched file before moving on, and import the ones that are modules
- commit the unrelated work first

**A comment states the rule; the report states the incident.** Comments in this codebase had
become an incident log — dated anecdotes, transcript excerpts, the tuning history of individual
thresholds, internal phase and ticket numbers. That material goes stale where nobody updates it
and makes the code harder to read. Say what the guard or option *is* and which constraint gives
it its shape; the story of what went wrong belongs in `docs/reports/`, where
`reference/comment-provenance.md` holds what was removed. The same applies to config comments
and to this file: neither should assert what an option is currently set to, because the file
itself is right there.

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

This table is enforced, not just stated. `.claude/settings.json` is committed and carries the same list: `.env` and any `secrets/` are `deny`, and `Kaiacord.py`, `config/**`, `memory/**`, `kaia_persona.md` and `user_logs/**` are `ask`. A permission prompt on one of those is the rule working. Local-only overrides go in `.claude/settings.local.json`, which is git-ignored.

**`user_profile.md` has more than one writer.** `compact_forum_profiles.py` and
`generate_user_profiles.py` both rebuild it from a fixed key list, and neither consulted
`kaia_identities.registry`. Making one of them identity-aware on Sept 18 was undone at 03:41 the
next morning by the other, which replaced Kaia's own self-reference document with a third-person
personality profile assembled from her own posts. Anything that writes this file has to ask the
registry who the account belongs to first; `test_every_writer_of_user_profile_consults_the_identity_registry`
enforces it.

It has now been stripped three times — twice by a second writer, once by the *test suite* running
tools that have no argparse. `compact_forum_profiles.py --repair-identity --apply` restores it
from the registry in seconds and touches nothing else, so run that whenever
`test_identity_and_profiles` fails rather than hunting for the cause first.

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
| Corpus layout | `knowledge_base/README.md` — **read before adding a folder** ([§10](#10-knowledge-base)) |
| Shell tooling | `scripts/README.md` — what `kaia-tools.sh` exposes |
| Contributing | `CONTRIBUTING.md` — human-facing PR workflow |

> `docs/reports/` is **git-ignored** — it contains transcript excerpts and runtime telemetry. It
> exists in a working checkout but not on GitHub, so do not link it from tracked documentation.
> Start at `STATUS.md` (where each subsystem stands) and `DECISIONS.md` (the only list of unbuilt
> work — anything you find and do not fix goes there, with an ID). Record what you did as a new
> phase in `log/engineering-log.md`, and update `STATUS.md` when a subsystem's state changes.

---

## 16. Fine-Tuning

`finetune/` trains a persona LoRA for `gemma3:12b` on her own logs and exports a GGUF for Ollama.
It is **off the runtime path** — nothing in `utils/` imports it, and the bot runs the stock model
until a Modelfile is built and registered. `scripts/run_finetune.sh` drives it; the numbered steps
are meant to be runnable individually and the wrapper deliberately skips two of them
(`01_convert_logs.py`, because the dataset is pre-built, and `01b_augment_data.py`, which would
overwrite it).

Only `*.py`, `Modelfile` and the directory skeletons are tracked. `dataset/`, `output/`,
`checkpoints/`, `llama.cpp/` and every `.gguf`/`.safetensors` are git-ignored — the corpus is real
user messages.

Two constraints that are easy to break and silent when broken:

- **`num_ctx` in the Modelfile should equal `performance.max_context_tokens`.** The bot sends
  `num_ctx` on every call, so the Modelfile value is only the fallback for a request that omits
  it — `ollama run`, or a call site built without `chat_options`. Such a request at a different
  size reloads the model, and at 2,048 it discards the oldest ~14k tokens of a real prompt —
  persona, constitution, retrieved context, in that order — with no error. If the model OOMs at
  load, lower both together.
- **A fine-tuned model is meant to replace the runtime injection, not stack with it.** The
  `SYSTEM` block is the short prompt the weights were trained against, and the bot overrides it
  every turn with the full persona plus the constitution — a model that has learned the voice and
  is then argued out of it by several thousand tokens of instructions. Shrinking the injection is
  the migration; changing the `SYSTEM` line is not.

Validation is `05b_test_ollama.py` (live Ollama) and `05c_evaluate_persona.py`, not the stub in
`05_validate.py`. Training and the merge both want the GPU to themselves — see
[§4](#4-architecture-rules) on `gpu_semaphore` being process-local.
