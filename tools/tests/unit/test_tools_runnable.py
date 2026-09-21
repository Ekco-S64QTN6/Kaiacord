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


def test_no_tool_reconfigures_logging_at_import_scope():
    """`exec_module` above runs every tool's import block, and so does the live
    bot: `kaia_dream` imports `generate_profile` from a tool during the nightly
    profile refresh.

    `generate_user_profiles.py` called `replace_all_logging()` at import scope,
    so that ran inside the running process every night. It emits the "Unified
    logging system initialized" marker that CLAUDE.md §9 and §11 tell you to
    segment the production log by — 6 of 23 markers in one log were this rather
    than a boot — and it strips every handler off the root logger while
    re-hijacking stdout and stderr. Reconfiguring global logging is a script's
    decision to make, so it belongs under the `__main__` guard.
    """
    import ast

    offenders = []
    for tool in TOOLS:
        try:
            tree = ast.parse(tool.read_text(encoding="utf-8"))
        except SyntaxError:
            continue                    # test_tools_parse covers this
        if "development" in tool.parts:
            continue                    # profiling scripts time this call by design
        for node in tree.body:          # top level only; a __main__ guard is an ast.If
            if (isinstance(node, ast.Expr)
                    and isinstance(node.value, ast.Call)
                    and getattr(node.value.func, "id", "") == "replace_all_logging"):
                offenders.append(f"{tool}:{node.lineno}")

    assert not offenders, (
        "replace_all_logging() at import scope — move it under "
        f"`if __name__ == \"__main__\":`: {offenders}"
    )


def test_no_corpus_writer_builds_frontmatter_with_an_f_string():
    """`f'keywords: [{", ".join(keywords)}]'` turned a block list into a flow
    sequence full of `- ` entries and left 1,074 of 6,741 corpus files — 16% —
    unparseable. `f'title: "{title}"'` breaks the same way on the first quote,
    and the values are forum thread titles, Discord display names and book
    titles that nobody controls.

    Nothing downstream catches it: the RAG indexer reads frontmatter with line
    regexes rather than a YAML parser, so retrieval keeps working while the
    block is unreadable to everything that parses it.

    Flags an f-string that *starts* with a bare `key:` and interpolates on that
    line — which is how a frontmatter line is built — unless every value on it
    goes through an escaper. A `print(f"Created summary: {path}")` does not
    start with a key, so it does not match; the first version of this test
    keyed on a literal `{`, which an f-string never contains, and passed
    against the exact code it was written to catch.
    """
    import ast
    import re

    # Frontmatter keys only. `^[a-z_]+:` was tried and matches every log line
    # of the form f"thread_id: {x}", which is noise, not a finding.
    KEY_LINE = re.compile(r"^(?:title|summary|keywords|category|document_type"
                          r"|tags|author|participants|source_url|topic)"
                          r"\s*:\s*\S*\x00")
    ESCAPERS = {"yaml_escape", "_escape_yaml", "dumps", "dump_frontmatter",
                "safe_dump", "identity_yaml"}

    allowed = {
        Path("utils/core/frontmatter.py"),
        Path("tools/maintenance/repair_frontmatter.py"),
    }

    def escaped(node):
        """True if every interpolation in this f-string goes through an escaper."""
        vals = [v for v in node.values if isinstance(v, ast.FormattedValue)]
        if not vals:
            return True
        for v in vals:
            call = v.value
            if not isinstance(call, ast.Call):
                return False
            fn = call.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name not in ESCAPERS:
                return False
        return True

    offenders = []
    for root in (Path("tools"), Path("utils")):
        for src in root.rglob("*.py"):
            if "tests" in src.parts or src in allowed:
                continue
            try:
                tree = ast.parse(src.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.JoinedStr):
                    continue
                text = "".join(
                    v.value if isinstance(v, ast.Constant) and isinstance(v.value, str)
                    else "\x00"
                    for v in node.values)
                if KEY_LINE.match(text) and not escaped(node):
                    offenders.append(f"{src}:{node.lineno}")

    assert not offenders, (
        "frontmatter built by string formatting — use "
        f"utils.core.frontmatter.dump_frontmatter: {offenders}")
