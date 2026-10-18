"""KAIA // OPS: the log parser, the readers and the server, on synthetic files.

Nothing here reads the real log or memory/: every test points the readers at
a temporary tree.
"""
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import pytest

from utils.admin import logscan as L
from utils.admin import sources as S


def at(y, mo, d, h, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s).timestamp()


# ── dating lines ─────────────────────────────────────────────────────

def test_lines_are_dated_back_from_the_files_last_write_across_midnights():
    raw = ["[23:58:00] INFO: late", "[00:01:00] INFO: after midnight", "  continuation",
           "[09:00:00] INFO: morning", "[23:30:00] INFO: next night", "[00:10:00] INFO: last"]
    dated = L.date_lines(raw, at(2026, 10, 18, 0, 15))
    assert dated[-1][0] == at(2026, 10, 18, 0, 10)
    assert dated[4][0] == at(2026, 10, 17, 23, 30)
    assert dated[3][0] == at(2026, 10, 17, 9, 0)
    assert dated[1][0] == at(2026, 10, 17, 0, 1)
    assert dated[0][0] == at(2026, 10, 16, 23, 58)
    assert dated[2] == (dated[1][0], "", "  continuation")      # a traceback line keeps its parent's stamp


def test_a_last_line_later_in_the_day_than_the_files_mtime_is_from_yesterday():
    dated = L.date_lines(["[22:00:00] INFO: x"], at(2026, 10, 18, 9, 0))
    assert dated[0][0] == at(2026, 10, 17, 22, 0)


def test_shape_folds_numbers_and_quoted_text_so_repeats_group():
    a = L.shape("Disconnected from voice... Reconnecting in 1.62s for 'Ekco'")
    b = L.shape("Disconnected from voice... Reconnecting in 3s for 'Starkind'")
    assert a == b


# ── extracting events ────────────────────────────────────────────────

LOG = """[04:34:56] INFO: Unified logging system initialized
[04:34:56] INFO: Ensuring all models are flushed from VRAM
[04:40:00] DEBUG: [TOKEN_DEBUG] prompt_eval_count=16960 eval_count=129 num_ctx=32768
[04:40:00] ACTION: TOTAL processing for abys_17079: 20.97s
[04:40:01] DEBUG: Retrieval confidence: 0.79 (12 nodes)
[04:40:02] DEBUG: [chat_e1241608] Finished in 19.35s
[04:40:03] DEBUG: [rpg_combat_summary_0a1b2c3d] Finished in 3.10s
[04:44:22] INFO: Memory Audit: RSS 452.5 MB
[04:59:22] INFO: Memory Audit: RSS 1261.5 MB (malloc_trim gave back 41 MB → 1220 MB)
[05:00:00] SUCCESS: [unprompted] quip posted as 🪡 **Unspooling:** + Bluesky: how the sea keeps secrets
[05:01:00] SUCCESS: [unprompted] proactive posted as (no label): been quiet without you around.
[05:02:00] WARNING: [APOLOGY_GUARD] Trimmed offending clause, kept substance
[05:02:01] WARNING: [VERACITY GUARD] Sanitized 3 ellipsis-affect patterns inline (no retry).
[05:03:00] INFO: [scanner] voice on 460.5750 MHz (business), 63s: Southbound
[05:04:00] INFO: [records] planned: blend into Something
[05:04:01] WARNING: [records] voice thread 120 ms late
[05:05:00] INFO: Fast-path intent: SUMMARIZATION (general)
[05:06:00] ERROR: Failed to acquire data lock for RAG persistence (SHUTDOWN)
Traceback (most recent call last):
  File "x.py", line 1
[05:07:00] WARNING: Slow response: on_message took 61.2s
[06:00:00] INFO: Unified logging system initialized
[06:00:01] INFO: profile refresh continues
[07:00:00] INFO: Shutting down...
"""


def scan_of(text, mtime=None):
    sc = L.Scan()
    L.extract(sc, L.date_lines(text.rstrip("\n").split("\n"), mtime or at(2026, 10, 18, 7, 30)))
    return sc


def test_every_parsed_series_reads_its_line():
    sc = scan_of(LOG)
    assert sc.tokens == [(at(2026, 10, 18, 4, 40), 16960, 129, 32768)]
    assert sc.latency == [(at(2026, 10, 18, 4, 40), "abys_17079", 20.97)]
    assert sc.retrieval == [(at(2026, 10, 18, 4, 40, 1), 0.79, 12)]
    assert [(g[1], g[2]) for g in sc.gpu] == [("chat", 19.35), ("rpg_combat_summary", 3.10)]
    assert [(r[1], r[2]) for r in sc.rss] == [(452.5, 0), (1261.5, 41)]
    assert [(u[1], u[2]) for u in sc.unprompted] == [("quip", "🪡 Unspooling"), ("proactive", "(no label)")]
    assert [g[1] for g in sc.guards] == ["APOLOGY_GUARD", "VERACITY GUARD"]
    assert [(s[1], s[2]) for s in sc.scanner] == [("voice", 460.575)]
    assert [r[1] for r in sc.records] == ["blend"] and [v[1] for v in sc.voice_late] == [120]
    assert [(i[1], i[2]) for i in sc.intents] == [("SUMMARIZATION", "general")]
    assert [s[1] for s in sc.slow] == [61.2]
    assert len(sc.errors) == 1 and sc.errors[0][1] == "ERROR"
    assert len(sc.shutdowns) == 1


def test_a_boot_is_the_marker_followed_by_the_vram_flush_and_a_reinitialised_logger_is_not():
    sc = scan_of(LOG)
    assert [(b[1], b[2]) for b in sc.boots] == [(True, False), (False, False)]


def test_a_segment_with_test_fixtures_is_flagged():
    sc = scan_of("[01:00:00] INFO: Unified logging system initialized\n"
                 "[01:00:00] INFO: Ensuring all models are flushed from VRAM\n"
                 "[01:00:05] DEBUG: response from <MagicMock id='1'>\n")
    assert sc.boots[0][1:] == (True, True)


def test_levels_are_counted_per_hour():
    sc = scan_of(LOG)
    h4 = int(at(2026, 10, 18, 4) // 3600 * 3600)
    assert sc.levels_hour[h4]["DEBUG"] == 4 and sc.levels_hour[h4]["INFO"] == 4


# ── following the live log ───────────────────────────────────────────

def test_the_follower_reads_appended_lines_and_rescans_after_rotation(tmp_path):
    log = tmp_path / "kaiacord.log"
    log.write_text("[10:00:00] INFO: one\n[10:00:01] DEBUG: [TOKEN_DEBUG] prompt_eval_count=10 eval_count=2 num_ctx=32768\n")
    ls = L.LogScanner(tmp_path)
    ls.full_scan()
    assert ls.scan.seq == 2 and len(ls.scan.tokens) == 1
    with open(log, "a") as fh:
        fh.write("[10:00:02] DEBUG: [TOKEN_DEBUG] prompt_eval_count=11 eval_count=3 num_ctx=32768\n[10:00:03] INFO: half")
    assert ls.poll() == 1                      # a line without its newline waits
    assert [t[1] for t in ls.scan.tokens] == [10, 11]
    assert ls.scan.tokens[1][0] - ls.scan.tokens[0][0] == 1
    log.write_text("[11:00:00] INFO: fresh file\n")   # rotated: shorter than what was read
    ls.poll()
    assert ls.scan.seq == 1 and ls.scan.tokens == []


def test_the_follower_carries_the_date_across_midnight(tmp_path):
    log = tmp_path / "kaiacord.log"
    log.write_text("[23:59:58] INFO: before\n")
    os.utime(log, (at(2026, 10, 17, 23, 59, 59),) * 2)
    ls = L.LogScanner(tmp_path)
    ls.full_scan()
    with open(log, "a") as fh:
        fh.write("[00:00:03] DEBUG: [TOKEN_DEBUG] prompt_eval_count=5 eval_count=1 num_ctx=32768\n")
    ls.poll()
    assert ls.scan.tokens[0][0] == at(2026, 10, 18, 0, 0, 3)


# ── readers ──────────────────────────────────────────────────────────

@pytest.fixture
def tree(tmp_path, monkeypatch):
    mem, kb = tmp_path / "memory", tmp_path / "knowledge_base"
    (mem / "records").mkdir(parents=True)
    (mem / "radio").mkdir()
    (mem / "agent_boards").mkdir()
    (kb / "user_logs" / "Ekco_177").mkdir(parents=True)
    monkeypatch.setattr(S, "MEM", mem)
    monkeypatch.setattr(S, "KB", kb)
    return tmp_path


def test_records_reader_takes_the_measured_verdict_from_each_plan(tree):
    rows = [{"ts": 1, "status": "planned", "kind": "blend", "check": "locked: 8/8 bars agree", "source": "hand"},
            {"ts": 2, "status": "planned", "kind": "blend", "check": "NOT locked: 3/8"},
            {"ts": 3, "status": "planned", "kind": "cut", "check": ""},
            {"ts": 4, "status": "done", "kind": "blend"}, {"ts": 5, "status": "called_off", "kind": "cut"}]
    (S.MEM / "records" / "transitions.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    (S.MEM / "records" / "graph.json").write_text(json.dumps({"records": {"a": {"seconds": 120}, "b": {"seconds": 60}},
                                                             "edges": {"a": {"b": {}}}, "sets": [["a", "b"]], "method": 4}))
    out = S.records()
    assert [(p[1], p[3], p[4]) for p in out["planned"]] == [("blend", "hand", "locked"), ("blend", "", "not locked"),
                                                            ("cut", "", "")]
    assert sorted(map(tuple, out["outcomes"])) == [("blend", "done", 1), ("cut", "called_off", 1)]
    assert out["degree"] == [1, 0] and out["with_partner"] == 1 and out["sets"] == [{"n": 2, "minutes": 3}]


def test_radio_reader_opens_the_ledger_read_only(tree):
    db = S.MEM / "radio" / "local_ledger.sqlite3"
    con = sqlite3.connect(db)
    con.executescript("""create table channels (freq_hz integer primary key, band text, service text, label text,
        hits integer, voice integer, data integer, hours text);
        create table events (id integer primary key, freq_hz integer, ts real, seconds real, kind text, transcript text);
        insert into events (freq_hz, ts, seconds, kind, transcript) values (460575000, 10, 63, 'voice', 'Southbound');
        insert into events (freq_hz, ts, seconds, kind, transcript) values (144390000, 11, 1, 'data', null);""")
    con.commit()
    con.close()
    before = db.stat().st_mtime_ns
    out = S.radio()
    assert [(e[3], e[4]) for e in out["events"]] == [("voice", 1), ("data", 0)]
    assert db.stat().st_mtime_ns == before


def test_board_errors_are_shown_without_their_html(tree):
    (S.MEM / "agent_boards" / "log.jsonl").write_text(json.dumps(
        {"ts": 1, "board": "agent_room", "event": "error",
         "error": "HTTP 500: <html><head><title>500 Server Error</title></head><body><h1>Error</h1></body></html>"}) + "\n")
    detail = S.social()["boards"][0][4]
    assert "<" not in detail and "500 Server Error" in detail


def test_voice_reader_counts_her_shapes_per_day_and_leaves_people_alone(tree):
    log = S.KB / "user_logs" / "Ekco_177" / "interactions_202610.md"
    log.write_text(
        "[2026-10-18 09:00:00] Ekco: a quiet morning. a pattern. a habit. a tendency. a slip.\n\n"
        "[2026-10-18 09:00:10] Kaia: a quiet hum, ekco. a pattern identified. a tendency observed. "
        "a habit acknowledged. a slip noted.\n\nand the rest of it.\n\n"
        "[2026-10-18 09:01:00] Ekco: ok\n\n"
        "[2026-10-18 09:01:10] Kaia: it's just. a signal.\n")
    day = S.voice()["days"][0]
    assert day["day"] == "2026-10-18" and day["replies"] == 2 and day["user_turns"] == 2
    assert day["a_quiet_pct"] == 50.0 and day["litany_pct"] == 50.0 and day["cut_pct"] == 50.0
    assert S.voice()["people_by_day"]["2026-10-18"] == {"Ekco": 2}


def test_a_reader_that_fails_reports_the_error_instead_of_taking_the_page_down(tmp_path):
    c = S.Cache()
    out = c.get("x", lambda: [tmp_path / "nope"], lambda: 1 / 0)
    assert out["error"].startswith("ZeroDivisionError") and "source" in out


def test_the_cache_rereads_only_when_a_source_changes(tmp_path):
    f = tmp_path / "a.json"
    f.write_text("1")
    calls = []
    c = S.Cache()
    read = lambda: (calls.append(1), {"v": f.read_text()})[1]
    assert c.get("a", lambda: [f], read)["v"] == "1"
    c.get("a", lambda: [f], read)
    assert len(calls) == 1
    f.write_text("22")
    assert c.get("a", lambda: [f], read)["v"] == "22" and len(calls) == 2


# ── the server ───────────────────────────────────────────────────────

@pytest.fixture
def server(tree, monkeypatch):
    from utils.admin import server as srv
    logs = tree / "logs"
    logs.mkdir()
    (logs / "kaiacord.log").write_text(LOG)
    (S.MEM / "mood_history.jsonl").write_text(json.dumps({"ts": 1, "v": 0.2, "a": 0.9, "e": 0.5}) + "\n")
    st = srv.State()
    st.logs = L.LogScanner(logs)
    st.logs.full_scan()
    monkeypatch.setattr(srv, "STATE", st)
    httpd = srv.ThreadingHTTPServer(("127.0.0.1", 0), srv.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", st
    httpd.shutdown()


def fetch(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_the_server_answers_with_parsed_data_and_its_sources(server):
    base, _ = server
    code, body = fetch(base + "/api/logstats")
    data = json.loads(body)
    assert code == 200 and data["tokens"][0][1] == 16960 and data["source"]
    code, body = fetch(base + "/api/src/mood")
    data = json.loads(body)
    assert data["series"] == [[1, 0.2, 0.9, 0.5]] and "memory/mood_history.jsonl" in " ".join(data["source"])
    assert fetch(base + "/api/src/nothing")[0] == 404


def test_the_log_endpoint_filters_by_level_and_pattern(server):
    base, _ = server
    lines = json.loads(fetch(base + "/api/logs?level=WARNING")[1])["lines"]
    assert lines and all(l[2] in ("WARNING", "ERROR", "CRITICAL") for l in lines)
    lines = json.loads(fetch(base + "/api/logs?q=TOKEN_DEBUG")[1])["lines"]
    assert len(lines) == 1 and "prompt_eval_count" in lines[0][3]
    lines = json.loads(fetch(base + "/api/logs?q=%28unbalanced")[1])["lines"]   # a bad regex is a literal
    assert lines == []


def test_the_server_serves_nothing_outside_its_folders(server):
    base, _ = server
    assert fetch(base + "/static/../../utils/admin/server.py")[0] == 404
    assert fetch(base + "/static/%2e%2e/%2e%2e/.env")[0] == 404
    assert fetch(base + "/art/../../.env.png")[0] == 404
    assert fetch(base + "/art/nothex.png")[0] == 404


def test_a_check_cannot_be_started_from_another_origin(server):
    base, _ = server
    code, body = fetch(base + "/api/run/audit", "POST", {"Origin": "http://evil.example"})
    assert code == 403
    assert json.loads(fetch(base + "/api/run/nope", "POST")[1])["error"] == "no such check"


def test_every_check_is_a_read_only_invocation():
    from utils.admin.server import CHECKS
    for label, cmd in CHECKS.values():
        assert "--apply" not in cmd and "--fix" not in cmd, label


def test_answering_requests_writes_nothing(server, tree):
    """Read-only by default: no file is opened for writing while it serves."""
    base, _ = server
    writes = []
    armed = [True]

    def hook(event, args):
        if not armed[0]:
            return
        if event == "open" and len(args) > 1 and isinstance(args[1], str) and any(c in args[1] for c in "wax+"):
            writes.append(args[0])
        elif event in ("os.remove", "os.rename", "os.replace", "shutil.rmtree"):
            writes.append(args[0])
    sys.addaudithook(hook)
    try:
        for path in ("/api/logstats", "/api/logs", "/api/src/mood", "/api/src/records", "/api/src/radio",
                     "/api/src/social", "/api/src/growth", "/api/src/beliefs", "/api/checks", "/api/live"):
            fetch(base + path)
    finally:
        armed[0] = False
    assert [w for w in writes if str(tree) in str(w)] == []
