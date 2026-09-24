#!/usr/bin/env python3
"""
Fetch what Kaia's shortwave listening needs. Run once; safe to re-run.

    python tools/maintenance/fetch_radio_assets.py            # kiwiclient + speech-to-text
    python tools/maintenance/fetch_radio_assets.py --no-model # skip the ~3 GB model download

- kiwiclient (jks-prv), pinned, cloned into assets/kiwiclient/. It carries no
  top-level licence and parts of it are GPL, so it is fetched, never
  committed, and run as its own process.
- faster-whisper into this venv, and the large-v3 model into the Hugging Face
  cache. Transcription runs on the CPU: the GPU belongs to Ollama.

`!skyking` and `!numbers` need none of this — only recording, transcription
and `!radio` do.
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / "assets" / "kiwiclient"
REPO = "https://github.com/jks-prv/kiwiclient.git"
COMMIT = "4eb733e6b6147f7fbeb97ced64cdac029b202d18"     # 2026-08-03, tested
MODEL = "large-v3"


def run(*cmd, **kw) -> int:
    print("→", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, **kw).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-model", action="store_true", help="skip the speech-to-text model download")
    args = ap.parse_args()

    if not shutil.which("git") or not shutil.which("ffmpeg"):
        print("!! git and ffmpeg must both be on PATH")
        return 1
    if not (DEST / ".git").is_dir():
        DEST.parent.mkdir(parents=True, exist_ok=True)
        if run("git", "clone", "-q", REPO, str(DEST)):
            return 1
    if run("git", "-C", str(DEST), "fetch", "-q", "origin") or \
       run("git", "-C", str(DEST), "checkout", "-q", COMMIT):
        return 1
    print(f"  kiwiclient at {COMMIT[:7]} in {DEST.relative_to(ROOT)}")

    if run(sys.executable, "-m", "pip", "install", "-q", "faster-whisper"):
        return 1
    if not args.no_model:
        print(f"→ downloading the {MODEL} speech model (about 3 GB, once)")
        code = ("from faster_whisper import WhisperModel;"
                f"WhisperModel('{MODEL}', device='cpu', compute_type='int8')")
        if run(sys.executable, "-c", code):
            return 1
    print("\nready. `!radio hfgcs` in a voice channel, or wait for the next scheduled watch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
