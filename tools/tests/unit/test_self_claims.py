"""A self-model whose claims move with what she actually says."""
from utils.core import self_claims as sc

TURNS = ["honestly, i don't know the answer to that one and i'd rather not guess.",
         "yeah that's wrong. the patch landed in 2019, not 2021, check the changelog.",
         "sure, whatever you think is best, you're probably right about all of it."]


def test_seeded_claims_need_a_real_quote():
    reply = {"claims": [{"claim": "I admit when I don't know", "quote": "i don't know the answer to that one"},
                        {"claim": "I am endlessly patient", "quote": "i am endlessly patient"}]}
    claims = sc.apply_seed(reply, TURNS, 1.0)
    assert [c["claim"] for c in claims] == ["i admit when i don't know"]


def test_a_claim_goes_down_when_her_words_go_against_it():
    claims = [{"claim": "i hold my ground on facts", "confidence": 0.6, "evidence": []}]
    events = sc.apply_review(claims, [0], {"results": [{"i": 0, "supports": [],
        "contradicts": ["whatever you think is best, you're probably right"]}]}, TURNS, 2.0)
    assert claims[0]["confidence"] == 0.48 and events[0]["type"] == "self_claim_weakened"
    # An invented quote moves nothing.
    sc.apply_review(claims, [0], {"results": [{"i": 0, "contradicts": ["i always cave instantly"]}]}, TURNS, 3.0)
    assert claims[0]["confidence"] == 0.48


def test_the_self_model_is_shown_only_when_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "STORE", str(tmp_path / "self.json"))
    sc.save([{"claim": "i admit when i don't know", "confidence": 0.7}])
    assert "i admit when i don't know (0.7)" in sc.note("kaia, what are you like when you're stuck?")
    assert sc.note("what's the weather like") == ""
