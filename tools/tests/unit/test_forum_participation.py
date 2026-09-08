"""Forum participation policy — when Kaia posts, and to what.

Posting on a public forum is different from replying in Discord: the people
there did not ask to hear from her. The operator's requirement is that regulars
do not conclude they are being spammed by a bot, which makes three things
testable — timing, frequency, and whether the thread was worth answering.

The previous implementation posted every two hours around the clock, chose
uniformly at random from the top eight threads, and kept its rate limit in a
list on the client object that every restart cleared.
"""
import json
import time

import pytest

from utils.social.forum_participation import (
    PostLedger,
    PostingWindow,
    load_interest_terms,
    rank_threads,
    score_thread,
)


# ── When ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hour,inside", [
    (0, True), (1, True), (3, True),
    (4, False), (12, False), (18, False), (23, False),
])
def test_window_wraps_midnight(hour, inside):
    """The operator asked for after-midnight posting, so start > end."""
    from datetime import datetime
    assert PostingWindow(0, 4).contains(datetime(2026, 9, 7, hour)) is inside


@pytest.mark.parametrize("hour,inside", [(9, True), (17, False), (2, False)])
def test_a_daytime_window_still_works(hour, inside):
    from datetime import datetime
    assert PostingWindow(8, 17).contains(datetime(2026, 9, 7, hour)) is inside


def test_equal_hours_means_always_on():
    from datetime import datetime
    w = PostingWindow(0, 0)
    assert all(w.contains(datetime(2026, 9, 7, h)) for h in range(24))


# ── How often ────────────────────────────────────────────────────────

@pytest.fixture
def ledger(tmp_path):
    return PostLedger(path=tmp_path / "ledger.json")


def test_a_fresh_ledger_permits_posting(ledger):
    assert ledger.may_post(max_per_day=2, min_hours_between=4)[0] is True


def test_minimum_interval_is_enforced(ledger):
    ledger.record(1, "t")
    allowed, why = ledger.may_post(max_per_day=2, min_hours_between=4)
    assert allowed is False and "minimum" in why


def test_daily_cap_is_enforced(ledger):
    for tid in (1, 2):
        ledger.record(tid, "t")
        ledger.posts[-1]["ts"] -= 5 * 3600
    allowed, why = ledger.may_post(max_per_day=2, min_hours_between=4)
    assert allowed is False and "daily cap" in why


def test_the_cap_survives_a_restart(ledger, tmp_path):
    """The old rate limit lived in memory on the client, so every restart reset
    the daily cap — which is how a burst of posts happens."""
    for tid in (1, 2):
        ledger.record(tid, "t")
        ledger.posts[-1]["ts"] -= 5 * 3600
    ledger.save()
    reopened = PostLedger(path=ledger.path)
    assert reopened.may_post(max_per_day=2, min_hours_between=4)[0] is False


def test_posts_outside_the_window_do_not_count_against_today(ledger):
    ledger.record(1, "old")
    ledger.posts[-1]["ts"] -= 30 * 3600          # yesterday
    assert ledger.posts_since(24) == []
    assert ledger.may_post(max_per_day=1, min_hours_between=4)[0] is True


def test_thread_cooldown_prevents_repeat_replies(ledger):
    """Replying repeatedly in one thread is the clearest bot tell. The old
    filter only skipped threads where she was the *last* poster."""
    ledger.record(4242, "a thread")
    assert ledger.thread_is_cool(4242, cooldown_hours=72) is False
    assert ledger.thread_is_cool(9999, cooldown_hours=72) is True


def test_thread_cooldown_expires(ledger):
    ledger.record(4242, "a thread")
    ledger.posts[-1]["ts"] -= 100 * 3600
    assert ledger.thread_is_cool(4242, cooldown_hours=72) is True


def test_a_corrupt_ledger_does_not_crash(tmp_path):
    bad = tmp_path / "ledger.json"
    bad.write_text("{not json", encoding="utf-8")
    assert PostLedger(path=bad).may_post(max_per_day=2, min_hours_between=4)[0] is True


def test_ledger_writes_are_atomic(ledger):
    ledger.record(1, "t")
    assert ledger.path.exists()
    assert not ledger.path.with_suffix(".tmp").exists()
    json.loads(ledger.path.read_text(encoding="utf-8"))


# ── What ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def interest():
    terms = load_interest_terms()
    if not terms:
        pytest.skip("no belief/anchor store to build interests from")
    return terms


def test_interests_come_from_her_own_memory(interest):
    """Not a hand-written keyword list — her interests drift as she does."""
    assert 200 < len(interest) < 5000, f"{len(interest)} terms"
    assert all(isinstance(v, float) for v in interest.values())


def test_curated_labels_outweigh_incidental_words(interest):
    """An earlier version read the persona prose too and reached 2,411 terms,
    at which point "else", "making" and "think" were interest signals and every
    thread cleared the threshold."""
    for generic in ("else", "making", "think", "really", "thing"):
        assert generic not in interest, f"{generic!r} should carry no signal"


def test_a_substantive_thread_outscores_small_talk(interest):
    substantive, _ = score_thread(
        "Anyone else think AI is making the internet worse?",
        "generated slop everywhere, search is useless, the open web is being replaced "
        "by walled gardens and ad farms, platform capture is basically complete",
        interest, reply_count=8)
    smalltalk, _ = score_thread(
        "What's everyone drinking tonight?",
        "Bourbon. Cheers all. Been a long week honestly, glad it is finally over now.",
        interest, reply_count=4)
    assert substantive > smalltalk


def test_a_huge_thread_is_penalised(interest):
    kwargs = dict(title="Is privacy dead?",
                  recent_text="data brokers, surveillance advertising, platform lock-in, "
                              "does anyone have meaningful control over their information",
                  interest=interest)
    small, _ = score_thread(**kwargs, reply_count=6)
    huge, _ = score_thread(**kwargs, reply_count=3400)
    assert huge < small, "a 3,400-reply megathread does not need another voice"


def test_an_empty_thread_is_penalised(interest):
    thin, _ = score_thread("privacy", "ok", interest)
    full, _ = score_thread("privacy", "a genuine discussion of data brokers and "
                           "surveillance advertising and what control actually means "
                           "in practice for ordinary people online today", interest)
    assert full > thin


def test_the_reason_is_always_explicable(interest):
    """The choice has to be defensible to the operator reviewing the draft. A
    random pick cannot be explained to anyone."""
    _score, reason = score_thread("Is privacy dead?", "data brokers and platforms",
                                  interest, reply_count=5)
    assert reason and reason != "no particular signal"


class _T:
    def __init__(self, tid, title, replies=5):
        self.thread_id, self.title, self.reply_count = tid, title, replies


def test_ranking_drops_everything_below_the_threshold(interest):
    threads = [_T(1, "What's everyone drinking tonight?"),
               _T(2, "post your desk setup")]
    ranked = rank_threads(threads, interest, lambda t: "short", minimum=2.0)
    assert ranked == [], "if nothing is interesting, a person posts nothing"


def test_ranking_returns_the_best_first(interest):
    threads = [_T(1, "What's everyone drinking tonight?"),
               _T(2, "Is privacy dead?"),
               _T(3, "post your desk setup")]
    texts = {2: "data brokers, surveillance advertising and platform lock-in, does "
                "anyone actually have meaningful control over their information"}
    ranked = rank_threads(threads, interest, lambda t: texts.get(t.thread_id, "short"),
                          minimum=0.0)
    assert ranked[0][2].thread_id == 2


# ── The prompt ───────────────────────────────────────────────────────



# ── Lurking ──────────────────────────────────────────────────────────

def test_lurking_counts_only_the_forum_she_posts_in(tmp_path, monkeypatch):
    """A first version counted recursively and scored 4,516/15 — the offline
    import of the *technical* forum, which says nothing about whether she has
    been reading Off Topic, where she actually posts."""
    from utils.social import forum_participation as fp
    posts, users = tmp_path / "forum_posts", tmp_path / "user_logs"
    (posts / "technical").mkdir(parents=True)
    for i in range(50):
        (posts / "technical" / f"thread_{i}_x.md").write_text("x", encoding="utf-8")
    users.mkdir()
    monkeypatch.setattr(fp, "FORUM_POSTS_DIR", posts)
    monkeypatch.setattr(fp, "FORUM_USER_LOGS_DIR", users)
    ready, detail = fp.lurk_progress(min_threads=15, min_users=25)
    assert ready is False and detail.startswith("0/15 threads")


def test_lurking_clears_once_she_has_read_enough(tmp_path, monkeypatch):
    from utils.social import forum_participation as fp
    posts, users = tmp_path / "forum_posts", tmp_path / "user_logs"
    posts.mkdir()
    users.mkdir()
    for i in range(15):
        (posts / f"thread_{i}_x.md").write_text("x", encoding="utf-8")
    for i in range(25):
        d = users / f"forum_user{i}_{i}"
        d.mkdir()
        (d / "post_history.md").write_text("posts", encoding="utf-8")
    (users / "Starkind_519557167779676160").mkdir()   # a Discord user, not a forum one
    monkeypatch.setattr(fp, "FORUM_POSTS_DIR", posts)
    monkeypatch.setattr(fp, "FORUM_USER_LOGS_DIR", users)
    assert fp.lurk_progress(min_threads=15, min_users=25)[0] is True


def test_lurking_survives_a_missing_corpus(tmp_path, monkeypatch):
    from utils.social import forum_participation as fp
    monkeypatch.setattr(fp, "FORUM_POSTS_DIR", tmp_path / "nope")
    monkeypatch.setattr(fp, "FORUM_USER_LOGS_DIR", tmp_path / "nope")
    assert fp.lurk_progress()[0] is False


# ── Configuration ────────────────────────────────────────────────────

def test_technical_posting_stays_off_when_the_forum_is_on():
    """The operator turned the forum back on for Off Topic specifically. The
    technical flow answered strangers' questions without staying inside the
    wiki and tech docs it was meant to be grounded in, and it shared a single
    switch with Off Topic — so enabling one silently enabled both."""
    import yaml
    with open("config/default_config.yaml", encoding="utf-8") as fh:
        forum = yaml.safe_load(fh)["forum"]
    assert forum["enabled"] is True
    assert forum["auto_scrape"] is True, "posting depends on having read the forum"
    assert forum["tech_support_enabled"] is False
    assert forum["auto_reply"] is False


def test_posting_budget_is_modest():
    import yaml
    with open("config/default_config.yaml", encoding="utf-8") as fh:
        forum = yaml.safe_load(fh)["forum"]
    assert forum["max_posts_per_day"] <= 3, "a couple a night, not a feed"
    assert forum["min_hours_between_posts"] >= 3
    assert forum["thread_cooldown_hours"] >= 24
    assert forum["post_window_start_hour"] == 0 and forum["post_window_end_hour"] == 4


def test_status_survives_a_recorded_post(tmp_path, monkeypatch):
    """`!forum status` is consulted precisely when she has been posting. An
    earlier version called max() straight on the ledger's dicts, so it worked
    while the ledger was empty and raised TypeError from the first post on."""
    from utils.social import forum_participation as fp
    from utils.social.kaia_forum import ForumClient

    ledger = PostLedger(path=tmp_path / "ledger.json")
    ledger.record(1234, "a thread")
    monkeypatch.setattr(fp, "LEDGER_PATH", ledger.path)

    client = ForumClient.__new__(ForumClient)
    client._logged_in, client.base_url, client.forum_id = True, "https://x", 19
    status = client.get_status()

    assert status["posts_today"] == 1
    assert status["last_post"] != "never"
    assert "T" in status["last_post"], "should be an ISO timestamp"


# ── Interjecting vs. conversing ──────────────────────────────────────
#
# The caps exist to stop her walking into strangers' threads too often. They
# were never meant to govern answering someone who answered her — she is not
# capped in Discord either, and going quiet for three days after a reply is
# rude rather than restrained.

from utils.social.forum_participation import INITIATION, REPLY, looks_repetitive  # noqa: E402


def test_only_openers_count_against_the_daily_cap(ledger):
    for tid in (1, 2):
        ledger.record(tid, "t", kind=REPLY)
        ledger.posts[-1]["ts"] -= 5 * 3600
    assert ledger.may_post(max_per_day=2, min_hours_between=4)[0] is True, \
        "replies should not consume the budget for openers"


def test_openers_still_count(ledger):
    for tid in (1, 2):
        ledger.record(tid, "t", kind=INITIATION)
        ledger.posts[-1]["ts"] -= 5 * 3600
    assert ledger.may_post(max_per_day=2, min_hours_between=4)[0] is False


def test_spacing_only_looks_at_openers(ledger):
    ledger.record(1, "opener", kind=INITIATION)
    ledger.posts[-1]["ts"] -= 5 * 3600
    ledger.record(1, "a reply", kind=REPLY)          # just now
    assert ledger.may_post(max_per_day=2, min_hours_between=4)[0] is True


def test_replying_is_allowed_in_a_thread_on_opener_cooldown(ledger):
    """The 72h cooldown governs interjecting. If someone in that thread has
    since said something to her, staying silent for three days is the wrong
    behaviour, not the safe one."""
    ledger.record(4242, "t", kind=INITIATION)
    assert ledger.thread_is_cool(4242, cooldown_hours=72) is False
    ledger.posts[-1]["ts"] -= 3600
    assert ledger.may_reply(4242, newest_post_id="p9")[0] is True


def test_a_reply_waits_a_few_minutes(ledger):
    ledger.record(4242, "t", kind=REPLY, last_seen_post_id="p1")
    allowed, why = ledger.may_reply(4242, newest_post_id="p2", min_minutes_between=20)
    assert allowed is False and "minimum" in why


def test_she_will_not_post_twice_into_the_same_silence(ledger):
    """The one path to the runaway behaviour the caps exist to prevent, and the
    one that matters most if she ever ends up replying to another bot."""
    ledger.record(4242, "t", kind=REPLY, last_seen_post_id="p7")
    ledger.posts[-1]["ts"] -= 3600
    allowed, why = ledger.may_reply(4242, newest_post_id="p7")
    assert allowed is False and "nothing new" in why

    allowed, _ = ledger.may_reply(4242, newest_post_id="p8")
    assert allowed is True, "someone said something new; she should answer"


def test_a_thread_she_has_never_touched_is_open(ledger):
    assert ledger.may_reply(999, newest_post_id="p1")[0] is True


def test_the_watch_list_is_where_she_has_spoken(ledger):
    """It used to be `forum.allowed_threads`, maintained by hand — so someone
    could reply to her and get nothing back."""
    ledger.record(11, "one", kind=INITIATION)
    ledger.record(22, "two", kind=REPLY)
    ledger.record(11, "one again", kind=REPLY)
    ledger.record(33, "old", kind=INITIATION)
    ledger.posts[-1]["ts"] -= 40 * 24 * 3600

    watch = ledger.threads_posted_in(within_hours=14 * 24)
    assert set(watch) == {11, 22}, "stale threads drop off the watch list"
    assert len(watch) == len(set(watch)), "each thread appears once"


# ── Repetition ───────────────────────────────────────────────────────

def test_a_repeated_opening_is_caught():
    """Her forum posts sit permanently side by side on a profile page, where a
    template opening is far more visible than in a scrolling chat. In Discord
    the same blind spot showed up as a bare-name opener on 22.4% of turns."""
    prior = ["honestly the whole thing is just enshittification with extra steps",
             "vanilla servers are fine, the client is the problem"]
    repetitive, why = looks_repetitive("honestly the whole thing is a mess", prior)
    assert repetitive is True and "opens like" in why


def test_saying_the_same_thing_again_is_caught():
    prior = ["data brokers sell everything and nobody reads the consent dialog anyway"]
    repetitive, _ = looks_repetitive(
        "nobody reads the consent dialog, data brokers sell everything anyway", prior)
    assert repetitive is True


def test_a_different_post_passes():
    prior = ["honestly the whole thing is just enshittification with extra steps"]
    assert looks_repetitive("the velious patch broke my UI mods again", prior)[0] is False


def test_nothing_to_compare_against_is_not_repetitive():
    assert looks_repetitive("anything at all here", [])[0] is False
    assert looks_repetitive("", ["something"])[0] is False


# ── One pipeline ─────────────────────────────────────────────────────

def test_forum_drafts_go_through_the_discord_pipeline():
    """There were two implementations. The auto-reply path called
    process_external_mention — the real pipeline, with RAG and memory. The
    auto-post task hand-rolled a prompt and called ollama directly at a fixed
    temperature, which is why her forum voice drifted from her Discord voice."""
    import ast
    from pathlib import Path

    src = Path("utils/core/background_tasks.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_make_forum_auto_post_task")
    body = ast.get_source_segment(src, fn)
    assert "draft_forum_reply" in body
    assert "ollama_client.chat" not in body, "auto-post should not call the model directly"
    assert "load_persona_async" not in body, "prompt assembly belongs in the pipeline"


def test_external_mentions_get_a_stable_channel_id():
    """`hash()` on a str is salted per process, so this id — which keys channel
    memory — changed on every restart, silently discarding the conversation
    history for every external platform."""
    from pathlib import Path
    src = Path("utils/infrastructure/system/external_mention.py").read_text(encoding="utf-8")
    assert "hash(platform)" not in src
    assert "crc32" in src


def test_each_forum_thread_keeps_its_own_memory():
    from utils.infrastructure.system.external_mention import process_external_mention
    import inspect
    assert "conversation_key" in inspect.signature(process_external_mention).parameters


def test_the_thread_block_parses_the_way_the_processor_reads_it():
    """The seam between forum_drafting and message_processor. The drafting side
    writes THREAD TITLE / THREAD CONTEXT and the [REPLYING_TO] wrapper; the
    processor unwraps both with regexes. Nothing else checks they agree."""
    import re
    from utils.social.forum_drafting import format_thread_context

    posts = [{"post_number": 1, "author": "Bregan", "content": "search is useless now"},
             {"post_number": 2, "author": "Nilbog", "content": "it's all AI slop farms"}]
    block = format_thread_context("Is the web cooked?", posts)

    title_m = re.search(r"THREAD TITLE:\s*(.*?)(?:\n\n|\n|$)", block)
    ctx_m = re.search(r"THREAD CONTEXT:\s*(.*)", block, re.DOTALL)
    assert title_m and title_m.group(1).strip() == "Is the web cooked?"
    assert ctx_m and "Nilbog" in ctx_m.group(1)

    lines = [l.strip() for l in ctx_m.group(1).split("\n") if l.strip()]
    last = next(l for l in reversed(lines) if re.match(r"^#\d+", l))
    assert re.sub(r"^#\d+\s*", "", last) == "Nilbog: it's all AI slop farms"

    wrapped = f"[REPLYING_TO]\nit's all AI slop farms\n[USER_MESSAGE]\n{block}"
    parent = wrapped.split("[REPLYING_TO]")[1].split("[USER_MESSAGE]")[0].strip()
    assert parent == "it's all AI slop farms"
    assert wrapped.split("[USER_MESSAGE]")[-1].strip().startswith("THREAD TITLE:")


def test_a_bare_user_directory_is_not_evidence_she_read_anyone(tmp_path, monkeypatch):
    """A backfill run created 142 `forum_*` directories holding only placeholder
    profiles ("haven't formed a strong opinion yet") and the gate read 142/25
    and opened. The gate is meant to mean she has read these people."""
    from utils.social import forum_participation as fp
    posts, users = tmp_path / "forum_posts", tmp_path / "user_logs"
    posts.mkdir()
    users.mkdir()
    for i in range(20):
        (posts / f"thread_{i}_x.md").write_text("x", encoding="utf-8")
    for i in range(40):
        d = users / f"forum_stub{i}_{i}"
        d.mkdir()
        (d / "user_profile.md").write_text(
            "summary: \"Forum user from Project 1999 Off Topic.\"", encoding="utf-8")
    monkeypatch.setattr(fp, "FORUM_POSTS_DIR", posts)
    monkeypatch.setattr(fp, "FORUM_USER_LOGS_DIR", users)
    ready, detail = fp.lurk_progress(min_threads=15, min_users=25)
    assert ready is False
    assert "0/25 forum users" in detail


def test_a_placeholder_profile_does_not_start_the_deep_scrape_cooldown(tmp_path):
    """Two writers share the filename user_profile.md. The placeholder one runs
    first in a backfill, and existence-plus-mtime let it suppress the real
    scrape for every user in the run."""
    from utils.social.kaia_forum import _is_synthesised_profile

    stub = tmp_path / "stub.md"
    stub.write_text('---\nsummary: "Forum user from Project 1999 Off Topic."\n'
                    'document_type: Narrative/Log\n---\n', encoding="utf-8")
    real = tmp_path / "real.md"
    real.write_text('---\nrank: "Sage"\ntotal_posts: 4210\n'
                    'document_type: "User Personality Profile"\n---\n', encoding="utf-8")

    assert _is_synthesised_profile(stub) is False
    assert _is_synthesised_profile(real) is True
    assert _is_synthesised_profile(tmp_path / "missing.md") is False


# ── Distinctiveness ──────────────────────────────────────────────────

def test_a_word_in_every_thread_carries_little_weight(tmp_path, monkeypatch):
    """Belief keywords include ordinary words — "problem", "system", "keep",
    "sure". Matching on those scored ordinary chat as highly as the threads she
    actually has something to say about: measured against the real corpus, 86%
    of threads cleared the interest threshold, which is random selection with
    extra steps."""
    from utils.social import forum_participation as fp
    posts = tmp_path / "forum_posts"
    posts.mkdir()
    for i in range(40):
        # "system" is everywhere; "enshittification" is in one thread.
        body = "system problem keep sure " * 10
        if i == 0:
            body += " enshittification"
        (posts / f"thread_{i}_x.md").write_text(body, encoding="utf-8")

    monkeypatch.setattr(fp, "FORUM_POSTS_DIR", posts)
    monkeypatch.setattr(fp, "_idf_cache", None)
    d = fp.term_distinctiveness(refresh=True)

    assert d["system"] < 0.2, "a word in every thread narrows nothing down"
    assert d["enshittification"] > 0.8
    assert d["system"] < d["enshittification"]


def test_no_corpus_means_no_opinion_about_any_term(tmp_path, monkeypatch):
    """A fresh install must behave as it did before this was measured, not
    silently score every term at zero."""
    from utils.social import forum_participation as fp
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setattr(fp, "FORUM_POSTS_DIR", empty)
    monkeypatch.setattr(fp, "_idf_cache", None)
    assert fp.term_distinctiveness(refresh=True) == {}

    monkeypatch.setattr(fp, "_idf_cache", {})
    interest = {"privacy": 1.0}
    score, _ = fp.score_thread("privacy and data brokers", "a" * 200, interest)
    assert score > 0, "scoring must still work with no corpus to measure against"


def test_the_configured_threshold_matches_the_calibration():
    """The threshold and the scoring are calibrated together; changing one
    without the other silently reopens the valve that is meant to let her post
    nothing on a dull night."""
    import yaml
    with open("config/default_config.yaml", encoding="utf-8") as fh:
        assert yaml.safe_load(fh)["forum"]["min_interest_score"] == 3.0


# ── Posting to a Latin-1 board ───────────────────────────────────────

def test_an_em_dash_survives_the_round_trip():
    """Kaia's first real forum post read "under the hoodâ€”it always feels".

    The board serves and expects ISO-8859-1; aiohttp urlencodes form fields as
    UTF-8, so the three bytes of U+2014 were stored as three Latin-1 characters.
    Verified against the live board: it stores em dashes as &#8212;, which is
    what a browser posting to a legacy-charset form sends.
    """
    from urllib.parse import parse_qs
    from utils.social.kaia_forum import encode_form

    body = "curious what they changed under the hood—it feels like a black box"
    sent = encode_form({"message": body})

    assert b"\xe2\x80\x94" not in sent, "no raw UTF-8 bytes"
    assert b"%26%238212%3B" in sent, "em dash should go as the &#8212; entity"

    stored = parse_qs(sent.decode("ascii"), encoding="iso-8859-1")["message"][0]
    assert stored == body.replace("—", "&#8212;")
    assert "â€" not in stored, "the mojibake signature must be gone"


def test_latin1_characters_go_as_themselves_not_entities():
    """An accent is representable in the board's charset, so it needs no
    escaping — only genuinely unrepresentable characters become entities."""
    from utils.social.kaia_forum import encode_form
    assert b"caf%E9" in encode_form({"message": "café"})


def test_anything_outside_the_charset_still_gets_through():
    from utils.social.kaia_forum import encode_form
    sent = encode_form({"message": "\U0001f600 你好"}).decode("ascii")
    assert "%26%23128512%3B" in sent      # emoji
    assert "%26%2320320%3B" in sent       # CJK


def test_the_replacement_list_did_not_become_the_fix():
    """The encoding is handled by encode_form. The small replace list in
    post_reply is a style choice for a plain-text board — straight quotes, plain
    ellipses — and must not grow into a per-character encoding workaround."""
    import ast
    from pathlib import Path

    src = Path("utils/social/kaia_forum.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "post_reply")
    body = ast.get_source_segment(src, fn)
    assert body.count(".replace(") <= 6, "encoding belongs in encode_form, not here"
    assert "encode_form(post_data)" in body


def test_both_forum_posts_use_the_encoder():
    """Login posts a username too, and it has the same problem."""
    from pathlib import Path
    src = Path("utils/social/kaia_forum.py").read_text(encoding="utf-8")
    assert src.count("encode_form(") >= 3          # definition + 2 call sites
    assert "data=login_data" not in src
    assert "data=post_data," not in src


# ── Reply chains ─────────────────────────────────────────────────────
#
# On P99 a quote box is how you say who you are talking to. Her first real post
# landed in a 929-post thread as a bare "yeah, that's good to hear" with no
# visible referent, because whether to quote was a 40% coin flip and it lost.

def test_she_always_quotes_the_person_she_is_answering():
    from utils.social.forum_drafting import pick_quote_target
    posts = [{"author": "OriginalContentGuy", "content": "Sorry I'm married to the sea.", "post_id": 1},
             {"author": "Ekco", "content": "she'll come here again", "post_id": 3800296}]
    for _ in range(20):        # was a coin flip; must now be deterministic
        target = pick_quote_target(posts, "Kaia")
        assert target is not None and target["author"] == "Ekco"


def test_her_own_posts_are_never_the_quote_target():
    from utils.social.forum_drafting import pick_quote_target
    posts = [{"author": "Ekco", "content": "hello", "post_id": 1},
             {"author": "Kaia", "content": "her own last post", "post_id": 2}]
    assert pick_quote_target(posts, "Kaia")["author"] == "Ekco"
    assert pick_quote_target([posts[1]], "Kaia") is None


def test_a_quote_does_not_carry_someone_elses_quote_into_it():
    """The scrape flattens vBulletin's quote boxes into the body text. Quoting a
    post that itself quotes someone would reproduce that text inside her quote
    box, attributed to the wrong person — the Reply With Quote button strips
    exactly this."""
    from utils.social.forum_drafting import own_words
    raw = ("fine, she'll come here again, Opus 5 improved the old posting system\n"
           "Quote:\n"
           "Originally Posted by Claude\n"
           "Both are already set that way - auto_reply: false")
    assert own_words(raw) == "fine, she'll come here again, Opus 5 improved the old posting system"


def test_a_post_that_is_only_a_quote_gives_nothing_to_quote():
    """Superseded. This test previously asserted the opposite — that a
    quote-only post falls back to its whole content — and that assertion was
    the bug: it put BradZax's words inside a box attributed to Jimjam. Kept as
    a marker so the fallback is not reinstated as a "fix"."""
    from utils.social.forum_drafting import own_words
    assert own_words("Quote:\nsomething they said\nthis") == ""


def test_long_quotes_are_trimmed():
    from utils.social.forum_drafting import own_words
    out = own_words("word " * 500, limit=200)
    assert len(out) <= 204 and out.endswith("...")


def test_the_quote_block_is_valid_vbulletin_bbcode():
    from utils.social.kaia_forum import ForumClient
    c = ForumClient.__new__(ForumClient)
    assert c.format_quote("Ekco", 3800296, "hi") == "[QUOTE=Ekco;3800296]hi[/QUOTE]\n\n"


def test_a_missing_post_id_does_not_produce_broken_bbcode():
    """`[QUOTE=Ekco;None]` is not valid BBCode — vB renders it literally. The
    two-argument form is valid and only loses the jump link."""
    from utils.social.kaia_forum import ForumClient
    c = ForumClient.__new__(ForumClient)
    assert c.format_quote("Ekco", None, "hi") == "[QUOTE=Ekco]hi[/QUOTE]\n\n"
    assert "None" not in c.format_quote("Ekco", None, "hi")


def test_a_hostile_username_cannot_break_out_of_the_quote_tag():
    from utils.social.kaia_forum import ForumClient
    c = ForumClient.__new__(ForumClient)
    out = c.format_quote("bad];name", 1, "hi")
    assert out.count("[QUOTE=") == 1 and out.startswith("[QUOTE=badname;1]")


# ── Budgets at the post gate ─────────────────────────────────────────

def test_a_reply_is_not_blocked_by_the_opener_cap(tmp_path, monkeypatch):
    """`post_reply` gated every post on `may_post`, the *opener* budget. Once
    the 2/day cap was reached she would have gone silent mid-conversation —
    the exact opposite of the documented rule that answering someone who
    answered her is not capped."""
    from utils.social import forum_participation as fp
    from utils.social.kaia_forum import ForumClient
    from utils.infrastructure.system.yaml_config import config

    ledger = PostLedger(path=tmp_path / "ledger.json")
    for tid in (1, 2):                      # opener budget fully spent today
        ledger.record(tid, "t", kind=INITIATION)
        ledger.posts[-1]["ts"] -= 5 * 3600
    ledger.record(77, "a thread", kind=REPLY, last_seen_post_id="p1")
    ledger.posts[-1]["ts"] -= 3 * 3600
    ledger.save()                           # record() saved before this mutation
    monkeypatch.setattr(fp, "LEDGER_PATH", ledger.path)

    client = ForumClient.__new__(ForumClient)
    assert client._check_rate_limit(config) is False, "openers are spent"
    assert client._check_rate_limit(config, kind=REPLY, thread_id=77,
                                    newest_post_id="p2") is True


def test_a_reply_is_still_bounded(tmp_path, monkeypatch):
    from utils.social import forum_participation as fp
    from utils.social.kaia_forum import ForumClient
    from utils.infrastructure.system.yaml_config import config

    ledger = PostLedger(path=tmp_path / "ledger.json")
    ledger.record(77, "a thread", kind=REPLY, last_seen_post_id="p1")
    monkeypatch.setattr(fp, "LEDGER_PATH", ledger.path)
    client = ForumClient.__new__(ForumClient)

    assert client._check_rate_limit(config, kind=REPLY, thread_id=77,
                                    newest_post_id="p2") is False   # too soon
    ledger.posts[-1]["ts"] -= 3600
    ledger.save()
    assert client._check_rate_limit(config, kind=REPLY, thread_id=77,
                                    newest_post_id="p1") is False   # nothing new


def test_the_reply_watcher_has_a_real_pipeline():
    """It read `bot_state.ctx`, which BotState has never defined, so the
    watcher took its early return on every pass and could not have replied to
    anyone."""
    import inspect
    from pathlib import Path
    import utils.social.forum_tasks as ft

    assert hasattr(ft, "ctx")
    assert "app_ctx" in inspect.signature(ft.start_forum_tasks).parameters
    src = Path("utils/social/forum_tasks.py").read_text(encoding="utf-8")
    assert "bot_state, 'ctx'" not in src
    assert "start_forum_tasks(app_ctx)" in Path(
        "utils/social/social_tasks.py").read_text(encoding="utf-8")


def test_no_dead_reply_bookkeeping():
    """`forum_reply_times` had no readers left, and each write serialised the
    whole BotState. Checks for the write, not the word — the first version of
    this test failed on the comment explaining the removal."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("utils/social/forum_tasks.py").read_text(encoding="utf-8"))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert "forum_reply_times" not in attrs


# ── Drafting is not conversing ───────────────────────────────────────

def test_a_forum_draft_does_not_write_to_anyone_s_history():
    """Routing forum drafts through the Discord pipeline bought RAG, memory and
    the filter stack — and also its persistence, which is wrong. It wrote a
    whole forum thread into a Discord user's interaction log, created a
    directory keyed by a vBulletin id beside the real Discord user, and saved
    one person's forum post as a *different* person's open loop."""
    import inspect
    from pathlib import Path
    from utils.social.forum_drafting import draft_forum_reply
    from utils.infrastructure.system.external_mention import process_external_mention

    assert "no_persist" in inspect.signature(process_external_mention).parameters
    assert "no_persist=True" in inspect.getsource(draft_forum_reply)

    proc = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    assert 'getattr(ctx.message, "no_persist", False)' in proc
    # The guard must sit before the background logging task is created.
    guard = proc.index('getattr(ctx.message, "no_persist", False)')
    bg = proc.index("_background_logging_and_memory(ctx))")
    assert guard < bg, "the no-persist guard must precede the logging task"


def test_the_draft_flag_reaches_the_message():
    from utils.infrastructure.system.messaging import MockMessage, MockUser, MockChannel
    m = MockMessage("x", MockUser(1, "a", "a"), MockChannel(1), "vbulletin", no_persist=True)
    assert m.no_persist is True
    assert MockMessage("x", MockUser(1, "a", "a"), MockChannel(1)).no_persist is False


# ── Quoting the right person (Phase 93) ──────────────────────────────

def _post_div(html):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


VB_QUOTE_FIRST = '''
<div id="post_message_3800299">
  <div>
    <div class="smallfont">Quote:</div>
    <table><tr><td>
      <div>Originally Posted by <strong>BradZax</strong></div>
      lol im not exagurating anything<br/>
      Datacenters: 2 billion gallons a year<br/>
      You people are STUPID.
    </td></tr></table>
  </div>
  It is funny cos their nuts are so dry. Maybe they need even more water?
</div>'''


def test_the_scraper_separates_a_posters_own_words():
    """Jimjam's post was a BradZax quote box followed by one line of his own.
    Kaia quoted the whole flattened thing — BradZax's words included — inside a
    box attributed to Jimjam. Flattened text has no reliable boundary; the
    structure does, so the split happens at scrape time."""
    import asyncio
    from utils.social.kaia_forum import ForumClient

    client = ForumClient.__new__(ForumClient)
    posts = asyncio.run(client._parse_posts(_post_div(VB_QUOTE_FIRST)))
    assert len(posts) == 1
    assert posts[0].own_text == (
        "It is funny cos their nuts are so dry. Maybe they need even more water?")
    assert "BradZax" in posts[0].content, "thread context keeps the quoted material"
    assert "BradZax" not in posts[0].own_text


def test_own_words_prefers_the_structural_extraction():
    from utils.social.forum_drafting import own_words
    post = {"author": "Jimjam",
            "own_text": "It is funny cos their nuts are so dry.",
            "content": "Quote:\nOriginally Posted by\nBradZax\nlol im not exagurating\n"
                       "It is funny cos their nuts are so dry."}
    assert own_words(post) == "It is funny cos their nuts are so dry."


def test_a_quote_only_post_yields_nothing_to_quote():
    """The old fallback returned the entire content here, which is how another
    person's words ended up in the box."""
    from utils.social.forum_drafting import own_words
    assert own_words({"content": "Quote:\nOriginally Posted by\nY\ntheir words only"}) == ""


def test_own_words_still_handles_the_quote_last_shape():
    from utils.social.forum_drafting import own_words
    assert own_words({"content": "my own line\nQuote:\nOriginally Posted by\nY\ntheirs"}) \
        == "my own line"


def test_no_empty_quote_box_is_emitted():
    """If there is nothing of theirs to quote, post without a quote rather than
    with an empty box."""
    from pathlib import Path
    for f in ("utils/core/background_tasks.py", "utils/social/forum_tasks.py"):
        src = Path(f).read_text(encoding="utf-8")
        assert "and quoted:" in src, f"{f} builds a quote without checking it is non-empty"


# ── One decision per draft ───────────────────────────────────────────

def test_the_review_buttons_cannot_run_twice():
    """Posting takes seconds and the buttons stayed live throughout, because
    `disabled = True` only reaches Discord on the next message edit — which
    happened after the post. A second click posted-then-failed: the operator
    saw "FAILED TO POST" for a post that had gone through."""
    import inspect
    from utils.social.kaia_forum import ForumDraftReviewView

    for name in ("accept", "reject"):
        src = inspect.getsource(getattr(ForumDraftReviewView, name))
        assert '_handled' in src, f"{name} has no re-entry guard"

    accept = inspect.getsource(ForumDraftReviewView.accept)
    guard = accept.index("self._handled = True")
    post = accept.index("post_reply(")
    edit = accept.index("interaction.message.edit")
    assert guard < post, "the guard must precede the post"
    assert edit < post, "the disabled state must reach Discord before the slow call"


# ── A failure to generate is not a post ──────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("i'm drawing a blank on that one. hit me again?", True),
    ("that took too long. try again in a bit.", True),
    ("the data's a bit scrambled right now. ask me again later.", True),
    ("honestly the whole thing is enshittification with extra steps", False),
    ("the data centre numbers are scrambled in that article, but the point holds", False),
])
def test_generation_failures_are_recognised(text, expected):
    from utils.social.forum_drafting import is_generation_failure
    assert is_generation_failure(text) is expected


# ── Embedded video dumps ─────────────────────────────────────────────

def test_a_run_of_embedded_video_ids_becomes_a_count():
    """`[embed]xxxxxxxxxxx[/embed]` flattens to a bare 11-character id. One
    user's post_history.md held 256 of them; 694 across 44 files."""
    from utils.social.kaia_forum import collapse_video_ids
    text = "check these:\n- NynnApj2smY\n- 7yy0n3WXHng\n- Jayj1rIrVJI\n- alMyFJA__Jg\nthoughts?"
    assert collapse_video_ids(text) == "check these:\n[4 embedded videos]\nthoughts?"


def test_a_single_video_keeps_its_identity():
    from utils.social.kaia_forum import collapse_video_ids
    out = collapse_video_ids("watch:\n- NynnApj2smY\nwell?", {"NynnApj2smY": "A Title"})
    assert out == "watch:\n[video: A Title]\nwell?"
    assert collapse_video_ids("watch:\n- NynnApj2smY\nwell?") == "watch:\n[video NynnApj2smY]\nwell?"


@pytest.mark.parametrize("word", [
    "information", "engineering", "consequence", "blackburrow", "scaramouche",
    "feelsbadman", "REEEEEEEEEE",
])
def test_eleven_letter_words_are_not_mistaken_for_video_ids(word):
    """Length alone would eat real words — all of these appear in the corpus."""
    from utils.social.kaia_forum import _looks_like_video_id
    assert _looks_like_video_id(word) is False


@pytest.mark.parametrize("vid", ["NynnApj2smY", "7yy0n3WXHng", "alMyFJA__Jg", "w_U8sXbpjqs"])
def test_real_video_ids_are_detected(vid):
    from utils.social.kaia_forum import _looks_like_video_id
    assert _looks_like_video_id(vid) is True


def test_both_scrape_paths_collapse_videos():
    """The old resolver ran only in thread parsing and only matched a line that
    was *exactly* the id — the history writer emits "- <id>" list items, so
    nothing matched there at all."""
    from pathlib import Path
    src = Path("utils/social/kaia_forum.py").read_text(encoding="utf-8")
    assert "_collapse_videos(content)" in src, "thread parsing"
    assert "collapse_video_ids(block)" in src, "post-history writer"


# ── The forum guidance was steering her to one-word posts (Phase 98) ──


# ── Not regenerating the same failure forever ────────────────────────

def test_a_failed_draft_is_remembered(ledger):
    """The watcher redrafted the same thread against the same last post every
    30 minutes: 20 identical failures in 14 hours, each a 14,700-token prompt."""
    ledger.note_skip(443378, "p9")
    assert ledger.already_tried(443378, "p9") is True
    assert ledger.already_tried(443378, "p10") is False
    assert ledger.already_tried(999, "p9") is False


def test_a_skip_does_not_consume_the_posting_budget(ledger):
    """Recorded in `posts` it consumed the opener spacing and blocked real
    posts, so skips live in their own map."""
    ledger.note_skip(443378, "p9")
    assert ledger.may_post(max_per_day=2, min_hours_between=4)[0] is True
    assert ledger.may_reply(443378, "p9")[0] is True
    assert ledger.posts == []


def test_skips_survive_a_restart(ledger):
    from utils.social.forum_participation import PostLedger
    ledger.note_skip(443378, "p9")
    assert PostLedger(path=ledger.path).already_tried(443378, "p9") is True


def test_the_watcher_checks_before_generating():
    """The check has to come before the model call, or it saves nothing."""
    import inspect
    from utils.social.forum_tasks import _reply_to_replies
    src = inspect.getsource(_reply_to_replies)
    assert src.index("already_tried") < src.index("draft_forum_reply(")


# ── A short draft is retried, not silently dropped ───────────────────


# ── The forum prompt is the Discord prompt (Phase 98) ────────────────


def test_the_anti_bot_rules_still_exist_in_the_filter():
    """Removing the prompt text must not remove the behaviour it duplicated."""
    from utils.core.response_filter import BotSpeakFilter as B
    assert B.harden("ekco,") == ""                       # addressee-only
    assert "hope this helps" not in B.harden("that works. hope this helps!").lower()


# ── The forum uses the Discord pipeline, unmodified ──────────────────


def test_the_thread_actually_reaches_the_prompt():
    """`root_context` is injected only inside `if ctx.parent_context:`. Sending
    [ORIGINAL_POST] without [REPLYING_TO] meant the thread was parsed and then
    dropped, so she answered eight words with no context — Discord replies ran
    372-861 characters in the same window while forum drafts ran 26-120."""
    import inspect
    from utils.social.forum_drafting import draft_forum_reply
    src = inspect.getsource(draft_forum_reply)
    for marker in ("[ORIGINAL_POST]", "[REPLYING_TO]", "[USER_MESSAGE]"):
        assert marker in src, f"{marker} not sent"

    from pathlib import Path
    proc = Path("utils/core/message_processor.py").read_text(encoding="utf-8")
    i = proc.index("if ctx.parent_context:")
    assert "root_context" in proc[i:i + 400], "root is still gated behind parent"


def test_the_reply_target_is_what_they_were_answering():
    from utils.social.forum_drafting import own_words, _as_dict
    posts = [{"post_id": 1, "author": "BradZax", "content": "datacenters use 2bn gallons"},
             {"post_id": 2, "author": "Ekco", "content": "test test hello hello"}]
    previous = own_words(_as_dict(posts[-2]))
    assert previous == "datacenters use 2bn gallons"


def test_the_person_s_post_is_the_user_message():
    """It was inverted: the *thread* was sent as [USER_MESSAGE] and the post
    being answered as background, so the model answered the thread. A reply to
    "test test hello hello" came back about the Well-Formed Outcome Process."""
    from utils.social.forum_drafting import format_thread_context, own_words

    posts = [{"post_number": 920, "author": "BradZax", "content": "datacenters use 2bn gallons"},
             {"post_number": 921, "author": "Ekco", "content": "reply to this kaia, test test hello hello"}]
    block = format_thread_context("The absolute state of AI results.", posts)
    content = f"[ORIGINAL_POST]\n{block}\n[USER_MESSAGE]\n{own_words(posts[-1])}"

    main = content.split("[USER_MESSAGE]")[-1].strip()
    assert main == "reply to this kaia, test test hello hello"
    assert "THREAD TITLE" not in main, "the thread is background, not the message"


def test_the_drafting_call_is_a_single_unmodified_pass():
    import inspect
    from utils.social.forum_drafting import draft_forum_reply
    src = inspect.getsource(draft_forum_reply)
    assert src.count("process_external_mention(") == 1
    for added in ("for attempt in range", "too thin to post", "MIN_DRAFT_CHARS"):
        assert added not in src, f"still adding something: {added}"
