# Gemini Report — In-Depth Review, Bug Hunting & System Health

**Date:** 19 October 2026  
**Auditor:** Gemini (DeepMind Advanced Agentic Reviewer)  
**Target Repository:** Kaiacord (`discord.py 2.7.1`, Python 3.12, RTX 3060 12 GB, Ollama)  
**Scope:** Review task only (zero runtime code changes). Full audit of git commits from **17 October 2026** and **18 October 2026**, uncommitted working tree changes, cognitive and safety pipelines, radio/scanner architecture, KAIA // OPS admin dashboard, memory/retrieval consistency, and empirical bug hunting.

---

## 1. Executive Summary & System Baseline

### 1.1 Test Suite & Runtime Baseline
The repository was evaluated using the project virtualenv (`venv/bin/python3`) adhering strictly to `CLAUDE.md`:
- **Fast & Medium Unit Test Suite (`pytest -m "not ollama and not gpu and not slow"`):**
  - **2,955 passed, 2 skipped, 56 deselected, 1 xfailed** in 370.91s (6m 10s).
  - **Zero failures, zero broken invariants.**
  - `XFAIL`: `test_contamination_filter_rejects_ascii_ellipsis_affect_spam` (documented and intended trade-off to prevent false-positive regenerations on valid cadences like `"three... two... one."`).
- **Radio & Scanner Subsystem Suite (`test_rx_receiver.py`, `test_rx_dashboard.py`, `test_local_scanner.py`):**
  - **80 passed, 1 skipped** in 194.55s.
- **Production Bot Status:**
  - Active and healthy in a tmux/kitty process (PID 2268), executing scheduled tasks (e.g. KiwiSDR listen on M12).
  - Telemetry isolation verified: test logs route strictly to `logs/kaiacord.test.log` without contaminating production telemetry.

### 1.2 Commits Audited (17–18 October 2026)
Across the 13 commits on 17–18 October (plus uncommitted tree changes), **over 6,150 insertions and 420 deletions across 40 files** were introduced:
1. `56e9a01` `[kaia]`: Her voice back: address tag strip, name-less grading opener, short stock fragments, paragraph reflow, and log cleaner.
2. `3b34ecf` `[kaia]`: Dream beliefs start tentative (0.6) and firm up (+0.08); rejection of reported source views and unnamed global anchors.
3. `115d65a` `[art]`: Flames in the whole spectrum (`_spectrum_lut`, equalized quantiles, saturation lift).
4. `cde4a88` `[social]`: Boards echo: replied post quoted above Kaia's response; check-in error naming.
5. `452325d` `[docs]`: Documentation of voice template rules, log cleaner, and full-spectrum art.
6. `0083132` `[kaia]`: Mid-sentence ellipsis joined instead of cutting grammar holes.
7. `4d4defa` `[kaia]`: Refusal of psychological diagnoses in dream insights; conversational fatigue lookback pinned to 45m; NLTK tokenizer warm-up on RAG reindex.
8. `ea5991f` `[kaia]`: Forum namesakes of server members segregated in RAG queries unless linked in the identity registry.
9. `817841d` `[kaia]`: Pinned `NEVER_FINAL` list for ellipsis defusing to prevent fusing legitimate clause endings.
10. `baae388` `[docs]`: Documentation of ellipsis defuse, dream beliefs, and voice holding.
11. `05caa4c` `[kaia]`: Litany collapsing (`collapse_litany`) for runs of 3+ verbless fragments; expanded 10-word `a ...` fragment keys.
12. `af7433a` `[infra]`: **KAIA // OPS**: Complete read-only admin web dashboard (127.0.0.1:47433) running in an isolated process to eliminate GIL contention with the audio/voice engine.
13. `52bd944` `[infra]`: **KAIA//RX Receiver**: Live in-place tuning via child process queue commands, background `Stream` thread, stateful overlap-save decimation, `LiveSquelch`, habitual data suppression, bookmarks/highlights, and Gqrx CSV exchange.
14. **Uncommitted Working Changes**: Multimon-ng APRS/POCSAG packet decoder (`decode.py`), conversation follow peek scanning (`_peek` in `waterfall.py`), highlight ranking heuristics (`interest.py`), and unprompted limits tuning (`config/kaia.yaml`).

---

## 2. High-Priority Bugs & Latent Defects Discovered

### Bug 1: `collapse_litany` Character Threshold Guard Aborts Short Litanies
- **Location:** [`utils/core/safety_pipeline.py:1115`](file:///home/ekco/github/Kaiacord/utils/core/safety_pipeline.py#L1115)
- **Code:**
  ```python
  out = re.sub(r"(\n\s*\n){2,}", "\n\n", "".join(out_paras)).strip()
  if len(out) < 40:
      return text
  ```
- **Mechanism:**  
  `collapse_litany` was written to truncate repetitive runs of 3+ verbless `"a/an ..."` fragments down to the first two (`LITANY_KEEP = 2`). However, line 1115 blindly imported the `< 40` guard originally meant for `strip_grading_opener`.  
  If Kaia outputs 3 or 4 short fragments (e.g. `"a quiet signal. a simple reminder. a gentle nudge. a familiar rhythm."`), the first two fragments total 34 characters. When collapsed, `len(out)` is 34 (< 40).  
  **Because `len(out) < 40`, `collapse_litany` discards the collapse and returns the entire uncollapsed 4-fragment litany!**
- **Empirical Verification:**
  ```python
  text = 'a quiet signal. a simple reminder. a gentle nudge. a familiar rhythm.'
  P.collapse_litany(text)
  # Returns: 'a quiet signal. a simple reminder. a gentle nudge. a familiar rhythm.' (NO COLLAPSE!)
  ```
- **Recommendation for Claude:**  
  Change the exit condition from `if len(out) < 40: return text` to checking whether `len(out) >= 2` or `if not out.strip(): return text`. Unlike prefix strip guards, `collapse_litany` only removes trailing redundancy and keeps the core opening; aborting on short total length directly defeats its purpose.

---

### Bug 2: Filter Ordering Inversion Between `collapse_litany` and `reflow_paragraphs`
- **Location:**  
  - [`utils/core/message_processor.py:2485-2486`](file:///home/ekco/github/Kaiacord/utils/core/message_processor.py#L2485-L2486)
  - [`tools/maintenance/clean_kaia_turns.py:62-63`](file:///home/ekco/github/Kaiacord/tools/maintenance/clean_kaia_turns.py#L62-L63)
  - [`utils/core/safety_pipeline.py:1244`](file:///home/ekco/github/Kaiacord/utils/core/safety_pipeline.py#L1244)
- **Code:**
  ```python
  ctx.response_text = PostGenerationSafetyPipeline.collapse_litany(ctx.response_text)
  ctx.response_text = PostGenerationSafetyPipeline.reflow_paragraphs(ctx.response_text)
  ```
- **Mechanism:**  
  1. `collapse_litany` operates strictly on runs of fragments *within a single paragraph*:
     ```python
     for para in re.split(r"(\n\s*\n)", text):
         if "\n" in para.strip(): continue # Skips verse/lists
         sents = cls._sentences(para)
         # Counts runs in sents...
     ```
  2. When Kaia outputs her characteristic fragmented one-line paragraphs separated by `\n\n`:
     ```text
     a pattern identified.

     a tendency observed.

     a habit acknowledged.

     a defense strategy.
     ```
  3. `collapse_litany` runs **first**. It sees 4 separate paragraphs, each containing exactly **1 sentence**. Since `len(run) == 1 < 3`, it collapses **nothing**!
  4. `reflow_paragraphs` runs **second**. It joins the short one-line paragraphs together into:
     ```text
     a pattern identified. a tendency observed. a habit acknowledged. a defense strategy.
     ```
  5. The response ships with all 4 litany fragments intact!
- **Empirical Verification:**
  Running `reflow_paragraphs(collapse_litany(text))` leaves all 4 fragments. Running `collapse_litany(reflow_paragraphs(text))` properly collapses them to:
  `'a pattern identified. a tendency observed.'`.
- **Recommendation for Claude:**  
  In `message_processor.py`, `clean_kaia_turns.py`, and `detemplate_history`, either:
  1. Run `reflow_paragraphs` **before** `collapse_litany`, OR
  2. Run `collapse_litany` **after** `reflow_paragraphs` so any joined paragraph with excess fragments is collapsed before leaving the pipeline.

---

### Bug 3: `_CLAUSE_VERB` is Auxiliary-Only — Lexical Verb Sentences Mistaken for Verbless Fragments
- **Location:** [`utils/core/safety_pipeline.py:807-810`](file:///home/ekco/github/Kaiacord/utils/core/safety_pipeline.py#L807-L810), used in [`_litany_fragment`](file:///home/ekco/github/Kaiacord/utils/core/safety_pipeline.py#L1083)
- **Mechanism:**  
  `_CLAUSE_VERB` is defined as:
  ```python
  _CLAUSE_VERB = re.compile(
      r"\b(?:is|are|was|were|be|been|being|am|has|have|had|do|does|did|can|could|will|would|shall|"
      r"should|may|might|must)\b|\b(?:it|that|there|here|he|she|what|who|where|how|let)['\u2019]s\b|"
      r"['\u2019](?:re|ve|ll|d|m)\b", re.IGNORECASE)
  ```
  Notice that `_CLAUSE_VERB` matches **only auxiliary verbs and contractions**.  
  `_litany_fragment` assumes any sentence starting with `a/an` that has `<= 10` words and does not match `_CLAUSE_VERB` is a "verbless fragment".  
  If Kaia writes a series of short, complete, grammatical sentences with active lexical verbs without auxiliaries:
  - *"a cold wind blows."* (Subject: wind, Verb: blows)
  - *"a dog barks."* (Subject: dog, Verb: barks)
  - *"a distant bell tolls."* (Subject: bell, Verb: tolls)
  None of these verbs match `_CLAUSE_VERB`. As a result, `_litany_fragment` classifies all three as "verbless fragments" and `collapse_litany` drops the third complete sentence!
- **Recommendation for Claude:**  
  Ensure `_litany_fragment` only classifies sentences matching her known stock fragment adjectives or abstract nouns (`_stock_fragment`), rather than treating any sentence without an auxiliary verb as verbless.

---

### Bug 4: `clean_kaia_turns.py` Appends Uncleaned Text to History Window
- **Location:** [`tools/maintenance/clean_kaia_turns.py:89-91`](file:///home/ekco/github/Kaiacord/tools/maintenance/clean_kaia_turns.py#L89-L91)
- **Code:**
  ```python
  text = body.strip()
  new = clean(text, previous)
  previous.append(text)          # <--- Appends original uncleaned text!
  del previous[:-WINDOW]
  ```
- **Mechanism:**  
  When iterating through turns in `clean_log()`, `previous` is passed into `strip_repeated_lines(out, previous, window=WINDOW)`.  
  If turn $N$ had an offending address tag `(speaking exclusively to ...)` or litany that was stripped in `new`, line 90 appends the raw uncleaned `text` to `previous`.  
  When turn $N+1$ is cleaned, `strip_repeated_lines` compares turn $N+1$ against text that was already excised from turn $N$.
- **Recommendation for Claude:**  
  Append `new` instead of `text`: `previous.append(new)`.

---

### Bug 5: `BotState.save()` Snapshot Dictionary Assembly Sits Outside the Mutation Retry Loop
- **Location:** [`utils/infrastructure/system/bot_state.py:165-216`](file:///home/ekco/github/Kaiacord/utils/infrastructure/system/bot_state.py#L165-L216)
- **Background:**  
  `audit_report.md` (Next session, item 3) flagged:
  > *"test_bot_state_save::test_save_survives_concurrent_mutation failed once under the full suite (3 Oct evening: 'dictionary changed size during iteration'), passed 3/3 alone — the caller-thread snapshot in BotState.save() still has a window. Find it before it drops a real save."*
- **Root Cause Identified:**  
  The retry loop was added to catch concurrent mutations during `json.dumps(state)`:
  ```python
  state = {
      ...
      'quip_history': list(self.quip_history),                             # Line 170
      'channel_last_activity': {str(k): v for k, v in self.channel_last_activity.items()}, # Line 187
      'unprompted_sources': {k: dict(v) for k, v in self.unprompted_sources.items()},     # Line 191
      'channel_memory': {str(k): list(v) for k, v in self.channel_memory.items()},        # Line 194
  }
  for attempt in range(20):
      try:
          payload = json.dumps(state, indent=2)
          break
      except RuntimeError:
          ...
  ```
  Look at lines 170, 187, 191, and 194! The dictionary and deque comprehensions iterate directly over live mutable structures (`self.channel_last_activity`, `self.unprompted_sources`, `self.channel_memory`, `self.quip_history`).  
  **These comprehensions execute outside the `for attempt in range(20):` block.**  
  If another coroutine (e.g., `on_message` logging to `channel_memory` or updating `channel_last_activity`) modifies the dict while line 187 or 194 is executing:
  Python immediately raises `RuntimeError: dictionary changed size during iteration` at line 187/194, skipping the retry loop entirely, landing in `except Exception as e:` at line 220, and **dropping the save completely!**
- **Recommendation for Claude:**  
  Move the definition of `state = { ... }` *inside* the `for attempt in range(20):` retry block. This guarantees that any concurrent mutation during comprehension evaluation triggers a clean retry instead of aborting the save.

---

### Bug 6: Peek Scanning in `waterfall.py` (Uncommitted) Thread Churn & Zero-Division Risk
- **Location:** [`utils/radio/waterfall.py:885-896`](file:///home/ekco/github/Kaiacord/utils/radio/waterfall.py#L885-L896), [`_peek:922`](file:///home/ekco/github/Kaiacord/utils/radio/waterfall.py#L922)
- **Code:**
  ```python
  elif (follow and own and not live and not sides and resumed is None
        and quiet >= SILENCE_S + PEEK_AFTER_S and time.time() - last_peek >= PEEK_EVERY_S):
      source.close()
      self._handoff = self._peek(dongle, center)
      dongle.tune(center)
      ...
      source = _source(dongle, int(FS * HOLD_CHUNK_S))
  ```
- **Mechanism & Edge Cases:**  
  1. **Thread Churn on the Dongle:** In `_hold`, during conversation follow quiet periods (`FOLLOW_IDLE_S = 15s`), every 1.5 seconds (`PEEK_EVERY_S = 1.5`), `source.close()` terminates the background `Stream` thread and joins it for up to 2.0s, retunes, and spawns a new thread via `_source(...)`. A 15-second pause causes 10 rapid thread creations/terminations.
  2. **USB Concurrency Collision:** In `Stream.close()`, `self.t.join(2)` can time out if C `rtlsdr_read_sync` is blocked in bulk transfer. If it times out, `_peek` calls `dongle.tune(center)` while the stream thread is still inside librtlsdr C bulk read, risking segfaults or corrupted IQ streams.
  3. **ZeroDivisionError Risk in `_peek`:**
     ```python
     others = [c for c in self._schedule() if c != center]
     for _ in range(min(PEEK_SLICES, len(others))):
         c = others[self._peek_i % len(others)]
     ```
     If `others` is empty (e.g. only 1 slice configured in the band or scheduled), `len(others) == 0`. While `range(0)` avoids execution, defensive coding requires `if not others: return None` before modulo calculations.
  4. **Audio Loss on Over Handoff:** Retuning to 2 slices and back takes ~250–350 ms. If the other speaker responds during that window, the initial syllable/callsign is clipped.
- **Recommendation for Claude:**  
  Keep `PEEK_EVERY_S` at a more conservative interval (e.g. 3.0–4.0s) or only peek once per hold pause, and ensure `source.close()` cleanly halts before any `dongle.tune()` call.

---

### Bug 7: SQLite Multi-Process Concurrency Lacks WAL Mode
- **Location:** [`utils/radio/ledger.py:25-55`](file:///home/ekco/github/Kaiacord/utils/radio/ledger.py#L25-L55)
- **Mechanism:**  
  Commit `af7433a` introduced `kaia_admin.py` (KAIA // OPS) as an independent process connecting to `local_ledger.sqlite3` with `mode=ro` (read-only). Simultaneously, `rx_dashboard.py` and the bot's scanner process write events to `local_ledger.sqlite3`.  
  However, `local_ledger.sqlite3` is created without setting `PRAGMA journal_mode = WAL;`. In default rollback journal mode (DELETE), any write transaction locks the entire database file with an exclusive OS lock. If `kaia_admin.py` or the dashboard queries the database while a write or batch catch commit is in progress, it risks encountering `sqlite3.OperationalError: database is locked`.
- **Recommendation for Claude:**  
  Add `con.execute("PRAGMA journal_mode = WAL")` in `ledger.py:_db()` upon connection/schema initialization. In WAL mode, concurrent readers never block writers, and writers never block readers.

---

### Bug 8: `strip_address_tag` Returns Unstripped Leak When Text is Minimal
- **Location:** [`utils/core/safety_pipeline.py:1121`](file:///home/ekco/github/Kaiacord/utils/core/safety_pipeline.py#L1121)
- **Code:**
  ```python
  out = cls._ADDRESS_TAG.sub("", text or "")
  if out == (text or ""):
      return text
  out = re.sub(r"\n{3,}", "\n\n", out).strip()
  return out if len(out) >= 2 else text
  ```
- **Mechanism:**  
  If the LLM outputs *only* the leaked prompt tag (e.g. `(speaking exclusively to starkind)`), `out` becomes `""` (`len(out) < 2`).  
  Because of `return out if len(out) >= 2 else text`, it falls back and returns `text`, directly emitting the prompt leak to Discord!
- **Recommendation for Claude:**  
  If stripping the address tag empties the output, return `""` (empty string) so the downstream pipeline can properly trigger a retry/regeneration.

---

## 3. Subsystem Health & Deep-Dive Analysis

### 3.1 Cognitive & Safety Pipeline (`utils/core/`)
- **Address Tag Stripping (`strip_address_tag`):** Effectively cured the regression where `(speaking exclusively to X)` prepended 100% of turns by 16 Oct.
- **Ellipsis Defusing (`repair_cut_ellipsis` & `defuse_ellipsis_affect`):** The narrowed `NEVER_FINAL` regex (`just|a|an|the|my|your|their|our|its|that's|it's|there's|what's|very|rather|somewhat`) accurately prevents the destructive clause cuts that plagued early September ("it's just. a signal."). Real clause endings (`"scared of."`, `"here for."`, `"anything but."`) are preserved.
- **Addressee Guard (`correct_addressee`):** Verified working in tests. Fixed the issue where Tenno was addressed as "starkind" due to history contamination.

### 3.2 Dream Engine & Belief Consolidation (`utils/core/kaia_dream.py`)
- **Gradual Belief Confidence:** Beliefs starting at 0.6 and incrementing by 0.08 on repeated reinforcement prevents the previous issue where 94% of beliefs sat at 0.9 confidence after a single dream.
- **Reporting & Diagnosis Filters:** `REPORTED_VIEW` (`"the author believes..."`) and `DIAGNOSIS` (`"likely driven by...", "meltdown"`) successfully prevent external editorializing from entering Kaia's personal belief graph and relationship models.
- **Jaccard Topic Comparison:** `_same_position` cleanly compares 4+ letter words with a 0.5 threshold without requiring an expensive or non-deterministic LLM call.

### 3.3 Fractal Art Engine (`utils/core/kaia_art.py`)
- **Full-Spectrum Colour Wheel (`_spectrum_lut`):** The conversion of Electric Sheep palettes from 2–3 hue stops to full 360-degree cyclical traverses (`_spectrum_lut`) directly addresses Ekco's feedback ("only 2-3 colors"). Test `test_every_palette_goes_round_the_colour_wheel` confirms 4–9 active hue bins across all seeds.
- **Saturation Lift:** `SAT_LIFT` properly prevents destructive desaturation where multiple color arcs overlap in density.

### 3.4 KAIA // OPS Dashboard (`utils/admin/`, `assets/admin/`, `tools/maintenance/kaia_admin.py`)
- **Process Isolation:** Serving on 127.0.0.1:47433 in its own independent process completely eliminates the 400–500ms GIL stalls that previously impacted the audio engine during full log parsing.
- **Date Reconstruction (`logscan.py`):** The midnight walkback algorithm elegantly reconstructs true dates for log lines that only store time-of-day (`[HH:MM:SS]`) by walking backward from file `mtime`.
- **CVD Colour Validation:** Categorical colors for charts are properly verified for color-blind distinction.
- **CSRF / Origin Check:** Verified functional on POST `/api/run/<check>`.

### 3.5 KAIA//RX Receiver & Scanner (`utils/radio/`)
- **In-Place Retuning:** Eliminates process forking and dongle re-initialization delays (tuning reduced from >1.5s to 34–180ms).
- **Decimator Statefulness:** `resample_poly` with overlap-save prevents edge clicks and phase discontinuities.
- **Habitual Burst Suppression:** Suppresses repeated telemetry bursts (e.g. 462.275 MHz timers), saving ~28% of nightly scanning time.
- **multimon-ng Decoding (`decode.py` in uncommitted changes):** Successfully integrates APRS and POCSAG decoding when the system binary is available, gracefully falling back when absent.

---

## 4. Discrepancies in Documentation & Tracking

1. **`master_report.md` Missing Commit Hashes:**  
   - Commit `52bd944` is cited in `master_report.md` line 366 ("KAIA//RX as a receiver... history Phase 166"), but `history.md` ends at **Phase 165**! Phase 166 was never committed to `history.md`.
2. **`audit_report.md` Outdated "Next Session" Items:**  
   - `audit_report.md` item 0000000 ("Restart for ea5991f and 817841d") was partially done by the 18 Oct reboot, but still lists tasks that should be updated.
   - Item 3 regarding `test_bot_state_save` was unresolved in the document. With the root cause diagnosed above (Bug 5), this can now be formally addressed.
3. **`CLAUDE.md` Pass Count:**  
   - Line 60 correctly advises: *"Take the baseline from the suite, not from here."* The current suite count has expanded to **2,955 passing tests** (up from 2,856 in early October).

---

## 5. Strategic Roadmap & Actionable Suggestions for Claude Code

When Claude Code resumes development, it should prioritize the following actions:

### Phase A: Fix High-Priority Safety Pipeline Logic
1. **Fix `collapse_litany` Character Guard:**  
   Remove `if len(out) < 40: return text` in `PostGenerationSafetyPipeline.collapse_litany`. Replace with `if not out.strip(): return text`.
2. **Re-order Pipeline Filters:**  
   In `MessageProcessor.process()`, `clean_kaia_turns.py:clean()`, and `detemplate_history()`, run `reflow_paragraphs` **before** `collapse_litany` (or apply `collapse_litany` after reflow).
3. **Protect Lexical Verbs in `_litany_fragment`:**  
   Refine `_litany_fragment` to check against `_stock_fragment` rather than treating any clause lacking an auxiliary verb as a fragment.
4. **Fix History Tracking in `clean_kaia_turns.py`:**  
   In `clean_log()`, append `new` to `previous` instead of `text`.

### Phase B: State Persistence & Concurrency
5. **Enclose `BotState.save()` Snapshot in Retry Loop:**  
   Move `state = { ... }` inside `for attempt in range(20):` in `utils/infrastructure/system/bot_state.py` to prevent unhandled `RuntimeError` during concurrent dictionary comprehensions.
6. **Enable WAL Mode in SQLite Ledger:**  
   Add `con.execute("PRAGMA journal_mode = WAL")` in `utils/radio/ledger.py` to ensure clean concurrency between the bot scanner and KAIA // OPS / KAIA//RX.

### Phase C: Clean Up Radio Working Tree & Commit
7. **Commit the Uncommitted Radio Enhancements:**  
   Review and commit the uncommitted changes in `utils/radio/decode.py`, `utils/radio/interest.py`, `utils/radio/ledger.py`, and `test_rx_receiver.py` (which all passed 80/80 tests).
8. **Document Phase 166 in `history.md`:**  
   Add the missing Phase 166 entry for commit `52bd944` and update `audit_report.md` and `master_report.md`.

---

## 6. Verification Commands for the Next Session

To verify the codebase and validate the findings:
```bash
# 1. Run the full standard test suite
venv/bin/python3 -m pytest -q -m "not ollama and not gpu and not slow"

# 2. Run the dedicated radio and receiver test suite
venv/bin/python3 -m pytest tools/tests/unit/test_rx_receiver.py tools/tests/unit/test_rx_dashboard.py tools/tests/unit/test_local_scanner.py -q

# 3. Test collapse_litany with the short-fragment reproduction
venv/bin/python3 -c "from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P; print(repr(P.collapse_litany('a quiet signal. a simple reminder. a gentle nudge. a familiar rhythm.')))"

# 4. Dry-run the turn cleaner over logs (with bot stopped)
venv/bin/python3 tools/maintenance/clean_kaia_turns.py --show 10
```

---
*Report compiled autonomously by Gemini — Advanced Agentic Reviewer.*
