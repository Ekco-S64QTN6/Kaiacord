#!/usr/bin/env python3
"""Hardware check for the local RTL-SDR scanner, against NOAA Weather Radio.

The scanner's tests feed it synthetic IQ. This runs the same code (the
`Dongle` binding, the `Watcher`'s tuned and hopping modes, the squelch and
voice measures, the `rtl_fm` path a live listen uses) on the real dongle and
antenna, using only NOAA Weather Radio as a reference: seven fixed channels,
a continuous public broadcast, lawful to receive and to transcribe anywhere
in the US. Receive only; nothing is transmitted.

    venv/bin/python3 tools/diagnostics/scanner_hardware_check.py
    venv/bin/python3 tools/diagnostics/scanner_hardware_check.py --transcribe --out /tmp/rx-check

The bot's watcher owns the dongle during `radio.local.hours` and for nets: run
this outside them, or after `!scanner off`. It refuses while the dongle is
busy. It writes only to --out (a temporary folder by default), never to
memory/. The hopping step counts what keys up and reports no frequencies:
only the weather channels are named.

Exit status: 0 the checks passed, 1 a check failed, 2 the dongle could not be
used (busy, absent, or inside watch hours without --force).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: NOAA Weather Radio, the whole service: seven channels, 25 kHz apart.
NWR_HZ = [162_400_000, 162_425_000, 162_450_000, 162_475_000, 162_500_000, 162_525_000, 162_550_000]
#: One slice sees all seven, each clear of the tuner's centre spike.
SURVEY_CENTER_HZ = 162_150_000
# A weak local station reads 8 to 9 dB; averaged over seconds, an empty channel stays under 3.
PRESENT_DB = 6.0
FINE_NFFT = 65536                      # 36.6 Hz a bin at 2.4 MS/s


def in_watch_hours(spec: str, now: datetime) -> bool:
    """Whether `now` falls inside an "HH:MM-HH:MM" window (which may cross midnight)."""
    try:
        a, b = spec.split("-")
        lo = int(a[:2]) * 60 + int(a[3:5])
        hi = int(b[:2]) * 60 + int(b[3:5])
    except (ValueError, IndexError):
        return False
    t = now.hour * 60 + now.minute
    return lo <= t < hi if lo <= hi else (t >= lo or t < hi)


def channel_levels(power: np.ndarray, freqs: np.ndarray, channels: list[int]) -> dict[int, dict]:
    """For each channel: dB over the slice's median noise in a 12.5 kHz
    channel, and the carrier's offset from the nominal frequency (the centroid
    of what stands over the noise within 6 kHz, re-centred twice)."""
    noise = float(np.median(power))
    out = {}
    for f in channels:
        ch = np.abs(freqs - f) <= 6_250
        over = 10 * np.log10(max(float(power[ch].mean()), 1e-20) / max(noise, 1e-20))
        est = float(f)
        for _ in range(3):
            win = np.abs(freqs - est) <= 6_000
            w = np.clip(power[win] - 2 * noise, 0, None)
            if not w.sum() > 0:
                est = float("nan")
                break
            est = float((freqs[win] * w).sum() / w.sum())
        out[f] = {"over_db": round(over, 1), "offset_hz": None if est != est else round(est - f)}
    return out


def fine_power(iq: np.ndarray) -> np.ndarray:
    frames = len(iq) // FINE_NFFT
    x = iq[: frames * FINE_NFFT].reshape(frames, FINE_NFFT) * np.hanning(FINE_NFFT)
    return np.mean(np.abs(np.fft.fftshift(np.fft.fft(x, axis=1), axes=1)) ** 2, axis=0)


def ppm_from(levels: dict[int, dict]) -> float | None:
    """The crystal's error from the channels that are present: positive means
    the dongle reads high, which is the sign `radio.local.ppm` takes."""
    errs = [v["offset_hz"] / f * 1e6 for f, v in levels.items()
            if v["over_db"] >= PRESENT_DB and v["offset_hz"] is not None]
    return round(float(np.median(errs)), 1) if errs else None


def audio_report(audio: np.ndarray, wall_s: float) -> dict:
    from utils.radio import rtl, waterfall
    on, _voice = waterfall.carried(audio)
    probe = rtl.measure(audio, 0)
    hiss, _ = waterfall._frame_levels(audio)
    quieting = float(waterfall.HISS_DB - np.median(hiss[on])) if on.any() else 0.0
    return {
        "seconds_of_audio": round(len(audio) / waterfall.AUDIO_FS, 1),
        "wall_seconds": round(wall_s, 1),
        "kept_share": round(len(audio) / waterfall.AUDIO_FS / wall_s, 3) if wall_s else 0.0,
        "carried_share": round(float(on.mean()), 3) if len(on) else 0.0,
        "quieting_db": round(quieting, 1),
        "clipped_share": round(float((np.abs(audio.astype(np.int32)) >= 32000).mean()), 5) if len(audio) else 0.0,
        "rms": round(probe.rms), "hf_ratio": round(probe.hf_ratio, 3),
        "voice_like": bool(waterfall.voice_like(audio)),
    }


def write_wav(path: Path, audio: np.ndarray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio.astype(np.int16).tobytes())


def dongle_identity() -> dict:
    """What `rtl_test -t` says of the device; the process is killed and reaped."""
    p = subprocess.Popen(["rtl_test", "-t"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        out, _ = p.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
    info = {"device": "", "tuner": "", "gains_db": []}
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("0:"):
            info["device"] = s[2:].split(", SN")[0].strip()      # the serial is not recorded
        elif s.startswith("Found") and "tuner" in s:
            info["tuner"] = s[len("Found"):].replace("tuner", "").strip()
        elif s.startswith("Supported gain values"):
            info["gains_db"] = [float(x) for x in s.split(":", 1)[1].split()]
    return info


def can_open(gain: float, ppm: int) -> bool:
    from utils.radio.dongle import Dongle
    try:
        with Dongle(gain_db=gain, ppm=ppm):
            return True
    except RuntimeError:
        return False


def survey(gain: float, ppm: int, reads: int = 8) -> dict[int, dict]:
    from utils.radio import waterfall
    from utils.radio.dongle import Dongle
    with Dongle(sample_rate=waterfall.FS, gain_db=gain, ppm=ppm) as d:
        if not d.tune(SURVEY_CENTER_HZ):
            raise RuntimeError("the tuner refused the weather band")
        power = np.mean([fine_power(d.read(FINE_NFFT * 16)) for _ in range(reads)], axis=0)
    freqs = SURVEY_CENTER_HZ + (np.arange(FINE_NFFT) - FINE_NFFT // 2) * (waterfall.FS / FINE_NFFT)
    return channel_levels(power, freqs, NWR_HZ)


def listen(freq: int, seconds: float, gain: float, ppm: int) -> tuple[np.ndarray, float, int]:
    """The watcher's tuned mode on one channel, squelched as a listener hears it."""
    from utils.radio import waterfall
    chunks, catches = [], []
    stop = threading.Event()
    w = waterfall.Watcher(catches.append, gain_db=gain, stop=stop, sink=chunks.append, ppm=ppm)
    w.pin = {"freq": int(freq), "until": time.time() + seconds, "label": "NOAA Weather Radio"}
    w._exit_unpinned = True
    t0 = time.time()
    w.run()
    wall = time.time() - t0
    audio = np.concatenate(chunks) if chunks else np.zeros(0, np.int16)
    return audio, wall, len(catches)


def scan(seconds: float, gain: float, ppm: int) -> dict:
    """The watcher hopping as it does at night. Counts only."""
    from utils.radio import waterfall
    catches = []
    stop = threading.Event()
    w = waterfall.Watcher(catches.append, gain_db=gain, stop=stop, ppm=ppm)
    t = threading.Thread(target=w.run, name="hardware-check-scan")
    cpu0, t0 = time.process_time(), time.time()
    t.start()
    time.sleep(seconds)
    stop.set()
    t.join(timeout=90)
    wall = time.time() - t0
    held = [c for c in catches if c is not None]
    return {
        "wall_seconds": round(wall, 1), "stopped": not t.is_alive(), "passes": w.passes,
        "seconds_per_pass": round(wall / w.passes, 2) if w.passes else None,
        "slices": len(w.fast) + len(w.slow),
        "catches": len(held), "held_seconds": round(sum(c.seconds for c in held), 1),
        "voice_like": sum(1 for c in held if waterfall.voice_like(c.audio)),
        "in_weather_band": sum(1 for c in held if NWR_HZ[0] - 12_500 <= c.freq_hz <= NWR_HZ[-1] + 12_500),
        "cpu_share_of_one_core": round((time.process_time() - cpu0) / wall, 2) if wall else None,
    }


def rtl_fm_release(freq: int, gain: float, seconds: float = 3.0) -> dict:
    """The `rtl_fm` stream a live listen plays: opened, read, stopped, reaped."""
    from utils.radio import rtl
    p = rtl.open_stream(freq, int(gain))
    got = 0
    t0 = time.time()
    try:
        while time.time() - t0 < seconds:
            got += len(p.stdout.read(4096) or b"")
    finally:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=5)
    return {"bytes": got, "exit": p.returncode}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the RTL-SDR scanner on real hardware against NOAA Weather Radio.")
    ap.add_argument("--out", help="folder for the report and the weather clip (default: a new temporary folder)")
    ap.add_argument("--listen", type=float, default=45.0, help="seconds on the strongest weather channel")
    ap.add_argument("--scan", type=float, default=120.0, help="seconds of hopping; 0 skips it")
    ap.add_argument("--gain", type=float, help="tuner gain in dB (default: radio.local.gain)")
    ap.add_argument("--ppm", type=int, help="frequency correction (default: radio.local.ppm)")
    ap.add_argument("--transcribe", action="store_true", help="transcribe the weather clip on the CPU (loads large-v3)")
    ap.add_argument("--force", action="store_true", help="run inside radio.local.hours")
    a = ap.parse_args(argv)

    from utils.infrastructure.system.yaml_config import config
    from utils.radio import rtl
    gain = a.gain if a.gain is not None else float(config.get("radio.local.gain", rtl.DEFAULT_GAIN) or rtl.DEFAULT_GAIN)
    ppm = a.ppm if a.ppm is not None else rtl.ppm()
    hours = str(config.get("radio.local.hours", "") or "")
    if not rtl.available():
        print("rtl_fm / rtl_power are not installed.")
        return 2
    if in_watch_hours(hours, datetime.now()) and not a.force:
        print(f"Inside the scanner's watch hours ({hours}): the bot's watcher wants the dongle. Use --force to run anyway.")
        return 2
    if not can_open(gain, ppm):
        print("The RTL-SDR is busy or absent. If the bot's scanner holds it, `!scanner off` first.")
        return 2

    out = Path(a.out) if a.out else Path(tempfile.mkdtemp(prefix="kaia-rx-check-"))
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"when": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "gain_db": gain, "ppm_configured": ppm, "watch_hours": hours,
                    "load_average": [round(x, 2) for x in os.getloadavg()], "checks": {}}
    checks = report["checks"]

    report["dongle"] = dongle_identity()
    levels = survey(gain, ppm)
    report["weather_channels"] = {f"{f / 1e6:.3f}": v for f, v in levels.items()}
    present = [f for f, v in levels.items() if v["over_db"] >= PRESENT_DB]
    report["ppm_measured"] = ppm_from(levels)
    checks["a weather channel is received"] = bool(present)
    if report["ppm_measured"] is not None:
        # Half a 12.5 kHz channel at 450 MHz is 14 ppm: beyond that a catch is filed on the wrong channel.
        checks["frequency error within 5 ppm of radio.local.ppm"] = abs(report["ppm_measured"]) <= 5.0
    checks["dongle released after the survey"] = can_open(gain, ppm)

    if present:
        best = max(present, key=lambda f: levels[f]["over_db"])
        audio, wall, held = listen(best, a.listen, gain, ppm)
        clip = out / f"noaa_{best / 1e6:.3f}.wav"
        from utils.radio import waterfall
        write_wav(clip, audio, waterfall.AUDIO_FS)
        heard = audio_report(audio, wall)
        heard.update(channel=f"{best / 1e6:.3f}", clip=str(clip), holds=held)
        report["listen"] = heard
        checks["tuned audio has no gaps (95% of the time kept)"] = heard["kept_share"] >= 0.95
        checks["audio is not clipped"] = heard["clipped_share"] < 0.001
        # The watcher follows voice only under a full-quieting carrier, and a
        # weaker one fades through the squelch: both are judged only when the
        # reference station is strong enough for them to apply.
        heard["full_quieting"] = heard["quieting_db"] >= waterfall.FULL_QUIETING_DB
        if heard["full_quieting"]:
            checks["squelch stays open on a constant carrier"] = heard["carried_share"] >= 0.95
            checks["a broadcast voice reads as voice"] = heard["voice_like"]
        else:
            report["not_judged"] = (f"the weather station quiets the channel {heard['quieting_db']} dB, under the "
                                    f"{waterfall.FULL_QUIETING_DB:.0f} dB the squelch and voice checks need")
        checks["dongle released after the tuned listen"] = can_open(gain, ppm)
        if a.transcribe:
            from utils.radio import transcribe
            if transcribe.available():
                speech = out / "noaa_speech.wav"
                write_wav(speech, waterfall.speech_audio(audio), waterfall.AUDIO_FS)
                t0 = time.time()
                text = transcribe.transcribe_speech(speech)
                report["transcript"] = {"text": text, "words": len(text.split()), "seconds": round(time.time() - t0, 1)}
                checks["the weather broadcast transcribes to words"] = len(text.split()) >= 10
            else:
                report["transcript"] = {"skipped": "faster-whisper is not installed"}

        fm = rtl_fm_release(best, gain)
        report["rtl_fm"] = fm
        checks["rtl_fm stream delivers audio"] = fm["bytes"] > 0
        checks["dongle released after rtl_fm is stopped"] = can_open(gain, ppm)

    if a.scan > 0:
        report["scan"] = scan(a.scan, gain, ppm)
        checks["hopping stops when asked"] = report["scan"]["stopped"]
        checks["hopping completes passes"] = report["scan"]["passes"] > 0
        # A constant carrier raises its own floor and must not be held over and over.
        checks["the weather carrier is not held repeatedly"] = report["scan"]["in_weather_band"] <= 2
        checks["dongle released after hopping"] = can_open(gain, ppm)

    (out / "report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))
    failed = [k for k, ok in checks.items() if not ok]
    print(f"\n{len(checks) - len(failed)} of {len(checks)} checks passed. Report and clip: {out}")
    for k in failed:
        print(f"  FAILED: {k}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
