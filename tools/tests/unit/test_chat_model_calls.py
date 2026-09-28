"""Every call to the chat model keeps the loaded runner as it is.

Ollama keeps one runner per model. A request whose runner options (num_ctx,
num_gpu, num_thread, main_gpu) differ reloads it, and a request without
`keep_alive` resets its expiry to the server default of five minutes — this
server sets no OLLAMA_KEEP_ALIVE — so the model unloads soon after any
maintenance tool touches it and the next chat turn pays a cold load. Dream
consolidation did the first at 05:00 each morning (a reload at 4,096 context,
then another back to 32,768 on the next message).
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCANNED = ("utils", "tools", "finetune")


def _model_calls():
    for root in SCANNED:
        for path in (ROOT / root).rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if rel.startswith("tools/tests/") or "/llama.cpp/" in rel:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                # asyncio.to_thread(client.chat, model=..., ...) passes the method.
                if (isinstance(func, ast.Attribute) and func.attr == "to_thread" and node.args
                        and isinstance(node.args[0], ast.Attribute)):
                    func = node.args[0]
                if not (isinstance(func, ast.Attribute) and func.attr in ("chat", "generate")):
                    continue
                kw = {k.arg: k.value for k in node.keywords if k.arg}
                if "model" not in kw or "embed" in ast.unparse(kw["model"]).lower():
                    continue
                yield f"{rel}:{node.lineno}", kw


def test_every_chat_model_call_sets_keep_alive():
    missing = [where for where, kw in _model_calls() if "keep_alive" not in kw]
    assert not missing, f"no keep_alive (resets the model's expiry to 5 min): {missing}"


def test_every_chat_model_call_sends_runner_options():
    """No options at all means no num_ctx: served at Ollama's default context."""
    missing = [where for where, kw in _model_calls() if "options" not in kw]
    assert not missing, f"no options (reloads at the default context): {missing}"


def test_no_chat_model_call_builds_its_runner_options_by_hand():
    """A literal dict with no ** spread cannot carry the shared runner options."""
    bad = []
    for where, kw in _model_calls():
        opts = kw.get("options")
        if isinstance(opts, ast.Dict) and None not in opts.keys:
            bad.append(where)
    assert not bad, f"use chat_options(...) for: {bad}"


def _raw_payloads():
    """Request bodies posted to Ollama's HTTP API directly: a dict literal with
    a "model" key and "messages" or "prompt". The method-call scan above cannot
    see these; jspace_probe and the nightly enrich_metadata both sent them, one
    at three different num_ctx and a five-minute keep_alive, one with none."""
    for root in SCANNED:
        for path in (ROOT / root).rglob("*.py"):
            rel = str(path.relative_to(ROOT))
            if rel.startswith("tools/tests/") or "/llama.cpp/" in rel:
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.Dict):
                    continue
                keys = {k.value for k in node.keys if isinstance(k, ast.Constant)}
                if "model" in keys and keys & {"messages", "prompt"}:
                    yield f"{rel}:{node.lineno}", keys, node


# Deliberately bare: it samples the fine-tuned model under its own Modelfile
# (SYSTEM prompt and num_ctx), which is the point of the check, and that model
# is not the bot's runner.
RAW_EXEMPT = {"finetune/05b_test_ollama.py"}


def test_every_raw_ollama_request_sets_keep_alive_and_options():
    bad = [where for where, keys, _ in _raw_payloads()
           if not {"keep_alive", "options"} <= keys and where.split(":")[0] not in RAW_EXEMPT]
    assert not bad, f"raw Ollama request without keep_alive/options: {bad}"


def test_no_raw_ollama_request_builds_its_runner_options_by_hand():
    """jspace_probe sent {"temperature": .., "num_ctx": 2048}: keys present,
    values its own, and gemma3 reloaded at each size."""
    bad = []
    for where, _, node in _raw_payloads():
        for k, v in zip(node.keys, node.values):
            if (isinstance(k, ast.Constant) and k.value == "options"
                    and isinstance(v, ast.Dict) and None not in v.keys):
                bad.append(where)
    assert not bad, f"use chat_options(...) for: {bad}"

