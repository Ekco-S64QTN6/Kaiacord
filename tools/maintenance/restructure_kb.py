#!/usr/bin/env python3
"""One-off: flatten the knowledge_base top level from sixteen folders to twelve,
merging the pairs that were two names for one thing.

The moves:

    documents/tech_updates  ->  news/tech_updates
    corrupt_files           ->  _quarantine/corrupt_files
    quarantine/*            ->  _quarantine/*
    snapshots               ->  runtime/snapshots
    system_logs             ->  runtime/system_logs
    deep_dive_reports/*.md  ->  documents/
    blogs/*.md              ->  documents/

`_quarantine` takes the leading underscore that means "never indexed".
`runtime` does not, because snapshots *are* indexed (`source_type: snapshot`).

    python tools/maintenance/restructure_kb.py            # dry run
    python tools/maintenance/restructure_kb.py --apply

Dry run by default (CLAUDE.md §10). Uses git mv where the path is tracked so
history follows the file, and plain moves otherwise — most of the corpus is
git-ignored. Re-index afterwards.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

KB = Path("knowledge_base")

# (source, destination, mode). "tree" moves the directory itself; "contents"
# moves the files out of it and removes the empty directory.
MOVES = [
    (KB / "documents" / "tech_updates", KB / "news" / "tech_updates", "tree"),
    (KB / "corrupt_files", KB / "_quarantine" / "corrupt_files", "tree"),
    (KB / "quarantine", KB / "_quarantine", "contents"),
    (KB / "snapshots", KB / "runtime" / "snapshots", "tree"),
    (KB / "system_logs", KB / "runtime" / "system_logs", "tree"),
    (KB / "deep_dive_reports", KB / "documents", "contents"),
    (KB / "blogs", KB / "documents", "contents"),
]


def tracked(path: Path) -> bool:
    try:
        out = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)],
                             capture_output=True, text=True)
        return out.returncode == 0
    except Exception:                                   # noqa: BLE001
        return False


def move(src: Path, dst: Path, dry: bool) -> str:
    """Move one file, preferring git mv so tracked history follows it."""
    if dst.exists():
        # Never silently overwrite. A collision means two folders held a file
        # of the same name and the operator has to decide which survives.
        return f"COLLISION {src} -> {dst} (skipped)"
    if dry:
        return f"would move {src} -> {dst}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if tracked(src):
        r = subprocess.run(["git", "mv", str(src), str(dst)], capture_output=True, text=True)
        if r.returncode == 0:
            return f"git mv {src} -> {dst}"
    shutil.move(str(src), str(dst))
    return f"moved {src} -> {dst}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="perform the moves")
    args = ap.parse_args()
    dry = not args.apply

    if not KB.exists():
        print(f"{KB} not found. Run from the project root.")
        return 1

    print(f"Restructuring {KB}{'  (DRY RUN)' if dry else ''}\n")
    collisions = moved = 0

    for src, dst, mode in MOVES:
        if not src.exists():
            print(f"  skip   {src}  (not present)")
            continue

        if mode == "tree":
            if dst.exists():
                print(f"  MERGE  {src} -> {dst}  (destination exists; moving contents)")
                mode = "contents"
            else:
                line = move(src, dst, dry)
                print(f"  {line}")
                if line.startswith("COLLISION"):
                    collisions += 1
                else:
                    moved += 1
                continue

        files = sorted(p for p in src.rglob("*") if p.is_file())
        if not files:
            print(f"  empty  {src}  ({'would be' if dry else ''} removed)")
            if not dry:
                shutil.rmtree(src, ignore_errors=True)
            continue

        for f in files:
            rel = f.relative_to(src)
            line = move(f, dst / rel, dry)
            if line.startswith("COLLISION"):
                collisions += 1
                print(f"  {line}")
            else:
                moved += 1
        print(f"  {'would move' if dry else 'moved'} {len(files)} file(s) "
              f"from {src} -> {dst}")
        if not dry:
            shutil.rmtree(src, ignore_errors=True)

    print(f"\n{moved} file(s)/tree(s) {'would move' if dry else 'moved'}"
          + (f", {collisions} collision(s) skipped" if collisions else ""))
    if dry:
        print("Re-run with --apply.")
    else:
        print("Now re-index: venv/bin/python3 tools/maintenance/reindex_rag.py --clear")
    return 2 if collisions else 0


if __name__ == "__main__":
    raise SystemExit(main())
