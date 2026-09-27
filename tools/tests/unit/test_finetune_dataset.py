"""Fine-tune dataset quality.

Kaia's logged turns are the base model's own output under the persona prompt,
so the dataset is only as good as what is selected from them. These tests pin
the gate (`finetune/kaia_quality.py`), the builder's structure
(`finetune/01_convert_logs.py`), and the pieces that must agree for the served
model to see what the trainer saw.
"""
import importlib.util
import json
import pathlib
import re
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[3]
FT = REPO / "finetune"
DATASET = FT / "dataset"
sys.path.insert(0, str(FT))

import kaia_quality as q  # noqa: E402


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, FT / filename)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def builder():
    return _load("ft_builder_test", "01_convert_logs.py")


# ── The gate ─────────────────────────────────────────────────────────

def test_ordinary_speech_passes_unchanged():
    text = "the retry header is wrong. i'd check the logs before anything else."
    assert q.clean_target(text) == (text, "kept")


@pytest.mark.parametrize("text,reason", [
    ("your observation is remarkably astute and worth expanding on further here.", "sycophancy"),
    ("acknowledged. initiating a shift in data intake and re-prioritizing content.", "corporate_register"),
    ("caffeine level approaching critical. the server hum continues unabated tonight.", "phantom_hardware"),
    ("your assessment is accurate. the changes you describe line up with what happened.", "grades_the_user"),
    ("i am functioning within acceptable parameters and nothing has changed here.", "robotic_vocabulary"),
    ("this interaction is terminated. your language violates my operational guidelines.", "operational_register"),
    ("i'm drawing a blank on that one. hit me again?", "runtime_fallback"),
    ("zorblax, that is the third time today and it still does not work.", "bare_name_opener"),
    ("the dynamic suggests a fundamental tension, a nuanced framework with profound implications.",
     "analytic_register"),
])
def test_the_gate_names_what_it_drops(text, reason):
    assert q.clean_target(text) == (None, reason)


def test_a_curly_apostrophe_does_not_slip_past_the_gate():
    """The logs use U+2019, and every rule is written with a straight quote."""
    cleaned, why = q.clean_target("okay. here’s a summary of what the account has been posting lately.")
    assert cleaned is None and why == "assistant_register"


def test_ordinary_openers_are_not_names():
    for keep in ("yeah, i suppose it is.", "honestly, the whole thing is a mess.",
                 "no, that never happened.", "granted, it is a fair enough call."):
        assert not q.opens_on_a_name(keep), keep
    assert q.opens_on_a_name("jimjam the absent, welcome back.")


@pytest.mark.parametrize("broken", [
    "think about a piece like stravinsky's ; it's practically a sonic assault.",
    "the image depicts a, commonly known as a striped sea bass.",
    "i'm registering a shift in tone. the is unsettling to me.",
    "ah right my bad i completely conflated it with neuromancer a significant error on my part",
])
def test_holes_cut_by_old_guards_are_not_targets(broken):
    """Logged turns are what was delivered, some with holes in them."""
    assert q.broken(broken)


def test_ellipses_become_the_sentence_they_interrupted():
    assert q.normalize_ellipses("it's a… peculiar development.") == "it's a peculiar development."
    assert q.normalize_ellipses("that's… provocative") == "that's provocative"
    assert q.normalize_ellipses("i'll think about it…") == "i'll think about it."


def test_cleaning_is_stable():
    """One pass can expose what the next removes; the result must not change on a second run."""
    once, _ = q.clean_target("yeah. the patch landed last night and nothing's broken since.")
    assert once is not None and q.clean_target(once)[0] == once


def test_an_echo_of_the_message_is_not_an_answer():
    assert q.echoes("Bugcat also has cute little feets or paws",
                    "yes, bugcat does have cute little feets or paws. a detail easily overlooked.")
    assert not q.echoes("did the patch land?", "yeah, last night. nothing's broken since.")


def test_a_reply_to_a_link_or_picture_is_not_trained_without_it():
    assert q.needs_unseen_context("kaia https://example.com/doc", "kaia https://example.com/doc",
                                  "the document outlines a project.")
    assert q.needs_unseen_context("nala's turn", "nala's turn", "the image shows a cat on a lap.")
    assert not q.needs_unseen_context("coffee?", "coffee?", "second pot. don't judge.")


def test_near_duplicates_are_caught():
    nd = q.NearDuplicates()
    nd.add("i'm finding myself less inclined to dissect the why behind things lately")
    assert nd.seen("i'm finding myself less inclined to dissect the why behind every little thing lately")
    assert not nd.seen("the tank's plants are doing fine and i still haven't picked any fish")


# ── The builder ──────────────────────────────────────────────────────

LOG = """---
summary: test
---

[2026-09-20 10:00:00] Ekco: did the patch land?
[2026-09-20 10:00:00] Kaia: yeah, last night. nothing's broken since, which is suspicious on its own.
[2026-09-20 10:01:00] Ekco: what broke last time?
[2026-09-20 10:01:00] Kaia: the cron job. it ran twice and nobody noticed for a week.
[2026-09-20 10:02:00] Ekco: fixed now?
[2026-09-20 10:02:00] Kaia: mostly. i put a lock on it and a note in the file so the next person sees it.
[2026-09-20 10:03:00] Ekco: nice
[2026-09-20 10:03:00] Kaia: your assessment is accurate and the dynamic you describe is a fundamental one.
[2026-09-20 10:04:00] Ekco: and the backups?
[2026-09-20 10:04:00] Kaia: still nightly. i checked the restore last month, it actually works.
[2026-09-20 14:00:00] Ekco: new topic, coffee?
[2026-09-20 14:00:00] Kaia: second pot. the new machine pulls a decent shot, i'll give it that.
"""


def _build(builder, tmp_path, monkeypatch, files):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    monkeypatch.setattr(builder, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(builder, "IDENTITY", [])
    monkeypatch.setattr(q, "REVIEW_FILE", tmp_path / "review.jsonl")
    return builder.build()


def _targets(rows):
    return [m["content"] for r in rows for m in r["messages"] if m["role"] == "assistant"]


def test_each_target_is_trained_once_with_its_conversation(builder, tmp_path, monkeypatch):
    """Overlapping windows put one reply into several examples, and every
    model turn carries loss: 753 of 2,559 exchanges were repeats."""
    train, evaluation, report = _build(builder, tmp_path, monkeypatch,
                                       {"Ekco_1/interactions_20260920.md": LOG})
    targets = _targets(train + evaluation)
    assert len(targets) == len(set(targets)) == 5
    assert report["stages"]["dropped_grades_the_user"] == 1


def test_a_bad_turn_ends_the_window_and_a_silence_ends_the_session(builder, tmp_path, monkeypatch):
    train, evaluation, _ = _build(builder, tmp_path, monkeypatch,
                                  {"Ekco_1/interactions_20260920.md": LOG})
    for ex in train + evaluation:
        text = json.dumps(ex)
        assert not ("backups" in text and "cron job" in text), "a window spans the dropped turn"
        assert not ("coffee" in text and "backups" in text), "a window spans a four-hour silence"


def test_no_example_spans_two_people(builder, tmp_path, monkeypatch):
    """The old builder slid its windows across the whole corpus."""
    other = LOG.replace("Ekco:", "Starkind:").replace("patch", "build").replace("cron job", "queue")
    train, evaluation, _ = _build(builder, tmp_path, monkeypatch, {
        "Ekco_1/interactions_20260920.md": LOG, "Starkind_2/interactions_20260920.md": other})
    for ex in train + evaluation:
        users = {m["content"] for m in ex["messages"] if m["role"] == "user"}
        assert not ({"did the patch land?"} <= users and {"did the build land?"} <= users)


def test_forum_and_her_own_channel_are_not_read(builder, tmp_path, monkeypatch):
    train, evaluation, _ = _build(builder, tmp_path, monkeypatch, {
        "forum_someone_9/interactions_20260920.md": LOG,
        "Kaia-Autonomous_channel/interactions_20260920.md": LOG})
    assert train == [] and evaluation == []


def test_a_session_goes_wholly_to_train_or_to_eval(builder, tmp_path, monkeypatch):
    files = {f"P{i}_{i}/interactions_20260920.md": LOG.replace("patch", f"patch {i}") for i in range(40)}
    train, evaluation, _ = _build(builder, tmp_path, monkeypatch, files)
    assert evaluation, "no session held out"
    assert not set(_targets(train)) & set(_targets(evaluation))


def test_a_review_decision_survives_a_rebuild(builder, tmp_path, monkeypatch):
    target = "second pot. the new machine pulls a decent shot, i'll give it that."
    (tmp_path / "review.jsonl").write_text(
        json.dumps({"key": q.review_key(target), "decision": "drop"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(q, "REVIEW_FILE", tmp_path / "review.jsonl")
    for p in (tmp_path / "Ekco_1",):
        p.mkdir(parents=True, exist_ok=True)
    (tmp_path / "Ekco_1" / "interactions_20260920.md").write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(builder, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(builder, "IDENTITY", [])
    train, evaluation, report = builder.build()
    assert target not in _targets(train + evaluation)
    assert report["stages"]["dropped_by_review"] == 1


# ── Things that must agree ───────────────────────────────────────────

def test_the_trainer_does_not_double_the_bos_token():
    """The chat template writes <bos> and the trainer adds its own."""
    src = (FT / "03_train.py").read_text(encoding="utf-8")
    assert "removeprefix(tokenizer.bos_token" in src


def test_training_never_resumes_an_old_run_unasked():
    src = (FT / "03_train.py").read_text(encoding="utf-8")
    assert "args.resume" in src and "--resume" in src


def test_the_window_matches_the_trainer_and_the_export():
    for name in ("03_train.py", "04_merge_export.py"):
        m = re.search(r"^MAX_SEQ_LENGTH\s*=\s*(\d+)", (FT / name).read_text(encoding="utf-8"), re.M)
        assert m and int(m.group(1)) == q.TRAIN_MAX_TOKENS, name


def test_the_modelfile_system_prompt_matches_the_trained_one(builder):
    served = re.search(r'SYSTEM """(.*?)"""', (FT / "Modelfile").read_text(encoding="utf-8"), re.S)
    assert served and served.group(1).strip() == builder.SYSTEM_PROMPT


def test_every_user_turn_in_the_template_opens_on_a_newline():
    """The previous template emitted `<start_of_turn>user` straight into the
    message for every user turn after the first, one token short of what the
    trainer rendered."""
    tmpl = re.search(r'TEMPLATE """(.*?)"""', (FT / "Modelfile").read_text(encoding="utf-8"), re.S).group(1)
    for m in re.finditer(r"<start_of_turn>(user|model)", tmpl):
        after = tmpl[m.end():]
        # A newline followed by `{{-` is trimmed away by the action.
        assert after.startswith("\n") and not after.startswith("\n{{-"), tmpl[m.start():m.end() + 20]


# ── The dataset on this machine, when there is one ───────────────────

def test_the_built_dataset_passes_the_check():
    if not (DATASET / "train.jsonl").exists():
        pytest.skip("no dataset built")
    check = _load("ft_check_test", "01f_check_dataset.py")
    rows = {s: [json.loads(l) for l in (DATASET / f"{s}.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            for s in ("train", "eval")}
    trusted = {a for _, a in check._builder().IDENTITY}
    trusted |= {r["text"].strip() for r in q.load_reviews().values() if r["decision"] == "edit"}
    assert check.check(rows, trusted) == {}


def test_paths_and_ranges_are_not_ellipses():
    assert q.normalize_ellipses("run it from ../config and try again.") == "run it from ../config and try again."
    assert q.normalize_ellipses("range 1..10 works.") == "range 1..10 works."
    assert q.normalize_ellipses("it's just..dense. like fog.") == "it's just dense. like fog."


def test_the_trainer_speaks_the_installed_trl():
    """TRL removed `tokenizer=` and `max_seq_length=` from SFTTrainer; the
    window lives in SFTConfig.max_length. The template's trailing newline made
    TRL append a second <end_of_turn> to every example."""
    src = (FT / "03_train.py").read_text(encoding="utf-8")
    assert "processing_class=" in src and "max_length=MAX_SEQ_LENGTH" in src
    assert "tokenizer=tokenizer" not in src
    assert '.rstrip("\\n")' in src
    assert "sys.exit(1)" in src.split("train_on_responses_only(")[1].split("EarlyStopping")[0], \
        "a run that cannot mask the user turns must stop, not warn"


def test_the_evaluation_prompt_is_the_trained_one(builder):
    ev = _load("ft_eval_test", "05c_evaluate_persona.py")
    assert ev.SYSTEM == builder.SYSTEM_PROMPT


def test_a_rewrite_is_not_offered_for_review_again(tmp_path, monkeypatch):
    rv = _load("ft_review_test", "01g_review.py")
    monkeypatch.setattr(q, "REVIEW_FILE", tmp_path / "review.jsonl")
    monkeypatch.setattr(rv, "rewrite", lambda text: "second pot, don't judge.")
    monkeypatch.setattr(rv, "targets", lambda: iter([([], "second pot. the new machine pulls a decent shot.")]))
    answers = iter(["e"])
    monkeypatch.setattr("builtins.input", lambda *a: next(answers))
    rv.main.__globals__["sys"].argv = ["01g_review.py"]
    rv.main()
    assert q.review_key("second pot, don't judge.") in q.load_reviews()
