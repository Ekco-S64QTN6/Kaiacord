#!/usr/bin/env python3
"""Ask the RAG index a question and show what retrieval returns.

    venv/bin/python3 tools/diagnostics/ask_index.py "who wrote Neuromancer?"
    venv/bin/python3 tools/diagnostics/ask_index.py --news "what happened with the outage"
    venv/bin/python3 tools/diagnostics/ask_index.py --top 10 --show 300 "pixel the robot cat"

Runs the same `KaiaRAG.retrieve` a chat turn does, against a copy of
memory/rag_storage: a failed load of the live store is treated as corruption
and deleted, so nothing here opens it directly while the bot may be writing.
Embeds the query through Ollama on the CPU; nothing is written anywhere.
"""
import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("KAIACORD_LOG_FILE", os.path.join(tempfile.gettempdir(), "kaiacord.ask_index.log"))


async def ask(query: str, top: int, news: bool, show: int) -> int:
    from utils.core.kaia_rag import KaiaRAG

    live = ROOT / "memory" / "rag_storage"
    if not (live / "file_manifest.json").exists():
        print(f"No index at {live}", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="kaia_index_") as tmp:
        snapshot = Path(tmp) / "rag_storage"
        shutil.copytree(live, snapshot)
        rag = KaiaRAG(persist_dir=str(snapshot))
        await rag.initialize_async()
        # Classified the way a chat turn is, so routing matches what she does.
        from utils.core.intent_classifier import IntentParser
        from utils.core.message_processor import MessageProcessor
        intent = IntentParser().fast_parse(query)
        category = MessageProcessor._derive_legacy_category(None, intent) if intent else "general"
        print(f"intent: {intent.suggested_strategy if intent else 'none'} ({category})")
        results = await rag.retrieve(query, top_k=top, include_news=news,
                                     category=category, intent=intent)

    if not results:
        print("Nothing retrieved.")
        return 0
    for i, r in enumerate(results, 1):
        meta = r.get("metadata") or {}
        where = meta.get("file_path") or meta.get("file_name") or "?"
        print(f"{i:>2}. {r.get('score', 0):.3f}  {r.get('label', '')}  "
              f"[{meta.get('retrieval_method', '?')}]\n    {where}")
        if show:
            text = " ".join((r.get("content") or "").split())
            print(f"    {text[:show]}{'…' if len(text) > show else ''}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("query")
    ap.add_argument("--top", type=int, default=8, help="results to request (default 8)")
    ap.add_argument("--news", action="store_true", help="include news briefs, as a news turn does")
    ap.add_argument("--show", type=int, default=160, help="characters of each hit to print (0 hides)")
    args = ap.parse_args()
    return asyncio.run(ask(args.query, args.top, args.news, args.show))


if __name__ == "__main__":
    sys.exit(main())
