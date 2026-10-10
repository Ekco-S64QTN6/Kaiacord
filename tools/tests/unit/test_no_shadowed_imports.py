"""A name imported inside a function is local to the whole function.

`from x import clean` in one branch makes every other branch's `clean` an
unbound local, so the module-level import is never reached: `!memory beliefs`
and `!memory anchors` raised UnboundLocalError on every call that way, and the
profile writer's `write_atomic` failed every refresh for ten days.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCANNED = ("utils", "tools", "finetune")


def _own_nodes(fn):
    stack = list(ast.iter_child_nodes(fn))
    while stack:
        n = stack.pop()
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        yield n
        stack.extend(ast.iter_child_nodes(n))


def _bound(node):
    return [(a.asname or a.name).split(".")[0] for a in node.names]


def shadowed_uses(source: str) -> list:
    tree = ast.parse(source)
    module = {nm for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)) for nm in _bound(n)}
    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = list(_own_nodes(fn))
        local = {}
        for n in nodes:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for nm in _bound(n):
                    local[nm] = min(local.get(nm, n.lineno), n.lineno)
        for n in nodes:
            if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in module
                    and n.id in local and n.lineno < local[n.id]):
                found.append(f"{fn.name}:{n.lineno} uses {n.id} before its local import (line {local[n.id]})")
    return found


def test_the_check_catches_the_shape_that_broke_memory_beliefs():
    src = (
        "from m import clean\n"
        "def handle(sub):\n"
        "    if sub == 'beliefs':\n"
        "        return clean('x')\n"
        "    elif sub == 'self':\n"
        "        from m import box, clean\n"
        "        return clean(box)\n"
    )
    assert shadowed_uses(src)


def test_no_function_shadows_a_module_import_it_uses_earlier():
    bad = []
    for top in SCANNED:
        for p in (ROOT / top).rglob("*.py"):
            if "llama.cpp" in p.parts or "venv" in p.parts:
                continue
            try:
                src = p.read_text(encoding="utf-8")
                hits = shadowed_uses(src)
            except (SyntaxError, UnicodeDecodeError):
                continue
            bad += [f"{p.relative_to(ROOT)} {h}" for h in hits]
    assert not bad, "\n".join(bad)
