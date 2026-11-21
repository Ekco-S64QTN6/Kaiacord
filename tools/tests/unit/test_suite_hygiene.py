"""Meta-tests: properties the test suite itself must hold.

The September 2026 audit found 24 of 51 collected test files containing zero
`assert` statements — they passed by not raising, and several exercised a
private copy of the implementation rather than the real one. Fixing those
files individually does not stop the next one being written, so the rules are
enforced here instead.
"""
import ast
import io
import pathlib
import re

import pytest

TESTS_ROOT = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = TESTS_ROOT.parent.parent

COLLECTED_DIRS = ("unit", "integration")

# Smoke tests: their whole job is to prove a path runs end to end without
# raising, so there is no return value to assert on. Being on this list is
# not the same as being excluded from a normal run — that takes a marker, and
# a test that reaches the live Ollama daemon must carry `ollama`.
#
# This list is a backlog, not a permanent exemption. Anything added to it
# should carry a reason on the same line.
ASSERTLESS_ALLOWLIST: set[str] = {
    "test_embed_device.py",     # asserts nothing; proves embeddings stay on CPU
}


def _collected_test_files():
    for sub in COLLECTED_DIRS:
        for path in sorted((TESTS_ROOT / sub).rglob("test_*.py")):
            yield path


def _parse(path):
    return ast.parse(io.open(path, encoding="utf-8").read()), io.open(path, encoding="utf-8").read()


def _test_functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            yield node


def _asserts_something(path):
    """A test that asserts nothing passes whatever the code does."""
    tree, source = _parse(path)
    # pytest.raises / pytest.warns / unittest assertX are assertions too.
    return (any(isinstance(n, ast.Assert) for n in ast.walk(tree))
            or "pytest.raises" in source or "pytest.warns" in source or ".assert" in source)


def _real_home(path):
    """Nine files hardcoded a real home directory, so the suite ran on exactly
    one machine. Placeholders like /home/user/... in fixture data are never
    opened and are fine."""
    source = io.open(path, encoding="utf-8").read()
    homes = [seg for seg in re.findall(r"/home/([A-Za-z0-9._-]+)", source)
             if seg not in {"user", "username", "youruser", "USER"}]
    return homes[0] if homes else None


# Calls that are conventional at import time; what matters is work that *runs*.
_IMPORT_TIME_CALLS = {"append", "insert", "load_dotenv", "skip", "register", "basicConfig", "seed",
                      "addinivalue_line", "print", "filterwarnings", "setLevel", "getLogger"}


def _module_level_call(path):
    """A bare call at module scope runs during *collection*: `test_vram.py` did
    `asyncio.run(main())` this way and evicted the production model from VRAM
    every time anyone ran the suite."""
    tree, _ = _parse(path)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name not in _IMPORT_TIME_CALLS:
                return name
    return None


def test_every_test_file_asserts_something():
    bad = [p.name for p in _collected_test_files()
           if p.name not in ASSERTLESS_ALLOWLIST and not _asserts_something(p)]
    assert not bad, f"these define tests but never assert anything: {bad}"


def test_no_hardcoded_absolute_paths():
    me = pathlib.Path(__file__).name     # this file names the pattern it looks for
    bad = [f"{p.name} (/home/{h})" for p in _collected_test_files()
           if p.name != me and (h := _real_home(p))]
    assert not bad, f"use tmp_path or paths relative to __file__: {bad}"


def test_no_module_level_execution():
    bad = [f"{p.name}: {n}()" for p in _collected_test_files() if (n := _module_level_call(p))]
    assert not bad, f'guard these with if __name__ == "__main__": {bad}'


# Files that read (never write) production memory/ paths. Reading live state
# makes a test environment-dependent but cannot corrupt anything, so these are
# tolerated rather than rewritten.
MEMORY_READERS = {"test_performance_bench.py", "test_md_logging.py"}


def test_tests_do_not_write_into_the_memory_directory():
    """Four tests persisted artifacts into the live memory/ directory:
    a 128 KB RAG index, a smoke-test log, and two profile writes."""
    write_calls = ("open(", "mkdir", "makedirs", "write_text", "json.dump", "shutil.copy")
    offenders = []
    for path in _collected_test_files():
        if path.name in MEMORY_READERS:
            continue
        source = io.open(path, encoding="utf-8").read()
        if not any(n in source for n in ('"memory/', "'memory/", '"./memory', "'./memory")):
            continue
        if "tmp_path" in source or "monkeypatch" in source:
            continue
        if any(call in source for call in write_calls):
            offenders.append(path.name)
    assert not offenders, (
        f"{offenders} write into the production memory/ directory. "
        "Use tmp_path or monkeypatch."
    )


def test_pytest_ini_declares_every_marker_in_use():
    """--strict-markers turns an undeclared marker into an error; this catches
    it at the suite level with a clearer message."""
    ini = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    declared = {
        line.split(":", 1)[0].strip()
        for line in ini.splitlines()
        if line.startswith("    ") and ":" in line and not line.strip().startswith("#")
    }
    declared |= {"parametrize", "asyncio", "xfail", "skip", "skipif", "filterwarnings"}

    used = set()
    for sub in COLLECTED_DIRS:
        for path in (TESTS_ROOT / sub).rglob("test_*.py"):
            tree, _ = _parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
                    if getattr(node.value.value, "id", None) == "pytest" and node.value.attr == "mark":
                        used.add(node.attr)

    assert used <= declared, f"undeclared pytest markers in use: {sorted(used - declared)}"


def test_no_bare_except_clauses_in_utils():
    """A bare `except:` also catches KeyboardInterrupt and SystemExit. Four of
    these sat in the retrieval hot path, in loops that run over every node of
    every retrieval, so a Ctrl-C landing inside one was silently discarded."""
    import ast
    from pathlib import Path

    offenders = []
    for f in sorted(Path("utils").rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                offenders.append(f"{f}:{node.lineno}")
    assert not offenders, "bare except clauses: " + ", ".join(offenders)
