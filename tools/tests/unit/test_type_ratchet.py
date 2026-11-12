"""The type ratchet lets a file keep its old mypy errors and refuses new ones."""
from tools.maintenance import type_ratchet as ratchet


def test_changed_files_keeps_production_python_and_follows_renames():
    status = "\n".join([
        "M\tutils/core/a.py",
        "A\tutils/core/new.py",
        "R087\tutils/old_name.py\tutils/new_name.py",
        "M\ttools/maintenance/tool.py",
        "M\tutils/audio/levels.json",
        "D\tutils/gone.py",
    ])
    assert ratchet.changed_files(status) == {
        "utils/core/a.py": "utils/core/a.py",
        "utils/core/new.py": None,
        "utils/new_name.py": "utils/old_name.py",
    }


def test_parse_errors_reads_error_lines_and_ignores_notes():
    output = "\n".join([
        'utils/a.py:12: error: Incompatible types in assignment  [assignment]',
        'utils/a.py:12: note: see the docs',
        'utils/b.py:3:9: error: Name "x" is not defined  [name-defined]',
        "Found 2 errors in 2 files (checked 2 source files)",
    ])
    assert ratchet.parse_errors(output) == {
        "utils/a.py": [(12, "Incompatible types in assignment  [assignment]")],
        "utils/b.py": [(3, 'Name "x" is not defined  [name-defined]')],
    }


def test_existing_errors_that_only_moved_are_not_a_regression():
    files = {"utils/a.py": "utils/a.py"}
    base = {"utils/a.py": [(10, "old error  [arg-type]")]}
    head = {"utils/a.py": [(42, "old error  [arg-type]")]}
    assert ratchet.compare(files, base, head) == []


def test_a_new_error_fails_and_is_the_one_named():
    files = {"utils/a.py": "utils/a.py"}
    base = {"utils/a.py": [(10, "old error  [arg-type]")]}
    head = {"utils/a.py": [(10, "old error  [arg-type]"), (20, "new error  [attr-defined]")]}
    assert ratchet.compare(files, base, head) == [
        ("utils/a.py", 1, 2, [(20, "new error  [attr-defined]")])]


def test_a_new_file_starts_from_zero_and_a_rename_from_its_old_path():
    files = {"utils/new.py": None, "utils/moved.py": "utils/was.py"}
    base = {"utils/was.py": [(1, "kept  [misc]")]}
    head = {"utils/new.py": [(5, "fresh  [misc]")], "utils/moved.py": [(1, "kept  [misc]")]}
    assert ratchet.compare(files, base, head) == [("utils/new.py", 0, 1, [(5, "fresh  [misc]")])]


def test_report_says_when_nothing_changed_and_names_a_failure():
    assert "nothing to check" in ratchet.report({}, [], {}, {})
    files = {"utils/a.py": "utils/a.py"}
    head = {"utils/a.py": [(20, "new error  [attr-defined]")]}
    text = ratchet.report(files, ratchet.compare(files, {}, head), {}, head)
    assert "FAIL" in text and "line 20: new error" in text
