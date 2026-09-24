# Fixes & Improvement History

This document was consolidated into the project's reports archive.

Those reports live in `docs/reports/`, which is **git-ignored** — they quote user
transcripts and runtime telemetry, so they stay on the deployment machine rather
than in the public repository. Nothing here links into that tree, because such a
link resolves on the deployment machine and 404s for everyone else.

In a working checkout:

| Path *(local only)* | Contents |
|:--|:--|
| `docs/reports/STATUS.md` | Where every subsystem stands today |
| `docs/reports/DECISIONS.md` | Everything proposed and not built, for the operator to decide |
| `docs/reports/log/engineering-log.md` | Phase-by-phase engineering log, Phase 67 onward (`history-phases-1-66.md` before that) |
| `docs/reports/README.md` | Index of the whole tree |

For changes that are public, `git log` is the record — commit messages in this
repository carry the reasoning, the measurement and the failure that prompted
each fix.
