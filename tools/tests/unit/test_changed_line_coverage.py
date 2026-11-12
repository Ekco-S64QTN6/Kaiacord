"""Changed-line coverage reporting treats untested added code as uncovered."""
from tools.maintenance.changed_line_coverage import (
    changed_line_report, changed_python_lines, statement_lines,
)


def test_changed_python_lines_reads_added_hunks_and_ignores_other_paths():
    diff = """diff --git a/utils/example.py b/utils/example.py
+++ b/utils/example.py
@@ -2,0 +3,2 @@
+first_added()
+second_added()
diff --git a/tools/example.py b/tools/example.py
+++ b/tools/example.py
@@ -1,0 +2 @@
+not_production()
"""
    assert changed_python_lines(diff) == {"utils/example.py": {3, 4}}


def test_changed_line_coverage_applies_initial_floor_and_exclusions():
    coverage = {
        "files": {
            "utils/example.py": {
                "executed_lines": [3],
                "missing_lines": [4],
                "excluded_lines": [],
            }
        }
    }
    summary, passed = changed_line_report(coverage, {"utils/example.py": {3, 4}}, 20.0)
    assert passed
    assert "1/2" in summary
    assert "50.0%" in summary


def test_changed_lines_missing_from_report_count_as_uncovered():
    summary, passed = changed_line_report(
        {"files": {}}, {"utils/not_tested.py": {10, 11}}, 20.0, statements_of=lambda path: None)
    assert not passed
    assert "0/2" in summary
    assert "FAIL" in summary


def test_no_changed_production_lines_is_informational():
    summary, passed = changed_line_report({"files": {}}, {}, 20.0)
    assert passed
    assert "No added production statements" in summary


def test_excluded_changed_lines_are_not_in_the_gate():
    coverage = {
        "files": {
            "utils/example.py": {
                "executed_lines": [],
                "missing_lines": [3],
                "excluded_lines": [4],
            }
        }
    }
    summary, passed = changed_line_report(coverage, {"utils/example.py": {3, 4}}, 0.0)
    assert passed
    assert "0/1" in summary
    assert "| 1 |" in summary


def test_comments_and_docstrings_added_to_a_covered_file_are_not_uncovered_code():
    coverage = {"files": {"utils/example.py": {
        "executed_lines": [1, 2, 3], "missing_lines": [], "excluded_lines": []}}}
    summary, passed = changed_line_report(coverage, {"utils/example.py": set(range(10, 20))}, 20.0)
    assert passed
    assert "No added production statements" in summary


def test_only_the_statements_among_added_lines_are_measured():
    coverage = {"files": {"utils/example.py": {
        "executed_lines": [3], "missing_lines": [6], "excluded_lines": []}}}
    summary, passed = changed_line_report(coverage, {"utils/example.py": {3, 4, 5, 6}}, 20.0)
    assert passed
    assert "1/2" in summary


def test_an_unimported_file_is_measured_by_its_own_statements():
    source = '"""Module docstring."""\n# a comment\nVALUE = {\n    "a": 1,\n}\n\ndef f():\n    """Doc."""\n    return VALUE\n'
    assert statement_lines(source) == {3, 7, 9}
    summary, passed = changed_line_report(
        {"files": {}}, {"utils/new.py": set(range(1, 10))}, 20.0,
        statements_of=lambda path: statement_lines(source))
    assert not passed
    assert "0/3" in summary
