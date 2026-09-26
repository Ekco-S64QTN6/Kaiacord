#!/usr/bin/env python3
"""Compare book chunk sizes on real retrieval before rebuilding the index.

Every document type is split with SentenceSplitter(1024, 200). Books are long
continuous prose, and a 1024-token chunk can hold a whole scene, which dilutes
the one passage a question is about. This embeds knowledge_base/books/ at each
candidate size, asks questions whose answer is a known phrase in a known book,
and reports how often the answer lands in the top k — so the rebuild uses a
size that measured better, not one that sounds better.

Read-only: nothing under knowledge_base/ or memory/ is written. It embeds
through the local Ollama daemon; run it with the bot stopped (the GPU is
then free, and --gpu is ~9x faster than CPU).

    venv/bin/python3 tools/maintenance/compare_book_chunking.py --sizes 1024 512 384 --gpu
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

BOOKS = ROOT / "knowledge_base" / "books"

#: (question, book filename fragment, phrase the answer contains)
QUESTIONS = [
    ("what colour was the sky above the port in neuromancer", "Neuromancer", "television"),
    ("what are molly's eyes like in neuromancer", "Neuromancer", "mirrored"),
    ("who does hiro protagonist deliver pizza for", "Snow Crash", "cosa nostra"),
    ("what is snow crash, the thing hiro is offered", "Snow Crash", "virus"),
    ("what is the answer to the ultimate question of life the universe and everything", "Hitchhikers", "forty-two"),
    ("why should a hitchhiker always know where their towel is", "Hitchhikers", "towel"),
    ("what device lets people fuse with mercer", "Do Androids Dream", "empathy box"),
    ("what test tells androids from humans", "Do Androids Dream", "voigt"),
    ("what drug do the citizens of the world state take", "Brave New World", "soma"),
    ("what animal is jones in johnny mnemonic", "Johnny Mnemonic", "dolphin"),
    ("what does the way of the samurai consist of according to hagakure", "Hagakure", "death"),
    ("which fable about a map opens simulacra and simulation", "Simulacra", "borges"),
    ("what are the nanomachines that ate the earth in postsingular", "Postsingular", "nants"),
    ("who is the protagonist of deus ex", "Deus Ex", "denton"),
    ("what does kevin kelly say about the hive mind of bees", "Out of Control", "hive"),
    ("what does marcus aurelius say to tell yourself in the morning", "Meditations", "meddling"),
]


def chunk(text: str, size: int, overlap: int) -> list[str]:
    from llama_index.core.node_parser import SentenceSplitter
    return SentenceSplitter(chunk_size=size, chunk_overlap=overlap).split_text(text)


def embed(texts: list[str], gpu: bool, instruction: str) -> list[list[float]]:
    import ollama
    from utils.infrastructure.system.yaml_config import config
    client = ollama.Client()
    out = []
    for i in range(0, len(texts), 32):
        batch = [f"{instruction}{t}" for t in texts[i:i + 32]]
        r = client.embed(model=config.embedding_model, input=batch,
                         options={"num_gpu": 99 if gpu else 0, "num_ctx": config.embedding_context_tokens})
        out += r["embeddings"]
    return out


def cos(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sizes", nargs="+", type=int, default=[1024, 512])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--gpu", action="store_true", help="embed on the GPU (bot stopped)")
    args = ap.parse_args()

    from utils.infrastructure.system.yaml_config import config
    q_inst, t_inst = config.rag_query_instruction or "", config.rag_text_instruction or ""
    books = {p.name: p.read_text(encoding="utf-8", errors="replace") for p in sorted(BOOKS.glob("Book - *.md"))}
    print(f"{len(books)} books, {sum(len(t) for t in books.values()):,} characters")
    q_vecs = embed([q for q, _, _ in QUESTIONS], args.gpu, q_inst)

    results = {}
    for size in args.sizes:
        started = time.time()
        chunks = [(name, c) for name, text in books.items() for c in chunk(text, size, max(32, size // 5))]
        vecs = embed([c for _, c in chunks], args.gpu, t_inst)
        hits, right_book, ranks = 0, 0, []
        for (q, book, phrase), qv in zip(QUESTIONS, q_vecs):
            order = sorted(range(len(chunks)), key=lambda i: -cos(qv, vecs[i]))[:args.k]
            found = [n for n, i in enumerate(order)
                     if book.lower() in chunks[i][0].lower() and re.search(re.escape(phrase), chunks[i][1], re.I)]
            if found:
                hits += 1
                ranks.append(found[0] + 1)
            if any(book.lower() in chunks[i][0].lower() for i in order):
                right_book += 1
        results[size] = (hits, right_book, ranks, len(chunks), time.time() - started)
        print(f"size {size:>5}: answer in top {args.k} for {hits}/{len(QUESTIONS)} · right book "
              f"{right_book}/{len(QUESTIONS)} · mean rank {sum(ranks) / len(ranks) if ranks else 0:.1f} · "
              f"{len(chunks)} chunks · {results[size][4]:.0f}s")

    best = max(results, key=lambda s: (results[s][0], -sum(results[s][2]) / max(1, len(results[s][2]))))
    print(f"\nbest: {best}. Current setting: 1024. Only rebuild if the best beats 1024 by more than one question.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
