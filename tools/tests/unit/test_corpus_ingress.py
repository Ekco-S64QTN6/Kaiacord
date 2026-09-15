"""Every route into knowledge_base/ has to leave retrievable metadata.

Three paths write into the corpus, and each was leaving something out:

  * Discord chat logging creates every daily file with `summary: ""` and
    `keywords: []` — it has to, the day has not happened yet — and nothing
    filled them in. 51 of 144 were still empty, in the `logs` index, which is
    where her memory of a conversation actually comes from.
  * `!youtube` derives keywords by splitting the title, so "AI Can Reproduce.
    Who Controls Its Children?" yielded Can, Who, Its.
  * `!download` went through `process_ingress`, fixed separately in 67cecbe.
"""
import inspect

import pytest

from tools.maintenance.youtube_to_kb_md import derive_keywords


def test_title_function_words_are_not_keywords():
    kws = derive_keywords("AI Can Reproduce. Who Controls Its Children?",
                          "Gabriel Torch", "body text here")
    for junk in ("Can", "Who", "Its"):
        assert junk not in kws, f"{junk!r} is still treated as a topic"


def test_real_title_terms_survive():
    """The title and channel are genuine topical signals — a name there is a
    topic, which is why they are added unconditionally."""
    kws = derive_keywords("Cory Doctorow on AI", "Novara Media", "body text")
    assert "Doctorow" in kws and "Novara" in kws


def test_sentence_openers_are_still_excluded():
    """The pre-existing guard must survive the expanded stop list."""
    body = "Yeah. Well I think so. Right. Okay. " * 6
    assert not {"Yeah", "Well", "Right", "Okay"} & set(derive_keywords("", "", body))


def test_discord_logs_get_enriched_on_a_schedule():
    """`enrich_metadata.py` is idempotent and does the right job; it simply
    never ran unless someone typed !enrich or used the tools menu."""
    from utils.core.background_tasks import CoreTaskManager

    assert hasattr(CoreTaskManager, "_make_metadata_enrichment_task")
    src = inspect.getsource(CoreTaskManager._make_metadata_enrichment_task)
    assert "enrich_metadata.py" in src
    assert "knowledge_base.auto_enrich" in src, "no way to switch it off"
    assert "auto_enrich_limit" in src, "an unbounded pass can stall the night"


def test_the_enrichment_task_is_actually_started():
    from utils.core.background_tasks import CoreTaskManager

    start = inspect.getsource(CoreTaskManager.start)
    assert "metadata_enrichment_task.start()" in start, "task defined but never started"


def test_enrichment_is_configurable():
    import yaml

    cfg = yaml.safe_load(open("config/default_config.yaml"))
    kb = cfg.get("knowledge_base", {})
    assert kb.get("auto_enrich") is True
    assert isinstance(kb.get("auto_enrich_limit"), int)
