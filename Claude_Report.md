# Claude — Kaiacord Codebase Review
**Date:** March 4, 2026
**Scope:** Phase 27/28 Rollback — Remove all Qwen3.5 and !think artifacts; restore gemma3:12b as canonical model
**Reviewer:** Claude (Senior Principal Engineer)

---

## Executive Summary

Ekco has decided to roll back the Phase 27 Qwen3.5 migration and abandon the `!think` command. This is the right call — `!think` was never fully implemented (the handler was a dead stub), and Qwen's reliability issues outweigh its benefits at this time. The Phase 28 work (CQ-01 file split, PF-05 SDK migration, SEC-01 docs) is clean, independent of the model choice, and should be **kept in full**.

This report is the action document for Gemini. It contains a precise, exhaustive list of every file that references Qwen or `!think`, what to do to each one, and what to leave alone. Gemini should work through this list top to bottom, run the test suite after all changes, and update MASTER_REPORT.md and GEMINI_Report.md to record the rollback.

**After this cleanup, the codebase should contain zero references to `qwen3.5`, `qwen`, `!think`, `think_mode`, or `think_handler` anywhere outside of archived/historical documents.**

---

## Complete Qwen + !think Artifact Inventory

### 🔴 Code — Delete or Gut These Files

---

**1. `utils/commands/think_handler.py` — DELETE the file entirely**

The entire file exists only for `!think`. It is a dead stub. Remove it.

```bash
git rm utils/commands/think_handler.py
```

---

**2. `utils/commands/registry.py` — Remove the !think import and dispatch block**

Remove these two sections:

```python
# DELETE this import line:
from utils.commands.think_handler import handle_think_command

# DELETE this dispatch block:
if content.startswith("!think"):
    await handle_think_command(ctx, msg, send_kaia_response)
    return True
```

No other changes to this file.

---

**3. `utils/infrastructure/system/bot_state.py` — Remove `think_mode_users`**

In `BotState.__init__`, remove this line:
```python
self.think_mode_users: set = set()  # Transient: users with <think> tag visibility enabled
```

No other changes. The `is_generating` field on the adjacent line is unrelated — leave it.

---

**4. `utils/core/message_processor.py` — Remove `_THINK_BLOCK_PATTERN`**

At the module-level constants block, remove this line:
```python
_THINK_BLOCK_PATTERN = re.compile(r'<think>(.*?)</think>', re.DOTALL)
```

This pattern was only there to support the (never-implemented) `!think` spoiler formatting. It is referenced nowhere in the active code paths. The `_JSON_RESPONSE_PATTERN` and `_JSON_WRAPPER_PATTERN` on adjacent lines are unrelated — leave them.

Also remove the comment in `_call_ollama_with_retries` that says "especially for owners with think mode" and rephrase it as a plain comment about the BotSpeakFilter safety net only.

---

### 🔴 Code — Targeted Edits

---

**5. `utils/infrastructure/system/yaml_config.py` — Three changes**

**Change A** — Fix the stale inline comment at the top of the file:
```python
# REMOVE:
CONTEXT_WINDOW_TOKENS = 12000  # Default for qwen3.5:9b

# REPLACE WITH:
CONTEXT_WINDOW_TOKENS = 12000  # Default context window for gemma3:12b
```

**Change B** — Fix the `chat_model` property Python fallback:
```python
# CURRENT (wrong fallback):
return self.get_path('models.chat', 'qwen3.5:9b')

# REPLACE WITH:
return self.get_path('models.chat', 'gemma3:12b')
```

**Change C** — Fix the `classification_join_seconds` Python fallback (pre-existing mismatch surfaced this session):
```python
# CURRENT (15.0 fallback is dangerously low — the YAML default is 40.0):
return self.get_path('timeouts.classification_join_seconds', 15.0)

# REPLACE WITH:
return self.get_path('timeouts.classification_join_seconds', 40.0)
```

---

**6. `utils/core/kaia_rag_retriever.py` — Remove Qwen attribution from comment in `sanitize_log_content`**

The `<think>` stripping logic itself should stay — it is a harmless, zero-cost defensive measure. Only remove the comment that attributes it to Qwen:

```python
# CURRENT comment (remove the Qwen attribution):
# Strip <think>...</think> reasoning blocks from new reasoning models (like Qwen 3.5)

# REPLACE WITH:
# Strip <think>...</think> reasoning blocks (defensive strip — no-op for current models)
```

Do not remove the `re.sub(r'<think>.*?</think>', ...)` line or the orphaned-tag strip below it.

---

**7. `utils/core/intent_classifier.py` — Remove Qwen attribution from any comment near `RE_THINK_BLOCK`**

The `RE_THINK_BLOCK` regex itself should stay for the same reason as above. Remove or neutralize any comment near it that references "Qwen" or "reasoning models." The regex strips think blocks from the classifier's own LLM output — a valid defensive measure regardless of model.

---

### 🟡 Config — Update These Files

---

**8. `config/default_config.yaml` — Remove Qwen-specific NOTE comment in the embedding section**

```yaml
# REMOVE this entire comment block:
  # NOTE: qwen3.5:2b does NOT expose Ollama's embedding API (returns 501).
  # nomic-embed-text-cpu is the correct embedding model — it runs CPU-only
  # via num_gpu:0 in kaia_rag.py, saving VRAM for the main 9b model.

# REPLACE WITH:
  # nomic-embed-text-cpu runs CPU-only via num_gpu:0, preserving VRAM for the chat model.
```

The model values themselves (`gemma3:12b`, `gemma2:2b`) are **already correct** in this file — do not touch them.

---

**9. `config/kaia.yaml` — Verify no Qwen references exist**

Scan the file. It currently has no `models:` section so no action is expected, but confirm with grep before moving on.

---

### 🟡 Tests — Update the Test Suite

---

**10. `tools/tests/unit/test_tier1_features.py` — Remove two test classes**

Delete the following classes entirely:

- `class TestThinkTagHandling` — tests `<think>` regex logic only needed for `!think`
- `class TestBotStateThinkMode` — tests `think_mode_users` which is being removed

**Leave all other classes untouched:** `TestFlagAuditCommands`, `TestSnapshotHandler`, `TestProvenanceFormatting`, `TestSnapshotMetadata`, `TestAuditConfig`, and `TestSanitizeLogContent`.

Note: `TestSanitizeLogContent` tests that `sanitize_log_content` strips `<think>` tags from RAG logs. Since the underlying strip logic is being kept as a defensive measure, these tests remain valid and should stay.

---

### 🔵 Documentation — Update These Files

---

**11. `docs/01-getting-started/installation.md` — Update all model references**

In Step 5 ("Pull AI Models"), replace:
```bash
# Chat model (8GB VRAM)
ollama pull qwen3.5:9b

# Classification model (runs on CPU)
ollama pull qwen3.5:2b
```
With:
```bash
# Chat model (~7GB VRAM)
ollama pull gemma3:12b

# Classification model (runs on CPU)
ollama pull gemma2:2b
```

In Step 7 ("Verify Installation"), update the expected health check output from `qwen3.5:9b` / `qwen3.5:2b` to `gemma3:12b` / `gemma2:2b`.

In the "Models Not Loading" troubleshooting section at the bottom, replace the `ollama pull qwen3.5:9b` example with `ollama pull gemma3:12b`.

---

**12. `docs/03-architecture/gpu-management.md` — Update model table and body text**

The model table currently shows `qwen3.5:9b` and `qwen3.5:2b`. Replace both with `gemma3:12b` and `gemma2:2b` throughout. Update any VRAM figures accordingly (gemma3:12b uses ~7GB). Update context window references to match the configured `8192` tokens in `kaia.yaml`.

---

**13. `docs/06-troubleshooting/common-issues.md` — Update model references**

Any `qwen3.5:9b` in code blocks or error examples should become `gemma3:12b`.

---

**14. `docs/02-user-guide/news-system.md` — Update model reference in dependencies section**

The line referencing `qwen3.5:9b` for local summarization should become `gemma3:12b`.

---

### 🔵 Planning & Reports — Archive These Files

---

**15. `docs/reports/planning/Kaiacord_Phase27_ActionPlan.docx.md` — Archive**

Move to `docs/reports/archive/`:
```bash
git mv docs/reports/planning/Kaiacord_Phase27_ActionPlan.docx.md \
        docs/reports/archive/Kaiacord_Phase27_ActionPlan_ARCHIVED.md
```

Add a warning header at the very top of the file after moving it:
```markdown
> [!WARNING]
> **ARCHIVED — SUPERSEDED.** Phase 27 (Qwen3.5 migration) was rolled back March 4, 2026.
> Gemma3:12b remains the production model. This plan is retained for historical reference only.
```

---

**16. `docs/reports/README.md` — Update the planning table entry**

```markdown
# CURRENT:
| qwen_3_5_upgrade_plan.md | ⏸ DEFERRED | Qwen 3.5 9B migration — deferred until gemma3:12b is fully stable |

# REPLACE WITH:
| qwen_3_5_upgrade_plan.md | ❌ CANCELLED | Qwen 3.5 9B migration — rolled back Mar 4, 2026. Gemma3:12b is the production model. |
```

---

**17. `docs/reports/planning/ROADMAP.md` — Update Qwen section**

Replace section 1.1 ("Qwen 3.5 9B Migration [DEFERRED]") with:

```markdown
### 1.1 Qwen 3.5 9B Migration [CANCELLED]
**Status:** Rolled back March 4, 2026. Reliability issues prevented stable production operation.
**Decision:** Gemma3:12b remains the production chat model. Gemma2:2b remains the classification model.
**No further action required.**
```

---

### 🔵 Tools — Archive

---

**18. `tools/pre_migration_check.py` — Archive**

This entire file is the "Kaia Qwen 3.5 Pre-Migration Validation Tool" and has zero utility after the rollback. Move it:

```bash
git mv tools/pre_migration_check.py tools/archive/pre_migration_check_ARCHIVED.py
```

---

## What to Leave Alone

The following Phase 28 work is **correct, model-agnostic, and must not be touched:**

- The CQ-01 file split: `kaia_rag_indexer.py`, `kaia_rag_persistence.py`, `kaia_rag_query.py`, `kaia_rag_retriever.py`, the `kaia_intelligence.py` facade, `intent_classifier.py`, `context_optimizer.py`
- The PF-05 SDK migration: `update_kaia_news.py` using `google-genai`
- The SEC-01 X/twikit security documentation
- The BM25 persistence (pickle) from Phase 26
- The `<think>` strip lines in `sanitize_log_content` (`kaia_rag_retriever.py`) — keep, just update the comment
- The `RE_THINK_BLOCK` regex in `intent_classifier.py` — keep, just remove the Qwen attribution comment
- `rag.query_instruction: "search_query: "` and `text_instruction: "search_document: "` in `default_config.yaml` — these belong to `nomic-embed-text` and are correct regardless of chat model

---

## Post-Cleanup Verification Checklist

After making all changes, Gemini must complete these steps in order:

**Step 1 — Run the test suite:**
```bash
PYTHONPATH=. pytest tools/tests/ -q
```
Expected: 61+ passing, 0 new failures. The two removed test classes should no longer appear. `TestSanitizeLogContent` must still pass.

**Step 2 — Grep for remaining references:**
```bash
grep -r "qwen" . --include="*.py" --include="*.yaml" --include="*.md" \
     --exclude-dir=".git" --exclude-dir="docs/reports/archive" \
     --exclude-dir="tools/archive" -i -l

grep -r "think_mode\|think_handler\|think_command\|!think\|_THINK_BLOCK" . \
     --include="*.py" --include="*.md" \
     --exclude-dir=".git" --exclude-dir="docs/reports/archive" -i -l
```
Both greps must return zero files outside of archived locations and this report itself.

**Step 3 — Update `MASTER_REPORT.md`:**

Add a new Phase 29 entry:
```
### Phase 29: Qwen/!think Rollback
**Engineer:** Antigravity (Gemini)
- Rolled back Phase 27 Qwen3.5 migration per Ekco decision (Mar 4, 2026).
- Gemma3:12b (chat) and gemma2:2b (classification) restored as canonical models.
- Removed !think command and all supporting code (stub handler, think_mode_users
  state, _THINK_BLOCK_PATTERN, registry entry, tests).
- Updated all docs, config comments, and planning files.
- Phase 28 work (CQ-01 split, PF-05 SDK, SEC-01 docs) retained in full — unaffected.
```

**Step 4 — Update `GEMINI_Report.md`** with the same Phase 29 summary.

---

## Open Issues Carried Forward

| ID | Status | Notes |
|---|---|---|
| **CQ-03 — Bare excepts in tools/** | ⏳ Open | Flagged Feb 26, still unaddressed. |
| **CQ-06 — `knowledge_boundary.py` re.MULTILINE** | ⏳ Unknown | Flagged Feb 26. Verify whether this was fixed in an earlier phase. |
| **M-01 — `kaia_rag_persistence.py` registry singleton** | ⏳ Open | New this session. A second `IdentityRegistry` instance may be created. Low priority. |
| **SEC-01 — X/twikit notice** | ⚠️ Unverifiable | MASTER_REPORT claims done. Confirm `docs/02-user-guide/x-security-notice.md` exists on disk. |

---

## Files Examined This Session

| File | Reason |
|---|---|
| `utils/commands/think_handler.py` | Confirmed dead stub — full deletion |
| `utils/commands/registry.py` | Confirmed `!think` import and dispatch present |
| `utils/infrastructure/system/bot_state.py` | Confirmed `think_mode_users` field |
| `utils/core/message_processor.py` | Confirmed `_THINK_BLOCK_PATTERN` defined but unused |
| `utils/core/kaia_rag_retriever.py` | Confirmed Qwen comment in `sanitize_log_content` |
| `utils/core/intent_classifier.py` | Confirmed `RE_THINK_BLOCK` and Qwen comment |
| `utils/infrastructure/system/yaml_config.py` | Confirmed stale fallback and comment; confirmed `classification_join_seconds` mismatch |
| `config/default_config.yaml` | Confirmed model values correct; Qwen comment to clean |
| `config/kaia.yaml` | Confirmed no models section present |
| `docs/01-getting-started/installation.md` | Confirmed all model references are qwen3.5 |
| `docs/03-architecture/gpu-management.md` | Confirmed qwen3.5 throughout |
| `docs/02-user-guide/news-system.md` | Confirmed qwen3.5:9b in dependencies section |
| `docs/06-troubleshooting/common-issues.md` | Confirmed qwen3.5:9b in code blocks |
| `docs/reports/planning/Kaiacord_Phase27_ActionPlan.docx.md` | Confirmed Qwen migration plan — archive |
| `docs/reports/planning/ROADMAP.md` | Confirmed Qwen section present |
| `docs/reports/README.md` | Confirmed qwen_3_5_upgrade_plan.md entry |
| `tools/pre_migration_check.py` | Entire file is Qwen-specific — archive |
| `tools/tests/unit/test_tier1_features.py` | Confirmed two test classes to remove |
