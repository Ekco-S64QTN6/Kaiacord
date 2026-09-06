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

# Collected test modules only: `verification/` holds manual diagnostic scripts
# that pytest does not pick up, and `archive/` is kept for reference.
COLLECTED_DIRS = ("unit", "integration")

# Smoke tests: their whole job is to prove a path runs end to end against a
# real service without raising, so there is no return value to assert on.
# Every entry needs Ollama, a built index, or the network — they are excluded
# from a normal run with `-m "not ollama and not network and not slow"`.
#
# This list is a backlog, not a permanent exemption. It shrank from 24 files
# to these during the September 2026 audit; anything added to it should come
# with a reason on the same line.
ASSERTLESS_ALLOWLIST: set[str] = {
    "test_bm25_cache.py",       # builds and reloads a BM25 cache via embeddings
    "test_embed_device.py",     # asserts nothing; proves embeddings stay on CPU
    "test_exact_rag.py",        # exact-match retrieval against the live index
    "test_md_logging.py",       # markdown interaction logging round-trip
    "test_memory.py",           # RAG memory recall against the live index
    "test_news_manager.py",     # fetches and parses live feeds
    "test_news_parsing.py",     # parses a live feed payload
    "test_quip_samples.py",     # generates quips through Ollama
    "test_quips.py",            # quip smoke test through Ollama
    "test_loop_responsiveness.py",  # timing probe on the logging bridge
}


def _collected_test_files():
    for sub in COLLECTED_DIRS:
        for path in sorted((TESTS_ROOT / sub).glob("test_*.py")):
            yield path


def _parse(path):
    return ast.parse(io.open(path, encoding="utf-8").read()), io.open(path, encoding="utf-8").read()


def _test_functions(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            yield node


@pytest.mark.parametrize(
    "path", list(_collected_test_files()), ids=lambda p: p.name
)
def test_every_test_file_asserts_something(path):
    """A test that asserts nothing passes whatever the code does."""
    if path.name in ASSERTLESS_ALLOWLIST:
        pytest.skip("allowlisted")
    tree, source = _parse(path)

    has_assert = any(isinstance(n, ast.Assert) for n in ast.walk(tree))
    # pytest.raises / pytest.warns / unittest assertX are assertions too.
    has_raises = "pytest.raises" in source or "pytest.warns" in source
    has_unittest = ".assert" in source

    assert has_assert or has_raises or has_unittest, (
        f"{path.name} defines tests but never asserts anything. It will pass "
        "regardless of what the code under test does."
    )


@pytest.mark.parametrize(
    "path", list(_collected_test_files()), ids=lambda p: p.name
)
def test_no_hardcoded_absolute_paths(path):
    """Nine files hardcoded a real home directory, so the suite ran on exactly
    one machine.

    Generic placeholders like /home/user/... inside synthetic fixture data are
    fine — they are never opened, they stand in for a path shape.
    """
    if path.name == pathlib.Path(__file__).name:
        return  # this file names the offending pattern in its own message
    source = io.open(path, encoding="utf-8").read()
    real_homes = [
        seg for seg in re.findall(r"/home/([A-Za-z0-9._-]+)", source)
        if seg not in {"user", "username", "youruser", "USER"}
    ]
    assert not real_homes, (
        f"{path.name} hardcodes /home/{real_homes[0]}/... Use tmp_path, or "
        "resolve paths relative to __file__."
    )


@pytest.mark.parametrize(
    "path", list(_collected_test_files()), ids=lambda p: p.name
)
def test_no_module_level_execution(path):
    """A bare call at module scope runs during *collection*.

    `test_vram.py` did `asyncio.run(main())` this way, which unloaded and
    reloaded gemma3:12b — evicting the production model from VRAM — every time
    anyone ran the suite.
    """
    tree, _ = _parse(path)
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            # sys.path manipulation, env loading and module-level skips are
            # conventional at import time; what matters is work that *runs*.
            if name in {"append", "insert", "load_dotenv", "skip", "register",
                        "basicConfig", "seed", "addinivalue_line", "print",
                        "filterwarnings", "setLevel", "getLogger"}:
                continue
            pytest.fail(
                f"{path.name} calls {name}() at module scope; it will run "
                "during pytest collection. Guard it with "
                'if __name__ == "__main__":'
            )


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
        for path in (TESTS_ROOT / sub).glob("test_*.py"):
            tree, _ = _parse(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute):
                    if getattr(node.value.value, "id", None) == "pytest" and node.value.attr == "mark":
                        used.add(node.attr)

    assert used <= declared, f"undeclared pytest markers in use: {sorted(used - declared)}"
