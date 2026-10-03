"""Kaia listens: scheduled recordings, transcription, the log, the cross-check.

Two kinds of listening, both scheduled so a receiver slot is only held while
something is expected:

- **HFGCS watches.** At a few fixed UTC times a day, a squelched recording of
  8992 kHz USB from a North American KiwiSDR. The squelch writes one file per
  transmission; anything too short or without the shape of an EAM broadcast
  is dropped as noise.
- **Number stations Kaia follows** (`radio.follow`; E07, V07, S11a, M12 and
  E11 by default). A recording from a European receiver from a minute before
  Priyom's scheduled start — at most one per station a day and six in all,
  preferring whichever she has gone longest without, so a day rotates rather
  than filling up with E11's null messages.

Each keeper is converted to Opus, logged to memory/radio/ and posted to
#kaia-opolis. HFGCS catches are also transcribed on the CPU and parsed.
Number stations are not: Whisper on a station reading digit groups through
HF fading loops on its own output ("8-1-4-0-8-0-0" forty times, "thank you",
"he was born on the hill"), so a number-station catch is posted as a
recording, with the clip, and no transcript. EAM transcriptions are
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
# Voice and Morse stations that carry real traffic, E11 last: it is mostly
# null messages ("000 000"). Digital stations record as noise, and V13 beams
# at East Asia, out of reach of the European receivers used here.
DEFAULT_FOLLOW = ["E07", "V07", "S11A", "M12", "E11"]
NUMBERS_PER_DAY = 6            # recordings a day across every station
NUMBERS_PER_STATION_DAY = 1    # so a day's listening rotates between stations
NUMBERS_RECORD_S = 7 * 60
MIN_TRANSMISSION_S = 25        # an EAM broadcast runs well over a minute
SQUELCH_DB = 12
STATE_CACHE = "watch_state"
# UVB-76 calibration samples: a buzz-break detector has to be built against a
# real buzz, and 4625 kHz only carries at night in Europe. Collected, not posted.
UVB76_KHZ = 4625.0
UVB76_SAMPLE_TIMES = ["21:00", "00:00", "03:00"]      # UTC
UVB76_SAMPLE_S = 120

#: One listen of each kind at a time: an HFGCS watch holds its lock for twenty
#: minutes, and a number station falling inside it must not be skipped.
_busy = {"hfgcs": asyncio.Lock(), "numbers": asyncio.Lock(), "uvb76": asyncio.Lock()}


def _lock_for(job: dict) -> asyncio.Lock:
    return _busy.get(job["kind"]) or _busy.setdefault(job["kind"], asyncio.Lock())


def heard_at(wav: Path, fallback: datetime) -> datetime:
    """kiwirecorder names each file for when it started — per squelch opening,
    not per watch — so the log and the cross-check get the real time."""
    try:
        return datetime.strptime(wav.name[:16], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return fallback


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
        if _cfg("uvb76_samples", True):
            for hhmm in UVB76_SAMPLE_TIMES:
                h, m = (int(x) for x in hhmm.split(":"))
                start = now.replace(hour=h, minute=m, second=0, microsecond=0)
                key = f"uvb76:{start:%Y-%m-%dT%H:%M}"
                if start <= now < start + timedelta(minutes=5) and key not in done:
                    jobs.append({"key": key, "kind": "uvb76", "station": "UVB-76", "khz": UVB76_KHZ,
                                 "mode": "usb", "seconds": UVB76_SAMPLE_S, "region": "ne", "squelch": None})
        follow = [s.upper() for s in _cfg("follow", DEFAULT_FOLLOW)]
        today, last = _numbers_done(done, now)
        if sum(today.values()) < int(_cfg("numbers_per_day", NUMBERS_PER_DAY)):
            numbers = []
            for t in schedule_items:
                station = t.station.upper()
                if station not in follow or not t.khz:
                    continue
                if today.get(station, 0) >= NUMBERS_PER_STATION_DAY:
                    continue
                key = f"num:{t.station}:{t.start:%Y-%m-%dT%H:%M}:{t.khz:g}"
                lead = t.start - timedelta(seconds=60)
                if lead <= now < t.start + timedelta(minutes=2) and key not in done:
                    numbers.append({"key": key, "kind": "numbers", "station": t.station, "khz": t.khz,
                                    "mode": (t.mode or "usb").lower(), "seconds": NUMBERS_RECORD_S,
                                    "region": "eu", "squelch": None})
            # One number-station job starts per tick; make it the station she
            # has gone longest without, then the follow list's order.
            numbers.sort(key=lambda j: (last.get(j["station"].upper(), ""),
                                        follow.index(j["station"].upper())))
            jobs += numbers
    return jobs


def _numbers_done(done: set[str], now: datetime) -> tuple[dict, dict]:
    """({station: recordings today}, {station: last recording date}) from the
    done keys, "num:<station>:<YYYY-MM-DDTHH:MM>:<khz>"."""
    today, last = {}, {}
    day = f"{now:%Y-%m-%d}"
    for key in done:
        parts = key.split(":")
        if len(parts) < 3 or parts[0] != "num":
            continue
        station, when = parts[1].upper(), parts[2]
        if when.startswith(day):
            today[station] = today.get(station, 0) + 1
        last[station] = max(last.get(station, ""), when)
    return today, last


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
                   check=True, timeout=120, capture_output=True)   # never onto the dashboard's terminal
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


def keyed_tone(wav: Path) -> dict:
    """Is there a keyed tone — Morse, a signalling tone — and how sure.

    Two tests, because each alone kept static:
    - the tone stands out within the recording's own passband. Measured
      against the whole 300–3000 Hz band, CW mode's ~450 Hz filter made every
      recording "tonal": the empty band outside the filter is the median, so
      whatever noise the filter passed towered over it. An M12 slot of pure
      static was kept and posted that way.
    - it switches on and off. A stray carrier in static stands out too, and
      kept an E11 slot on a steady 1500 Hz whistle.
    Returns {"keyed": bool, "prominence_db", "on_share", "keys_per_min", "hz"}."""
    import wave as _wave
    import numpy as np
    out = {"keyed": False, "prominence_db": 0.0, "on_share": 0.0, "keys_per_min": 0.0, "hz": 0}
    try:
        with _wave.open(str(wav), "rb") as w:
            rate = w.getframerate()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(float)
    except Exception:
        return out
    n = rate // 20                                        # 50 ms frames
    frames = len(a) // n
    if frames < 40:
        return out
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(a[:frames * n].reshape(frames, n) * win, axis=1)) ** 2
    f = np.fft.rfftfreq(n, 1 / rate)
    avg = spec.mean(axis=0)
    speech = (f > 300) & (f < 3000)
    peak = int(np.argmax(np.where(speech, avg, 0)))
    # The passband: bins the receiver's filter let through (within 30 dB of the
    # loudest), found with the tone masked out, so a clean tone's own skirt
    # doesn't become the reference it is measured against.
    rest = speech.copy()
    rest[max(0, peak - 5):peak + 6] = False
    if rest.sum() < 3:
        return out
    passband = rest & (avg > avg[rest].max() / 1000)
    out["hz"] = int(f[peak])
    out["prominence_db"] = round(float(10 * np.log10(avg[peak] / np.median(avg[passband]))), 1)
    env = 10 * np.log10(spec[:, max(0, peak - 1):peak + 2].sum(axis=1) + 1e-9)
    on = env > np.percentile(env, 20) + 8
    out["on_share"] = round(float(on.mean()), 2)
    out["keys_per_min"] = round(float(np.count_nonzero(np.diff(on.astype(int)) == 1) / (frames * 0.05 / 60)), 1)
    # 8 dB: weak synthetic Morse measures ~9, the E11 whistle 5.3.
    out["keyed"] = bool(out["prominence_db"] >= 8 and 0.1 <= out["on_share"] <= 0.9
                        and out["keys_per_min"] >= 20)
    return out


def numbers_signal(wav: Path) -> tuple[str, dict]:
    """Why a number-station recording is worth keeping — "tones" or "speech" —
    or '' for static, with the measurements behind the verdict. A scheduled
    station that doesn't show, or doesn't propagate, records seven minutes of
    noise, and that was being posted."""
    tone = keyed_tone(wav)
    if tone["keyed"]:
        return "tones", tone
    if transcribe.available():
        try:
            text = transcribe.transcribe_speech(wav, language=None)
        except Exception as e:
            log_warning(f"[radio] speech check failed for {wav.name}: {e}")
            return "unchecked", tone
        if len(text.split()) >= 3 and len(set(text.lower().split())) / len(text.split()) >= 0.3:
            return "speech", {**tone, "words": len(text.split())}
    return "", tone


async def process(job: dict, wav: Path, receiver: kiwi.Receiver, started: datetime) -> Optional[dict]:
    """One recording → a log entry, or None if it was noise."""
    seconds = await asyncio.to_thread(_seconds, wav)
    why = job.setdefault("dropped", {})
    if job["kind"] == "hfgcs" and seconds < MIN_TRANSMISSION_S:
        why["under 25 s"] = why.get("under 25 s", 0) + 1
        wav.unlink(missing_ok=True)
        return None
    entry_id = f"{started:%Y%m%dT%H%M%S}-{job['station'].lower()}-{secrets.token_hex(2)}"
    transcript = ""
    if job["kind"] == "hfgcs" and transcribe.available():
        try:
            transcript = await transcribe.transcribe(wav, language="en")
        except Exception as e:
            log_warning(f"[radio] transcription failed for {wav.name}: {e}")
    heard, measured = "", None
    if job["kind"] == "numbers":
        heard, measured = await asyncio.to_thread(numbers_signal, wav)
        if not heard:
            log_info(f"[radio] {job['station']} on {job['khz']:g} kHz: nothing but static — not kept "
                     f"(tone {measured['prominence_db']:+.0f} dB, on {measured['on_share']:.0%}, "
                     f"{measured['keys_per_min']:.0f} keys/min; no speech)")
            wav.unlink(missing_ok=True)
            return None
    parsed = None
    if job["kind"] == "hfgcs":
        # Without a transcript nothing separates an EAM from a burst of noise,
        # and every squelch opening would be posted.
        if not transcript or not looks_like_eam(transcript):
            key = "no words" if not transcript else "not an EAM"
            why[key] = why.get(key, 0) + 1
            if transcript and len(transcript) > len(job.get("sample", "")):
                job["sample"] = transcript
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
    if heard:
        # Why it was kept, so a clip can be audited against the verdict.
        entry["heard"], entry["measured"] = heard, measured
    radio_log.add(entry)
    return entry


#: The buzz, measured on 22 night samples from five receivers in Finland and
#: Poland (26 Sept – 3 Oct): a period of 3.0–3.3 s, on about 40% of it, with an
#: S-meter autocorrelation at that period of 0.42–0.58.
BUZZ_PERIOD_S = (2.6, 3.8)
BUZZ_STRENGTH = 0.35
#: Under this spread (p90 − p10 of the S-meter) nothing is on the frequency.
SIGNAL_SPAN_DB = 6.0


def buzz_state(readings: list) -> dict:
    """What 4625 kHz was doing over a run of S-meter readings ([(time, dBm)]):
    "buzz" (the pattern intact), "quiet" (no signal over the noise) or
    "changed" — a signal that is not the buzz: a voice message, a marker, the
    station doing something else. Only "changed" is news."""
    import numpy as np
    if len(readings) < 30:
        return {"state": "unknown"}
    t = np.array([(r[0] if isinstance(r[0], (int, float)) else datetime.fromisoformat(str(r[0])).timestamp())
                  for r in readings], float)
    v = np.array([r[1] for r in readings], float)
    t -= t[0]
    if t[-1] < 20:
        return {"state": "unknown"}
    span = float(np.percentile(v, 90) - np.percentile(v, 10))
    y = np.interp(np.arange(0, t[-1], 0.05), t, v)
    y = y - y.mean()
    ac = np.correlate(y, y, "full")[len(y) - 1:]
    ac = ac / (ac[0] or 1)
    lo, hi = int(2.0 / 0.05), int(5.0 / 0.05)
    k = lo + int(np.argmax(ac[lo:hi]))
    period, strength = k * 0.05, float(ac[k])
    out = {"period_s": round(period, 2), "strength": round(strength, 2), "span_db": round(span, 1)}
    if span < SIGNAL_SPAN_DB:
        return {"state": "quiet", **out}
    if BUZZ_PERIOD_S[0] <= period <= BUZZ_PERIOD_S[1] and strength >= BUZZ_STRENGTH:
        return {"state": "buzz", **out}
    return {"state": "changed", **out}


def _silent(wav: Path) -> bool:
    """True for a recording that is digital silence: some receivers sent 60 s of
    zeros for every sample while their S-meter read the buzz."""
    import wave
    import numpy as np
    try:
        with wave.open(str(wav)) as f:
            a = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    except Exception:
        return True
    return len(a) == 0 or int(np.abs(a).max()) < 4


async def sample_uvb76(job: dict, poster=None) -> Optional[Path]:
    """Two minutes of S-meter readings and a clip from a north-eastern European
    receiver, kept in memory/radio/uvb76/ for calibrating a buzz detector.
    Returns the sample's JSON path, or None."""
    import json
    folder = radio_log.clips_dir().parent / "uvb76"
    folder.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    receivers = kiwi.choose(await kiwi.directory(), job["khz"], job["region"], n=4)
    for i, r in enumerate(receivers):
        try:
            readings = await kiwi.smeter(r, job["khz"], "usb", job["seconds"])
        except FeedError as e:
            log_warning(f"[radio] UVB-76 sample: {e}; trying the next receiver")
            continue
        stem = f"{started:%Y%m%dT%H%M}"
        # The clip from this receiver, or the next whose audio is not silence.
        clip, clip_from = None, None
        for cr in [r] + receivers[i + 1:]:
            try:
                wavs = await kiwi.record(cr, job["khz"], "usb", 60, folder / "work", label="uvb76")
            except FeedError as e:
                log_debug(f"[radio] UVB-76 clip: {e}")
                continue
            good = [w for w in wavs if not await asyncio.to_thread(_silent, w)]
            if not good and wavs:
                log_warning(f"[radio] UVB-76 clip from {cr.location or cr.host} was silence; trying the next receiver")
            if good:
                clip = await asyncio.to_thread(_to_opus, good[0], folder / f"{stem}.ogg")
                clip_from = cr
            for w in wavs:
                w.unlink(missing_ok=True)
            if clip:
                break
        state = buzz_state(readings)
        out = folder / f"{stem}.json"
        from utils.core.atomic_write import write_atomic
        write_atomic(out, json.dumps({
            "started": started.isoformat(), "khz": job["khz"], "receiver": r.host,
            "receiver_location": r.location,
            "clip": clip.name if clip else None,
            "clip_receiver": clip_from.host if clip_from else None,
            "buzz": state,
            "readings": [[t.isoformat(), dbm] for t, dbm in readings]}, indent=1))
        levels = [dbm for _, dbm in readings]
        log_info(f"[radio] UVB-76 sample from {r.location or r.host}: {len(levels)} readings, "
                 f"{min(levels):.0f} to {max(levels):.0f} dBm; {state['state']}"
                 + (f" (period {state.get('period_s')} s, strength {state.get('strength')})" if "period_s" in state else ""))
        if state["state"] == "changed":
            await _uvb76_changed(job, started, state, clip, clip_from or r, poster)
        return out
    log_warning("[radio] UVB-76 sample: no north-east European receiver gave readings")
    return None


async def _uvb76_changed(job: dict, started: datetime, state: dict, clip: Optional[Path],
                         receiver, poster) -> None:
    """The buzz broke: keep the clip in the radio log, transcribe it in Russian
    (Whisper large-v3 reads Russian), and post it like any other catch."""
    import shutil
    entry_id = f"{started:%Y%m%dT%H%M%S}-uvb76-{secrets.token_hex(2)}"
    transcript = ""
    kept = None
    if clip:
        kept = radio_log.clips_dir() / f"{entry_id}.ogg"
        await asyncio.to_thread(shutil.copyfile, clip, kept)
        if transcribe.available():
            try:
                transcript = await transcribe.transcribe(kept, language="ru")
            except Exception as e:
                log_warning(f"[radio] UVB-76 transcription failed: {e}")
            finally:
                transcribe.release_if_idle()
    entry = {
        "id": entry_id, "kind": "uvb76", "station": "UVB-76", "khz": job["khz"], "mode": "usb",
        "receiver": receiver.host, "receiver_location": receiver.location, "started": started.isoformat(),
        "seconds": 60.0 if kept else 0.0, "clip": kept.name if kept else None, "transcript": transcript,
        "parsed": None, "check": None, "posted": False, "heard": "changed", "measured": state,
    }
    radio_log.add(entry)
    log_warning(f"[radio] UVB-76: the buzz broke (period {state.get('period_s')} s, strength "
                f"{state.get('strength')}, {state.get('span_db')} dB over the noise)"
                + (f"; heard: {transcript[:120]!r}" if transcript else ""))
    if poster:
        try:
            if await poster(entry):
                radio_log.update(entry_id, posted=True)
        except Exception as e:
            log_warning(f"[radio] posting the UVB-76 break failed: {e}")


async def run_job(job: dict, poster=None) -> list[dict]:
    """Record, process, post. One job at a time across the process."""
    if not kiwi.available():
        log_debug("[radio] kiwiclient not installed; skipping a scheduled listen")
        return []
    if job["kind"] == "uvb76":
        async with _lock_for(job):
            await sample_uvb76(job, poster)
        return []
    async with _lock_for(job):
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
            try:
                entry = await process(job, wav, receiver, heard_at(wav, started))
            except Exception as e:
                # One bad file must not strand the rest in work/ or end the job.
                log_warning(f"[radio] processing {wav.name} failed: {type(e).__name__}: {e}")
                wav.unlink(missing_ok=True)
                continue
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
        elif wavs and job.get("dropped"):
            reasons = ", ".join(f"{n} {k}" for k, n in job["dropped"].items())
            sample = job.get("sample", "")
            log_info(f"[radio] {job['station']}: kept none of {len(wavs)} ({reasons})"
                     + (f"; longest heard: {sample[:120]!r}" if sample else ""))
        return entries


async def tick(poster=None, now: Optional[datetime] = None) -> None:
    """Start whatever is due. Called every minute by the radio task."""
    from utils.radio import priyom
    now = now or datetime.now(timezone.utc)
    schedule = priyom.upcoming(read_cache(priyom.CACHE), hours=1, now=now - timedelta(minutes=5))
    launched: set[str] = set()
    for job in due_jobs(now, schedule, _done()):
        # One of each kind at a time. The lock is only taken once the task
        # runs, so a second job of a kind started this tick would pass the
        # check and then wait out the first — starting long after its window.
        if job["kind"] in launched or _lock_for(job).locked():
            continue                   # the next tick retries while the window is open
        launched.add(job["kind"])
        _mark_done(job["key"])
        from utils.infrastructure.monitoring.async_task_registry import task_registry
        task_registry.register(f"radio_job_{job['key']}", asyncio.create_task(run_job(job, poster)))


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
