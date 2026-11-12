# Tests

```
tools/tests/
├── unit/              # Component tests, mostly isolated; some carry slow/ollama markers
├── integration/       # More than one subsystem together, and anything that needs a live service
├── live_write_guard.py # Audit hook: fails the run on any write under memory/, knowledge_base/ or logs/ outside a .test path
└── conftest.py        # Repo root on sys.path, installs the guard, and refuses live model teardown
```

Configuration lives in `pytest.ini` at the repo root: `testpaths`, marker
declarations, `--strict-markers`, and the asyncio loop scope.

Everything under `tools/tests` named `test_*.py` is collected. What keeps a test
that needs Ollama, a GPU, or public internet out of an ordinary run is its markers:
anything that reaches the daemon must carry `ollama`, GPU-dependent work carries `gpu`,
slow sweeps carry `slow`, and public-internet access carries `network`. Without those
markers, a suite run can reach a live service or load a model and evict `gemma3:12b` from VRAM.

The same holds anywhere in the tree. `test_embed_device.py` and `test_bm25_cache.py` (since
removed) sat in `unit/` with no marker and embedded through the bot's own Ollama on every
"no external services" run; `test_embed_device.py` carries `ollama` now and lives in `integration/`.
`journalctl -u ollama` during a suite run is the check — it should show no
`/api/embed` or `/api/chat` at all.

## Running

```bash
venv/bin/python3 -m pytest                                          # everything (loads gemma3:12b)
venv/bin/python3 -m pytest -m "not ollama and not gpu and not slow and not network" # no external services
venv/bin/python3 -m pytest tools/tests/unit -q -m "not ollama and not gpu and not slow and not network" # isolated unit tests
venv/bin/python3 -m pytest tools/tests/unit/test_response_filters.py::test_harden_is_idempotent
```

A directory path alone does not deselect marked tests. When running a subset such as
`tools/tests/unit/`, apply the same marker filter unless you deliberately want to run
slow/model/GPU/network checks. Markers classify tests; they do not skip them automatically.

## Markers

| Marker | Meaning |
|---|---|
| `slow` | Takes more than a couple of seconds |
| `gpu` | Needs a GPU and a loaded model |
| `ollama` | Needs a running Ollama daemon |
| `network` | Reaches the public internet |
| `integration` | Exercises more than one subsystem |

`--strict-markers` is on: an undeclared marker is an error, not a silent
no-op. Add new ones to `pytest.ini`.

## Suite hygiene

`unit/test_suite_hygiene.py` enforces properties of the suite itself. The
September 2026 audit found that **24 of 51 collected test files contained no
`assert` at all** — they passed by not raising — and several exercised a
private copy of the implementation rather than the real one
(`test_rate_limiter.py` defined its own `RateLimiter`; `test_phase7_filters.py`
defined a `ResponseStyleHarden` class that exists nowhere in the codebase).

The checks:

- **Every collected file asserts something.** Smoke tests whose only job is
  "this runs against a real service without raising" go in
  `ASSERTLESS_ALLOWLIST` with a one-line reason. That list is a backlog to
  shrink, not a permanent exemption.
- **No hardcoded home directories.** Nine files contained `/home/<user>/...`,
  so the suite ran on exactly one machine. `/home/user/...` inside synthetic
  fixture data is fine — it is a path shape, never opened.
- **No module-level execution.** A VRAM probe (since deleted) called
  `asyncio.run(main())` at import, which pytest runs during *collection* — so
  every suite run unloaded and reloaded `gemma3:12b`, evicting the production
  model from VRAM. Guard scripts with `if __name__ == "__main__":`.
- **No writes into `memory/`.** Four tests persisted artifacts into the live
  memory directory. Use `tmp_path` or `monkeypatch`. The hygiene test sees
  only what it scans: the TTRPG world state was written live by every run until
  28 Sept, found by running the suite under an audit hook
  (`docs/04-development/testing.md`).

## Notable suites

| File | Covers |
|---|---|
| `test_suite_hygiene.py` | Invariants of the suite itself (see above) |
| `test_command_registry.py` | `!` command routing, `!help` rendering, admin gating |
| `test_fractal_flame.py` | `!art` tone mapping, quality gate, accumulator |
| `test_desire_engine.py` | Needs vector driving proactive initiation |
| `test_reactions_and_logging.py` | Emoji selection and log payload compaction |
| `test_memory_layer_regressions.py` | Observation digest, belief and relationship eviction |
| `test_response_filters.py` | Post-generation filter behaviour |
| `test_phase69_filter_regressions.py` | Specific over-stripping incidents |

## CI coverage

The general unit workflow records focused offline coverage with `pytest-cov`. It uploads
`coverage.xml` and `coverage.json` as the `offline-unit-coverage` artifact and publishes
the changed-line result in the Actions run summary.

The initial gate requires 20% coverage of added, non-excluded lines in changed production files
under `utils/`. It uses the tests selected for the changed paths; added lines missing from the
coverage data count as uncovered. No added production lines means the gate is informational.
This is an incremental signal, not a whole-suite or production-runtime coverage percentage.
Hardware, GPU, Ollama, and network tests remain excluded from this offline measurement.

## Writing a test

Assert on behaviour, against the real implementation:

```python
from utils.infrastructure.system.rate_limiter import RateLimiter

def test_blocks_past_the_limit():
    rl = RateLimiter(requests_per_minute=3)
    for _ in range(3):
        rl.is_allowed(1)
    assert rl.is_allowed(1) is False
```

Anything touching the filesystem takes `tmp_path`. Anything needing a service
carries the matching marker. If an expectation is right but the code does not
meet it yet, use `pytest.mark.xfail(strict=True, reason=...)` — that keeps the
expectation visible and fails loudly if the behaviour is ever fixed, which
deleting the test would not.

## Fixtures

`conftest.py` holds one, autouse: `_no_live_teardown` replaces the GPU manager's
`unload_all_models`, `force_clear_gpu` and `kill_orphaned_runners` with recorders, and a test that
calls one fails the run (two shutdown tests once unloaded the live model). It also installs
`live_write_guard`, which fails the run and names the test for any write under `memory/`,
`knowledge_base/` or `logs/` outside a `.test` path. Otherwise use pytest's own `tmp_path` and
`monkeypatch`, and put a shared fixture in `conftest.py` when a second test needs it.
