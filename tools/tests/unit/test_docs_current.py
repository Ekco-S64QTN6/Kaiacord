"""Documentation claims that can be checked against the code.

Most doc rot is unfalsifiable prose, but some of it is not: a command table, a
model list, a folder layout and a link are all things the repository can verify
about itself. Every assertion here corresponds to something that was actually
found stale on 2026-09-19 — `gemma2:2b` was still in three install guides a
month after the model was removed, and `!music` had never been documented.
"""
import re
from pathlib import Path

import pytest

DOCS = [p for p in Path("docs").rglob("*.md") if "reports" not in p.parts]
TRACKED = DOCS + [Path("README.md"), Path("CLAUDE.md")]


def test_every_command_in_the_registry_is_documented():
    """`registry.py` is the single source of truth for `!` commands, and says so.
    `!music` shipped without ever reaching the command guide."""
    from utils.commands.registry import COMMANDS

    doc = Path("docs/02-user-guide/commands.md").read_text(encoding="utf-8")
    missing = [c.name for c in COMMANDS if f"!{c.name.lstrip('!')}" not in doc]
    assert not missing, f"undocumented commands: {missing}"


def test_no_document_tells_anyone_to_pull_a_model_we_do_not_use():
    """Three install guides said `ollama pull gemma2:2b` for a month after the
    model was removed — a 1.6 GB download for something nothing loads."""
    offenders = []
    for p in TRACKED:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "ollama pull" in line and "gemma2" in line:
                offenders.append(f"{p}: {line.strip()}")
    assert not offenders, offenders


def test_the_embedding_model_is_named_with_its_suffix():
    """`nomic-embed-text` and `nomic-embed-text-cpu` are different tags. A pull
    instruction for the bare name leaves the health check reporting a miss."""
    offenders = []
    for p in TRACKED:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if "ollama pull nomic-embed-text" in line and "-cpu" not in line:
                offenders.append(f"{p}: {line.strip()}")
    assert not offenders, offenders


def test_relative_links_in_tracked_docs_resolve():
    broken = []
    for p in TRACKED:
        for m in re.finditer(r"\[[^\]]+\]\(([^)#][^)]*)\)",
                             p.read_text(encoding="utf-8", errors="replace")):
            target = m.group(1).split("#")[0]
            if not target or target.startswith(("http", "mailto")):
                continue
            if not (p.parent / target).exists():
                broken.append(f"{p} -> {target}")
    assert not broken, broken


def test_nothing_tracked_links_into_the_git_ignored_reports_tree():
    """`docs/reports/` holds user transcripts and runtime telemetry and is
    git-ignored, so a link into it resolves on the deployment machine and 404s
    for everyone else. CLAUDE.md §15 says so; two links were added anyway."""
    offenders = []
    for p in TRACKED:
        for m in re.finditer(r"\[[^\]]+\]\(([^)]*reports/[^)]*)\)",
                             p.read_text(encoding="utf-8", errors="replace")):
            offenders.append(f"{p} -> {m.group(1)}")
    assert not offenders, offenders


@pytest.mark.parametrize("folder", [
    "corrupt_files", "deep_dive_reports", "blogs", "system_logs",
])
def test_docs_do_not_reference_folders_that_were_merged_away(folder):
    """The knowledge_base top level was flattened from sixteen folders to twelve
    in September 2026. A doc naming a folder that no longer exists sends the
    reader somewhere empty."""
    offenders = []
    for p in DOCS:
        text = p.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if f"knowledge_base/{folder}" in line:
                offenders.append(f"{p}: {line.strip()[:90]}")
    assert not offenders, offenders
