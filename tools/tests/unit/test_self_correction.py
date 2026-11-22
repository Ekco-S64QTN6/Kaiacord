"""She corrects a grounded claim only when its source contradicts it."""
import asyncio
import json
import time
from types import SimpleNamespace

from utils.core import self_correction as sc

PASSAGE = ("Neuromancer is a 1984 science fiction novel by William Gibson. It was the first "
           "novel to win the Nebula Award, the Philip K. Dick Award and the Hugo Award.")


def test_a_verdict_needs_a_verbatim_quote_with_a_different_fact():
    claim = "neuromancer came out in 1986 and won the hugo."
    assert sc.accept(claim, PASSAGE, {"contradicts": True, "quote": "a 1984 science fiction novel"})
    assert sc.accept(claim, PASSAGE, {"contradicts": True, "quote": "published in 1984"}) is None
    assert sc.accept(claim, PASSAGE, {"contradicts": True, "quote": "the Hugo Award"}) is None
    assert sc.accept(claim, PASSAGE, {"contradicts": False, "quote": "a 1984 science fiction novel"}) is None


def test_a_quote_that_repeats_the_claims_numbers_agrees_with_it():
    """Posted on 25 Sept as a correction; the source said the same thing."""
    passage = "so we're not planning uh big 300 megawatts, 1 gigawatt data centers anymore"
    assert sc.accept("a 1 gigawatt data center cancelled.", passage,
                     {"contradicts": True, "quote": "we're not planning uh big 300 megawatts, 1 gigawatt"}) is None


def test_only_factual_sentences_are_recorded():
    reply = "honestly it's a great read. neuromancer came out in 1986, which surprises people."
    assert sc.fact_sentences(reply) == ["neuromancer came out in 1986, which surprises people."]


def test_a_contradiction_is_recorded_and_not_posted_while_the_flag_is_off(tmp_path, monkeypatch):
    book = tmp_path / "Book - Neuromancer by William Gibson.md"
    book.write_text("# Neuromancer\n\n" + PASSAGE + "\n\nUnrelated paragraph about cats.\n")
    monkeypatch.setattr(sc, "CLAIMS", str(tmp_path / "claims.jsonl"))
    monkeypatch.setattr(sc, "CORRECTIONS", str(tmp_path / "corrections.jsonl"))
    sc.record_claim(5, "Ekco", "when was neuromancer out?",
                    "neuromancer, the science fiction novel, came out in 1986.", [str(book)])
    rows = [json.loads(l) for l in open(sc.CLAIMS)]
    for r in rows:
        r["ts"] -= 3600
    open(sc.CLAIMS, "w").write("".join(json.dumps(r) + "\n" for r in rows))

    async def chat(**kw):
        return {"message": {"content": json.dumps(
            {"contradicts": True, "quote": "a 1984 science fiction novel"})}}

    async def guard(model_name, priority, coro, task_id):
        return await coro
    from utils.infrastructure.gpu import gpu_manager
    monkeypatch.setattr(gpu_manager.gpu_memory_manager, "run_with_gpu_guard", guard)
    ctx = SimpleNamespace(config=SimpleNamespace(chat_model="m", get=lambda k, d=None: d),
                          ollama_client=SimpleNamespace(chat=chat), bot=None)
    assert asyncio.run(sc.check(ctx)) == 1
    [entry] = [json.loads(l) for l in open(sc.CORRECTIONS)]
    assert entry["verdict"] == "contradicted" and "1984" in entry["quote"]
    assert "i had that wrong" in sc.correction_text(entry)
    # Never twice on the same claim, and at most one a day.
    assert asyncio.run(sc.check(ctx)) == 0


def test_detail_or_another_subject_is_not_a_contradiction():
    """Recorded as contradictions (memory/self_corrections.jsonl, 12–13 Nov)."""
    mana = ("This article details an experiment within the AI Village, where an AI agent "
            "borrowed Ṁ5,000 in play money and lost it.")
    assert sc.accept("that story about claude opus 4.6 borrowing and losing mana.", mana,
                     {"contradicts": True, "quote": "an AI agent borrowed Ṁ5,000 in play money"}) is None
    mythos = ("Across all replications, Claude Mythos 5 performed worse than all of our other "
              "production models, including Claude Opus 5 and Claude Mythos 5.1.")
    assert sc.accept("the fact that you isolated the issue so precisely, tracing it back to a single pr—#375—is impressive.",
                     mythos, {"contradicts": True, "quote": mythos}) is None


def test_a_version_given_wrong_is_still_a_contradiction():
    passage = "Claude Opus 4.6 is a frontier model released in February."
    assert sc.accept("opus 4.8 is kind of an asshole model.", passage,
                     {"contradicts": True, "quote": "Claude Opus 4.6 is a frontier model"})
