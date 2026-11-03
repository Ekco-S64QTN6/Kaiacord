"""What she writes carries a repeat penalty; what is extracted as JSON does not."""
import ast
from pathlib import Path

from utils.infrastructure.gpu.gpu_manager import chat_options, voice_sampling


def test_the_penalty_is_on_and_a_sampling_option_only():
    sampling = voice_sampling()
    assert sampling["repeat_penalty"] > 1.0 and sampling["repeat_last_n"] == 64
    with_voice = chat_options(temperature=0.7, **sampling)
    plain = chat_options(temperature=0.7)
    for runner_option in ("num_ctx", "num_gpu", "num_thread", "main_gpu"):
        assert with_voice[runner_option] == plain[runner_option]
    assert "repeat_penalty" not in plain, "extraction and exact recall stay without it"


def _source(path):
    return Path(path).read_text(encoding="utf-8")


def test_every_path_in_her_voice_asks_for_it():
    for path in ("utils/core/message_processor.py", "utils/core/kaia_monologue.py", "utils/core/kaia_proactive.py",
                 "utils/core/background_tasks.py", "utils/core/relationship_impressions.py",
                 "utils/core/kaia_dream.py"):
        assert "voice_sampling()" in _source(path), path
    assert _source("utils/core/kaia_dream.py").count("voice_sampling()") == 4


def test_no_json_call_asks_for_it():
    """A penalty on repeated tokens would fight the JSON a call asked for."""
    for path in Path("utils").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            fmt = kw.get("format")
            if isinstance(fmt, ast.Constant) and fmt.value == "json" and "options" in kw:
                assert "voice_sampling" not in ast.dump(kw["options"]), f"{path}:{node.lineno}"


def test_a_shared_stock_image_is_found_and_a_particular_one_is_not():
    from utils.core.relationship_impressions import stock_image
    others = ["ekco is a whirlwind of intense energy", "lune is someone who appreciates logic"]
    assert stock_image("toxigen is a whirlwind of ideas", others) == "whirlwind"
    assert stock_image("cecily’s a whirlwind, really", others) == "whirlwind"
    assert stock_image("starkind is a surprisingly gentle presence", others) == ""
    assert stock_image("jimjam argues until the point is gone", others) == ""
    assert stock_image("tenno is a good person", ["ekco is a good person"]) == "", "says nothing about either"


def test_no_opener_hint_hands_her_a_sentence_to_copy():
    """Every opener opened on its hint's example, word for word: "randomly remembered that
    conversation…", "was just thinking about that thing…", "been sitting with this thought…"."""
    assert "Example tone" not in _source("utils/core/kaia_proactive.py")
    assert "'I noticed...'" not in _source("utils/core/background_tasks.py")


def test_an_absence_check_in_says_who_it_is_for_after_the_filters():
    """The reported post: "[unprompted] proactive posted as (no label): been quiet without you
    around. hope everything's alright." Runs the real opener, with the model answering."""
    import asyncio
    from unittest.mock import AsyncMock
    from utils.core.kaia_proactive import ProactiveEngine, ProactiveTrigger

    async def scenario(reply, kind="absence"):
        engine = ProactiveEngine.__new__(ProactiveEngine)
        engine._gather_cognitive_injections = lambda *a, **k: ""
        client = AsyncMock()
        client.chat.return_value = {"message": {"content": reply}}
        trigger = ProactiveTrigger(trigger_type=kind, channel_id=1, context="away a while",
                                   target_user="GuardNGnowm", source_category=kind)
        return await engine.generate_opener(trigger, client, "m", "persona", bot_state=None)

    named = asyncio.run(scenario("guardngnowm, been quiet without you around. hope everything's alright."))
    assert named.lower().startswith("guardngnowm, been quiet")
    assert "guardngnowm" in asyncio.run(scenario("been quiet without you around. hope everything's alright."))
    assert named.lower().count("guardngnowm") == 1
    other = asyncio.run(scenario("been sitting with something about old radios and why they last.", kind="belief_musing"))
    assert "guardngnowm" not in other, "only a check-in is addressed"
