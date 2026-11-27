# Quality gate

What CI checks besides the tests, what each check blocks, and the baseline it started from
(measured 12 November 2026 on `main`). The rollout is gradual on purpose: each gate blocks only
what is already clean, so turning it on changed no existing code beyond one pre-initialised local.

| Check | Workflow | Tool (pinned) | Scope | Fails the run |
|:--|:--|:--|:--|:--|
| Lint | `quality.yml` | ruff 0.17.4 | whole repository, error rules only | yes |
| Type ratchet | `quality.yml` | mypy 2.4.1 | changed `utils/*.py` files, against their base | yes |
| Style count | `quality.yml` | ruff 0.17.4 | `utils`, `tools`, `.github` | no, run summary only |
| Dependency audit | `dependency-audit.yml` | pip-audit 2.10.1 | resolved `requirements.txt` graph | yes for requirements-changing PRs; report-only on schedule/manual |
| Changed-line coverage | `unit-tests.yml` | pytest-cov | added statements in changed `utils/*.py` | yes, 20% floor |

There is no formatter, and no check rewrites a file.

The 20% changed-line coverage floor applies only to added statements in changed `utils/*.py` files. It does **not** measure HTML, CSS or JavaScript under `assets/`; those surfaces need browser-level regression tests. A green Python coverage result is not front-end coverage.

## Running the checks locally

Neither tool is in `requirements.txt`; the bot does not need them.

```bash
venv/bin/python3 -m pip install ruff==0.17.4 mypy==2.4.1 pip-audit==2.10.1
venv/bin/ruff check .                                  # the lint gate; reads ruff.toml
venv/bin/python3 tools/maintenance/type_ratchet.py       # the type ratchet, against origin/main
venv/bin/pip-audit -r requirements.txt --desc off      # the dependency audit
```

To move a pinned tool version, change it in the workflow and in this file in one commit, and
re-measure the baseline below first: a newer release can add findings to rules already selected.

## Lint

`ruff.toml` selects `E9`, `F63`, `F7` and `F82`: syntax errors, comparisons that are always wrong,
statements that cannot run where they are, and undefined names. These are faults, not style, so
the gate runs over the whole tree and not only the files a change touches.

Baseline: two findings, both `F821`. `utils/admin/logscan.py` read a local that was only bound
later in the same loop (now pre-initialised). `utils/audio/records.py` names `beatgrid.Grid` in a
quoted dataclass annotation that is never evaluated; that file is excused from `F821` in
`ruff.toml`.

The classic style set (`E4,E7,E9,F`) stood at 1,298 findings and is reported, not gated:

| Rule | Count | | Rule | Count |
|:--|--:|:--|:--|--:|
| `F401` unused import | 376 | | `E741` ambiguous name | 62 |
| `E701` statement after a colon | 367 | | `F811` redefined while unused | 60 |
| `E402` import not at top | 100 | | `F841` unused variable | 45 |
| `F541` f-string without placeholders | 97 | | `E731` lambda assignment | 41 |
| `F405` name from a star import | 76 | | others | 74 |

A rule moves into `ruff.toml` when its count is zero, in a commit that only fixes that rule.
Many `E402` and `F401` hits are deliberate (imports inside a `try`, re-exports), so those two
need per-file decisions, not `--fix`.

## Type ratchet

`tools/maintenance/type_ratchet.py` runs mypy on each changed `utils/*.py` file twice, at the merge
base and at the head, and fails when a file's error count rose. The base commit is the baseline,
so nothing is stored and nothing needs regenerating. A new file starts from zero.

Flags: `--ignore-missing-imports --follow-imports=skip`. A file is judged on its own text, so an
error elsewhere cannot fail an unrelated change, and the job needs no project dependencies. The
cost is that cross-module type errors are not seen. Counts are compared per file, so a change that
fixes one error and adds another in the same file passes.

Baseline with those flags: 607 errors in 100 of 268 files under `utils/` (`core` 196, `ttrpg` 130,
`audio` 108, `commands` 43, `radio` 42, `social` 32, `infrastructure` 28, `news` 15, `admin` 12,
`sky` 1). The largest classes are `attr-defined` 163, `var-annotated` 80, `assignment` 77,
`arg-type` 77 and `union-attr` 67.

## Dependency audit

`pip-audit -r requirements.txt` runs weekly, on demand, and on pull requests that change
`requirements.txt` (or the audit workflow/report implementation). The resolved requirements graph
is a **blocking gate on pull requests**: a known advisory, a non-successful audit command, a missing
JSON result, or an invalid/incomplete report fails the check. The workflow runs pip-audit once,
preserves its JSON output, and builds the Markdown summary and artifact from that same result.

Weekly scheduled and manually dispatched runs are explicitly **report-only**. They still publish
vulnerability findings and scan errors to the summary and artifact, but do not fail the workflow.
A nonzero scanner exit or invalid report is never described as a clean scan in either mode.

A requirements-only scan on 27 November 2026 resolved 123 packages with zero advisories. Its
`requirements.txt` blob SHA matched the current main input at the time of the scan. This checks
only the declared requirements graph; it is not an audit of every package installed in the deployed
environment or the separate fine-tuning stack.

The deployed environment, audited on 12 November 2026, had advisories against 33 of 219 installed
packages. Seven were then pinned or bounded directly in `requirements.txt`:

| Package | Installed | Advisories | Fixed by |
|:--|:--|--:|:--|
| `pypdf` | 6.6.0 | 61 | 6.21.4 |
| `Pillow` | 12.0.0 | 59 | 13.0.0 |
| `nltk` | 3.9.2 | 42 | 3.10.4 |
| `aiohttp` | 3.13.3 | 32 | 3.14.4 |
| `PyNaCl` | 1.5.0 | 2 | 1.6.2 |
| `markdownify` | 0.11.6 | 1 | 0.14.1 |
| `python-dotenv` | 1.2.1 | 1 | 1.2.2 |

The rest are transitive (`cryptography`, `urllib3`, `starlette`, `requests`, `certifi` and
others) or belong to the fine-tuning stack, which is not in `requirements.txt` (`torch`,
`transformers`, `datasets`, `accelerate`, `sentence-transformers`).

**Follow-up, 26 November 2026:** the 12 November snapshot above is historical and its pypdf
"fixed by 6.21.4" row predates several later pypdf advisories. The direct pin is now
`pypdf==7.2.0`, released 26 November with additional limits for embedded-file dictionaries,
indexed colour-space lookup tables and CMap processing. `llama-index-readers-file==0.5.6` was removed because it caps pypdf below 7; Kaiacord now
reads TXT/MD/DOCX explicitly and sends PDFs only through the shared worker. A package upgrade is not the whole
mitigation: all four application entry points that parse PDFs (linked context, public download,
RAG ingestion/recovery and dream snippets) now use `utils/core/pdf_worker.py`. It applies a
single process-wide parser semaphore, bounded input/page/text sizes, and per-child address-space,
CPU and wall-clock ceilings. The download path has a larger byte/page/text allowance, but it
shares the same one-worker semaphore so it cannot create a second parser pool.
 The context path fails fast after one second; corpus indexing waits up to the worker queue
budget, and nightly dream extraction permits its bounded batch to drain serially rather than
silently dropping every PDF that loses the first semaphore race.

The dependency-audit artifact from this PR also found the still-permitted `PyNaCl==1.5.0`
floor (CVE-2025-69277) and `starlette==0.50.0` (pulled by the unused FastAPI/Uvicorn server
stack). The PyNaCl lower bound is raised to 1.6.2. Because discord.py 2.7.1's optional `[voice]`
extra requires `PyNaCl<1.6`, Kaiacord installs `discord.py==2.7.1` without that extra and lists
`PyNaCl>=1.6.2` and `davey>=0.1.6` separately; the voice client checks for those modules at
runtime. Searches of repository source found no FastAPI, Uvicorn, uvloop or watchfiles imports
or entry points, so those unused requirements were removed rather than upgrading an unused ASGI
framework stack. The next dependency-audit run must confirm the resolved environment is clear.

Policy:

- Every requirements-changing PR must produce a valid, non-empty JSON dependency report and a
  successful pip-audit command with zero known advisories. Vulnerabilities and scanner/resolver
  failures both fail the PR check.
- Weekly and manually dispatched runs remain report-only, but must distinguish a clean result,
  known advisories, and a failed/invalid scan in their summary and artifact.
- An advisory against a package that handles untrusted input (`pypdf`, `Pillow`, `aiohttp`,
  `beautifulsoup4`, `markdownify`) is fixed by raising the pin, with the suite run and the path
  exercised before it reaches the deployment.
- An advisory that does not apply is recorded as `--ignore-vuln <ID>` in the workflow, with a
  comment saying why and the date. No blanket ignores.

## Reproducible installs

`requirements.txt` mixes exact pins with lower bounds and there is no lockfile, so two installs a
month apart can differ in every transitive package. The intended workflow is a compiled
constraints file: `requirements.txt` stays the hand-edited input, and
`uv pip compile requirements.txt --python-version 3.12 -o requirements.lock`
writes the full pinned set, installed with `pip install -r requirements.txt -c requirements.lock`
in CI and on the deployment. It is not adopted yet: the lock has to be generated against the
deployment's platform and checked on it before CI installs from it.
