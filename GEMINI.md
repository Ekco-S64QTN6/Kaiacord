# GEMINI.md

**The canonical agent directive for this repository is [`AGENTS.md`](AGENTS.md). Read that file.**

This file exists only so that tools which look for `GEMINI.md` by name find a pointer.

---

### Why this is a pointer and not a copy

`GEMINI.md` and `AGENTS.md` were previously maintained as parallel documents. They drifted, and
by September 2026 they disagreed with each other and with the code:

- Both claimed importing from `utils/` "hangs indefinitely". It does not — verified on the venv
  and system interpreters. The claim steered agents away from the strongest verification method
  they had.
- Both specified Python 3.14+; the project venv runs 3.12.
- `AGENTS.md` gave two different monster counts in the same file (366 and 369; the real number
  was 369) and two different safety-pipeline layer counts.

Duplicated instructions rot independently. One source, many pointers.
