

def test_an_unasked_for_piece_gets_something_to_be_about(monkeypatch, tmp_path):
    """With only a mood word, every unprompted piece was titled "jitter"."""
    import json, time
    from collections import deque
    from utils.core import kaia_art_intent as K
    from utils.infrastructure.system.bot_state import bot_state
    mono = tmp_path / "monologue_log.jsonl"
    mono.write_text(json.dumps({"epoch": time.time(), "thought": "i keep thinking about cecily's jar"}) + "\n")
    monkeypatch.setattr("utils.infrastructure.monitoring.telemetry_paths.telemetry_path",
                        lambda p: str(mono) if "monologue" in p else str(tmp_path / "x"))
    monkeypatch.setitem(bot_state.channel_memory, 777, deque([
        {"role": "user", "content": "ekco: katamari damacy is the best video game ever"}]))
    seen = {K.inspiration(777) for _ in range(40)}
    assert any("katamari damacy" in s for s in seen) and any("cecily's jar" in s for s in seen)
    prompt = K._menu_prompt("", {"valence": 0.6, "arousal": 0.9, "energy": 0.9}, False,
                            'a thought you had recently: "x"', [{"title": "jitter"}, {"title": "static"}])
    assert 'on your mind — a thought you had recently: "x"' in prompt
    assert '"jitter", "static"' in prompt and "so is its title" in prompt
    assert "on your mind" not in K._menu_prompt("a lighthouse", {"valence": 0, "arousal": 0.5, "energy": 0.5},
                                                False, "", [])


def test_recent_art_reads_her_pieces_from_the_growth_log(monkeypatch, tmp_path):
    import json
    from utils.core import kaia_art_intent as K
    log = tmp_path / "growth_log.jsonl"
    log.write_text("\n".join(json.dumps(r) for r in [
        [],  # valid JSON, but not a growth-ledger event object
        {"type": "creation", "kind": "art", "title": "jitter", "summary": "[i made a piece called \"jitter\".]"},
        {"type": "creation", "kind": "music", "title": "a set"},
        {"type": "creation", "kind": "art", "title": "beacon", "summary": "[i made a piece called \"beacon\".]"},
    ]) + "\n")
    monkeypatch.setattr("utils.infrastructure.monitoring.telemetry_paths.telemetry_path", lambda p: str(log))
    assert [r["title"] for r in K.recent_art()] == ["jitter", "beacon"]


def test_the_commentary_is_shown_the_piece():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from PIL import Image
    from utils.commands import art_handler as A
    ctx = MagicMock()
    ctx.ollama_client.chat = AsyncMock(return_value={"message": {"content": "embers building cages."}})
    out = asyncio.run(A._comment(ctx, "look at it", Image.new("RGB", (2000, 1500), (200, 80, 0))))
    assert out == "embers building cages."
    user = ctx.ollama_client.chat.call_args.kwargs["messages"][1]
    assert user["images"] and isinstance(user["images"][0], str)
    import base64, io
    shown = Image.open(io.BytesIO(base64.b64decode(user["images"][0])))
    assert max(shown.size) == 896



def test_decide_offloads_art_history_reads_from_the_event_loop(monkeypatch):
    import asyncio
    import threading
    from types import SimpleNamespace
    from utils.core import kaia_art_intent as K

    loop_thread = threading.get_ident()
    worker_threads = []
    seen = {}

    def read_monologue_tail():
        worker_threads.append(threading.get_ident())
        return ["a thought about a lighthouse"]

    def read_recent_art():
        worker_threads.append(threading.get_ident())
        return [{"title": "earlier light"}]

    async def ask(_ctx, _prompt, _mood, _image, about, before):
        seen["about"] = about
        seen["before"] = before
        return None

    monkeypatch.setattr(K, "_recent_monologue_thoughts", read_monologue_tail)
    monkeypatch.setattr(K, "recent_art", read_recent_art)
    monkeypatch.setattr(K, "_ask", ask)

    intent = asyncio.run(K.decide(
        "",
        ctx=SimpleNamespace(ollama_client=object()),
        channel_id=987654321,
    ))

    assert len(worker_threads) == 2
    assert all(thread_id != loop_thread for thread_id in worker_threads)
    assert "a thought about a lighthouse" in seen["about"]
    assert seen["before"] == [{"title": "earlier light"}]
    assert intent.about == seen["about"]
