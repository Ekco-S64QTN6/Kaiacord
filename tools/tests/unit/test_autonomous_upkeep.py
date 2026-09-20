"""What has to run on its own to keep retrieval healthy.

Three deterministic corpus operations existed only behind `kaia-tools.sh`,
which means they happened when somebody thought of them. Rollup is the one
that matters: a day is the wrong unit for chunking — 533 of 1,112 daily files
once held fewer than the splitter's 6 turns — and it is a *monthly* operation,
so a backlog is invisible until the month turns and 305 files come due at once.
"""
import inspect
import re

import pytest

from utils.core.background_tasks import CoreTaskManager
from utils.infrastructure.system.yaml_config import config


# (attribute, the script it must invoke)
SCHEDULED = [
    ("corpus_hygiene_task", "rollup_user_logs.py"),
    ("corpus_hygiene_task", "build_user_folder_index.py"),
    ("corpus_hygiene_task", "audit_knowledge_base.py"),
    ("dream_curation_task", "triage_dreams.py"),
    ("dream_curation_task", "consolidate_dreams.py"),
    ("metadata_enrichment_task", "enrich_metadata.py"),
]


@pytest.mark.parametrize("attr,script", SCHEDULED)
def test_the_task_invokes_the_tool(attr, script):
    factory = getattr(CoreTaskManager, f"_make_{attr}")
    assert script in inspect.getsource(factory), (
        f"{attr} no longer runs {script}; it is back to being something "
        f"somebody has to remember")


@pytest.mark.parametrize("attr", sorted({a for a, _ in SCHEDULED}))
def test_the_task_is_started_and_stopped(attr):
    """A task that is created but never started is worse than absent: the code
    reads as though the work is covered."""
    start = inspect.getsource(CoreTaskManager.start)
    stop = inspect.getsource(CoreTaskManager.stop)
    assert f"self.{attr}.start()" in start, f"{attr} is never started"
    assert f"self.{attr}.stop()" in stop, f"{attr} is never stopped"


@pytest.mark.parametrize("key,default", [
    ("knowledge_base.auto_hygiene", True),
    ("knowledge_base.auto_enrich", True),
    ("dream_mode.auto_curate", True),
])
def test_each_autonomous_pass_has_a_switch(key, default):
    assert config.get(key, None) is default, f"{key} is missing from the defaults"


def test_the_hygiene_pass_makes_no_model_call():
    """It runs weekly and unattended. Anything here that reached for the GPU
    would compete with live chat, and the out-of-process semaphore cannot
    arbitrate that (CLAUDE.md §4)."""
    src = inspect.getsource(CoreTaskManager._make_corpus_hygiene_task)
    for forbidden in ("ollama", "chat_model", "run_with_gpu_guard", "consolidate_dreams"):
        assert forbidden not in src, f"corpus hygiene reaches for {forbidden}"


def test_the_audit_summary_excludes_the_backfill_backlog():
    """The backlog is pending work the nightly pass is already doing. Reporting
    it as a finding every week is how a warning stops being read."""
    src = inspect.getsource(CoreTaskManager._make_corpus_hygiene_task)
    assert "awaiting nightly" in src, (
        "the weekly audit warning will include the backfill backlog again")


def test_the_finding_regex_matches_real_audit_output():
    """Asserted against the shape the tool actually prints, not a guess."""
    sample = (
        "1319 corpus file(s) across 9 folder(s)\n"
        "  books:15  documents:78\n\n"
        "    300  no_frontmatter\n"
        "         news/archive/x.md\n"
        "      3  replacement_char\n"
        "    353  awaiting nightly metadata backfill (not a defect)\n"
    )
    findings = [
        l.strip() for l in sample.splitlines()
        if re.match(r"^\s+\d+\s+\w", l)
        and "corpus file" not in l
        and "awaiting nightly" not in l
    ]
    assert findings == ["300  no_frontmatter", "3  replacement_char"]
