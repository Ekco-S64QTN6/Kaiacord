"""A global name nothing defines is a NameError waiting for its branch to run.

`ast.parse` and `compileall` pass it. `run_caravan_arrival` called
`update_world_state` without importing it: every caravan posted its arrival,
raised, and never set `caravan_active`, so nobody could travel to it.
"""
import ast
import builtins
import symtable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCANNED = ("utils", "tools", "finetune", "scripts")
KNOWN = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__builtins__", "__spec__",
                              "__loader__", "__package__", "__path__", "__annotations__"}


def undefined_globals(source: str, filename: str = "<src>") -> list:
    tree = ast.parse(source)
    if any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        return []                         # a star import defines what it likes
    top = symtable.symtable(source, filename, "exec")
    defined = {s.get_name() for s in top.get_symbols()
               if s.is_assigned() or s.is_imported() or s.is_namespace()}
    defined |= {nm for n in ast.walk(tree) if isinstance(n, ast.Global) for nm in n.names}
    defined |= KNOWN
    found = []

    def walk(table):
        for s in table.get_symbols():
            if s.is_referenced() and s.get_name() not in defined and (table is top or s.is_global()):
                found.append((table.get_lineno(), table.get_name(), s.get_name()))
        for child in table.get_children():
            walk(child)

    walk(top)
    return sorted(set(found))


def test_the_check_sees_a_missing_import():
    src = "async def f():\n    from x import a\n    await update_world_state(a)\n"
    assert [n for _, _, n in undefined_globals(src)] == ["update_world_state"]
    assert undefined_globals("import os\ndef f():\n    return os.sep, len([])\n") == []


def test_no_module_uses_a_global_it_never_defines():
    bad = []
    for top in SCANNED:
        for path in sorted((ROOT / top).rglob("*.py")):
            if "tests" in path.relative_to(ROOT).parts:
                continue
            for line, scope, name in undefined_globals(path.read_text(encoding="utf-8"), str(path)):
                bad.append(f"{path.relative_to(ROOT)}:{line} {scope} uses {name!r}")
    assert not bad, "\n".join(bad)
