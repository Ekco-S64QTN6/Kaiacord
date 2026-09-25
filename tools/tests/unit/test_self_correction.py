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
