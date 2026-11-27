"""Validate and render the JSON result produced by pip-audit.

Pull requests that change requirements must fail closed: an advisory, a failed
audit command, or an absent/invalid report is a failed gate. Scheduled and
manual runs keep the same evidence but remain explicitly report-only.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


@dataclass(frozen=True)
class Advisory:
    package: str
    version: str
    advisory_id: str
    fix_versions: tuple[str, ...]


@dataclass(frozen=True)
class AuditResult:
    status: str
    dependencies_scanned: int
    advisories: tuple[Advisory, ...]
    error: str
    audit_outcome: str


def load_report(path: Path) -> tuple[Any | None, str]:
    """Load a pip-audit JSON report, returning a useful error on any failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, f"pip-audit did not create {path}"
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, f"could not read valid JSON from {path}: {exc}"


def assess_report(
    report: Any,
    *,
    report_error: str = "",
    audit_outcome: str,
) -> AuditResult:
    """Validate report shape and classify clean, vulnerable, or failed scans."""
    if report_error:
        return AuditResult("failed", 0, (), report_error, audit_outcome)
    if not isinstance(report, dict):
        return AuditResult("failed", 0, (), "report root must be a JSON object", audit_outcome)

    dependencies = report.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        return AuditResult(
            "failed", 0, (), "report has no non-empty dependencies list", audit_outcome
        )

    advisories: list[Advisory] = []
    for index, dependency in enumerate(dependencies):
        if not isinstance(dependency, dict):
            return AuditResult(
                "failed", len(dependencies), tuple(advisories),
                f"dependency entry {index} is not an object", audit_outcome,
            )
        package = dependency.get("name")
        version = dependency.get("version")
        vulnerabilities = dependency.get("vulns")
        if (
            not isinstance(package, str) or not package.strip()
            or not isinstance(version, str) or not version.strip()
            or not isinstance(vulnerabilities, list)
        ):
            return AuditResult(
                "failed", len(dependencies), tuple(advisories),
                f"dependency entry {index} is missing name, version, or vulns list",
                audit_outcome,
            )

        for vuln_index, vulnerability in enumerate(vulnerabilities):
            if not isinstance(vulnerability, dict):
                return AuditResult(
                    "failed", len(dependencies), tuple(advisories),
                    f"vulnerability entry {index}:{vuln_index} is not an object",
                    audit_outcome,
                )
            advisory_id = vulnerability.get("id")
            fix_versions = vulnerability.get("fix_versions", [])
            if (
                not isinstance(advisory_id, str) or not advisory_id.strip()
                or not isinstance(fix_versions, list)
                or not all(isinstance(value, str) for value in fix_versions)
            ):
                return AuditResult(
                    "failed", len(dependencies), tuple(advisories),
                    f"vulnerability entry {index}:{vuln_index} has an invalid schema",
                    audit_outcome,
                )
            advisories.append(
                Advisory(
                    package=package,
                    version=version,
                    advisory_id=advisory_id,
                    fix_versions=tuple(fix_versions),
                )
            )

    if audit_outcome != "success":
        return AuditResult(
            "failed",
            len(dependencies),
            tuple(advisories),
            f"pip-audit command outcome was {audit_outcome!r}, not 'success'",
            audit_outcome,
        )
    if advisories:
        return AuditResult(
            "vulnerable", len(dependencies), tuple(advisories), "", audit_outcome
        )
    return AuditResult("clean", len(dependencies), (), "", audit_outcome)


def _markdown_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render_markdown(result: AuditResult, *, event_name: str) -> str:
    """Render one report for both the Actions summary and downloadable artifact."""
    blocking = event_name == "pull_request"
    mode = (
        "BLOCKING — pull-request requirements gate"
        if blocking
        else f"REPORT ONLY — {event_name} run (scheduled/manual)"
    )
    if result.status == "clean":
        outcome = f"PASS — {result.dependencies_scanned} dependencies checked; no known advisories."
    elif result.status == "vulnerable":
        outcome = (
            f"VULNERABILITIES FOUND — {len(result.advisories)} advisory finding(s) "
            f"across {len({item.package for item in result.advisories})} package(s)."
        )
    else:
        outcome = f"AUDIT FAILED — the scan could not be verified: {result.error}"

    lines = [
        "# Dependency audit",
        "",
        f"- Mode: **{mode}**",
        f"- pip-audit command outcome: **{result.audit_outcome}**",
        f"- Result: **{outcome}**",
    ]
    if result.dependencies_scanned:
        lines.append(f"- Resolved dependencies: {result.dependencies_scanned}")
    if result.status == "vulnerable":
        lines.extend([
            "",
            "| Package | Resolved version | Advisory | Fixed versions |",
            "|:--|:--|:--|:--|",
        ])
        for item in result.advisories:
            fixed = ", ".join(item.fix_versions) or "No fixed version reported"
            lines.append(
                f"| {_markdown_cell(item.package)} | {_markdown_cell(item.version)} "
                f"| {_markdown_cell(item.advisory_id)} | {_markdown_cell(fixed)} |"
            )
    if not blocking and result.status != "clean":
        lines.extend([
            "",
            "This scheduled/manual run is report-only; the result is visible here and in the "
            "pip-audit artifact, but it does not fail the workflow.",
        ])
    return "\n".join(lines) + "\n"


def exit_code(result: AuditResult, *, event_name: str) -> int:
    """Only requirements-changing PR runs are blocking; every other event reports."""
    if event_name == "pull_request" and result.status != "clean":
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="pip-audit JSON report")
    parser.add_argument("--markdown", type=Path, required=True, help="Markdown artifact path")
    parser.add_argument("--summary-file", type=Path, help="GitHub Actions step-summary path")
    parser.add_argument("--audit-outcome", required=True)
    parser.add_argument("--event-name", required=True)
    args = parser.parse_args(argv)

    report, report_error = load_report(args.input)
    result = assess_report(
        report,
        report_error=report_error,
        audit_outcome=args.audit_outcome,
    )
    markdown = render_markdown(result, event_name=args.event_name)

    args.markdown.write_text(markdown, encoding="utf-8")
    if args.summary_file is not None:
        with args.summary_file.open("a", encoding="utf-8") as summary:
            summary.write(markdown)
            summary.write("\n")

    print(markdown, end="")
    return exit_code(result, event_name=args.event_name)


if __name__ == "__main__":
    raise SystemExit(main())
