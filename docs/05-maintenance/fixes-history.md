# Fixes & Improvement History

This document was consolidated into the project's reports archive.

Those reports live in `docs/reports/`, which is **git-ignored** — they quote user
transcripts and runtime telemetry, so they stay on the deployment machine rather
than in the public repository. Nothing here links into that tree, because such a
link resolves on the deployment machine and 404s for everyone else.

In a working checkout:

| Path *(local only)* | Contents |
|:--|:--|
| `docs/reports/01-status/history.md` | Development history, Phase 1 onward |
| `docs/reports/01-status/audit_report.md` | Phase-by-phase production audits |
| `docs/reports/01-status/master_report.md` | System status, metrics, strategic roadmap |
| `docs/reports/README.md` | Index of the whole tree |

For changes that are public, `git log` is the record — commit messages in this
repository carry the reasoning, the measurement and the failure that prompted
each fix.
