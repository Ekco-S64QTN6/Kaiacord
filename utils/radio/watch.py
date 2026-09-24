"""Kaia listens: scheduled recordings, transcription, the log, the cross-check.

Two kinds of listening, both scheduled so a receiver slot is only held while
something is expected:

- **HFGCS watches.** At a few fixed UTC times a day, a squelched recording of
  8992 kHz USB from a North American KiwiSDR. The squelch writes one file per
  transmission; anything too short or without the shape of an EAM broadcast
  is dropped as noise.
- **Number stations Kaia follows** (`radio.follow`, E11 by default). A
  recording from a European receiver from a minute before Priyom's scheduled
  start.

Each keeper is converted to Opus, transcribed on the CPU, parsed (EAMs),
logged to memory/radio/, and posted to #kaia-opolis. EAM transcriptions are
later matched with eam.watch's human copy of the same message; the accuracy
is recorded, not assumed.
"""
from __future__ import annotations

import asyncio
import difflib
import secrets
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_info, log_success, log_warning
from utils.infrastructure.system.yaml_config import config
from utils.radio import kiwi, log as radio_log, phonetic, transcribe
from utils.radio.fetch import FeedError, read_cache, write_cache

HFGCS_KHZ = 8992.0
DEFAULT_WINDOWS = ["03:10", "09:10", "15:10", "21:10"]      # UTC
DEFAULT_WINDOW_MIN = 20
DEFAULT_FOLLOW = ["E11"]
NUMBERS_RECORD_S = 7 * 60
MIN_TRANSMISSION_S = 25        # an EAM broadcast runs well over a minute
SQUELCH_DB = 12
STATE_CACHE = "watch_state"

_busy = asyncio.Lock()


def _cfg(key, default):
    return config.get(f"radio.{key}", default)


# ── scheduling ──────────────────────────────────────────────────────────────

def due_jobs(now: datetime, schedule_items: list, done: set[str]) -> list[dict]:
    """Jobs whose time has come and that have not run. Pure; the task calls it."""
    jobs = []
    if _cfg("listen", True):
        for hhmm in _cfg("hfgcs_windows_utc", DEFAULT_WINDOWS):
            h, m = (int(x) for x in str(hhmm).split(":"))
            start = now.replace(hour=h, minute=m, second=0, microsecond=0)
            key = f"hfgcs:{start:%Y-%m-%dT%H:%M}"
            if start <= now < start + timedelta(minutes=5) and key not in done:
                jobs.append({"key": key, "kind": "hfgcs", "station": "HFGCS", "khz": HFGCS_KHZ,
                             "mode": "usb", "seconds": 60 * int(_cfg("hfgcs_window_minutes", DEFAULT_WINDOW_MIN)),
                             "region": "na", "squelch": SQUELCH_DB})
        follow = {s.upper() for s in _cfg("follow", DEFAULT_FOLLOW)}
        for t in schedule_items:
            if t.station.upper() not in follow or not t.khz:
                continue
            key = f"num:{t.station}:{t.start:%Y-%m-%dT%H:%M}:{t.khz:g}"
            lead = t.start - timedelta(seconds=60)
            if lead <= now < t.start + timedelta(minutes=2) and key not in done:
                jobs.append({"key": key, "kind": "numbers", "station": t.station, "khz": t.khz,
                             "mode": (t.mode or "usb").lower(), "seconds": NUMBERS_RECORD_S,
                             "region": "eu", "squelch": None})
    return jobs


def _done() -> set[str]:
    return set(read_cache(STATE_CACHE).get("done") or [])


def _mark_done(key: str) -> None:
    done = sorted(_done() | {key})[-200:]
    write_cache(STATE_CACHE, {"done": done})


# ── processing ──────────────────────────────────────────────────────────────

def _seconds(path: Path) -> float:
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(path)], capture_output=True, text=True, timeout=30)
        return float(out.stdout.strip() or 0)
    except (subprocess.SubprocessError, ValueError):
        return 0.0


def _to_opus(wav: Path, dest: Path) -> Path:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav),
                    "-af", transcribe.PREPROCESS, "-c:a", "libopus", "-b:a", "24k", str(dest)],
                   check=True, timeout=120)
    return dest


def _known_callsigns() -> list[str]:
    from utils.radio import eam_watch
    cache = read_cache(eam_watch.MESSAGES_CACHE)
    names = {str(i.get("sender") or "").upper() for i in cache.get("messages") or []}
    names |= {str(n).upper() for n in cache.get("callsigns") or []}
    return sorted(n for n in names if n)


def looks_like_eam(transcript: str) -> bool:
    low = transcript.lower()
    cues = ("standby", "stand by", "message follows", "this is", "i say again", "break")
    return sum(c in low for c in cues) >= 2


async def process(job: dict, wav: Path, receiver: kiwi.Receiver, started: datetime) -> Optional[dict]:
    """One recording → a log entry, or None if it was noise."""
    seconds = await asyncio.to_thread(_seconds, wav)
    if job["kind"] == "hfgcs" and seconds < MIN_TRANSMISSION_S:
        wav.unlink(missing_ok=True)
        return None
    entry_id = f"{started:%Y%m%dT%H%M%S}-{job['station'].lower()}-{secrets.token_hex(2)}"
    transcript = ""
    if transcribe.available():
        lang = "en" if job["kind"] == "hfgcs" or job["station"].upper().startswith("E") else None
        try:
            transcript = await transcribe.transcribe(wav, language=lang)
        except Exception as e:
            log_warning(f"[radio] transcription failed for {wav.name}: {e}")
    parsed = None
    if job["kind"] == "hfgcs":
        if transcript and not looks_like_eam(transcript):
            wav.unlink(missing_ok=True)          # a squelch opening on voice that is not an EAM
            return None
        if transcript:
            p = phonetic.parse(transcript, _known_callsigns())
            parsed = {"callsign": p.callsign, "preamble": p.preamble, "message": p.message,
                      "uncertain": p.uncertain, "usable": p.usable}
    clip = radio_log.clips_dir() / f"{entry_id}.ogg"
    await asyncio.to_thread(_to_opus, wav, clip)
    wav.unlink(missing_ok=True)
    entry = {
        "id": entry_id, "kind": job["kind"], "station": job["station"], "khz": job["khz"],
        "mode": job["mode"], "receiver": receiver.host, "receiver_location": receiver.location,
        "started": started.isoformat(), "seconds": round(seconds, 1), "clip": clip.name,
        "transcript": transcript, "parsed": parsed, "check": None, "posted": False,
    }
    radio_log.add(entry)
    return entry


async def run_job(job: dict, poster=None) -> list[dict]:
    """Record, process, post. One job at a time across the process."""
    if not kiwi.available():
        log_debug("[radio] kiwiclient not installed; skipping a scheduled listen")
        return []
    async with _busy:
        receivers = kiwi.choose(await kiwi.directory(), job["khz"], job["region"])
        if not receivers:
            log_warning(f"[radio] no free {job['region']} receiver covers {job['khz']:g} kHz")
            return []
        work = radio_log.clips_dir().parent / "work"
        started = datetime.now(timezone.utc)
        wavs: list[Path] = []
        for r in receivers:
            try:
                wavs = await kiwi.record(r, job["khz"], job["mode"], job["seconds"], work,
                                         label=job["station"].lower(), squelch_db=job["squelch"])
                receiver = r
                break
            except FeedError as e:
                log_warning(f"[radio] {e}; trying the next receiver")
        else:
            return []
        log_info(f"[radio] {job['station']} on {job['khz']:g} kHz via {receiver.host}: "
                 f"{len(wavs)} recording(s)")
        entries = []
        for wav in wavs:
            entry = await process(job, wav, receiver, started)
            if entry:
                entries.append(entry)
                if poster:
                    try:
                        if await poster(entry):
                            radio_log.update(entry["id"], posted=True)
                    except Exception as e:
                        log_warning(f"[radio] posting {entry['id']} failed: {e}")
        transcribe.release_if_idle()
        if entries:
            log_success(f"[radio] kept {len(entries)} of {len(wavs)} from {job['station']}")
        return entries


async def tick(poster=None, now: Optional[datetime] = None) -> None:
    """Start whatever is due. Called every minute by the radio task."""
    from utils.radio import priyom
    now = now or datetime.now(timezone.utc)
    schedule = priyom.upcoming(read_cache(priyom.CACHE), hours=1, now=now - timedelta(minutes=5))
    for job in due_jobs(now, schedule, _done()):
        if _busy.locked():
            continue                   # one listen at a time; the next tick retries within its window
        _mark_done(job["key"])
        asyncio.create_task(run_job(job, poster))
        return


# ── the cross-check ─────────────────────────────────────────────────────────

def cross_check(eam_messages) -> int:
    """Match transcribed EAMs to eam.watch's human copies; record accuracy.
    Returns how many entries were checked this call."""
    checked = 0
    for e in radio_log.entries():
        parsed = e.get("parsed") or {}
        if e.get("kind") != "hfgcs" or e.get("check") or not parsed.get("message"):
            continue
        started = datetime.fromisoformat(e["started"])
        best, best_score = None, 0.0
        for m in eam_messages:
            if not m.time or abs(m.time - started) > timedelta(minutes=40):
                continue
            score = difflib.SequenceMatcher(None, parsed["message"], m.text).ratio()
            if score > best_score:
                best, best_score = m, score
        if best and best_score >= 0.5:
            acc = phonetic.accuracy(parsed["message"], best.text)
            radio_log.update(e["id"], check={"eam_id": best.id, "truth": best.text,
                                             "sender": best.sender, "accuracy": round(acc, 3)})
            checked += 1
    return checked
