# Tests

```
tools/tests/
├── unit/           # Fast, isolated tests — no network, no Ollama, no GPU
├── integration/    # More than one subsystem together
├── verification/   # Manual diagnostics, run by hand (not collected by pytest)
├── archive/        # One-off scripts from past debugging, kept for reference
└── conftest.py     # Shared fixtures
```

Configuration lives in `pytest.ini` at the repo root: `testpaths`, marker
declarations, `--strict-markers`, and the asyncio loop scope.

## Running

```bash
pytest                                        # everything
pytest -m "not ollama and not gpu and not slow"   # no external services
pytest tools/tests/unit -q                    # just the fast ones
pytest tools/tests/unit/test_response_filters.py::test_harden_is_idempotent
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
- **No module-level execution.** `verification/test_vram.py` called
  `asyncio.run(main())` at import, which pytest runs during *collection* — so
  every suite run unloaded and reloaded `gemma3:12b`, evicting the production
  model from VRAM. Guard scripts with `if __name__ == "__main__":`.
- **No writes into `memory/`.** Four tests persisted artifacts into the live
  memory directory. Use `tmp_path` or `monkeypatch`.

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

See `conftest.py`: `temp_dir`, `mock_config`, `mock_ollama_client`,
`mock_discord_message`, `mock_bot_state`, `mock_torch`, and others. `mock_config`
points at `tmp_path`; it previously used relative paths that resolved against
the caller's working directory and left index artifacts in the test tree.
