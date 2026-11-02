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
