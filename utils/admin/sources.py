"""Readers for what Kaiacord writes under memory/, knowledge_base/ and the system.

Every reader returns a dict carrying `source` — the files it read — so the page
can name where each number came from. Readers only open files for reading;
SQLite databases are opened read-only (`mode=ro`). Results are cached until one
of their source files changes (`Cache`).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[2]
MEM = ROOT / "memory"
KB = ROOT / "knowledge_base"


def rel(p) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def _jsonl(path: Path, limit: Optional[int] = None) -> list:
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rows.append(json.loads(ln))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows[-limit:] if limit else rows


def _json(path: Path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _ts(v) -> Optional[float]:
    """An epoch from a number, an ISO string or "YYYY-MM-DD HH:MM:SS"."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            continue
    return None


class Cache:
    """Memoise readers on the modification times of their sources."""

    def __init__(self):
        self._store: dict = {}

    def get(self, name: str, paths: Callable[[], list], fn: Callable[[], dict], ttl: float = 0.0) -> dict:
        sig = []
        for p in paths():
            try:
                st = os.stat(p)
                sig.append((str(p), st.st_mtime_ns, st.st_size))
            except OSError:
                sig.append((str(p), None, None))
        sig = tuple(sig)
        hit = self._store.get(name)
        if hit and hit[0] == sig and (not ttl or time.time() - hit[2] < ttl):
            return hit[1]
        started = time.time()
        try:
            val = fn()
        except Exception as e:              # a reader must not take the page down
            val = {"error": f"{type(e).__name__}: {e}"}
        val.setdefault("source", sorted({rel(p) for p, _, _ in sig}))
        val["read_ms"] = round((time.time() - started) * 1000, 1)
        val["as_of"] = time.time()
        self._store[name] = (sig, val, time.time())
        return val


# ── Kaia's state ─────────────────────────────────────────────────────

def mood() -> dict:
    rows = _jsonl(MEM / "mood_history.jsonl")
    state = _json(MEM / "mood_state.json", {})
    return {"series": [[r["ts"], r.get("v"), r.get("a"), r.get("e")] for r in rows if "ts" in r],
            "now": state, "n": len(rows)}


def desires() -> dict:
    return {"now": _json(MEM / "desires.json", {})}


def beliefs() -> dict:
    rows = _json(MEM / "beliefs.json", []) or []
    out = [{"topic": b.get("topic"), "position": (b.get("position") or "")[:300], "confidence": b.get("confidence"),
            "updated": b.get("last_updated"), "source": b.get("source"), "access": b.get("access_count", 0)}
           for b in rows if isinstance(b, dict)]
    return {"rows": out, "n": len(out),
            "confidence_hist": Counter(round(float(b["confidence"] or 0), 1) for b in out if b["confidence"] is not None)}


def anchors() -> dict:
    rows = _json(MEM / "anchors.json", []) or []
    out = [{"theme": a.get("theme"), "text": (a.get("anchor_text") or "")[:200], "user": a.get("user_name"),
            "weight": a.get("weight"), "effective": a.get("effective_weight"), "created": _ts(a.get("created_at")),
            "updated": _ts(a.get("updated_at")), "access": a.get("access_count", 0)} for a in rows if isinstance(a, dict)]
    return {"rows": out, "n": len(out)}


def growth() -> dict:
    """The growth log: beliefs formed and revised, insights, identity shifts, creations."""
    rows = _jsonl(MEM / "growth_log.jsonl")
    ev = []
    for r in rows:
        ts = _ts(r.get("ts"))
        if ts is None:
            continue
        label = r.get("topic") or r.get("title") or r.get("user") or r.get("kind") or ""
        text = r.get("new_position") or r.get("position") or r.get("summary") or r.get("content") or r.get("note") or ""
        ev.append([ts, r.get("type"), str(label)[:80], str(text)[:240]])
    return {"events": ev, "n": len(ev), "types": Counter(e[1] for e in ev)}


def relationships() -> dict:
    people = {}
    files = sorted(glob.glob(str(MEM / "relationships" / "*.json")))
    for f in files:
        if f.endswith(".impression.json"):
            continue
        uid = Path(f).stem
        data = _json(Path(f), [])
        events = data if isinstance(data, list) else (data or {}).get("events", [])
        evs = [[e.get("timestamp"), e.get("event_type"), e.get("emotional_weight"), (e.get("summary") or "")[:160]]
               for e in events if isinstance(e, dict) and e.get("timestamp")]
        imp = _json(Path(f.replace(".json", ".impression.json")), {}) or {}
        people[uid] = {"events": evs, "impression": imp.get("text", ""), "impression_written": imp.get("written")}
    names = _names()
    for uid, p in people.items():
        p["name"] = names.get(uid, uid)
    return {"people": people}


def _names() -> dict:
    """User id -> display name, from the user log folder names."""
    out = {}
    for d in glob.glob(str(KB / "user_logs" / "*_*")):
        base = os.path.basename(d)
        if base.startswith("forum_"):
            continue
        name, _, uid = base.rpartition("_")
        if uid.isdigit():
            out[uid] = name.replace("_", " ")
    return out


def monologue() -> dict:
    rows = _jsonl(MEM / "monologue_log.jsonl")
    out = [[r.get("epoch") or _ts(r.get("timestamp")), r.get("source"), (r.get("thought") or "")[:240]] for r in rows]
    return {"rows": [r for r in out if r[0]], "n": len(out)}


def self_docs() -> dict:
    out = {}
    for name in ("kaia_self_model.md", "identity_stream.md"):
        p = MEM / name
        try:
            out[name] = {"mtime": p.stat().st_mtime, "chars": p.stat().st_size,
                         "head": p.read_text(encoding="utf-8", errors="replace")[:1500]}
        except OSError:
            pass
    claims = _json(MEM / "self_claims.json", []) or []
    out["self_claims"] = [{"claim": c.get("claim"), "confidence": c.get("confidence")} for c in claims if isinstance(c, dict)]
    return out


def checks() -> dict:
    """Self-corrections, grounded-claim checks, hallucination flags, security trips."""
    sc = _jsonl(MEM / "self_corrections.jsonl")
    sec = _jsonl(MEM / "security_dogtag_replay.jsonl")
    return {"self_corrections": [[_ts(r.get("ts")), r.get("verdict"), (r.get("claim") or "")[:160]] for r in sc],
            # a rule carries the channel it fired in ("rule:1462…"); the rule is the category
            "security": [[_ts(r.get("timestamp")), r.get("trigger_type"), re.sub(r":\d{6,}$", "", str(r.get("matched_rule") or ""))]
                         for r in sec],
            "hallucination": [[_ts(r.get("timestamp")), (r.get("response_snippet") or "")[:160]]
                              for r in _jsonl(MEM / "hallucination_log.jsonl")]}


def generation() -> dict:
    """Per-reply records: strategy, retrieval confidence and nodes, length, time."""
    rows = _jsonl(MEM / "generation_log.jsonl")
    out = []
    for r in rows:
        ts = _ts(r.get("ts"))
        if ts is None or "response_time_s" not in r:
            continue
        out.append([ts, r.get("strategy"), r.get("category"), r.get("retrieval_confidence"), r.get("retrieval_nodes"),
                    r.get("response_len"), r.get("response_time_s")])
    return {"rows": out, "n": len(out)}


# ── Her words ───────────────────────────────────────────────────────

_TURN = re.compile(r"^\[(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\] ([^:\n]{1,60}): ?", re.M)


def voice() -> dict:
    """Per day, from her logged turns: replies, words, paragraphs, and the
    shapes that regressed in October (CLAUDE.md §5)."""
    try:
        from utils.core.safety_pipeline import PostGenerationSafetyPipeline as P
    except Exception:
        P = None
    days: dict = defaultdict(lambda: defaultdict(float))
    people: dict = defaultdict(lambda: defaultdict(int))
    for d in glob.glob(str(KB / "user_logs" / "*" / "interactions_*.md")):
        person = os.path.basename(os.path.dirname(d))
        if person.startswith("forum_"):
            continue
        try:
            text = open(d, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        marks = list(_TURN.finditer(text))
        for i, m in enumerate(marks):
            body = text[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(text)].strip()
            day, who = m.group(1), m.group(3).strip()
            pname = person.rpartition("_")[0].replace("_", " ")
            if who.lower() != "kaia":
                people[day][pname] += 1
                days[day]["user_turns"] += 1
                continue
            b = days[day]
            b["replies"] += 1
            words = len(body.split())
            paras = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
            b["words"] += words
            b["paras"] += len(paras)
            low = body.lower()
            b["a_quiet"] += bool(re.search(r"\ba quiet\b", low))
            b["tag"] += "speaking exclusively" in low
            b["cut"] += bool(re.search(r"\b(?:just|a|the|it['’]s|that['’]s)\. [a-z]", body))
            if P is not None:
                run = best = 0
                for s in P._sentences(body):
                    if P._litany_fragment(s):
                        run += 1
                        best = max(best, run)
                    else:
                        run = 0
                b["litany"] += best >= 4
    rows = []
    for day in sorted(days):
        b = days[day]
        n = b["replies"] or 0
        rows.append({"day": day, "replies": int(n), "user_turns": int(b["user_turns"]),
                     "words_per_reply": round(b["words"] / n, 1) if n else None,
                     "paras_per_reply": round(b["paras"] / n, 2) if n else None,
                     "words_per_para": round(b["words"] / b["paras"], 1) if b["paras"] else None,
                     "a_quiet_pct": round(100 * b["a_quiet"] / n, 1) if n else None,
                     "litany_pct": round(100 * b["litany"] / n, 1) if n else None,
                     "tag_pct": round(100 * b["tag"] / n, 1) if n else None,
                     "cut_pct": round(100 * b["cut"] / n, 1) if n else None})
    return {"days": rows, "people_by_day": {d: dict(v) for d, v in people.items()},
            "source": ["knowledge_base/user_logs/*/interactions_*.md (people only)"]}


def _voice_paths() -> list:
    return [p for p in glob.glob(str(KB / "user_logs" / "*" / "interactions_*.md")) if "/forum_" not in p]


# ── Corpus and index ────────────────────────────────────────────────

def corpus() -> dict:
    folders = {}
    for d in sorted(p for p in KB.iterdir() if p.is_dir()):
        n = size = 0
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.endswith(".md"):
                    n += 1
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        folders[d.name] = {"files": n, "mb": round(size / 1e6, 2), "indexed": not d.name.startswith(("_", "."))}
    manifest = _json(MEM / "rag_storage" / "file_manifest.json", {}) or {}
    types = Counter()
    for v in manifest.values():
        if isinstance(v, dict):
            types[v.get("type") or v.get("index_type") or "?"] += 1
    rag = {}
    for d in (MEM / "rag_storage").iterdir() if (MEM / "rag_storage").exists() else []:
        if d.is_dir():
            rag[d.name] = round(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) / 1e6, 1)
    dreams = defaultdict(lambda: defaultdict(int))
    for f in glob.glob(str(KB / "kaia_dreams" / "**" / "*.md"), recursive=True):
        m = re.search(r"dream_(\d{8})", os.path.basename(f))
        day = (datetime.strptime(m.group(1), "%Y%m%d").strftime("%Y-%m-%d") if m
               else datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d"))
        dreams[day][Path(f).parent.name] += 1
    return {"folders": folders, "manifest_entries": len(manifest), "manifest_types": dict(types),
            "rag_mb": rag, "dreams_by_day": {d: dict(v) for d, v in sorted(dreams.items())},
            "source": ["knowledge_base/*", "memory/rag_storage/file_manifest.json", "knowledge_base/kaia_dreams/**"]}


# ── Out in the world ────────────────────────────────────────────────

def social() -> dict:
    boards = _jsonl(MEM / "agent_boards" / "log.jsonl")
    forum = _jsonl(MEM / "forum_moderation_log.jsonl")
    def detail(r):
        text = r.get("text") or r.get("error") or r.get("why") or ""
        return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text))).strip()[:200]
    return {"boards": [[r.get("ts"), r.get("board"), r.get("event"), r.get("count"), detail(r),
                        r.get("where")] for r in boards if r.get("ts")],
            "forum": [[_ts(r.get("timestamp")), r.get("action"), r.get("forum_type"), (r.get("thread_title") or "")[:120]]
                      for r in forum],
            "source": ["memory/agent_boards/log.jsonl", "memory/forum_moderation_log.jsonl"]}


def radio() -> dict:
    db = MEM / "radio" / "local_ledger.sqlite3"
    out = {"events": [], "channels": []}
    if db.exists():
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        try:
            out["events"] = [list(r) for r in con.execute(
                "select ts, freq_hz, seconds, kind, (transcript is not null and transcript != '') "
                "from events order by ts")]
            out["channels"] = [list(r) for r in con.execute(
                "select freq_hz, band, service, label, hits, voice, data, hours from channels order by hits desc limit 40")]
        finally:
            con.close()
    eam = _json(MEM / "radio" / "eam_messages.json", {}) or {}
    out["eam_count"] = len(eam.get("messages", eam) if isinstance(eam, dict) else eam)
    return out


def records() -> dict:
    """Planned transitions with their measured verdict, and the partner graph."""
    rows = _jsonl(MEM / "records" / "transitions.jsonl")
    planned = []
    for r in rows:
        if r.get("ts") and r.get("status") in ("planned", None):
            check = r.get("check") or ""
            verdict = "locked" if check.startswith("locked") else "not locked" if check.startswith("NOT") else ""
            planned.append([r["ts"], r.get("kind"), r.get("mode"), r.get("source") or "", verdict,
                            r.get("beats"), (r.get("from") or "")[:80], (r.get("to") or "")[:80]])
    outcomes = Counter((r.get("kind"), r.get("status")) for r in rows if r.get("status") in ("done", "called_off"))
    g = _json(MEM / "records" / "graph.json", {}) or {}
    edges = g.get("edges", {})
    recs = g.get("records", {})
    deg = [len(edges.get(p, {})) for p in recs]
    sets = [{"n": len(st), "minutes": round(sum((recs.get(p) or {}).get("seconds") or 0 for p in st) / 60)}
            for st in g.get("sets", [])]
    return {"planned": planned, "outcomes": [[k, s, n] for (k, s), n in outcomes.items()],
            "edges": sum(len(v) for v in edges.values()), "records": len(recs),
            "with_partner": sum(1 for d in deg if d), "degree": deg, "sets": sets, "built": g.get("built"),
            "method": g.get("method"), "source": ["memory/records/transitions.jsonl", "memory/records/graph.json"]}


def art() -> dict:
    out = []
    for f in sorted(glob.glob(str(MEM / "art" / "*.json")), key=os.path.getmtime):
        d = _json(Path(f), {}) or {}
        intent = d.get("intent") or {}
        out.append({"id": Path(f).stem, "ts": os.path.getmtime(f), "title": intent.get("title"),
                    "palette": d.get("palette"), "symmetry": d.get("symmetry_k"), "render_s": d.get("render_time_s"),
                    "occupancy": d.get("occupancy"), "contrast": d.get("density_contrast"),
                    "image": Path(f).with_suffix(".png").exists()})
    return {"pieces": out}


def ttrpg() -> dict:
    chars = []
    for f in glob.glob(str(MEM / "ttrpg" / "characters" / "*.json")):
        d = _json(Path(f), {}) or {}
        chars.append({"name": d.get("character_name") or Path(f).stem, "player": d.get("user_name"), "level": d.get("level"),
                      "class": d.get("advanced_class") or d.get("class"), "location": d.get("location"),
                      "gil": d.get("gil"), "deaths": d.get("deaths"), "updated": d.get("last_updated")})
    fish = _json(MEM / "ttrpg" / "fishing_records.json", {}) or {}
    return {"characters": chars, "fishing_records": len(fish) if isinstance(fish, (dict, list)) else 0}


# ── The machine ─────────────────────────────────────────────────────

def bot_process() -> dict:
    """The bot's main process, if running (by command line, like kaia-tools does)."""
    out = {"running": False}
    try:
        import psutil
    except ImportError:
        return out
    for p in psutil.process_iter(["pid", "cmdline", "create_time", "memory_info", "ppid", "num_threads"]):
        cmd = p.info.get("cmdline") or []
        if len(cmd) >= 2 and cmd[-1].endswith("Kaiacord.py") and "python" in os.path.basename(cmd[0]):
            try:
                parent = psutil.Process(p.info["ppid"])
                if (parent.cmdline() or [""])[-1].endswith("Kaiacord.py"):
                    continue                    # a forked child (the scanner's watcher)
            except Exception:
                pass
            out = {"running": True, "pid": p.info["pid"], "started": p.info["create_time"],
                   "rss_mb": round(p.info["memory_info"].rss / 1e6), "threads": p.info["num_threads"],
                   "cpu_pct": p.cpu_percent(interval=0.2)}
            break
    out["source"] = ["/proc (psutil)"]
    return out


def system() -> dict:
    import psutil
    vm = psutil.virtual_memory()
    out = {"cpu_pct": psutil.cpu_percent(interval=0.2), "cpus": psutil.cpu_count(), "load": os.getloadavg(),
           "mem_total_gb": round(vm.total / 1e9, 1), "mem_used_gb": round((vm.total - vm.available) / 1e9, 1),
           "mem_pct": vm.percent, "swap_pct": psutil.swap_memory().percent,
           "disk_pct": psutil.disk_usage(str(ROOT)).percent, "boot": psutil.boot_time()}
    try:
        q = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=4)
        used, total, util, temp, power = [x.strip() for x in q.stdout.strip().split(",")]
        out["gpu"] = {"vram_used_mb": float(used), "vram_total_mb": float(total), "util_pct": float(util),
                      "temp_c": float(temp), "power_w": float(power)}
    except Exception:
        out["gpu"] = None
    out["source"] = ["/proc (psutil)", "nvidia-smi"]
    return out


def ollama() -> dict:
    import urllib.request
    out = {"up": False, "models": []}
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/ps", timeout=3) as r:
            data = json.loads(r.read())
        out["up"] = True
        for m in data.get("models", []):
            out["models"].append({"name": m.get("name"), "vram_mb": round((m.get("size_vram") or 0) / 1e6),
                                  "size_mb": round((m.get("size") or 0) / 1e6), "expires": m.get("expires_at"),
                                  "ctx": m.get("context_length")})
    except Exception as e:
        out["error"] = str(e)[:120]
    out["source"] = ["http://127.0.0.1:11434/api/ps"]
    return out


def ollama_journal(days: int = 14) -> dict:
    """Model loads (and the context size each was loaded at) from Ollama's journal."""
    out = {"loads": []}
    try:
        q = subprocess.run(["journalctl", "-u", "ollama", "--since", f"{days} days ago", "--no-pager", "-o", "short-unix",
                            "--grep", "n_ctx  |template selection"], capture_output=True, text=True, timeout=30)
    except Exception as e:
        return {"loads": [], "error": str(e)[:120], "source": ["journalctl -u ollama"]}
    pending = None
    for ln in q.stdout.splitlines():
        parts = ln.split(" ", 1)
        try:
            ts = float(parts[0])
        except (ValueError, IndexError):
            continue
        if (m := re.search(r"n_ctx\s+=\s+(\d+)", ln)):
            pending = (ts, int(m.group(1)))
        elif "template selection" in ln and pending:
            mm = re.search(r"model=registry\.ollama\.ai/library/([^\s]+)", ln)
            out["loads"].append([pending[0], mm.group(1) if mm else "?", pending[1]])
            pending = None
    out["source"] = ["journalctl -u ollama"]
    return out


def git_log(n: int = 30) -> dict:
    try:
        q = subprocess.run(["git", "-C", str(ROOT), "log", f"-{n}", "--format=%h\x1f%ct\x1f%s"],
                           capture_output=True, text=True, timeout=5)
        rows = [ln.split("\x1f") for ln in q.stdout.strip().splitlines()]
        return {"commits": [[r[0], float(r[1]), r[2]] for r in rows if len(r) == 3], "source": ["git log"]}
    except Exception as e:
        return {"commits": [], "error": str(e)[:120], "source": ["git log"]}


def config_summary() -> dict:
    """What is switched on, read from the config files (no secrets: .env is never read)."""
    try:
        import yaml
    except ImportError:
        return {}
    out = {}
    for name in ("default_config.yaml", "kaia.yaml"):
        try:
            out[name] = yaml.safe_load(open(ROOT / "config" / name, encoding="utf-8")) or {}
        except (OSError, ValueError):
            out[name] = {}
    merged = dict(out["default_config.yaml"])

    def deep(a, b):
        for k, v in (b or {}).items():
            a[k] = deep(dict(a.get(k) or {}), v) if isinstance(v, dict) and isinstance(a.get(k), dict) else v
        return a
    merged = deep(merged, out["kaia.yaml"])
    pick = lambda path: _dig(merged, path)
    flags = {k: pick(k) for k in ("forum.enabled", "bluesky.enabled", "x_twitter.enabled", "agent_boards.enabled",
                                   "unprompted.enabled", "unprompted.max_per_day", "dream_mode.enabled",
                                   "features.self_model_injection", "features.constitution_injection",
                                   "performance.max_context_tokens", "radio.enabled", "music.records_kaia_hands")}
    srcs = (pick("unprompted.sources") or {})
    return {"flags": flags, "unprompted_sources": srcs if isinstance(srcs, dict) else {},
            "source": ["config/default_config.yaml", "config/kaia.yaml"]}


def _dig(d, path):
    for part in path.split("."):
        if not isinstance(d, dict):
            return None
        d = d.get(part)
    return d
