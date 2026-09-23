"""A short in-memory history of RAG retrievals, for `!explain N`.

`KaiaRAG` keeps exactly one retrieval per channel — `_last_retrieval_results` —
so the turn worth investigating is gone the moment anyone says anything else.
By the time an answer looks wrong and someone types `!explain`, it is reporting
the sources for whatever was asked after it.

This is deliberately in memory and deliberately small. Retrieval traces quote
corpus text and user queries, so writing them to disk would put user content in
a second place that nobody prunes; a restart clearing the trace is the correct
trade.

`!explain 3` reads the third-most-recent entry. `!explain` with no argument
still reads the live cache, which is richer.
"""
from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Dict, List

#: Roughly an evening of conversation. Each entry holds trimmed heads, not whole
#: documents, so the whole buffer is a few tens of kilobytes.
MAX_TRACES = 25

#: How much of a node's text is kept. Enough to recognise the passage, not
#: enough to be a copy of it.
HEAD_CHARS = 160

_traces: deque = deque(maxlen=MAX_TRACES)
_lock = threading.Lock()


def _source_of(metadata: Dict[str, Any]) -> str:
    """A readable source label — the path relative to knowledge_base if possible."""
    path = metadata.get("file_path") or ""
    if not path:
        return "unknown"
    parts = os.path.normpath(path).split(os.sep)
    if "knowledge_base" in parts:
        rel = parts[parts.index("knowledge_base") + 1:]
        if rel:
            return "/".join(rel)
    return os.path.basename(path)


def _head(content: Any) -> str:
    """The opening of a node's text, after any frontmatter block.

    For most files the first HEAD_CHARS are nothing but `summary:` and
    `keywords:`, which identifies no passage at all.
    """
    text = str(content or "").lstrip()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    return " ".join(text.split())[:HEAD_CHARS]


def record(query: str, confidence: float, nodes: List[Dict[str, Any]]) -> None:
    """Append one retrieval to the trace. Never raises."""
    try:
        entry = {
            "ts": time.time(),
            "query": str(query or "")[:300],
            "confidence": round(float(confidence or 0.0), 3),
            "n": len(nodes or []),
            "nodes": [
                {
                    "score": float(node.get("score", 0.0) or 0.0),
                    "source": _source_of(node.get("metadata") or {}),
                    "category": (node.get("metadata") or {}).get("source_type", "unknown"),
                    "method": (node.get("metadata") or {}).get("retrieval_method", ""),
                    "head": _head(node.get("content", "")),
                }
                for node in (nodes or [])[:8]
            ],
        }
    except Exception:
        return
    with _lock:
        _traces.appendleft(entry)


def recent(count: int = 1) -> List[Dict[str, Any]]:
    """The `count` most recent retrievals, newest first."""
    with _lock:
        return list(_traces)[:max(0, int(count))]


def clear() -> None:
    """Drop the trace. Used by tests; there is no operational reason to call it."""
    with _lock:
        _traces.clear()
