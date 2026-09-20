"""The dream corpus tools.

`kaia_dreams/` is indexed as its own RAG index and `context_optimizer` labels
anything from it INTERNAL REFLECTION (DREAM) — as something Kaia thought. What
goes in there, and what happens to it afterwards, is therefore load-bearing.
"""
import importlib.util
from pathlib import Path

import pytest


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, Path(rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


triage = _load("_triage", "tools/maintenance/triage_dreams.py")
consol = _load("_consol", "tools/maintenance/consolidate_dreams.py")


# ── Triage ───────────────────────────────────────────────────────────

REFLECTION = (
    "---\nsource_type: kaia_reflection\n---\n\n"
    "# Dream Reflection: books/Snow Crash.md\nSource: books/Snow Crash.md\n\n"
    "## Original Fragment\n> the Deliverator belongs to an elite order.\n\n"
    "## Kaia's Reflection\n" + "stephenson meant it as a joke and it stopped being one. " * 6
)


def test_a_real_reflection_is_kept():
    assert triage.classify(REFLECTION) == "reflection"


def test_a_chat_transcript_is_not_a_dream():
    t = "---\ndocument_type: Transcript\n---\n\nUser: hey kaia\nKaia: hey.\n"
    assert triage.classify(t) == "transcript"


def test_a_transcript_fused_to_its_frontmatter_is_still_a_transcript():
    """Most of this corpus is malformed this way — the closing fence and the
    first line of content share a line, so `^User:` never matches and 272
    plainly-transcript files were filed as unclassifiable."""
    t = '---\nsummary: "x"\ndocument_type: Transcript\n---User: speeding ticket here and there\n'
    assert triage.classify(t) == "transcript"


def test_bold_speaker_labels_count_as_a_transcript():
    t = "---\nx: 1\n---\n\n**User:** down there. it's Spider's van.\n"
    assert triage.classify(t) == "transcript"


def test_the_model_reporting_nothing_to_dream_is_not_a_dream():
    t = ("---\nx: 1\n---\n\nThere is no meaningful interaction to extract from the "
         "provided chat log. Therefore, the cleaned log is empty.")
    assert triage.classify(t) == "empty"


def test_a_reflection_that_merely_mentions_an_empty_log_survives():
    """The empty-phrase test runs on the reflection body, not the whole file.

    She writes about her own logs constantly; condemning a real reflection for
    containing one of these phrases in passing would delete genuine material.
    """
    t = REFLECTION + "\n\nthere is no meaningful interaction in an empty room either."
    assert triage.classify(t) == "reflection"


def test_recursive_dreams_are_identified_but_not_condemned():
    t = REFLECTION.replace("Source: books/Snow Crash.md",
                           "Source: dream_20260413_035830_dream_20.md")
    assert triage.is_recursive(t)
    assert triage.classify(t) == "reflection"


# ── Title resolution ─────────────────────────────────────────────────

def test_nested_dream_prefixes_are_stripped():
    assert consol.clean_title("dream_20260518_030120_dream_20260413_035830_Snow_Crash") \
        == "Snow Crash"


def test_a_stem_that_is_nothing_but_prefixes_yields_no_title():
    assert consol.clean_title("dream_20260518_030120_dream_20") == ""


def test_the_author_suffix_is_dropped_so_one_book_is_one_group():
    assert consol.clean_title("Snow_Crash_By_Neal_Stephenson") == "Snow Crash"
    assert consol.clean_title("Neuromancer_by_William_Gibson") == "Neuromancer"


def test_clipped_titles_fold_into_their_full_spelling():
    """The engine truncates the source stem to 30 characters and a dream about a
    dream spends 22 of those on the parent's timestamp, so one book arrives
    under three keys. A clipped title is a *prefix* of the full one, which makes
    this exact rather than fuzzy."""
    m = consol.canonicalise(["Snow Cra", "Snow Crash", "Neuromancer", "Hagakure"])
    assert m["Snow Cra"] == "Snow Crash"
    assert m["Snow Crash"] == "Snow Crash"
    assert m["Neuromancer"] == "Neuromancer"
    assert m["Hagakure"] == "Hagakure"


def test_canonicalise_does_not_merge_unrelated_titles():
    m = consol.canonicalise(["Neuromancer", "Snow Crash", "Dune"])
    assert m["Dune"] == "Dune" and m["Snow Crash"] == "Snow Crash"


# ── Output hygiene ───────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected_tail", [
    ("a digital echo of something lost. lik...", "something lost."),
    ("it feels too. deliberate. Like…", "deliberate."),
])
def test_a_generation_cut_off_by_the_token_cap_is_trimmed(text, expected_tail):
    assert consol._trim_dangling(text).endswith(expected_tail)


@pytest.mark.parametrize("text", [
    "this one ends properly.",
    "i'm tired of the performative. just… tired.",
    "she uses ellipses… constantly… and that is fine.",
])
def test_her_own_cadence_survives(text):
    """`narration.finish_cleanly` reads a trailing ellipsis as a clean ending and
    leaves one behind when it gives up, which is how a merge produced
    "a digital echo of something lost. lik...". She also writes "just… tired."
    on purpose, so the ellipsis cannot simply be treated as a truncation mark."""
    assert consol._trim_dangling(text) == text


def test_model_preamble_and_headings_are_stripped():
    out = consol.strip_preamble(
        "Okay, here's a consolidated reflection.\n\n## Thoughts\n\nit stopped being a joke.\n\n"
        "Let me know if you'd like me to expand on this.")
    assert "Okay" not in out and "##" not in out and "Let me know" not in out
    assert "it stopped being a joke." in out


# ── The one that would destroy the corpus ────────────────────────────

def test_a_second_run_extends_the_document_instead_of_replacing_it(tmp_path, monkeypatch):
    """After the first pass archives its sources, a week of new dreams leaves a
    handful in the folder. Writing the group from those alone would overwrite a
    document synthesised from 229 reflections with one built from seven — and
    weekly automation would do it every week.
    """
    monkeypatch.setattr(consol, "OUT", tmp_path / "consolidated")
    key, subject = "people/Starkind", "Starkind"

    entries = [("2026-04-01", tmp_path / "a.md", "the first pass.")] * 229
    consol.write_document(key, subject, entries, "what she had arrived at.")

    path, prior, prior_n, prior_span = consol.existing_body(key, subject)
    assert prior_n == 229
    assert "what she had arrived at." in prior
    assert "# Starkind" not in prior, "heading leaked into the text fed back to the model"
    assert prior_span == "2026-04-01 to 2026-04-01"

    # A week later: seven new reflections.
    new = [("2026-09-19", tmp_path / "b.md", "a new one.")] * 7
    consol.write_document(key, subject, new, "extended.", prior_n, prior_span)
    _, _, after_n, after_span = consol.existing_body(key, subject)
    assert after_n == 236, "the count must be cumulative, not this run's total"
    assert after_span == "2026-04-01 to 2026-09-19", "the earlier start must survive"


# ── The merge that drifted ───────────────────────────────────────────

@pytest.mark.parametrize("text,reason", [
    ("**1. Key Themes:**\n\n* loss of optimism\n* pragmatism vs idealism\n* guilt",
     "bullet"),
    ("the narrator's initial idealism is being actively eroded by experience.",
     "third person"),
])
def test_an_essay_shaped_merge_is_caught(text, reason):
    """Asked to merge twelve passages about Starkind, the model produced
    "**1. Key Themes & Recurring Ideas:**" and bullets analysing "the narrator"
    — a literary essay about Kaia rather than Kaia thinking. 35 bullet lines
    went into the knowledge base labelled as her settled view of a friend."""
    assert consol.reads_as_essay(text), reason


@pytest.mark.parametrize("text", [
    "i keep coming back to it. it's not about androids, not really.",
    "the user's casual cruelty, the way systems are treated as disposable.",
    "it's a list of one - not a list.",
])
def test_her_own_prose_is_not_mistaken_for_an_essay(text):
    """"the user" is hers and stays: "the user's casual cruelty, the way systems
    are treated as disposable" is from the Do Androids Dream reflection this
    check exists to protect, and an earlier version of the rule rejected it."""
    assert consol.reads_as_essay(text) == ""



# ── The two tools must not eat each other ────────────────────────────

def test_triage_leaves_the_consolidated_documents_alone():
    """`consolidated/` is triage's *output*, not its input.

    Those documents carry `document_type: Consolidated Dream Reflection` and no
    `## Kaia's Reflection` heading, so `classify()` read all 46 of them as
    residue. The weekly curation task runs `triage_dreams --apply` *before*
    consolidation, so it would have quarantined the previous week's entire
    output every week — unattended, while logging a successful triage.
    """
    doomed = [str(f) for f, cls, _ in triage.scan() if cls != "reflection"]
    consolidated = [d for d in doomed if "consolidated" in d]
    assert not consolidated, (
        f"triage would quarantine {len(consolidated)} consolidated document(s)")


def test_the_weekly_task_triages_before_it_consolidates():
    """The ordering is what makes the bug above destructive rather than merely
    wrong, so it is worth pinning: if triage ever runs *after* consolidation
    without the exclusion, the same thing happens."""
    import inspect
    from utils.core.background_tasks import CoreTaskManager

    src = inspect.getsource(CoreTaskManager._make_dream_curation_task)
    assert src.index("triage_dreams.py") < src.index("consolidate_dreams.py")
