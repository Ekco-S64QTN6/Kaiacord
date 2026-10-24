"""KAIA // OPS — the admin dashboard's HTTP server, on 127.0.0.1 only.

Everything here is GET and reads files, except POST /api/run/<check>, which
runs one of the read-only diagnostics in CHECKS (a dry run or an audit; none of
them writes) in a niced subprocess, one at a time.

Three threads besides the server's own: the log follower (new lines once a
second), the machine sampler (CPU, memory, GPU, the bot's process, every
SAMPLE_S, kept for RING_S), and nothing else — every other number is read on
request and cached until its files change.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from utils.admin import sources as S
from utils.admin.logscan import LEVELS, LogScanner

ROOT = S.ROOT
ASSETS = ROOT / "assets" / "admin"
AVATAR = ROOT / "assets" / "kaia-avatar"
DEFAULT_PORT = 47433
SAMPLE_S = 3.0
RING_S = 24 * 3600
#: A process counts as a spike over either of these between two samples.
SPIKE_CPU = 150.0
SPIKE_RSS_MB = 4000

CHECKS = {
    "audit": ("Corpus audit (read-only)", [sys.executable, "tools/maintenance/audit_knowledge_base.py"]),
    "clean_dry": ("Kaia's turns: what the cleaner would change (dry run)",
                  [sys.executable, "tools/maintenance/clean_kaia_turns.py", "--show", "15"]),
    "health": ("Health check (Ollama, models, GPU, KB, config)", [sys.executable, "tools/maintenance/health_check.py"]),
}

READERS = {
    "mood": (S.mood, lambda: [S.MEM / "mood_history.jsonl", S.MEM / "mood_state.json"]),
    "desires": (S.desires, lambda: [S.MEM / "desires.json"]),
    "beliefs": (S.beliefs, lambda: [S.MEM / "beliefs.json"]),
    "anchors": (S.anchors, lambda: [S.MEM / "anchors.json"]),
    "growth": (S.growth, lambda: [S.MEM / "growth_log.jsonl"]),
    "relationships": (S.relationships, lambda: sorted((S.MEM / "relationships").glob("*.json"))),
    "monologue": (S.monologue, lambda: [S.MEM / "monologue_log.jsonl"]),
    "self": (S.self_docs, lambda: [S.MEM / "kaia_self_model.md", S.MEM / "identity_stream.md", S.MEM / "self_claims.json"]),
    "checks": (S.checks, lambda: [S.MEM / "self_corrections.jsonl", S.MEM / "security_dogtag_replay.jsonl",
                                  S.MEM / "hallucination_log.jsonl", S.MEM / "review_flags.jsonl"]),
    "generation": (S.generation, lambda: [S.MEM / "generation_log.jsonl"]),
    "voice": (S.voice, S._voice_paths),
    "corpus": (S.corpus, lambda: [S.MEM / "rag_storage" / "file_manifest.json", S.KB / "kaia_dreams"]),
    "social": (S.social, lambda: [S.MEM / "agent_boards" / "log.jsonl", S.MEM / "forum_moderation_log.jsonl"]),
    "radio": (S.radio, lambda: [S.MEM / "radio" / "local_ledger.sqlite3", S.MEM / "radio" / "eam_messages.json"]),
    "records": (S.records, lambda: [S.MEM / "records" / "transitions.jsonl", S.MEM / "records" / "graph.json"]),
    "art": (S.art, lambda: [S.MEM / "art"]),
    "ttrpg": (S.ttrpg, lambda: [S.MEM / "ttrpg" / "characters", S.MEM / "ttrpg" / "fishing_records.json"]),
    "journal": (S.ollama_journal, lambda: []),
    "git": (lambda: S.git_log(300), lambda: [ROOT / ".git" / "logs" / "HEAD"]),
    "config": (S.config_summary, lambda: [ROOT / "config" / "default_config.yaml", ROOT / "config" / "kaia.yaml"]),
}
#: Readers with no file to watch are re-read after this many seconds.
TTL = {"journal": 120.0, "corpus": 300.0}


class State:
    def __init__(self):
        self.logs = LogScanner(ROOT / "logs")
        self.cache = S.Cache()
        self.ring: deque = deque(maxlen=int(RING_S / SAMPLE_S))
        self.spikes: deque = deque(maxlen=300)
        self.started = time.time()
        self.bot: dict = {}
        self.ollama: dict = {}
        self.system: dict = {}
        self.run_lock = threading.Lock()
        self.runs: dict = {}

    # ── threads ──
    def follow(self):
        while True:
            try:
                self.logs.poll()
            except Exception:
                pass
            time.sleep(1.0)

    def sample(self):
        import psutil
        prev: dict = {}
        last = time.time()
        n = 0
        while True:
            n += 1
            now = time.time()
            dt = max(now - last, 1e-3)
            last = now
            cur = {}
            try:
                for p in psutil.process_iter(["pid", "name", "cpu_times", "memory_info", "cmdline"]):
                    info = p.info
                    ct = info.get("cpu_times")
                    if ct is None:
                        continue
                    ticks = ct.user + ct.system
                    key = (info["pid"], info["name"])
                    cur[key] = ticks
                    if key in prev:
                        cpu = 100 * (ticks - prev[key]) / dt
                        rss = (info.get("memory_info").rss if info.get("memory_info") else 0) / 1e6
                        if cpu >= SPIKE_CPU or (rss >= SPIKE_RSS_MB and not self._known_big(info)):
                            cmd = " ".join((info.get("cmdline") or [])[:6])[:160]
                            self.spikes.append([now, info["pid"], info["name"], round(cpu), round(rss), cmd])
            except Exception:
                pass
            prev = cur
            try:
                self.system = S.system()
                self.bot = S.bot_process()
                if n % 5 == 1:                 # Ollama logs every /api/ps; the bot already asks every 1.5 s
                    self.ollama = S.ollama()
                g = self.system.get("gpu") or {}
                self.ring.append([round(now, 1), self.system["cpu_pct"], self.system["mem_used_gb"],
                                  self.system["swap_pct"], g.get("vram_used_mb"), g.get("util_pct"),
                                  g.get("temp_c"), g.get("power_w"), self.bot.get("rss_mb"), self.bot.get("cpu_pct"),
                                  sum(m["vram_mb"] for m in self.ollama.get("models", []))])
            except Exception:
                pass
            time.sleep(SAMPLE_S)

    @staticmethod
    def _known_big(info) -> bool:
        """Ollama's runner and the bot are big by design; a spike is something else."""
        name = info.get("name") or ""
        cmd = " ".join(info.get("cmdline") or [])
        return name in ("ollama", "llama-server") or "ollama" in cmd or cmd.endswith("Kaiacord.py")

    # ── payloads ──
    def read(self, name: str) -> dict:
        fn, paths = READERS[name]
        return self.cache.get(name, paths, fn, ttl=TTL.get(name, 0.0))

    def logstats(self) -> dict:
        sc = self.logs.scan
        errs: dict = {}
        for ts, level, shape, text in sc.errors:
            e = errs.setdefault(shape, {"shape": shape, "level": level, "n": 0, "first": ts, "last": ts, "example": text})
            e["n"] += 1
            e["last"] = ts
            e["example"] = text
        return {"span": [sc.first_ts, sc.last_ts], "lines": sc.seq, "read_s": round(self.logs.read_seconds, 2),
                "levels_hour": sorted([h, c] for h, c in sc.levels_hour.items()),
                "tokens": sc.tokens, "latency": [[t, s] for t, _, s in sc.latency], "retrieval": sc.retrieval,
                "gpu": sc.gpu, "rss": sc.rss, "unprompted": sc.unprompted, "slow": sc.slow, "guards": sc.guards,
                "records": sc.records, "voice_late": sc.voice_late, "scanner": sc.scanner, "intents": sc.intents,
                "errors": sorted(errs.values(), key=lambda e: -e["last"]), "boots": sc.boots,
                "shutdowns": sc.shutdowns,
                "source": [S.rel(p) for p in self.logs.files()]}

    def log_lines(self, q: dict) -> dict:
        sc = self.logs.scan
        after = int(q.get("after", ["0"])[0] or 0)
        before = int(q.get("before", ["0"])[0] or 0)
        limit = min(int(q.get("limit", ["800"])[0] or 800), 5000)
        minlvl = q.get("level", [""])[0]
        text = q.get("q", [""])[0]
        since = float(q.get("since", ["0"])[0] or 0)
        until = float(q.get("until", ["0"])[0] or 0)
        lvl_ok = set(LEVELS[LEVELS.index(minlvl):]) if minlvl in LEVELS else None
        rx = None
        if text:
            try:
                rx = re.compile(text, re.I)
            except re.error:
                rx = re.compile(re.escape(text), re.I)
        out = []
        for seq, ts, level, line in reversed(sc.lines):
            if after and seq <= after:
                break
            if before and seq >= before:
                continue
            if until and ts is not None and ts > until:
                continue
            if since and ts is not None and ts < since:
                break
            if lvl_ok is not None and level not in lvl_ok:
                continue
            if rx is not None and not rx.search(line):
                continue
            out.append([seq, ts, level, line])
            if len(out) >= limit:
                break
        out.reverse()
        return {"lines": out, "seq": sc.seq, "kept_from": sc.lines[0][0] if sc.lines else 0,
                "source": [S.rel(self.logs.live_path)]}

    def live(self) -> dict:
        mood = S._json(S.MEM / "mood_state.json", {}) or {}
        return {"now": time.time(), "bot": self.bot, "ollama": self.ollama, "system": self.system,
                "mood": {k: mood.get(k) for k in ("valence", "arousal", "social_energy", "last_updated")},
                "seq": self.logs.scan.seq, "last_log": self.logs.scan.last_ts,
                "ring_tail": list(self.ring)[-1:] if self.ring else []}

    def run_check(self, name: str) -> dict:
        if name not in CHECKS:
            return {"error": "no such check"}
        if not self.run_lock.acquire(blocking=False):
            return {"error": "another check is running"}
        label, cmd = CHECKS[name]
        started = time.time()
        try:
            env = {**os.environ, "KAIACORD_LOG_FILE": str(ROOT / "logs" / "kaia_admin.log")}
            p = subprocess.run(["nice", "-n", "15", *cmd], cwd=ROOT, capture_output=True, text=True, timeout=600, env=env)
            out = {"name": name, "label": label, "cmd": " ".join(cmd[1:]), "rc": p.returncode,
                   "stdout": p.stdout[-60000:], "stderr": p.stderr[-8000:]}
        except subprocess.TimeoutExpired:
            out = {"name": name, "label": label, "rc": None, "stdout": "", "stderr": "timed out after 600 s"}
        finally:
            self.run_lock.release()
        out["started"], out["seconds"] = started, round(time.time() - started, 1)
        self.runs[name] = out
        return out


STATE: State = None  # type: ignore[assignment]
_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".png": "image/png",
          ".svg": "image/svg+xml", ".json": "application/json", ".webp": "image/webp"}


class Handler(BaseHTTPRequestHandler):
    server_version = "KaiaOps/1"

    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "max-age=300" if cache else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, default=str, separators=(",", ":")).encode(), "application/json")

    def _file(self, base: Path, rel: str):
        p = (base / rel).resolve()
        if not str(p).startswith(str(base.resolve()) + os.sep) or not p.is_file():
            return self._send(404, b"not found", "text/plain")
        self._send(200, p.read_bytes(), _TYPES.get(p.suffix, "application/octet-stream"), cache=p.suffix != ".html")

    def do_GET(self):
        u = urlparse(self.path)
        path, q = u.path, parse_qs(u.query)
        try:
            if path in ("/", "/index.html"):
                return self._file(ASSETS, "index.html")
            if path == "/api/ping":
                return self._json({"ok": True, "app": "kaia-ops", "pid": os.getpid()})
            if path == "/api/live":
                return self._json(STATE.live())
            if path == "/api/logs":
                return self._json(STATE.log_lines(q))
            if path == "/api/logstats":
                return self._json(STATE.logstats())
            if path == "/api/ring":
                return self._json({"rows": list(STATE.ring), "spikes": list(STATE.spikes), "started": STATE.started,
                                   "sample_s": SAMPLE_S, "source": ["/proc (psutil)", "nvidia-smi", "ollama /api/ps"]})
            if path == "/api/checks":
                return self._json({"checks": {k: v[0] for k, v in CHECKS.items()}, "runs": STATE.runs})
            if path.startswith("/api/src/"):
                name = path.rsplit("/", 1)[1]
                if name not in READERS:
                    return self._json({"error": "no such source"}, 404)
                return self._json(STATE.read(name))
            if (m := re.fullmatch(r"/art/([0-9a-f]{6,40})\.png", path)):
                return self._file(S.MEM / "art", m.group(1) + ".png")
            if path.startswith("/kaia/"):
                return self._file(AVATAR, path[len("/kaia/"):])
            if path.startswith("/static/"):
                return self._file(ASSETS, path[len("/static/"):])
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        path = urlparse(self.path).path
        # Same-origin only: a page elsewhere cannot start a check here.
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and origin.split("//", 1)[-1] != host:
            return self._json({"error": "cross-origin"}, 403)
        if (m := re.fullmatch(r"/api/run/(\w+)", path)):
            return self._json(STATE.run_check(m.group(1)))
        self._send(404, b"not found", "text/plain")


def serve(port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    global STATE
    STATE = State()
    STATE.logs.full_scan()
    threading.Thread(target=STATE.follow, daemon=True, name="ops-follow").start()
    threading.Thread(target=STATE.sample, daemon=True, name="ops-sample").start()
    srv = None
    for p in (port, 0):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), Handler)
            break
        except OSError:
            continue
    if srv is None:
        raise OSError("no port")
    srv.daemon_threads = True
    return srv
