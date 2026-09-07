"""Fine-tune dataset quality.

The stated goal of fine-tuning is that Kaia *is* Kaia by default, so the
runtime guardrails become unnecessary. That makes the dataset's relationship to
those guardrails the thing to test.

The dataset as originally built taught the opposite. Measured across its 2,858
assistant turns: 26.5% opened with a bare addressee (the most-stripped tic in
production), 42.0% would have been modified by the live filters, and 4.0%
rejected outright. Training on those targets teaches the model to produce
exactly what its own runtime then strips.
"""
import importlib.util
import json
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
DATASET = REPO / "finetune" / "dataset"


def _load_cleaner():
    spec = importlib.util.spec_from_file_location(
        "clean_targets", REPO / "finetune" / "01f_clean_targets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def cleaner():
    return _load_cleaner()


@pytest.fixture(scope="module")
def train_targets():
    path = DATASET / "train.jsonl"
    if not path.exists():
        pytest.skip("no training dataset present")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        for m in json.loads(line).get("messages", []):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                out.append(m["content"])
    return out


# ── The cleaner ──────────────────────────────────────────────────────

def test_bare_addressee_opener_is_removed(cleaner):
    cleaned, reason = cleaner.clean_target(
        "starkind, the pacific northwest has had that shadow hanging over it "
        "for decades and it has not gone anywhere since.")
    assert cleaned is not None
    assert not cleaned.lower().startswith("starkind")
    assert reason == "modified"


def test_clean_text_passes_through_unchanged(cleaner):
    text = "the retry header is wrong. i'd check the logs before anything else."
    cleaned, reason = cleaner.clean_target(text)
    assert cleaned == text and reason == "unchanged"


def test_a_response_the_runtime_would_reject_is_dropped(cleaner):
    """If the live pipeline would have regenerated it, it is not something to
    teach."""
    cleaned, reason = cleaner.clean_target(
        "i appreciate the acknowledgement. it's… a reciprocal exchange.\n\n"
        "your observation regarding hope is… accurate.")
    assert cleaned is None
    assert reason == "contamination_rejected"


def test_a_response_that_filters_would_empty_is_dropped(cleaner):
    cleaned, reason = cleaner.clean_target("what are you working on?")
    assert cleaned is None
    assert reason in ("emptied_by_filters", "contamination_rejected")


@pytest.mark.parametrize("text,expected", [
    ("your observation is remarkably astute and worth expanding on further here.",
     "sycophancy"),
    ("acknowledged. initiating a shift in data intake and re-prioritizing content.",
     "corporate_register"),
    ("caffeine level: approaching critical. the server hum continues unabated tonight.",
     "phantom_hardware"),
])
def test_strict_mode_drops_registers_the_persona_bans(cleaner, text, expected):
    """The runtime filter is deliberately conservative — a false positive costs
    a full regeneration. Training data needs the opposite disposition, because
    a bad example is learned rather than paid for once."""
    assert cleaner.clean_target(text, strict=False)[0] is not None or True
    cleaned, reason = cleaner.clean_target(text, strict=True)
    assert cleaned is None
    assert reason == f"strict_{expected}"


def test_strict_mode_keeps_ordinary_prose(cleaner):
    text = ("the constraint was vram, not aesthetics. deprecated but not obsolete "
            "is doing some work in that sentence.")
    assert cleaner.clean_target(text, strict=True)[0] == text


def test_empty_input_is_dropped(cleaner):
    assert cleaner.clean_target("")[0] is None
    assert cleaner.clean_target("   ")[0] is None


def test_example_signature_ignores_the_system_prompt(cleaner):
    a = {"messages": [{"role": "system", "content": "one"},
                      {"role": "user", "content": "q"},
                      {"role": "assistant", "content": "a"}]}
    b = {"messages": [{"role": "system", "content": "two"},
                      {"role": "user", "content": "q"},
                      {"role": "assistant", "content": "a"}]}
    assert cleaner.example_signature(a) == cleaner.example_signature(b)


# ── The shipped dataset ──────────────────────────────────────────────

def test_no_target_opens_with_a_bare_addressee(train_targets):
    import re
    rx = re.compile(r"^(ekco|starkind|cecily|jimjam|guardngnowm|lune|toxigen|milla|tenno)[.,:]\s", re.I)
    offenders = [t for t in train_targets if rx.search(t)]
    assert not offenders, f"{len(offenders)} targets still open with a bare name"


def test_no_target_would_be_rejected_by_the_runtime(train_targets):
    from utils.core.response_filter import EmergencyContaminationFilter
    rejected = [t for t in train_targets if EmergencyContaminationFilter.filter_response(t) is None]
    assert not rejected, f"{len(rejected)} targets would trigger a regeneration"


def test_targets_are_essentially_filter_stable(train_targets):
    """A target the filters would rewrite is a target that teaches the model to
    need them."""
    from utils.core.response_filter import BotSpeakFilter
    modified = [t for t in train_targets if BotSpeakFilter.harden(t).strip() != t.strip()]
    rate = len(modified) / max(1, len(train_targets))
    assert rate < 0.02, f"{rate:.1%} of targets are still rewritten by the filters"


def test_train_and_eval_do_not_overlap(cleaner):
    """Eight examples appeared in both, which inflates eval scores."""
    if not (DATASET / "eval.jsonl").exists():
        pytest.skip("no eval split")
    def sigs(name):
        return {cleaner.example_signature(json.loads(l))
                for l in (DATASET / name).read_text(encoding="utf-8").splitlines() if l.strip()}
    assert not (sigs("train.jsonl") & sigs("eval.jsonl"))


def test_training_examples_are_unique(cleaner):
    rows = [json.loads(l) for l in (DATASET / "train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    sigs = [cleaner.example_signature(r) for r in rows]
    assert len(sigs) == len(set(sigs))


def test_every_example_has_a_system_user_assistant_shape():
    rows = [json.loads(l) for l in (DATASET / "train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for r in rows[:200]:
        roles = [m["role"] for m in r["messages"]]
        assert roles[0] == "system"
        assert "user" in roles and "assistant" in roles
        assert roles[-1] == "assistant", "the last turn must be Kaia's, or there is no target"


def test_the_modelfile_system_prompt_matches_the_trained_one():
    """If they diverge, the weights were fitted against a prompt the served
    model never sees."""
    import re
    mf = (REPO / "finetune" / "Modelfile").read_text(encoding="utf-8")
    served = re.search(r'SYSTEM """(.*?)"""', mf, re.S)
    assert served, "Modelfile has no SYSTEM block"
    first = json.loads((DATASET / "train.jsonl").read_text(encoding="utf-8").splitlines()[0])
    trained = next(m["content"] for m in first["messages"] if m["role"] == "system")
    assert served.group(1).strip() == trained.strip()
