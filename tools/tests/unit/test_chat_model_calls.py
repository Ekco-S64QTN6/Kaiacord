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
SCANNED = ("utils", "tools/maintenance")


def _model_calls():
    for root in SCANNED:
        for path in (ROOT / root).rglob("*.py"):
            rel = str(path.relative_to(ROOT))
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


def test_no_chat_model_call_builds_its_runner_options_by_hand():
    """A literal dict with no ** spread cannot carry the shared runner options."""
    bad = []
    for where, kw in _model_calls():
        opts = kw.get("options")
        if isinstance(opts, ast.Dict) and None not in opts.keys:
            bad.append(where)
    assert not bad, f"use chat_options(...) for: {bad}"
