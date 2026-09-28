# Tests

```
tools/tests/
├── unit/           # Fast, isolated tests — no network, no Ollama, no GPU
├── integration/    # More than one subsystem together, and anything that needs a live service
└── conftest.py     # Puts the repo root on sys.path; nothing else
```

Configuration lives in `pytest.ini` at the repo root: `testpaths`, marker
declarations, `--strict-markers`, and the asyncio loop scope.

Everything under `tools/tests` named `test_*.py` is collected. What keeps a test
that needs Ollama or the GPU out of an ordinary run is its markers, so anything
that reaches the daemon must carry `ollama` (and `gpu`/`slow` as they apply), or a
suite run will load a model and evict `gemma3:12b` from VRAM.

The same holds anywhere in the tree. `test_embed_device.py` and `test_bm25_cache.py`
sat in `unit/` with no marker and embedded through the bot's own Ollama on every
"no external services" run; they carry `ollama` now and live in `integration/`.
`journalctl -u ollama` during a suite run is the check — it should show no
`/api/embed` or `/api/chat` at all.

## Running

```bash
venv/bin/python3 -m pytest                                          # everything (loads gemma3:12b)
venv/bin/python3 -m pytest -m "not ollama and not gpu and not slow" # no external services
venv/bin/python3 -m pytest tools/tests/unit -q                      # just the fast ones
venv/bin/python3 -m pytest tools/tests/unit/test_response_filters.py::test_harden_is_idempotent
```

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

`conftest.py` holds none. Its fifteen fixtures were used by no test, and several
no longer worked (a bot-state fixture called the instance as if it were the
class, a mock Ollama listed the removed `gemma2:2b`, an `event_loop` override that
pytest-asyncio 1.x ignores). Use pytest's own `tmp_path` and `monkeypatch`, and
put a shared fixture in `conftest.py` when a second test needs it.
