"""Listening through the public KiwiSDR network.

KiwiSDRs are volunteer-run receivers with a handful of listener slots each.
The public directory (kiwisdr.com/public, mirrored as a JS array at
rx.linkfanel.net) says where each one is, what it covers, how many slots are
free and whether it enforces time limits. `kiwirecorder.py` from jks-prv's
kiwiclient does the talking; it is fetched at install time into
assets/kiwiclient/ (tools/maintenance/fetch_radio_assets.py), never vendored,
and run as a separate process.

Etiquette, which is also how this is built: pick receivers with a free slot
and no time limit, identify ourselves, stay only as long as the recording
needs, and never hold a slot while nothing is scheduled.
"""
from __future__ import annotations

import asyncio
import json
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from utils.infrastructure.logging.kaia_logger import log_debug, log_warning
from utils.radio.fetch import FeedError, USER_AGENT, is_stale, read_cache, write_cache

DIRECTORY_URL = "http://rx.linkfanel.net/kiwisdr_com.js"
DIRECTORY_CACHE = "kiwi_directory"
DIRECTORY_MAX_AGE_S = 3 * 3600       # slot counts go stale well inside a day
ROOT = Path(__file__).resolve().parents[2]
KIWICLIENT = ROOT / "assets" / "kiwiclient"
RECORDER = KIWICLIENT / "kiwirecorder.py"
DEFAULT_PORT = 8073          # the directory lists proxy receivers without one
KIWI_USER = "Kaia (Kaiacord bot)"
SAMPLE_RATE = 12000          # what a Kiwi sends in audio mode

#: Where to listen from, as (lat_min, lat_max, lon_min, lon_max).
REGIONS = {
    "na": (24.0, 55.0, -125.0, -60.0),     # HFGCS is loudest in North America
    "eu": (35.0, 62.0, -10.0, 30.0),       # most number stations are European or Russian
    "ne": (50.0, 68.0, 18.0, 45.0),        # north-east Europe: UVB-76 on 4625 kHz carries here at night
}


@dataclass
class Receiver:
    host: str
    port: int
    name: str
    location: str
    lat: float
    lon: float
    users: int
    users_max: int
    snr: int
    low_hz: int
    high_hz: int
    ext_api: int = 0          # listener slots the owner allows non-browser clients


    def covers(self, khz: float) -> bool:
        return self.low_hz <= khz * 1000 <= self.high_hz

    @property
    def free(self) -> int:
        return self.users_max - self.users


def _host_port(url: str) -> tuple[str, int]:
    hit = re.match(r"^\w+://([^/:]+)(?::(\d+))?", url or "")
    if not hit:
        raise ValueError(url)
    return hit[1], int(hit[2] or DEFAULT_PORT)


def parse_directory(text: str) -> list[Receiver]:
    """The directory is a JavaScript array with trailing commas; parse it as JSON."""
    try:
        body = text[text.index("["): text.rindex("]") + 1]
        rows = json.loads(re.sub(r",\s*([\]}])", r"\1", body))
    except (ValueError, json.JSONDecodeError) as e:
        raise FeedError("the KiwiSDR directory is not in the expected shape") from e
    out = []
    for r in rows:
        try:
            if r.get("offline") != "no" or r.get("status") != "active":
                continue
            # "⏳ Limits" means a time limit is enforced; "⏳🚫 Limits" means it is off.
            if "⏳ Limits" in (r.get("sdr_hw") or ""):
                continue
            lat, lon = (float(v) for v in str(r["gps"]).strip("() ").split(","))
            low, high = (int(float(v)) for v in str(r.get("bands") or "0-30000000").split("-")[:2])
            snr_parts = [int(p) for p in str(r.get("snr") or "0").split(",") if p.strip().lstrip("-").isdigit()]
            # A receiver that allows no API clients accepts the connection and
            # closes it ~10 s later without sending audio; kiwirecorder then
            # reconnects forever, silently. 140 of 851 in the directory do this.
            ext_api = int(r.get("ext_api") or 0)
            if ext_api < 1:
                continue
            host, port = _host_port(r["url"])
            out.append(Receiver(host=host, port=port, name=str(r.get("name") or host),
                                location=str(r.get("loc") or ""), lat=lat, lon=lon,
                                users=int(r.get("users") or 0), users_max=int(r.get("users_max") or 0),
                                snr=snr_parts[-1] if snr_parts else 0, low_hz=low, high_hz=high,
                                ext_api=ext_api))
        except (KeyError, TypeError, ValueError):
            continue
    return out


async def directory(force: bool = False) -> list[Receiver]:
    cache = read_cache(DIRECTORY_CACHE)
    if force or not cache.get("text") or is_stale(cache, DIRECTORY_MAX_AGE_S):
        import aiohttp
        from utils.core.sanitizer import public_only_connector, read_capped
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30),
                                             headers={"User-Agent": USER_AGENT},
                                             connector=public_only_connector()) as s:
                async with s.get(DIRECTORY_URL) as resp:
                    if resp.status != 200:
                        raise FeedError(f"KiwiSDR directory answered HTTP {resp.status}")
                    text = (await read_capped(resp, 4_000_000)).decode("utf-8", "replace")
        except FeedError:
            raise
        except Exception as e:
            if cache.get("text"):
                log_warning(f"[radio] KiwiSDR directory unreachable, using the cached copy: {e}")
                return parse_directory(cache["text"])
            raise FeedError(f"KiwiSDR directory: {type(e).__name__}: {e}") from e
        receivers = parse_directory(text)          # validate before caching
        if not receivers:
            raise FeedError("the KiwiSDR directory listed no usable receivers")
        write_cache(DIRECTORY_CACHE, {"text": text})
        return receivers
    return parse_directory(cache["text"])


def choose(receivers: list[Receiver], khz: float, region: str = "na",
           avoid: tuple[str, ...] = (), n: int = 3) -> list[Receiver]:
    """The best few receivers for a frequency: in the region, covering it, with
    a free slot, ranked by signal-to-noise then free slots."""
    lat0, lat1, lon0, lon1 = REGIONS.get(region, REGIONS["na"])
    pool = [r for r in receivers
            if lat0 <= r.lat <= lat1 and lon0 <= r.lon <= lon1
            and r.covers(khz) and r.free >= 1 and r.host not in avoid]
    pool.sort(key=lambda r: (r.snr, r.free), reverse=True)
    return pool[:n]


def available() -> bool:
    return RECORDER.is_file()


def _die_with_parent() -> None:
    """Runs in the child before exec: the kernel sends SIGTERM when the process
    that started it dies. A recorder holds a slot on someone else's receiver,
    and one orphaned by a crash or a killed script kept two slots for six hours
    with nothing left to stop it."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG
    except Exception:
        pass


def _recorder_cmd(r: Receiver, khz: float, mode: str) -> list[str]:
    return [sys.executable, "-u", str(RECORDER), "-s", r.host, "-p", str(r.port),
            "-f", f"{khz:g}", "-m", mode.lower(), "-u", KIWI_USER, "-q",
            # info level: connection failures are logged there, and -q alone
            # makes a refused connection completely silent.
            "--log_level=info"]


async def _stop(proc: asyncio.subprocess.Process, grace: float = 8.0) -> None:
    """SIGINT first, so kiwirecorder closes its WAV properly; then kill."""
    if proc.returncode is not None:
        return
    try:
        proc.send_signal(signal.SIGINT)
        await asyncio.wait_for(proc.wait(), grace)
    except (asyncio.TimeoutError, ProcessLookupError):
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass


async def record(receiver: Receiver, khz: float, mode: str, seconds: float, out_dir: Path,
                 label: str, squelch_db: Optional[float] = None) -> list[Path]:
    """Record for `seconds` into out_dir. With a squelch, only openings are
    written, one file each; without, one file. Returns the WAVs written."""
    if not available():
        raise FeedError("kiwiclient is not installed — run tools/maintenance/fetch_radio_assets.py")
    # Absolute: the recorder runs in assets/kiwiclient/, and a relative
    # memory/radio/work sent every file it wrote into a folder that isn't there.
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    before = set(out_dir.glob("*.wav"))
    cmd = _recorder_cmd(receiver, khz, mode) + ["-d", str(out_dir), "--station", label]
    if squelch_db is not None:
        cmd += ["-T", f"{squelch_db:g}", "--squelch-tail", "3"]
    else:
        cmd += ["--tlimit", f"{int(seconds)}"]
    log_debug(f"[radio] recording {khz:g} kHz {mode} from {receiver.host} for {seconds:.0f}s")
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(KIWICLIENT),
                                                stdout=asyncio.subprocess.DEVNULL,
                                                stderr=asyncio.subprocess.PIPE,
                                                preexec_fn=_die_with_parent)
    refused, last = await _watch_stderr(proc, seconds + 20)
    quit_early = proc.returncode is not None
    await _stop(proc)
    written = sorted(set(out_dir.glob("*.wav")) - before)
    if refused and not written:
        raise FeedError(f"{receiver.host} {refused}")
    if quit_early and not written:
        # kiwirecorder exits 0 even when a thread of it crashed.
        raise FeedError(f"{receiver.host} recorder stopped early: {last or 'no output'}")
    # Drop a squelch opening that is only noise-length.
    return [p for p in written if p.stat().st_size > SAMPLE_RATE * 2 * 3]


_REFUSALS = ("Failed to connect", "server closed the connection", "Too busy", "too many users",
             "Password", "banned")


async def _watch_stderr(proc, deadline_s: float) -> tuple[str, str]:
    """Read kiwirecorder's log as it arrives (a full pipe would block it) until
    it exits or the deadline passes. A receiver that refuses us twice is given
    up on at once instead of after the whole window. Returns (why it refused
    or '', the last line it logged)."""
    strikes, reason, last = 0, "", ""
    loop = asyncio.get_running_loop()
    end = loop.time() + deadline_s
    while proc.returncode is None and loop.time() < end:
        try:
            line = await asyncio.wait_for(proc.stderr.readline(), max(0.1, end - loop.time()))
        except asyncio.TimeoutError:
            break
        if not line:
            await proc.wait()
            break
        text = line.decode("utf-8", "replace")
        if text.strip():
            last = text.strip()[-200:]
        hit = next((r for r in _REFUSALS if r.lower() in text.lower()), None)
        if hit:
            strikes += 1
            reason = f"refused the connection ({hit})"
            if strikes >= 2:
                break
    return reason, last


async def smeter(receiver: Receiver, khz: float, mode: str, seconds: float) -> list[tuple]:
    """Timestamped signal strength, ~6 readings a second: (datetime UTC, dBm).

    RSSI comes from the receiver itself, before its audio AGC — which levels
    the audio so thoroughly that loudness can't tell a beacon from noise.
    """
    from datetime import datetime, timezone
    if not available():
        raise FeedError("kiwiclient is not installed — run tools/maintenance/fetch_radio_assets.py")
    cmd = [sys.executable, "-u", str(RECORDER), "-s", receiver.host, "-p", str(receiver.port),
           "-f", f"{khz:g}", "-m", mode, "-u", KIWI_USER, "--S-meter=0", "--ts", "--tlimit", f"{int(seconds)}",
           # the frequency is the centre of the passband, so the carrier sits in it
           "--pbc"]
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(KIWICLIENT), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL,
                                                preexec_fn=_die_with_parent)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), seconds + 30)
    except asyncio.TimeoutError:
        await _stop(proc)
        out = b""
    readings = []
    for line in out.decode("utf-8", "replace").splitlines():
        m = re.match(r"(\d{2}-\w{3}-\d{4} \d{2}:\d{2}:\d{2}) UTC RSSI:\s*(-?\d+(?:\.\d+)?)", line.strip())
        if m:
            when = datetime.strptime(m.group(1), "%d-%b-%Y %H:%M:%S").replace(tzinfo=timezone.utc)
            readings.append((when, float(m.group(2))))
    if not readings:
        raise FeedError(f"{receiver.host} returned no signal readings")
    return readings


def open_stream(receiver: Receiver, khz: float, mode: str):
    """A live stream: kiwirecorder --nc writes raw s16le mono at 12 kHz to
    stdout. A plain Popen, because discord.py's FFmpegPCMAudio reads a real
    OS pipe; an asyncio StreamReader is not one."""
    import subprocess
    if not available():
        raise FeedError("kiwiclient is not installed — run tools/maintenance/fetch_radio_assets.py")
    return subprocess.Popen(_recorder_cmd(receiver, khz, mode) + ["--nc"], cwd=str(KIWICLIENT),
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            preexec_fn=_die_with_parent)


def first_audio(proc, timeout: float = 12.0) -> bool:
    """Block until the stream delivers audio, or give up. Run it in a thread."""
    import select
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    return bool(ready) and proc.poll() is None


def close_stream(proc) -> None:
    if proc.poll() is None:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(3)
        except Exception:
            proc.kill()
