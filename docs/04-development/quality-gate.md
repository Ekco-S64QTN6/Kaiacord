# Quality gate

What CI checks besides the tests, what each check blocks, and the baseline it started from
(measured 12 November 2026 on `main`). The rollout is gradual on purpose: each gate blocks only
what is already clean, so turning it on changed no existing code beyond one pre-initialised local.

| Check | Workflow | Tool (pinned) | Scope | Blocks a merge |
|:--|:--|:--|:--|:--|
| Lint | `quality.yml` | ruff 0.17.4 | whole repository, error rules only | yes |
| Type ratchet | `quality.yml` | mypy 2.4.1 | changed `utils/*.py` files, against their base | yes |
| Style count | `quality.yml` | ruff 0.17.4 | `utils`, `tools`, `.github` | no, run summary only |
| Dependency audit | `dependency-audit.yml` | pip-audit 2.10.1 | `requirements.txt`, resolved | no, report-only |
| Changed-line coverage | `unit-tests.yml` | pytest-cov | added statements in changed `utils/*.py` | yes, 20% floor |

There is no formatter, and no check rewrites a file.

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

`pip-audit -r requirements.txt` runs weekly, on demand, and on any change to `requirements.txt`.
It is report-only: the result is in the run summary and the `pip-audit` artifact, with package,
resolved version, advisory ID and fixed version.

It does not block because advisories arrive on their own schedule and the baseline is not clean.
The deployed environment, audited on 12 November 2026, had advisories against 33 of 219 installed
packages. Seven are pinned or bounded directly in `requirements.txt`:

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

Policy:

- An advisory against a package that handles untrusted input (`pypdf`, `Pillow`, `aiohttp`,
  `beautifulsoup4`, `markdownify`) is fixed by raising the pin, with the suite run and the path
  exercised before it reaches the deployment.
- An advisory that does not apply is recorded as `--ignore-vuln <ID>` in the workflow, with a
  comment saying why and the date. No blanket ignores.
- The job becomes blocking for `requirements.txt` changes once the direct pins above are raised.

## Reproducible installs

`requirements.txt` mixes exact pins with lower bounds and there is no lockfile, so two installs a
month apart can differ in every transitive package. The intended workflow is a compiled
constraints file: `requirements.txt` stays the hand-edited input, and
`uv pip compile requirements.txt --python-version 3.12 -o requirements.lock`
writes the full pinned set, installed with `pip install -r requirements.txt -c requirements.lock`
in CI and on the deployment. It is not adopted yet: the lock has to be generated against the
deployment's platform and checked on it before CI installs from it.
