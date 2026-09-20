"""Every maintenance tool must at least start.

`ast.parse` and importing a *module* both pass on a script whose top-level
imports are ordered wrongly, because a `tools/` script only puts the project on
`sys.path` at runtime. Converting the corpus writers to `write_atomic` inserted
that import above `sys.path.insert(...)` in two of them, and both died with
`ModuleNotFoundError: No module named 'utils'` — invisible to the syntax check,
invisible to the suite, and invisible until someone ran them.

`rollup_user_logs` is the one that mattered: it is a monthly operation and the
next time it was due was 1 October.

Running `--help` exercises the whole import block without doing any work.
"""
import subprocess
import sys
from pathlib import Path

import pytest

# Everything reachable from kaia-tools, plus the corpus writers. A tool that
# cannot start is not a tool.
TOOLS = sorted(
    p for p in Path("tools").rglob("*.py")
    if "tests" not in p.parts
    and p.name != "__init__.py"
    and "--help" not in p.name
)


# Exercising a tool by running `python tool.py --help` is NOT safe. Sixteen of
# these have no argparse, so the argument is ignored and the script simply RUNS
# — `sanitize_logs`, `kb_cleanse_user_logs`, `repair_kb` and
# `precision_repair_kb` all rewrite `knowledge_base/user_logs/` in place. An
# earlier version of this file did exactly that and stripped the identity
# frontmatter off every forum profile, twice, while claiming to be a read-only
# check.
#
# `exec_module` under a name other than "__main__" runs the whole import block —
# which is what is actually being tested — and leaves anything guarded by
# `if __name__ == "__main__":` alone.
PROBE = """
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_probe_module", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
"""


def _starts(path: Path):
    """Import the tool's module body. Returns (ok, output)."""
    r = subprocess.run([sys.executable, "-c", PROBE, str(path)],
                       capture_output=True, text=True, timeout=90)
    combined = (r.stdout or "") + (r.stderr or "")
    broke = ("ModuleNotFoundError" in combined
             or "ImportError" in combined
             or "SyntaxError" in combined
             or "IndentationError" in combined)
    return (not broke), combined


# One subprocess per tool, ~80 of them. That is a sweep, not a unit test, so it
# is excluded from the default `-m "not ollama and not gpu and not slow"` run
# and invoked deliberately:
#     venv/bin/python3 -m pytest tools/tests/unit/test_tools_runnable.py -q
@pytest.mark.slow
@pytest.mark.parametrize("path", TOOLS, ids=lambda p: str(p))
def test_the_tool_can_start(path):
    ok, out = _starts(path)
    assert ok, f"{path} cannot start:\n{out[-600:]}"


def test_the_import_of_the_atomic_helper_comes_after_sys_path_insert():
    """The specific ordering that broke two tools. A script that inserts the
    project root on `sys.path` must do so before importing from `utils`."""
    offenders = []
    for p in TOOLS:
        src = p.read_text(encoding="utf-8", errors="replace")
        if "from utils." not in src or "sys.path.insert" not in src:
            continue
        first_utils = min(
            (src.index(line) for line in src.splitlines()
             if line.startswith("from utils.") or line.startswith("import utils")),
            default=None)
        if first_utils is None:
            continue
        insert_at = src.index("sys.path.insert")
        if first_utils < insert_at:
            offenders.append(str(p))
    assert not offenders, f"utils imported before sys.path.insert in: {offenders}"
