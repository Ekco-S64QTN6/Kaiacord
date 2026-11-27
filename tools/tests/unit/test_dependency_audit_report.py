"""Fail-closed and report-only behavior for the dependency-audit workflow."""
import json

from tools.maintenance import dependency_audit_report as audit


def _clean_report():
    return {
        "dependencies": [
            {"name": "aiohttp", "version": "3.14.4", "vulns": []},
            {"name": "pypdf", "version": "7.2.0", "vulns": []},
        ]
    }


def _vulnerable_report():
    report = _clean_report()
    report["dependencies"][0]["vulns"] = [
        {"id": "PYSEC-2099-123", "fix_versions": ["3.14.5"]}
    ]
    return report


def test_clean_requirements_report_passes_the_blocking_pull_request_gate():
    result = audit.assess_report(_clean_report(), audit_outcome="success")

    assert result.status == "clean"
    assert result.dependencies_scanned == 2
    assert result.advisories == ()
    assert audit.exit_code(result, event_name="pull_request") == 0
    assert "BLOCKING" in audit.render_markdown(result, event_name="pull_request")
    assert "no known advisories" in audit.render_markdown(
        result, event_name="pull_request"
    )


def test_advisory_in_requirements_report_fails_the_blocking_pull_request_gate():
    result = audit.assess_report(_vulnerable_report(), audit_outcome="failure")

    assert result.status == "vulnerable"
    assert len(result.advisories) == 1
    assert result.advisories[0].advisory_id == "PYSEC-2099-123"
    assert audit.exit_code(result, event_name="pull_request") == 1

    markdown = audit.render_markdown(result, event_name="pull_request")
    assert "PYSEC-2099-123" in markdown
    assert "3.14.5" in markdown
    assert "REPORT ONLY" not in markdown


def test_successful_audit_command_with_advisory_still_fails_closed():
    result = audit.assess_report(_vulnerable_report(), audit_outcome="success")

    assert result.status == "vulnerable"
    assert audit.exit_code(result, event_name="pull_request") == 1


def test_failed_audit_command_cannot_be_mistaken_for_a_clean_report():
    result = audit.assess_report(_clean_report(), audit_outcome="failure")

    assert result.status == "failed"
    assert "not 'success'" in result.error
    assert audit.exit_code(result, event_name="pull_request") == 1
    assert "AUDIT FAILED" in audit.render_markdown(
        result, event_name="pull_request"
    )


def test_missing_or_malformed_json_fails_the_pull_request_gate(tmp_path):
    missing, error = audit.load_report(tmp_path / "missing.json")
    result = audit.assess_report(
        missing, report_error=error, audit_outcome="failure"
    )

    assert result.status == "failed"
    assert "did not create" in result.error
    assert audit.exit_code(result, event_name="pull_request") == 1

    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{not json", encoding="utf-8")
    malformed, error = audit.load_report(malformed_path)
    malformed_result = audit.assess_report(
        malformed, report_error=error, audit_outcome="success"
    )
    assert malformed_result.status == "failed"
    assert "valid JSON" in malformed_result.error
    assert audit.exit_code(malformed_result, event_name="pull_request") == 1


def test_invalid_or_empty_dependency_report_fails_closed():
    for payload in ({}, {"dependencies": []}, {"dependencies": [{"name": "aiohttp"}]}):
        result = audit.assess_report(payload, audit_outcome="success")
        assert result.status == "failed"
        assert audit.exit_code(result, event_name="pull_request") == 1


def test_scheduled_and_manual_runs_are_explicitly_report_only():
    vulnerable = audit.assess_report(_vulnerable_report(), audit_outcome="failure")
    missing = audit.assess_report(
        None, report_error="pip-audit did not create pip-audit.json",
        audit_outcome="failure",
    )

    for event_name, result in (
        ("schedule", vulnerable),
        ("workflow_dispatch", missing),
    ):
        assert audit.exit_code(result, event_name=event_name) == 0
        markdown = audit.render_markdown(result, event_name=event_name)
        assert "REPORT ONLY" in markdown
        assert "does not fail the workflow" in markdown
    assert "PYSEC-2099-123" in audit.render_markdown(
        vulnerable, event_name="schedule"
    )
    assert "AUDIT FAILED" in audit.render_markdown(
        missing, event_name="workflow_dispatch"
    )


def test_cli_writes_both_artifact_and_actions_summary_even_for_a_failed_audit(tmp_path):
    report_path = tmp_path / "pip-audit.json"
    markdown_path = tmp_path / "pip-audit.md"
    summary_path = tmp_path / "summary.md"
    report_path.write_text(json.dumps(_vulnerable_report()), encoding="utf-8")

    result = audit.main([
        "--input", str(report_path),
        "--markdown", str(markdown_path),
        "--summary-file", str(summary_path),
        "--audit-outcome", "failure",
        "--event-name", "pull_request",
    ])

    assert result == 1
    assert "PYSEC-2099-123" in markdown_path.read_text(encoding="utf-8")
    assert "PYSEC-2099-123" in summary_path.read_text(encoding="utf-8")
