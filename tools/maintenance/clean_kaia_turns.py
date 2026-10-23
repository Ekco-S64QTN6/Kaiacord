#!/usr/bin/env python3
"""Run today's reply filters over what Kaia already said, where she reads it back.

Her logged turns are retrieved into later prompts and her recent turns are
shown as history, so a tic that shipped teaches the next reply. From 7 Oct the
"(speaking exclusively to …)" note copied out of the prompt and the name-less
grading opener ("a quiet affirmation. a measured assessment.") spread that way.
This applies the same filters the bot now applies before sending —
`repair_cut_ellipsis`, `strip_address_tag`, `strip_repeated_lines` (against her previous six turns in
the same conversation), `strip_grading_opener` and `reflow_paragraphs` (short
lines joined back into paragraphs, no word changed) — to:

  - Kaia's turns in knowledge_base/user_logs/<person>/interactions_*.md
    (people only; forum histories are other people's posts)
  - her turns in memory/bot_state.json's channel memory
  - her own posts in memory/agent_boards/state.json
  - memory/anchors.json: global anchors about an unnamed person
  - memory/beliefs.json: "beliefs" that report a source's view
  - memory/relationships/*.json: dream insights that diagnose a person

A person's turns are never touched: the rewrite is refused for a file if any
non-Kaia turn would differ. Dry run by default; --apply writes, after copying
every file it changes to memory/backups/kaia_turns_<stamp>/. Refuses to write
while the bot is running (it holds bot_state.json and appends to today's logs);
stop it first. Then reindex the logs (`reindex_rag.py`) so retrieval serves the
cleaned turns.

    venv/bin/python3 tools/maintenance/clean_kaia_turns.py            # what would change
    venv/bin/python3 tools/maintenance/clean_kaia_turns.py --show 20  # and twenty of the changes
    venv/bin/python3 tools/maintenance/clean_kaia_turns.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TURN = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\] ([^:\n]{1,60}): ?", re.MULTILINE)
WINDOW = 6


def bot_running() -> bool:
    out = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    return any(re.search(r"(?:^|/)python[0-9.]*\s+(?:\S*/)?Kaiacord\.py\b", ln) for ln in out.splitlines())


def clean(text: str, previous: list) -> str:
    from utils.core.response_filter import EmergencyContaminationFilter as E
    from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    out = E.repair_cut_ellipsis(P.strip_address_tag(text))
    out = P.strip_repeated_lines(out, previous, window=WINDOW)
    out = P.strip_grading_opener(out)
    out = P.reflow_paragraphs(out)
    out = P.collapse_litany(out)
    return out if out.strip() else text


def split_turns(raw: str) -> tuple:
    """(preamble, [(who, header, body)]) where header + body is the turn exactly."""
    marks = list(TURN.finditer(raw))
    if not marks:
        return raw, []
    turns = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        turns.append((m.group(2).strip(), raw[m.start():m.end()], raw[m.end():end]))
    return raw[:marks[0].start()], turns


def clean_log(raw: str, previous: list) -> tuple:
    """(new text, changed turns [(before, after)]), carrying `previous` (her
    recent turns, as she said them) across the files of one conversation."""
    pre, turns = split_turns(raw)
    out, changes = [pre], []
    for who, head, body in turns:
        if who.lower() != "kaia":
            out.append(head + body)
            continue
        text = body.strip()
        new = clean(text, previous)
        previous.append(text)
        del previous[:-WINDOW]
        if new != text:
            tail = body[len(body.rstrip()):]
            out.append(head + new + (tail or "\n"))
            changes.append((text, new))
        else:
            out.append(head + body)
    return "".join(out), changes


def others_unchanged(old: str, new: str) -> bool:
    a = [(w, h + b) for w, h, b in split_turns(old)[1] if w.lower() != "kaia"]
    b = [(w, h + b_) for w, h, b_ in split_turns(new)[1] if w.lower() != "kaia"]
    return a == b and split_turns(old)[0] == split_turns(new)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--show", type=int, default=0, help="print this many changed turns")
    args = ap.parse_args()
    if args.apply and bot_running():
        print("the bot is running: it holds bot_state.json and appends to today's logs. Stop it first.",
              file=sys.stderr)
        return 2
    from utils.core.atomic_write import write_atomic
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = ROOT / "memory" / "backups" / f"kaia_turns_{stamp}"
    shown, totals = 0, {"files": 0, "turns": 0}

    def keep(path: Path):
        if args.apply:
            dest = backup / path.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)

    def show(where, changes):
        nonlocal shown
        for before, after in changes:
            if shown >= args.show:
                return
            shown += 1
            print(f"\n── {where}\n  before: {before[:300]!r}\n  after:  {after[:300]!r}")

    logs = ROOT / "knowledge_base" / "user_logs"
    for person in sorted(p for p in logs.iterdir() if p.is_dir() and not p.name.startswith(("forum_", ".", "_"))):
        previous: list = []
        for f in sorted(person.glob("interactions_*.md")):
            raw = f.read_text(encoding="utf-8")
            new, changes = clean_log(raw, previous)
            if not changes:
                continue
            if not others_unchanged(raw, new):
                print(f"REFUSED {f.relative_to(ROOT)}: a turn that is not hers would change", file=sys.stderr)
                continue
            totals["files"] += 1
            totals["turns"] += len(changes)
            show(f.relative_to(ROOT), changes)
            if args.apply:
                keep(f)
                write_atomic(f, new)

    state = ROOT / "memory" / "bot_state.json"
    if state.exists():
        s = json.loads(state.read_text(encoding="utf-8"))
        n = 0
        for ch, rows in (s.get("channel_memory") or {}).items():
            previous = []
            for t in rows:
                if isinstance(t, dict) and t.get("role") == "assistant" and not t.get("event"):
                    text = str(t.get("content", ""))
                    new = clean(text, previous)
                    previous.append(text)
                    if new != text:
                        show(f"channel memory {ch}", [(text, new)])
                        t["content"] = new
                        n += 1
        if n:
            totals["turns"] += n
            totals["files"] += 1
            if args.apply:
                keep(state)
                write_atomic(state, json.dumps(s, indent=2))

    boards = ROOT / "memory" / "agent_boards" / "state.json"
    if boards.exists():
        s = json.loads(boards.read_text(encoding="utf-8"))
        n = 0

        def walk(node):
            nonlocal n
            if isinstance(node, dict):
                if node.get("mine") is True and isinstance(node.get("text"), str):
                    new = clean(node["text"], [])
                    if new != node["text"]:
                        show("agent boards", [(node["text"], new)])
                        node["text"] = new
                        n += 1
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for v in node:
                    walk(v)
        walk(s)
        if n:
            totals["turns"] += n
            totals["files"] += 1
            if args.apply:
                keep(boards)
                write_atomic(boards, json.dumps(s, ensure_ascii=False, indent=2))

    # Her self-model and identity stream are injected whole; the old ellipsis
    # fallback left "guardngnowm is. persistent" and "a certain. respect" in them.
    from utils.core.response_filter import EmergencyContaminationFilter as E
    for doc in (ROOT / "memory" / "kaia_self_model.md", ROOT / "memory" / "identity_stream.md"):
        if doc.exists():
            raw = doc.read_text(encoding="utf-8")
            new = E.repair_cut_ellipsis(raw)
            if new != raw:
                show(doc.relative_to(ROOT), [(raw[:300], new[:300])])
                totals["turns"] += 1
                totals["files"] += 1
                if args.apply:
                    keep(doc)
                    write_atomic(doc, new)

    # Memory the dream engine wrote under rules since tightened: a global anchor
    # about an unnamed "he", and a "belief" that is a source's view.
    from utils.core.kaia_dream import DreamEngine
    anchors = ROOT / "memory" / "anchors.json"
    if anchors.exists():
        rows = json.loads(anchors.read_text(encoding="utf-8"))
        keep_rows = [a for a in rows if a.get("user_id") or not DreamEngine.UNNAMED_PERSON.search(a.get("anchor_text", ""))]
        if len(keep_rows) != len(rows):
            for a in rows:
                if a not in keep_rows and shown < args.show:
                    shown += 1
                    print(f"\n── anchor dropped: {a.get('anchor_text', '')[:200]!r}")
            totals["turns"] += len(rows) - len(keep_rows)
            totals["files"] += 1
            if args.apply:
                keep(anchors)
                write_atomic(anchors, json.dumps(keep_rows, indent=2))
    beliefs = ROOT / "memory" / "beliefs.json"
    if beliefs.exists():
        rows = json.loads(beliefs.read_text(encoding="utf-8"))
        keep_rows = [b for b in rows if not DreamEngine.REPORTED_VIEW.match(b.get("position", ""))]
        if len(keep_rows) != len(rows):
            for b in rows:
                if b not in keep_rows and shown < args.show:
                    shown += 1
                    print(f"\n── belief dropped: {b.get('topic')}: {b.get('position', '')[:200]!r}")
            totals["turns"] += len(rows) - len(keep_rows)
            totals["files"] += 1
            if args.apply:
                keep(beliefs)
                write_atomic(beliefs, json.dumps(keep_rows, indent=2))

    # Dream "insights" that diagnose a person: an analyst's file, not hers.
    # (Third-person ones are kept: many are fair, only in the wrong voice.)
    for rel in sorted((ROOT / "memory" / "relationships").glob("*.json")):
        if rel.name.endswith(".impression.json"):
            continue
        try:
            data = json.loads(rel.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        events = data if isinstance(data, list) else data.get("events", [])
        drop = [e for e in events if isinstance(e, dict) and e.get("event_type") == "insight"
                and DreamEngine.DIAGNOSIS.search(e.get("summary", ""))]
        if not drop:
            continue
        for e in drop:
            if shown < args.show:
                shown += 1
                print(f"\n── insight dropped ({rel.name}): {e.get('summary', '')[:200]!r}")
        kept = [e for e in events if e not in drop]
        out = kept if isinstance(data, list) else {**data, "events": kept}
        totals["turns"] += len(drop)
        totals["files"] += 1
        if args.apply:
            keep(rel)
            write_atomic(rel, json.dumps(out, indent=2))

    verb = "cleaned" if args.apply else "would clean"
    print(f"\n{verb} {totals['turns']} of her turns in {totals['files']} files"
          + (f"; originals in {backup.relative_to(ROOT)}" if args.apply and totals["files"] else "")
          + ("" if args.apply else " (dry run: --apply to write)"))
    if args.apply and totals["files"]:
        print("next: venv/bin/python3 tools/maintenance/reindex_rag.py (with the bot stopped) so retrieval serves them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
