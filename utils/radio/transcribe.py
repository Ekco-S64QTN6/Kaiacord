"""Speech to text for HF voice, on the CPU.

faster-whisper `large-v3` in int8. Measured on eam.watch recordings with a
known human copy: small and medium models, and any model fed the raw audio or
a voice-activity filter, produced hallucinations ("Alpha Alpha Alpha…",
"Thanks for watching!"); large-v3 on band-passed, level-normalised 16 kHz audio
read EAMs at 97–100% of characters once the readbacks were merged
(`phonetic.parse`).

The GPU belongs to Ollama (CLAUDE.md §4): device is always "cpu". The model is
~3 GB of RAM, so it is loaded for a job and dropped after a quiet spell, and
only one job runs at a time.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug

MODEL = "large-v3"
IDLE_UNLOAD_S = 15 * 60
# Speech band, then even out HF fading. Enough on the test captures; noise
# reduction (afftdn) did not rescue the one clip nothing could read.
PREPROCESS = "highpass=f=250,lowpass=f=3200,dynaudnorm"

_lock = threading.Lock()
_model = None
_last_used = 0.0


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _threads() -> int:
    return max(2, min(10, (os.cpu_count() or 4) - 2))


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        log_debug(f"[radio] loading speech model {MODEL} (cpu, int8)")
        _model = WhisperModel(MODEL, device="cpu", compute_type="int8", cpu_threads=_threads())
    return _model


def release_if_idle() -> None:
    """Called on the event loop every minute. Never waits: a transcription on
    another thread holds the lock for up to a minute, and waiting for it here
    froze the whole bot for that long."""
    global _model
    if not _lock.acquire(blocking=False):
        return
    try:
        if _model is not None and time.time() - _last_used > IDLE_UNLOAD_S:
            _model = None
            _return_memory()
            log_debug("[radio] speech model released")
    finally:
        _lock.release()


def _return_memory() -> None:
    """Hand the freed model back to the OS. Dropping the reference freed about
    200 MB of the ~2.3 GB it took; glibc kept the rest mapped, and the bot sat
    at 7 GB until a restart. malloc_trim returns it."""
    import gc
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def prepare(src: Path, dst: Path) -> Path:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                    "-af", PREPROCESS, "-ar", "16000", "-ac", "1", str(dst)], check=True, timeout=120,
                   capture_output=True)   # never onto the dashboard's terminal
    return dst


def transcribe_file(path: Path, language: Optional[str] = "en") -> str:
    """Blocking. Run it in a thread."""
    global _last_used
    with _lock:
        clean = path.with_suffix(".16k.wav")
        try:
            prepare(path, clean)
            segments, _info = _load().transcribe(
                str(clean), language=language, beam_size=5, vad_filter=False,
                condition_on_previous_text=False, temperature=0.0)
            text = " ".join(s.text.strip() for s in segments)
        finally:
            clean.unlink(missing_ok=True)
            _last_used = time.time()
    return _strip_hallucinations(text)


# Whisper's training-data tics: YouTube outros it appends to audio that ends
# in noise.
_OUTROS = ("thanks for watching", "thank you for watching", "please subscribe",
           "subtitles by", "thank you.")


def _strip_hallucinations(text: str) -> str:
    low = text.lower()
    for o in _OUTROS:
        i = low.rfind(o)
        if i != -1 and i > len(low) - 40:
            text, low = text[:i].rstrip(" ,."), low[:i].rstrip(" ,.")
    return text.strip()


async def transcribe(path: Path, language: Optional[str] = "en") -> str:
    return await asyncio.to_thread(transcribe_file, path, language)
