#!/usr/bin/env python3
"""Set up !art: build flam3 and fetch an Electric Sheep flock.

    venv/bin/python3 tools/maintenance/fetch_art_flock.py --build-flam3   # once
    venv/bin/python3 tools/maintenance/fetch_art_flock.py --count 300     # genomes
    venv/bin/python3 tools/maintenance/fetch_art_flock.py --gate          # preview-check the flock

flam3 (GPL) is built from Scott Draves' repository into ~/.local/bin and run
as a separate program; nothing of it enters this repository. The genomes go
to memory/art/flock/ (git-ignored). Algorithm-generated sheep are CC BY-NC 3.0
— non-commercial use with attribution, which `!art` adds to every post; see
https://electricsheep.org/license/.

Building needs git, gcc, make, autoconf/automake/libtool, libxml2, libpng and
libjpeg (all in a standard Arch install).
"""
import argparse
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

FLAM3_REPO = "https://github.com/scottdraves/flam3.git"


def build_flam3(prefix: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "flam3"
        steps = [
            ["git", "clone", "--depth", "1", FLAM3_REPO, str(src)],
            # The shipped build files want an automake that is long gone.
            ["autoreconf", "-fi"],
            ["./configure", f"--prefix={prefix}", "--enable-shared=no",
             "CFLAGS=-O3 -march=native -fcommon -std=gnu11"],
            ["make", f"-j{os.cpu_count() or 4}"],
            ["make", "install"],
        ]
        for cmd in steps:
            print("$", " ".join(cmd), flush=True)
            r = subprocess.run(cmd, cwd=src if cmd[0] != "git" else tmp,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if r.returncode:
                print(r.stderr[-2000:], file=sys.stderr)
                return r.returncode
    print(f"flam3 installed in {prefix / 'bin'}")
    return 0


def gate() -> int:
    """Preview every genome once; mark the ones that render empty or blown out."""
    from utils.core import kaia_sheep as ks
    index = ks.load_index()
    checked = rejected = 0
    for name, info in sorted(index.items()):
        if "previewed" in info:
            continue
        path = ks.FLOCK_DIR / f"{name}.flam3"
        if not path.exists():
            continue
        ok = ks._preview_ok(path.read_text())
        info["previewed"] = True
        if not ok:
            info["rejected"] = True
            rejected += 1
        checked += 1
        if checked % 25 == 0:
            ks.save_index(index)
            print(f"  {checked} checked, {rejected} rejected", flush=True)
    ks.save_index(index)
    print(f"{checked} checked, {rejected} rejected; flock usable: {len(ks.flock())}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-flam3", action="store_true", help="clone and build flam3 into --prefix")
    ap.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    ap.add_argument("--count", type=int, default=0, help="new genomes to download")
    ap.add_argument("--gate", action="store_true", help="preview-check genomes not yet checked")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    if not (args.build_flam3 or args.count or args.gate):
        ap.print_help()
        return 2
    if args.build_flam3 and (rc := build_flam3(args.prefix)):
        return rc
    from utils.core import kaia_sheep as ks
    if args.count:
        added = ks.fetch_flock(args.count, rng=random.Random(args.seed))
        print(f"added {added}; flock now {len(ks.load_index())} genomes in {ks.FLOCK_DIR}")
    if args.gate:
        gate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
