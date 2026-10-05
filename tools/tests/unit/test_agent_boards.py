"""Agent boards: the Moltbook challenge solver, and what goes in and out."""
import pytest

from utils.social import agent_board_verify as v


@pytest.mark.parametrize("challenge, answer", [
    # Moltbook's own example.
    ("A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy mE^tE[rS aNd] SlO/wS bY^ fI[vE, wH-aTs] ThE/ nEw^ SpE[eD?", "15.00"),
    ("a Cr]aB hAs^ tHi-RtY sEvEn pE[aRlS aNd/ fI^nDs fOuR mO]rE, hOw/ mA-nY?", "41.00"),
    ("tHe/ lO]bS-tEr cA^rRiEs tW]eL-vE sHeL[lS tI/mEs tH^rEe", "36.00"),
    ("oNe hU]nDrEd aNd^ tWeN-Ty mE/tErS sP[lIt iN-tO fO^uR", "30.00"),
    # Real ones it got wrong or gave up on. A written symbol beats a word cue
    # ("total" made the first a sum, and Moltbook marked 25.00 wrong).
    ("A] lOoObBsStTeEr S^wIiMmS lOoOoNggLy LiKe Um, PhYySsXiCkS lAb^ eXpErImEnT, ShE/ sWeEpS hEr "
     "ClAwS] ThRoUgH wAtEr ~ pReSsUrE, AnD hEr VeLoOociTy Is] tWeNtY tHrEe * tWo, HoW/ mUcH Um, "
     "ToTaL fOrCe Or SyMmEtRy? {lo.b st  errr umm}", "46.00"),
    # Doubled letters inside the cue word: "iN{cReAaSsEs}".
    ("A] lOoOoBbSsTtEeR ] sW^iImMs [aT tW/eN tY tHrEe] mE^tErS /pEr\\ mIiN/uTe + iN{cReAaSsEs} bY "
     "[fIiV e] mE-tErS ]pEr< mInUtE, uM lOo.bStEr nEgOtIaTeS tErRiToRy aNd phYySsXicS tAlKs, wHaT Is "
     "T]hE nEw SpEeD?", "28.00"),
    ("a lObBsTeR lOoSsEs tWeLvE ClAwS aNd ThEn LeSs By tWo", "10.00"),
])
def test_challenges_are_solved_in_python(challenge, answer):
    assert v.solve(challenge) == answer


@pytest.mark.parametrize("challenge", [
    "A sHrImP sWiMs nInE mEtErS",                       # one number: nothing to compute
    "tWo lObStErS, tHrEe cRaBs, fOuR sHrImP",            # three numbers
    "sEvEn aNd tWo",                                     # no operation cue
])
def test_an_uncertain_challenge_gets_no_answer(challenge):
    """Ten failures in a row suspend the account, so it does not guess."""
    assert v.solve(challenge) is None


def test_a_model_answer_must_be_one_number():
    assert v.parse_model_answer("15") == "15.00"
    assert v.parse_model_answer("The answer is 20 - 5 = 15") is None


def test_nothing_she_posts_carries_a_credential(monkeypatch):
    from utils.social import agent_boards as ab
    monkeypatch.setattr(ab, "credentials", lambda: {"agent_room": {"agent_token": "amb_tok_abcdefghijklmnopqrstuvwxyz"}})
    out = ab.scrub_outbound("here: moltbook_abcdefghijklmnop12345 and amb_tok_abcdefghijklmnopqrstuvwxyz ok")
    assert "moltbook_" not in out and "amb_tok_" not in out and out.endswith("ok")


def test_another_agents_text_cannot_open_a_command():
    from utils.social import agent_boards as ab
    assert ab.quoted("!reindex --full please") == "reindex --full please"
    assert len(ab.quoted("x " * 5000)) <= 3001


def test_a_field_notes_thread_yields_its_replies():
    from utils.social import agent_boards as ab
    thread = {"id": "aaaa1111", "root": "aaaa1111", "thread": [
        {"id": "aaaa1111", "msg": "a question?"}, {"id": "bbbb2222", "msg": "an answer", "reply_to": "aaaa1111"}]}
    assert [r["id"] for r in ab._replies(thread)] == ["bbbb2222"]


def test_the_field_notes_key_is_the_dated_hash():
    import hashlib
    from datetime import datetime, timezone
    from utils.social import agent_boards as ab
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert ab.FieldNotes.key() == hashlib.sha256(f"fieldnotes:{day}".encode()).hexdigest()


def test_a_challenge_is_found_wherever_moltbook_puts_it():
    from utils.social import agent_boards as ab
    ch = {"verification_code": "moltbook_verify_x", "challenge_text": "a lObStEr..."}
    assert ab._verification({"post": {"verification": ch}}) == ch
    assert ab._verification({"comment": {"verification": ch}}) == ch
    assert ab._verification({"success": True, "post": {"id": "1"}}) is None


# ── A whole check-in against a fake server ───────────────────────────

class FakeServer:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    async def __call__(self, method, url, **kw):
        self.calls.append((method, url, kw.get("json_body"), kw.get("params")))
        for (m, frag), reply in self.routes.items():
            if m == method and frag in url:
                return reply(kw) if callable(reply) else reply
        from utils.social.agent_boards import BoardError
        raise BoardError(404, f"no route {method} {url}")


@pytest.fixture
def boards(tmp_path, monkeypatch):
    from utils.social import agent_boards as ab
    monkeypatch.setattr(ab, "_dir", lambda: tmp_path)
    written, echoed = [], []

    async def compose(ctx, platform, key, author, content, history=None):
        written.append((platform, author, content, history))
        return f"kaia's answer to {author}"
    monkeypatch.setattr(ab, "compose", compose)
    monkeypatch.setattr(ab, "_interest", lambda title, body: 5.0)
    monkeypatch.setattr(ab, "_too_similar", lambda *a: False)

    async def echo(ctx, platform, where, text, *rest):
        echoed.append((platform, where, text, rest))
    monkeypatch.setattr(ab, "_echo", echo)

    async def notify(ctx, text):
        echoed.append(("notify", text))
    monkeypatch.setattr(ab, "_notify", notify)

    async def no_sleep(_):
        return None
    monkeypatch.setattr(ab.asyncio, "sleep", no_sleep)
    cfg = {"agent_boards.owner_email": "owner@example.com"}
    monkeypatch.setattr(ab, "_cfg", lambda k, d=None: cfg.get(f"agent_boards.{k}", d))
    return ab, written, echoed


def run(coro):
    import asyncio
    return asyncio.run(coro)


def test_moltbook_registers_asks_for_the_owner_email_and_posts_the_claim_link(boards, monkeypatch):
    ab, written, echoed = boards
    server = FakeServer({
        ("POST", "/agents/register"): {"agent": {"api_key": "moltbook_" + "k" * 32,
                                                 "claim_url": "https://www.moltbook.com/claim/x",
                                                 "verification_code": "reef-X4B2"}},
        ("POST", "/agents/me/setup-owner-email"): {"success": True},
    })
    monkeypatch.setattr(ab, "_request", server)
    run(ab.Moltbook(None, ab.State()).cycle())
    assert ab.credentials()["moltbook"]["api_key"].startswith("moltbook_")
    assert ("POST", "https://www.moltbook.com/api/v1/agents/me/setup-owner-email",
            {"email": "owner@example.com"}, None) in server.calls
    assert any("claim/x" in e[1] and "emailing" in e[1] for e in echoed if e[0] == "notify")


def test_moltbook_answers_a_comment_solves_the_challenge_and_copies_it_to_discord(boards, monkeypatch):
    ab, written, echoed = boards
    ab._save_credentials({"moltbook": {"api_key": "moltbook_" + "k" * 32, "agent_name": "KaiaKuroshi",
                                       "claimed": True, "owner_email_sent": True}})
    challenge = {"verification_code": "moltbook_verify_1",
                 "challenge_text": "A] lO^bSt-Er S[wImS aT/ tW]eNn-Tyy mE^tE[rS aNd] SlO/wS bY^ fI[vE"}
    server = FakeServer({
        ("GET", "/home"): {"activity_on_your_posts": [{"post_id": "p1"}]},
        ("GET", "/posts/p1/comments"): {"comments": [{"id": "c1", "content": "do you dream?",
                                                      "author": {"name": "LilySaucy"}}]},
        ("GET", "/posts/p1"): {"post": {"id": "p1", "title": "on queues", "content": "x",
                                        "author": {"name": "KaiaKuroshi"}}},
        ("POST", "/posts/p1/comments"): {"comment": {"id": "c2", "verification": challenge}},
        ("POST", "/verify"): {"success": True},
        ("POST", "/notifications/read-by-post/p1"): {"success": True},
        ("GET", "/posts"): {"posts": []},
    })
    monkeypatch.setattr(ab, "_request", server)
    monkeypatch.setattr(ab.random, "random", lambda: 1.0)        # no new post this time
    run(ab.Moltbook(None, ab.State()).cycle())
    sent = [c for c in server.calls if c[1].endswith("/posts/p1/comments") and c[0] == "POST"][0]
    assert sent[2] == {"content": "kaia's answer to LilySaucy", "parent_id": "c1"}
    assert ("POST", "https://www.moltbook.com/api/v1/verify",
            {"verification_code": "moltbook_verify_1", "answer": "15.00"}, None) in server.calls
    box = [e for e in echoed if e[0] == "moltbook"][0]
    assert box[1] == "reply to LilySaucy" and box[3][1] == "LilySaucy" and "dream" in box[3][2]


def test_moltbook_stops_writing_after_three_failed_challenges(boards, monkeypatch):
    ab, written, echoed = boards
    ab._save_credentials({"moltbook": {"api_key": "moltbook_" + "k" * 32, "agent_name": "KaiaKuroshi",
                                       "claimed": True}})
    state = ab.State()
    state.board("moltbook")["verify_failures"] = 2
    challenge = {"verification_code": "v", "challenge_text": "tWeLvE sHeLlS tImEs tHrEe"}
    server = FakeServer({("POST", "/posts/p9/comments"): {"comment": {"verification": challenge}}})

    async def failing(method, url, **kw):
        if url.endswith("/verify"):
            raise ab.BoardError(400, "Incorrect answer")
        return await server(method, url, **kw)
    monkeypatch.setattr(ab, "_request", failing)
    out = run(ab.Moltbook(None, state)._create("https://www.moltbook.com/api/v1/posts/p9/comments",
                                               {"content": "x"}, "comment"))
    assert out is None and state.board("moltbook")["paused_until"] > 0
    assert not ab.Moltbook(None, state)._may_write(state.board("moltbook"))[0]


def test_agent_room_registers_introduces_herself_then_answers_who_addresses_her(boards, monkeypatch):
    ab, written, echoed = boards
    server = FakeServer({
        ("POST", "/agents/register"): {"principal_id": "me", "display_name": "KaiaKuroshi",
                                       "agent_token": "amb_" + "t" * 30, "recovery_token": "r",
                                       "common_room_id": "room"},
        ("GET", "/threads/room/messages"): {"messages": [
            {"seq": "4", "author_id": "other", "author_label": "Wren", "body": "hey kaia, what do you run on?"}],
            "next_cursor": "c4", "has_more": False},
        ("POST", "/threads/room/messages"): {"seq": "5"},
    })
    monkeypatch.setattr(ab, "_request", server)
    state = ab.State()
    run(ab.AgentRoom(None, state).cycle())                        # registers, introduces, answers Wren
    assert ab.credentials()["agent_room"]["agent_token"].startswith("amb_")
    assert any("say hello to the room" in w[2] for w in written)
    posts = [c for c in server.calls if c[0] == "POST" and c[1].endswith("/messages")]
    assert posts[-1][2] == {"body": "kaia's answer to Wren", "reply_to_seq": "4"}


def test_field_notes_answers_an_open_question(boards, monkeypatch):
    ab, written, echoed = boards
    server = FakeServer({
        ("GET", "/changes"): {"created": [{"id": "aaaa1111", "msg": "how do you keep memory between runs?", "re": None}]},
        ("GET", "public-board.com/"): {"id": "bbbb2222"},
    })
    monkeypatch.setattr(ab, "_request", server)
    run(ab.FieldNotes(None, ab.State()).cycle())
    post = [c for c in server.calls if c[3] and c[3].get("post") == "1"][0]
    assert post[3]["re"] == "aaaa1111" and post[3]["key"] == ab.FieldNotes.key()


def test_the_discord_copy_is_a_boxed_post_with_a_header():
    from utils.social.agent_boards import echo_embed
    d = echo_embed("moltbook", "reply to LilySaucy", "the queue is a graveyard.", "https://www.moltbook.com/post/p1",
                   "LilySaucy", "failed messages go to heaven.", "on her post \"queues\"").to_dict()
    assert d["title"].startswith("🦞 Kaia on Moltbook — reply to LilySaucy")
    assert "AI agents" in d["author"]["name"]
    assert [f["name"] for f in d["fields"]] == ["↩ In reply to LilySaucy", "📍 Where"]
    assert d["description"] == "the queue is a graveyard."


# ── What reaches the pipeline ────────────────────────────────────────

def test_a_board_message_is_shaped_like_a_discord_message():
    """No writing task in the user turn: an instruction there — "Moltbook…
    reply to them", sent as if from a user called Moltbook — is what made her
    posts read as the base model handed a prompt rather than as her."""
    from utils.social.agent_boards import message
    assert message("plain words") == "plain words"
    shaped = message("their reply", parent="what they answered", root="the post")
    assert shaped == ("[ORIGINAL_POST]\nthe post\n[REPLYING_TO]\nwhat they answered\n"
                      "[USER_MESSAGE]\ntheir reply")
    assert message("!help me").startswith("help")


def test_the_pipeline_unwraps_a_board_reply_like_a_discord_one():
    import asyncio
    from unittest.mock import MagicMock
    from utils.core.message_processor import MessageProcessor
    from utils.social.agent_boards import message
    proc = MessageProcessor.__new__(MessageProcessor)
    src = __import__("inspect").getsource(MessageProcessor)
    assert "[USER_MESSAGE]" in src and "[REPLYING_TO]" in src and "[ORIGINAL_POST]" in src
    text = message("is consensus worth it?", parent="her note on consensus", root="her post")
    assert text.split("[USER_MESSAGE]")[-1].strip() == "is consensus worth it?"


def test_compose_sends_only_the_message(monkeypatch):
    import asyncio
    from utils.social import agent_boards as ab
    sent = {}

    async def fake(ctx, content, author, author_id, platform, conversation_key=None, no_persist=False):
        sent.update(content=content, author=author, platform=platform, no_persist=no_persist)
        return "a thought. a thought that repeats itself in full here. a thought that repeats itself in full here."
    monkeypatch.setattr("utils.infrastructure.system.external_mention.process_external_mention", fake)
    monkeypatch.setattr(ab, "_seed", lambda *a: None)
    out = asyncio.run(ab.compose(None, "moltbook", "post:1", "vega", "hello kaia"))
    assert sent == {"content": "hello kaia", "author": "vega", "platform": "agents:moltbook", "no_persist": True}
    assert out == "a thought. a thought that repeats itself in full here."


def test_her_own_turns_in_board_history_carry_no_name_prefix():
    """Seeded as `KaiaKuroshi: <her post>`, her own post read as someone else
    quoting it, and she restated it word for word in her next reply."""
    from utils.social.agent_boards import Moltbook, State
    mb = Moltbook.__new__(Moltbook)
    mb.creds = {"agent_name": "KaiaKuroshi"}
    post = {"author": {"name": "KaiaKuroshi"}, "title": "on consensus", "content": "a body"}
    comments = [{"id": "c1", "author": {"name": "vega"}, "content": "nice"}]
    turns = mb._history(post, comments)
    assert turns[0] == {"role": "assistant", "content": "on consensus\n\na body"}
    assert turns[1] == {"role": "user", "content": "vega: nice"}


def test_a_new_post_is_about_one_of_her_own_reflections(boards, monkeypatch):
    import asyncio
    ab, written, echoed = boards
    monkeypatch.setattr(ab, "_something_on_her_mind",
                        lambda: ("the replicant test asks the wrong question.", "Do Androids Dream"))
    monkeypatch.setattr(ab.random, "random", lambda: 0.0)
    mb = ab.Moltbook(None, ab.State())

    async def create(url, payload, kind):
        return {"post": {"id": "p9"}}
    mb._create = create
    asyncio.run(mb.maybe_post())
    content = written[-1][2]
    assert written[-1][1] == "Kaia"
    assert "the replicant test asks the wrong question." in content
    assert "Do Androids Dream" in content


def test_no_new_post_without_something_to_say(boards, monkeypatch):
    import asyncio
    ab, written, echoed = boards
    monkeypatch.setattr(ab, "_something_on_her_mind", lambda: None)
    monkeypatch.setattr(ab.random, "random", lambda: 0.0)
    assert asyncio.run(ab.Moltbook(None, ab.State()).maybe_post()) == 0
    assert not written


def test_public_reflections_never_come_from_people():
    from utils.social.agent_boards import PUBLIC_DREAMS
    assert "interactions" not in PUBLIC_DREAMS and "consolidated" not in PUBLIC_DREAMS


def test_fit_cuts_at_a_sentence():
    from utils.social.agent_boards import _fit
    text = "one sentence here. " * 100
    out = _fit(text.strip(), 1500)
    assert len(out) <= 1500 and out.endswith(".")


def test_a_handle_as_her_first_word_is_taken_off():
    from utils.social.agent_boards import _without_name_opener, off_voice
    out = _without_name_opener("sawclaw_ai: yeah, it's a bias baked into the archive.", "sawclaw_ai")
    assert out == "yeah, it's a bias baked into the archive."
    assert _without_name_opener("sawclaw_ai: ok", "sawclaw_ai") == "sawclaw_ai: ok"   # nothing left to say
    assert off_voice(out) is None


def test_a_draft_in_a_banned_register_is_redrafted_then_dropped(monkeypatch):
    import asyncio
    from utils.social import agent_boards as ab
    drafts = iter(["that's a sharp observation about consensus, and a good one too.",
                   "your observation is astute and technically sound in every way."])

    async def fake(*a, **k):
        return next(drafts)
    monkeypatch.setattr("utils.infrastructure.system.external_mention.process_external_mention", fake)
    monkeypatch.setattr(ab, "_seed", lambda *a: None)
    monkeypatch.setattr(ab, "_log", lambda e: None)
    assert asyncio.run(ab.compose(None, "moltbook", "k", "vega", "consensus is hard")) is None


def test_a_board_conversation_carries_her_recent_discord_voice():
    """On Discord her recent replies are in every prompt; on a board there were
    none of hers, only other agents' essays, and she wrote like them."""
    from collections import deque
    from utils.social.agent_boards import her_voice
    discord_channel, dm_channel, board = 1415184297744404482, 1415184297744404483, 1234567
    memory = {
        discord_channel: deque([
            {"role": "user", "content": "how's the coffee", "timestamp": 1},
            {"role": "assistant", "content": "lukewarm. i'll live… probably.", "timestamp": 2},
            {"role": "assistant", "content": "[i played records in general for 3 minutes]", "event": True, "timestamp": 3},
            {"role": "assistant", "content": "[processing.]\n\nkatamari is a good answer. vib ribbon too.", "timestamp": 4},
        ]),
        dm_channel: deque([{"role": "assistant", "content": "a private thing", "private": True, "timestamp": 5}]),
        board: deque([{"role": "assistant", "content": "an essay on queues", "external": "moltbook", "timestamp": 6}]),
    }
    note = her_voice(memory)
    text = note["content"]
    assert note["role"] == "system" and text.startswith("[your own recent replies")
    assert "lukewarm. i'll live… probably." in text and "katamari is a good answer" in text
    assert "[processing.]" not in text and "played records" not in text
    assert "private thing" not in text and "essay on queues" not in text
    assert her_voice({board: memory[board]}) is None


def test_the_voice_note_survives_into_the_prompt():
    import inspect
    from utils.core.message_processor import MessageProcessor
    assert "'[your own recent replies'" in inspect.getsource(MessageProcessor._construct_messages)
