// KAIA // OPS — tabs, cards and the data that feeds them.
// Each card names the artefact its numbers came from in its footer; a TABLE
// button shows the rows behind the chart. Nothing is drawn that was not read.
"use strict";
const { Fmt, Stat, Tip, esc, sw, TimeChart, Bars, Hist, Heat, Strips, HBars, Spark, CSSV } = window.KC;
const $ = (s, el = document) => el.querySelector(s);
const PAL = () => ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6"].map(CSSV);
const OTHER = () => CSSV("--other");
const DAY = 86400;
const REST = "(the rest)";

// ── data ────────────────────────────────────────────────────────────
const D = { src: {}, logstats: null, live: null, ring: null, inflight: {} };
async function get(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}
async function src(name, force) {
  if (D.src[name] && !force) return D.src[name];
  if (!D.inflight[name]) D.inflight[name] = get(`/api/src/${name}`).then(v => { D.src[name] = v; delete D.inflight[name]; return v; }).catch(e => { delete D.inflight[name]; throw e; });
  return D.inflight[name];
}
async function logstats(force) {
  if (D.logstats && !force) return D.logstats;
  D.logstats = await get("/api/logstats"); return D.logstats;
}
function oops(e) { const el = $("#err"); el.textContent = String(e.message || e); el.style.display = "block"; clearTimeout(oops.t); oops.t = setTimeout(() => el.style.display = "none", 8000); console.error(e); }

// ── range filter ────────────────────────────────────────────────────
const RANGES = { "24H": DAY, "7D": 7 * DAY, "30D": 30 * DAY, "ALL": null };
let RANGE = "7D";
try { RANGE = localStorage.getItem("ops.range") || RANGE; } catch (e) {}
const range = () => { const s = RANGES[RANGE]; const now = Date.now() / 1000; return s ? [now - s, now] : [null, null]; };
const inRange = (ts, r = range()) => ts != null && (r[0] == null || ts >= r[0]) && (r[1] == null || ts <= r[1] + 60);

// ── helpers ─────────────────────────────────────────────────────────
// Colours follow the entity: ranks are taken over all the data, never the
// filtered range, so a range change does not repaint a series.
function palette(keysByCount, n = 6) {
  const P = PAL(), m = new Map();
  keysByCount.slice(0, n).forEach((k, i) => m.set(k, P[i]));
  return k => m.get(k) || OTHER();
}
function rank(items, keyOf) { const c = new Map(); for (const it of items) { const k = keyOf(it); c.set(k, (c.get(k) || 0) + 1); } return [...c.entries()].sort((a, b) => b[1] - a[1]).map(e => e[0]); }
function daysBetween(t0, t1) {
  const out = []; const d = new Date(t0 * 1000); d.setHours(0, 0, 0, 0);
  for (let t = d.getTime() / 1000; t <= t1; t += DAY) { const dd = new Date(t * 1000); dd.setHours(0, 0, 0, 0); const key = Stat.dayKey(dd.getTime() / 1000); if (!out.length || out[out.length - 1].key !== key) out.push({ key, ts: dd.getTime() / 1000, label: Fmt.day(dd.getTime() / 1000), title: dd.toDateString() }); }
  return out;
}
// events → stacked daily bars. top: ordered keys that get their own series.
function byDay(events, tsOf, keyOf, top, r = range()) {
  const ev = events.filter(e => inRange(tsOf(e), r));
  if (!ev.length) return { cats: [], series: [], n: 0 };
  const t0 = r[0] ?? Math.min(...ev.map(tsOf)), t1 = r[1] ?? Math.max(...ev.map(tsOf));
  const cats = daysBetween(t0, t1), idx = new Map(cats.map((c, i) => [c.key, i]));
  const color = palette(top, 6), own = new Set(top.slice(0, 6));
  const ser = new Map();
  for (const e of ev) {
    let k = keyOf(e); if (!own.has(k)) k = REST;
    if (!ser.has(k)) ser.set(k, new Array(cats.length).fill(0));
    const i = idx.get(Stat.dayKey(tsOf(e))); if (i != null) ser.get(k)[i]++;
  }
  const order = top.slice(0, 6).filter(k => ser.has(k)).concat(ser.has(REST) ? [REST] : []);
  return { cats, series: order.map(k => ({ name: k, color: k === REST ? OTHER() : color(k), values: ser.get(k) })), n: ev.length };
}
function legend(el, items) { el.innerHTML = items.map(i => `<span>${sw(i.color)}${esc(i.name)}</span>`).join(""); }
function srcLine(v, extra = "") {
  if (!v) return "";
  const s = (v.source || []).map(x => `<code>${esc(x)}</code>`).join(" · ");
  return `source: ${s}${extra ? " · " + extra : ""}${v.read_ms != null ? ` · read ${v.read_ms} ms` : ""}${v.as_of ? ` · as of ${new Date(v.as_of * 1000).toTimeString().slice(0, 8)}` : ""}`;
}
function tableHTML(cols, rows, limit = 500) {
  const head = cols.map(c => `<th class="${c.n ? "n" : ""}">${esc(c.h)}</th>`).join("");
  const body = rows.slice(-limit).reverse().map(r => "<tr>" + cols.map((c, i) => { const v = c.f ? c.f(r[i], r) : r[i]; return `<td class="${c.n ? "n" : ""}${c.w ? " w" : ""}">${c.raw ? v : esc(v ?? "")}</td>`; }).join("") + "</tr>").join("");
  return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${rows.length > limit ? `<div class="dim" style="padding:4px 8px">newest ${limit} of ${Fmt.n(rows.length)} rows</div>` : ""}`;
}

// ── cards and tiles ─────────────────────────────────────────────────
function card(root, { title, span = 6, h = 180, cls, noPlot }) {
  const el = document.createElement("section"); el.className = `card span${span}` + (cls ? " " + cls : "");
  el.innerHTML = `<header><h3>${esc(title)}</h3><div class="legend"></div><div class="tools"></div></header><div class="sub"></div>${noPlot ? "" : `<div class="plot" style="height:${h}px"></div>`}<div class="tblwrap"></div><div class="body"></div><footer></footer>`;
  root.appendChild(el);
  const c = { el, plot: $(".plot", el), legendEl: $(".legend", el), subEl: $(".sub", el), body: $(".body", el), foot: $("footer", el), tbl: $(".tblwrap", el) };
  c.legend = items => legend(c.legendEl, items);
  c.sub = html => c.subEl.innerHTML = html;
  c.source = (v, extra) => c.foot.innerHTML = srcLine(v, extra);
  c.table = (cols, rows) => {
    c._tbl = [cols, rows];
    if (!$(".tbtn", el)) {
      const b = document.createElement("button"); b.className = "btn tbtn"; b.textContent = "TABLE"; b.title = "the rows behind this chart";
      b.onclick = () => { el.classList.toggle("tbl"); b.classList.toggle("on"); if (el.classList.contains("tbl")) c.tbl.innerHTML = tableHTML(...c._tbl); };
      $(".tools", el).appendChild(b);
    }
    if (el.classList.contains("tbl")) c.tbl.innerHTML = tableHTML(cols, rows);
  };
  return c;
}
function tile(root, { key, span = 3, title }) {
  const el = document.createElement("div"); el.className = `tile span${span}`; if (title) el.title = title;
  el.innerHTML = `<div class="k">${esc(key)}</div><div class="v">—</div><div class="d"></div><div class="spk"></div><div class="flag"></div>`;
  root.appendChild(el);
  const sp = new Spark($(".spk", el), { height: 26 });
  return {
    el, spark: sp,
    set(v, unit, d, state, flag) {
      $(".v", el).innerHTML = `${v}${unit ? `<small>${unit}</small>` : ""}`; $(".d", el).innerHTML = d || "";
      el.classList.remove("ok", "warn", "bad"); if (state) el.classList.add(state);
      $(".flag", el).textContent = flag || (state === "bad" ? "✖ ALERT" : state === "warn" ? "▲ WATCH" : state === "ok" ? "● OK" : "");
    },
  };
}
const sect = (root, t, small) => { const el = document.createElement("div"); el.className = "sect"; el.innerHTML = `${esc(t)}${small ? `<small>${esc(small)}</small>` : ""}`; root.appendChild(el); };

// ── tabs ────────────────────────────────────────────────────────────
const TABS = [];
function tab(id, label, build, refresh, opts = {}) { TABS.push({ id, label, build, refresh, built: false, ...opts }); }
let CUR = null;
function show(id) {
  const t = TABS.find(x => x.id === id) || TABS[0]; CUR = t;
  document.querySelectorAll(".tab").forEach(e => e.classList.toggle("on", e.dataset.id === t.id));
  document.querySelectorAll(".view").forEach(e => e.classList.toggle("on", e.id === "v-" + t.id));
  $(".seg").style.visibility = t.noRange ? "hidden" : "visible";
  const root = $("#v-" + t.id);
  if (!t.built) { t.built = true; t.ctx = {}; t.build(root, t.ctx); }
  Promise.resolve(t.refresh(t.ctx)).catch(oops);
  try { localStorage.setItem("ops.tab", t.id); } catch (e) {}
  history.replaceState(null, "", "#" + t.id);
}
function nav() {
  const n = $("#nav");
  TABS.forEach((t, i) => {
    const b = document.createElement("div"); b.className = "tab"; b.dataset.id = t.id; b.innerHTML = `${t.label}<kbd>${i + 1}</kbd>`; b.onclick = () => show(t.id); n.appendChild(b);
    const v = document.createElement("div"); v.className = "view"; v.id = "v-" + t.id; $("#main").appendChild(v);
  });
  const seg = document.createElement("div"); seg.className = "seg"; seg.innerHTML = `<span class="lbl">RANGE</span>` + Object.keys(RANGES).map(k => `<button data-r="${k}" class="${k === RANGE ? "on" : ""}">${k}</button>`).join("");
  seg.onclick = e => { const r = e.target.dataset.r; if (!r) return; RANGE = r; try { localStorage.setItem("ops.range", r); } catch (x) {} seg.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.r === r)); if (CUR) Promise.resolve(CUR.refresh(CUR.ctx)).catch(oops); };
  n.appendChild(seg);
  addEventListener("keydown", e => {
    if (e.target.matches("input, textarea")) return;
    const i = parseInt(e.key, 10); if (i >= 1 && i <= TABS.length) show(TABS[i - 1].id);
  });
}

// ── header (live) ───────────────────────────────────────────────────
function pill(id, state, html) { const el = $("#" + id); const d = $(".dot", el); if (d) d.className = "dot " + (state || ""); $("b", el).innerHTML = html; }
function meter(id, frac, hot) { const el = $(`#${id} .meter`); el.classList.toggle("hot", !!hot); $("i", el).style.width = Math.max(0, Math.min(100, frac * 100)) + "%"; }
async function tickLive() {
  try {
    const L = D.live = await get("/api/live");
    const b = L.bot || {};
    pill("p-bot", b.running ? "on" : "off", b.running ? `pid ${b.pid} · up ${Fmt.dur(L.now - b.started)} · ${Fmt.n(b.rss_mb)} MB` : "NOT RUNNING");
    const o = L.ollama || {}, ms = o.models || [];
    pill("p-ollama", o.up ? (ms.length ? "on" : "warn") : "off", o.up ? (ms.length ? ms.map(m => `${esc(m.name.replace(/:latest$/, ""))} ${Fmt.n(m.vram_mb / 1024, 1)}G`).join(" · ") : "up · nothing resident") : "DOWN");
    const g = (L.system || {}).gpu;
    if (g) { const f = g.vram_used_mb / g.vram_total_mb; meter("p-vram", f, f > .95); $("#p-vram b").textContent = `${Fmt.n(g.vram_used_mb / 1024, 1)}/${Fmt.n(g.vram_total_mb / 1024, 1)}G · ${Fmt.n(g.util_pct)}% · ${Fmt.n(g.temp_c)}°C`; $("#p-vram").classList.toggle("bad", g.temp_c >= 85); }
    const s = L.system || {};
    if (s.cpu_pct != null) { meter("p-cpu", s.cpu_pct / 100, s.cpu_pct > 90); $("#p-cpu b").textContent = `${Fmt.n(s.cpu_pct)}% · load ${s.load[0].toFixed(1)}`; }
    if (s.mem_pct != null) { meter("p-mem", s.mem_pct / 100, s.mem_pct > 90); $("#p-mem b").textContent = `${Fmt.n(s.mem_used_gb, 1)}/${Fmt.n(s.mem_total_gb, 0)}G · swap ${Fmt.n(s.swap_pct)}%`; }
    const m = L.mood || {};
    if (m.valence != null) $("#p-mood b").textContent = `v ${m.valence.toFixed(2)} · a ${m.arousal.toFixed(2)} · e ${m.social_energy.toFixed(2)} · ${Fmt.ago(m.last_updated)}`;
    const age = L.now - (L.last_log || 0);
    pill("p-log", !L.last_log ? "off" : age < 1800 ? "on" : "warn", L.last_log ? Fmt.ago(L.last_log) : "—");
  } catch (e) { pill("p-bot", "off", "dashboard server unreachable"); }
}
setInterval(() => { $("#clock").textContent = new Date().toTimeString().slice(0, 8); }, 1000);

// ════════════════════════════════════════════════════════════════════
// OVERVIEW
// ════════════════════════════════════════════════════════════════════
tab("ov", "OVERVIEW", (root, x) => {
  sect(root, "LAST 24 HOURS", "tiles are fixed to the last 24 h; every tile names its source on hover");
  x.t = {
    replies: tile(root, { key: "REPLIES", title: "lines 'TOTAL processing for <user>' in logs/kaiacord.log" }),
    lat: tile(root, { key: "REPLY LATENCY P50", title: "TOTAL processing seconds, logs/kaiacord.log" }),
    tok: tile(root, { key: "PROMPT TOKENS P90", title: "[TOKEN_DEBUG] prompt_eval_count, logs/kaiacord.log; the limit is num_ctx on the same line" }),
    ret: tile(root, { key: "RETRIEVAL CONFIDENCE P50", title: "'Retrieval confidence: X (N nodes)', logs/kaiacord.log" }),
    guards: tile(root, { key: "GUARD LINES", title: "log lines tagged [*_GUARD] etc., logs/kaiacord.log — lines, not distinct replies" }),
    err: tile(root, { key: "ERRORS", title: "ERROR/CRITICAL lines, logs/kaiacord.log" }),
    unp: tile(root, { key: "UNPROMPTED POSTS", title: "'[unprompted] <source> posted as', logs/kaiacord.log" }),
    scan: tile(root, { key: "SCANNER CATCHES", title: "events, memory/radio/local_ledger.sqlite3" }),
  };
  x.mood = card(root, { title: "MOOD · LAST 72 H", span: 6, h: 150 });
  x.now = card(root, { title: "HER STATE NOW", span: 3, h: 150 });
  x.mach = card(root, { title: "MACHINE · SINCE THIS DASHBOARD STARTED", span: 3, h: 150 });
  x.act = card(root, { title: "LOG ACTIVITY · LINES PER HOUR × DAY", span: 8, h: 210 });
  x.errs = card(root, { title: "RECENT ERROR SHAPES", span: 4, noPlot: true });
  x.boots = card(root, { title: "BOOTS · REAL ONES ARE FOLLOWED BY THE VRAM FLUSH LINE", span: 6, noPlot: true });
  x.git = card(root, { title: "RECENT COMMITS", span: 6, noPlot: true });
  x.cMood = new TimeChart(x.mood.plot, { y: { min: -0.1, max: 1, fmt: v => v.toFixed(1) } });
  x.cNow = new HBars(x.now.plot, { max: 1, fmt: v => v.toFixed(2), labelW: 112 });
  x.cMach = new TimeChart(x.mach.plot, { y: { min: 0, max: 100, fmt: v => v + "%" } });
  x.cAct = new Heat(x.act.plot, { labelW: 64, colLabelW: 30 });
}, async x => {
  const [ls, mood, desires, radio, git] = await Promise.all([logstats(true), src("mood"), src("desires"), src("radio"), src("git")]);
  const now = Date.now() / 1000, d0 = now - DAY, r24 = [d0, now];
  const lat = ls.latency.filter(p => p[0] >= d0), tok = ls.tokens.filter(p => p[0] >= d0), ret = ls.retrieval.filter(p => p[0] >= d0);
  const hourly = (ev, tsi = 0) => { const out = []; for (let h = Math.floor(d0 / 3600) * 3600; h <= now; h += 3600) out.push([h, ev.filter(e => e[tsi] >= h && e[tsi] < h + 3600).length]); return out; };
  x.t.replies.set(Fmt.n(lat.length), "", `<b>${Fmt.n(ls.latency.filter(p => p[0] >= d0 - DAY && p[0] < d0).length)}</b> the 24 h before`); x.t.replies.spark.set(hourly(lat));
  const p50 = Stat.q(lat.map(p => p[1]), .5), p90 = Stat.q(lat.map(p => p[1]), .9);
  x.t.lat.set(p50 == null ? "—" : p50.toFixed(1), "s", `p90 <b>${p90 == null ? "—" : p90.toFixed(1)} s</b> · max <b>${lat.length ? Math.max(...lat.map(p => p[1])).toFixed(1) : "—"} s</b>`); x.t.lat.spark.set(lat.map(p => [p[0], p[1]]));
  const tp90 = Stat.q(tok.map(p => p[1]), .9), ctx = tok.length ? tok[tok.length - 1][3] : null;
  const frac = tp90 && ctx ? tp90 / ctx : 0;
  x.t.tok.set(tp90 == null ? "—" : Fmt.n(tp90), "", ctx ? `of num_ctx <b>${Fmt.n(ctx)}</b> (${Fmt.pct(100 * frac)}) · reply p90 <b>${Fmt.n(Stat.q(tok.map(p => p[2]), .9))}</b>` : "no turns", frac > .95 ? "bad" : frac > .85 ? "warn" : tok.length ? "ok" : "");
  x.t.tok.spark.set(tok.map(p => [p[0], p[1]]), { threshold: ctx, min: 0, max: ctx ? ctx * 1.05 : null });
  const rp = Stat.q(ret.map(p => p[1]), .5);
  x.t.ret.set(rp == null ? "—" : rp.toFixed(2), "", `${Fmt.n(ret.length)} retrievals · nodes p50 <b>${Fmt.n(Stat.q(ret.map(p => p[2]), .5))}</b>`); x.t.ret.spark.set(ret.map(p => [p[0], p[1]]));
  const g = ls.guards.filter(p => p[0] >= d0); const gtop = rank(g, e => e[1]).slice(0, 2);
  x.t.guards.set(Fmt.n(g.length), "", gtop.length ? gtop.map(k => `<b>${esc(k)}</b> ${g.filter(e => e[1] === k).length}`).join(" · ") : "none"); x.t.guards.spark.set(hourly(g));
  const errs = ls.errors.reduce((a, e) => a + (e.last >= d0 ? 1 : 0), 0); const errLines = []; for (const e of ls.errors) if (e.last >= d0) errLines.push(e);
  const eCount = errLines.reduce((a, e) => a + e.n, 0);
  x.t.err.set(Fmt.n(errs), errs === 1 ? "shape" : "shapes", errs ? `newest ${Fmt.ago(errLines[0].last)}: <b>${esc(errLines[0].shape.slice(0, 50))}</b>` : "none in 24 h", errs ? "bad" : "ok");
  const u = ls.unprompted.filter(p => p[0] >= d0);
  x.t.unp.set(Fmt.n(u.length), "", rank(u, e => e[1]).map(k => `${esc(k)} <b>${u.filter(e => e[1] === k).length}</b>`).join(" · ") || "none"); x.t.unp.spark.set(hourly(u));
  const sc = radio.events.filter(e => e[0] >= d0);
  x.t.scan.set(Fmt.n(sc.length), "", ["voice", "data", "carrier", "seen", "noise"].map(k => `${k} <b>${sc.filter(e => e[3] === k).length}</b>`).join(" · ")); x.t.scan.spark.set(hourly(sc));
  // mood
  const P = PAL(), t72 = now - 3 * DAY;
  const ms = mood.series.filter(r => r[0] >= t72);
  x.cMood.set([{ name: "valence", color: P[0], data: ms.map(r => [r[0], r[1]]), gap: 6 * 3600 }, { name: "arousal", color: P[1], data: ms.map(r => [r[0], r[2]]), gap: 6 * 3600 }, { name: "energy", color: P[2], data: ms.map(r => [r[0], r[3]]), gap: 6 * 3600 }], { range: [t72, now] });
  x.mood.legend([{ name: "valence", color: P[0] }, { name: "arousal", color: P[1] }, { name: "energy", color: P[2] }]);
  x.mood.source(mood, `${Fmt.n(ms.length)} of ${Fmt.n(mood.n)} rows`);
  const mn = mood.now || {}, dn = desires.now || {};
  x.cNow.set([["valence", mn.valence], ["arousal", mn.arousal], ["social energy", mn.social_energy], ["need: social", dn.social], ["need: intellect", dn.intellectual], ["need: creative", dn.creative], ["need: rest", dn.rest]]
    .filter(r => r[1] != null).map((r, i) => ({ label: r[0], value: r[1], color: i < 3 ? P[0] : P[3] })));
  x.now.sub(`mood ${Fmt.ago(mn.last_updated)} · needs ${Fmt.ago(dn.last_updated)} · ${Fmt.n(mn.interaction_count_today)} interactions today`);
  x.now.foot.innerHTML = "source: <code>memory/mood_state.json</code> · <code>memory/desires.json</code>";
  // machine
  const ring = D.ring = await get("/api/ring");
  x.cMach.set([{ name: "CPU", color: P[0], data: ring.rows.map(r => [r[0], r[1]]) }, { name: "GPU util", color: P[2], data: ring.rows.map(r => [r[0], r[5]]) },
    { name: "VRAM", color: P[3], data: ring.rows.map(r => [r[0], r[4] != null && D.live?.system?.gpu ? 100 * r[4] / D.live.system.gpu.vram_total_mb : null]) }], { y: { min: 0, max: 100, fmt: v => v + "%" } });
  x.mach.legend([{ name: "CPU", color: P[0] }, { name: "GPU util", color: P[2] }, { name: "VRAM", color: P[3] }]);
  x.mach.source(ring, `${ring.rows.length} samples every ${ring.sample_s} s since ${new Date(ring.started * 1000).toTimeString().slice(0, 5)}`);
  // activity heat
  const span = 14, days = daysBetween(now - (span - 1) * DAY, now);
  const lh = new Map(ls.levels_hour.map(([h, c]) => [h, Object.values(c).reduce((a, b) => a + b, 0)]));
  const cells = days.map(d => Array.from({ length: 24 }, (_, hr) => { const dt = new Date(d.ts * 1000); dt.setHours(hr); return lh.get(dt.getTime() / 1000) || 0; }));
  x.cAct.set(days.map(d => d.label), Array.from({ length: 24 }, (_, h) => ({ label: String(h).padStart(2, "0"), title: `${String(h).padStart(2, "0")}:00–${String(h).padStart(2, "0")}:59` })), cells, { fmt: v => Fmt.n(v) + " lines" });
  x.act.source(ls, `${Fmt.n(ls.lines)} lines · span ${Fmt.t(ls.span[0])} → ${Fmt.t(ls.span[1])} · parsed in ${ls.read_s} s`);
  x.act.table([{ h: "day" }, ...Array.from({ length: 24 }, (_, h) => ({ h: String(h).padStart(2, "0"), n: 1 }))], days.map((d, i) => [d.label, ...cells[i]]));
  // errors
  x.errs.body.innerHTML = `<div class="list">${ls.errors.slice(0, 14).map(e => `<div class="it"><div class="t">${Fmt.ago(e.last)}<br>×${e.n}</div><div title="${esc(e.example)}"><span class="L-${e.level}">${esc(e.shape)}</span></div></div>`).join("") || '<div class="dim">none</div>'}</div>`;
  x.errs.source(ls, `${ls.errors.length} shapes (numbers and quoted text folded)`);
  const boots = ls.boots.slice(-12).reverse();
  x.boots.body.innerHTML = tableHTML([{ h: "when" }, { h: "kind" }, { h: "fixtures" }, { h: "up until", n: 1 }],
    boots.map((b, i) => { const next = boots[i - 1]; return [Fmt.ts(b[0]), b[1] ? "boot" : "logging re-initialised (not a boot)", b[2] ? "test fixtures in segment" : "—", next ? Fmt.dur(next[0] - b[0]) : "running"]; }).reverse());
  x.boots.source(ls, `${ls.boots.filter(b => b[1]).length} real boots, ${ls.boots.filter(b => !b[1]).length} markers that were not`);
  x.git.body.innerHTML = tableHTML([{ h: "hash" }, { h: "when" }, { h: "subject", w: 1 }], git.commits.slice(0, 14).map(c => [c[0], Fmt.t(c[1]), c[2]]).reverse());
  x.git.source(git);
}, { noRange: true });

// ════════════════════════════════════════════════════════════════════
// KAIA — state and how it changes
// ════════════════════════════════════════════════════════════════════
tab("kaia", "KAIA", (root, x) => {
  x.mood = card(root, { title: "MOOD", span: 12, h: 220 });
  x.cMood = new TimeChart(x.mood.plot, { y: { min: -0.1, max: 1, fmt: v => v.toFixed(1) } });
  x.growth = card(root, { title: "GROWTH LOG · EVENTS PER DAY", span: 8, h: 200 });
  x.cGrowth = new Bars(x.growth.plot);
  x.gtypes = card(root, { title: "GROWTH EVENTS BY TYPE · IN RANGE", span: 4, h: 200 });
  x.cGtypes = new HBars(x.gtypes.plot, { labelW: 150 });
  sect(root, "BELIEFS & ANCHORS");
  x.bel = card(root, { title: "BELIEFS · LAST UPDATED × CONFIDENCE", span: 8, h: 210 });
  x.cBel = new TimeChart(x.bel.plot, { y: { min: 0, max: 1.02, fmt: v => v.toFixed(1) } });
  x.belh = card(root, { title: "BELIEF CONFIDENCE · DISTRIBUTION (ALL)", span: 4, h: 210 });
  x.cBelh = new Hist(x.belh.plot, { min: 0, max: 1, bins: 20, fmt: v => v.toFixed(2) });
  x.anc = card(root, { title: "ANCHORS · FORMED PER DAY BY PERSON", span: 8, h: 180 });
  x.cAnc = new Bars(x.anc.plot);
  x.ancw = card(root, { title: "ANCHOR WEIGHT · DISTRIBUTION (ALL)", span: 4, h: 180 });
  x.cAncw = new Hist(x.ancw.plot, { min: 0, max: 1, bins: 20, fmt: v => v.toFixed(2) });
  sect(root, "RELATIONSHIPS", "cumulative events per person; emotional weight as recorded");
  x.rel = card(root, { title: "RELATIONSHIP EVENTS · CUMULATIVE", span: 8, h: 220 });
  x.cRel = new TimeChart(x.rel.plot, {});
  x.relt = card(root, { title: "EVENT TYPES · IN RANGE", span: 4, h: 220 });
  x.cRelt = new HBars(x.relt.plot, { labelW: 110 });
  x.people = card(root, { title: "PEOPLE", span: 12, noPlot: true });
  sect(root, "INNER LIFE");
  x.mono = card(root, { title: "MONOLOGUE · THOUGHTS PER DAY BY SOURCE", span: 8, h: 190 });
  x.cMono = new Bars(x.mono.plot);
  x.monol = card(root, { title: "LATEST THOUGHTS", span: 4, noPlot: true });
  x.claims = card(root, { title: "SELF-CLAIMS · CONFIDENCE", span: 6, h: 240 });
  x.cClaims = new HBars(x.claims.plot, { max: 1, labelW: 260, fmt: v => v.toFixed(2) });
  x.chk = card(root, { title: "SELF-CHECKS · CORRECTIONS AND SECURITY TRIPS PER DAY", span: 6, h: 240 });
  x.cChk = new Bars(x.chk.plot);
}, async x => {
  const [mood, growth, beliefs, anchors, rel, mono, self, checks] = await Promise.all(["mood", "growth", "beliefs", "anchors", "relationships", "monologue", "self", "checks"].map(n => src(n)));
  const r = range(), P = PAL();
  x.cMood.set([{ name: "valence", color: P[0], data: mood.series.map(s => [s[0], s[1]]), gap: 6 * 3600 }, { name: "arousal", color: P[1], data: mood.series.map(s => [s[0], s[2]]), gap: 6 * 3600 }, { name: "social energy", color: P[2], data: mood.series.map(s => [s[0], s[3]]), gap: 6 * 3600 }], { range: r });
  x.mood.legend([{ name: "valence", color: P[0] }, { name: "arousal", color: P[1] }, { name: "social energy", color: P[2] }]);
  x.mood.source(mood, `${Fmt.n(mood.n)} rows (written on change; a gap over 6 h is a break in the line)`);
  x.mood.table([{ h: "time" }, { h: "valence", n: 1 }, { h: "arousal", n: 1 }, { h: "energy", n: 1 }], mood.series.filter(s => inRange(s[0], r)).map(s => [Fmt.ts(s[0]), s[1], s[2], s[3]]));
  // growth
  const gtop = rank(growth.events, e => e[1]);
  const gb = byDay(growth.events, e => e[0], e => e[1], gtop, r);
  x.cGrowth.set(gb.cats, gb.series); x.growth.legend(gb.series);
  x.growth.source(growth, `${Fmt.n(gb.n)} of ${Fmt.n(growth.n)} events in range`);
  x.growth.table([{ h: "time" }, { h: "type" }, { h: "about" }, { h: "text", w: 1 }], growth.events.filter(e => inRange(e[0], r)).map(e => [Fmt.ts(e[0]), e[1], e[2], e[3]]));
  const gcol = palette(gtop);
  x.cGtypes.set(gtop.map(k => ({ label: k, value: growth.events.filter(e => e[1] === k && inRange(e[0], r)).length, color: gcol(k) })).filter(i => i.value));
  x.gtypes.source(growth);
  // beliefs
  const btop = rank(beliefs.rows, b => b.source || "?"), bcol = palette(btop);
  x.cBel.set(btop.map(s => ({ name: s, color: bcol(s), type: "dots", r: 3.5, data: beliefs.rows.filter(b => (b.source || "?") === s && b.updated).map(b => [b.updated, b.confidence, b.topic]) })), { range: r });
  x.bel.legend(btop.map(s => ({ name: "source: " + s, color: bcol(s) })));
  x.bel.source(beliefs, `${beliefs.n} beliefs; hover a dot for its topic`);
  x.bel.table([{ h: "topic" }, { h: "confidence", n: 1 }, { h: "source" }, { h: "updated" }, { h: "accessed", n: 1 }, { h: "position", w: 1 }], [...beliefs.rows].sort((a, b) => (a.updated || 0) - (b.updated || 0)).map(b => [b.topic, b.confidence, b.source, Fmt.t(b.updated), b.access, b.position]));
  x.cBelh.set(beliefs.rows.map(b => b.confidence), { color: P[3] }); x.belh.source(beliefs);
  // anchors
  const atop = rank(anchors.rows, a => a.user || "(global)");
  const ab = byDay(anchors.rows, a => a.created, a => a.user || "(global)", atop, r);
  x.cAnc.set(ab.cats, ab.series); x.anc.legend(ab.series); x.anc.source(anchors, `${anchors.n} anchors; ${Fmt.n(ab.n)} formed in range`);
  x.anc.table([{ h: "created" }, { h: "person" }, { h: "theme" }, { h: "weight", n: 1 }, { h: "accessed", n: 1 }, { h: "anchor", w: 1 }], [...anchors.rows].sort((a, b) => (a.created || 0) - (b.created || 0)).map(a => [Fmt.t(a.created), a.user || "(global)", a.theme, a.weight, a.access, a.text]));
  x.cAncw.set(anchors.rows.map(a => a.weight), { color: P[4] }); x.ancw.source(anchors);
  // relationships
  const people = Object.entries(rel.people).map(([uid, p]) => ({ uid, ...p, n: p.events.length })).filter(p => p.n).sort((a, b) => b.n - a.n);
  const pcol = palette(people.map(p => p.name), 5);
  const series = people.slice(0, 5).map(p => { let c = 0; return { name: p.name, color: pcol(p.name), type: "step", data: p.events.slice().sort((a, b) => a[0] - b[0]).map(e => [e[0], ++c, e[1]]) }; });
  const rest = people.slice(5).flatMap(p => p.events).sort((a, b) => a[0] - b[0]);
  if (rest.length) { let c = 0; series.push({ name: `${people.length - 5} others`, color: OTHER(), type: "step", data: rest.map(e => [e[0], ++c, e[1]]) }); }
  x.cRel.set(series, { range: r, y: { min: 0, fmt: Fmt.k } }); x.rel.legend(series);
  x.rel.source(rel, `${people.length} people · ${Fmt.n(people.reduce((a, p) => a + p.n, 0))} events`);
  const allEv = people.flatMap(p => p.events.map(e => [e[0], p.name, e[1], e[2], e[3]]));
  x.rel.table([{ h: "time" }, { h: "person" }, { h: "type" }, { h: "weight", n: 1 }, { h: "summary", w: 1 }], allEv.filter(e => inRange(e[0], r)).sort((a, b) => a[0] - b[0]).map(e => [Fmt.ts(e[0]), e[1], e[2], e[3], e[4]]));
  const ttop = rank(allEv, e => e[2]), tcol = palette(ttop);
  x.cRelt.set(ttop.map(k => ({ label: k, value: allEv.filter(e => e[2] === k && inRange(e[0], r)).length, color: tcol(k) })).filter(i => i.value)); x.relt.source(rel);
  x.people.body.innerHTML = `<div class="people">${people.map((p, i) => `<div class="person"><div class="nm">${sw(pcol(p.name))}${esc(p.name)}<span>${p.n} events · last ${Fmt.ago(Math.max(0, ...p.events.map(e => e[0])))}</span></div><div class="ps" data-i="${i}"></div><div class="im" title="${esc(p.impression)}">${esc(p.impression || "no impression written")}</div></div>`).join("")}</div>`;
  x.people.source(rel, "the line is cumulative emotional weight; the text is her impression file");
  x.people.body.querySelectorAll(".ps").forEach(el => { const p = people[+el.dataset.i]; let c = 0; new Spark(el, { height: 36, color: pcol(p.name), fmt: v => "cumulative weight " + v.toFixed(2) }).set(p.events.slice().sort((a, b) => a[0] - b[0]).map(e => [e[0], c += (e[2] || 0)])); });
  // monologue
  const mtop = rank(mono.rows, m => m[1] || "?");
  const mb = byDay(mono.rows, m => m[0], m => m[1] || "?", mtop, r);
  x.cMono.set(mb.cats, mb.series); x.mono.legend(mb.series); x.mono.source(mono, `${Fmt.n(mb.n)} thoughts in range`);
  x.mono.table([{ h: "time" }, { h: "source" }, { h: "thought", w: 1 }], mono.rows.filter(m => inRange(m[0], r)).map(m => [Fmt.ts(m[0]), m[1], m[2]]));
  x.monol.body.innerHTML = `<div class="list">${mono.rows.slice(-14).reverse().map(m => `<div class="it"><div class="t">${Fmt.t(m[0])}<br><span class="tag">${esc(m[1])}</span></div><div>${esc(m[2])}</div></div>`).join("")}</div>`;
  x.monol.source(mono);
  // self
  const claims = (self.self_claims || []).slice().sort((a, b) => b.confidence - a.confidence);
  x.cClaims.set(claims.map(c => ({ label: c.claim || "?", value: c.confidence || 0, color: P[5], note: c.claim })));
  const sm = self["kaia_self_model.md"];
  x.claims.sub(sm ? `self-model rewritten ${Fmt.ago(sm.mtime)} · ${Fmt.n(sm.chars)} chars` : "");
  x.claims.source(self);
  const chk = [...checks.self_corrections.map(c => [c[0], "correction: " + (c[1] || "?")]), ...checks.security.map(s => [s[0], "security: " + (s[2] || s[1])]), ...checks.hallucination.map(h => [h[0], "hallucination flag"]), ...(checks.review_flags || []).map(f => [f[0], "review flag"])].filter(e => e[0]);
  const cb = byDay(chk, e => e[0], e => e[1], rank(chk, e => e[1]), r);
  x.cChk.set(cb.cats, cb.series); x.chk.legend(cb.series); x.chk.source(checks);
  x.chk.table([{ h: "time" }, { h: "kind" }], chk.filter(e => inRange(e[0], r)).sort((a, b) => a[0] - b[0]).map(e => [Fmt.ts(e[0]), e[1]]));
});

// ════════════════════════════════════════════════════════════════════
// VOICE — her words, from the logs she reads back
// ════════════════════════════════════════════════════════════════════
tab("voice", "VOICE", (root, x) => {
  sect(root, "HER LOGGED REPLIES, PER DAY", "people's DMs and channels in knowledge_base/user_logs; forum histories excluded; dotted lines are [kaia] commits");
  x.shape = card(root, { title: "TEMPLATE SHAPES · % OF HER REPLIES THAT DAY", span: 12, h: 240 });
  x.cShape = new TimeChart(x.shape.plot, { y: { min: 0, fmt: v => v + "%" } });
  x.len = card(root, { title: "WORDS · PER REPLY AND PER PARAGRAPH", span: 6, h: 190 });
  x.cLen = new TimeChart(x.len.plot, { y: { min: 0 } });
  x.par = card(root, { title: "PARAGRAPHS PER REPLY", span: 6, h: 190 });
  x.cPar = new TimeChart(x.par.plot, { y: { min: 0, fmt: v => v.toFixed(1) } });
  x.vol = card(root, { title: "TURNS PER DAY · HERS AND PEOPLE'S", span: 6, h: 190 });
  x.cVol = new TimeChart(x.vol.plot, { y: { min: 0 } });
  x.who = card(root, { title: "WHO SHE TALKED WITH · TURNS PER DAY", span: 6, h: 190 });
  x.cWho = new Bars(x.who.plot);
}, async x => {
  const [v, git] = await Promise.all([src("voice"), src("git")]);
  const r = range(), P = PAL();
  const days = v.days.map(d => ({ ...d, ts: Stat.dayStart(d.day) + 43200 })).filter(d => r[0] == null || d.ts + 43200 >= r[0]);
  const rv = [r[0], r[1] == null ? null : r[1] + 43200];
  const marks = git.commits.filter(c => c[2].startsWith("[kaia]")).map(c => ({ t: c[1], label: c[2] }));
  const S = (k, name, i) => ({ name, color: P[i], data: days.filter(d => d.replies >= 3).map(d => [d.ts, d[k], `${d.replies} replies`]) });
  const shapes = [S("a_quiet_pct", "'a quiet …'", 0), S("litany_pct", "litany (4+ 'a …' fragments)", 1), S("cut_pct", "cut ellipsis ('just. a')", 2), S("tag_pct", "'(speaking exclusively …)'", 3)];
  x.cShape.set(shapes, { range: rv, marks, y: { min: 0, fmt: v => v + "%", tip: v => Fmt.pct(v, 1) } }); x.shape.legend(shapes);
  x.shape.sub("days with fewer than 3 replies are left out — a percentage of one reply is noise");
  x.shape.source(v, `${days.length} days · counted by the same functions the filters use (safety_pipeline)`);
  const cols = [{ h: "day" }, { h: "replies", n: 1 }, { h: "people's turns", n: 1 }, { h: "words/reply", n: 1 }, { h: "paras/reply", n: 1 }, { h: "words/para", n: 1 }, { h: "a quiet %", n: 1 }, { h: "litany %", n: 1 }, { h: "cut %", n: 1 }, { h: "tag %", n: 1 }];
  const rows = days.map(d => [d.day, d.replies, d.user_turns, d.words_per_reply, d.paras_per_reply, d.words_per_para, d.a_quiet_pct, d.litany_pct, d.cut_pct, d.tag_pct]);
  x.shape.table(cols, rows);
  const len = [{ name: "words per reply", color: P[0], data: days.filter(d => d.replies >= 3).map(d => [d.ts, d.words_per_reply]) }, { name: "words per paragraph", color: P[2], data: days.filter(d => d.replies >= 3).map(d => [d.ts, d.words_per_para]) }];
  x.cLen.set(len, { range: rv, marks }); x.len.legend(len); x.len.source(v); x.len.table(cols, rows);
  x.cPar.set([{ name: "paragraphs per reply", color: P[3], data: days.filter(d => d.replies >= 3).map(d => [d.ts, d.paras_per_reply]) }], { range: rv, marks }); x.par.source(v);
  const vol = [{ name: "her replies", color: P[0], data: days.map(d => [d.ts, d.replies]) }, { name: "people's turns", color: P[1], data: days.map(d => [d.ts, d.user_turns]) }];
  x.cVol.set(vol, { range: rv }); x.vol.legend(vol); x.vol.source(v);
  const ev = []; for (const [day, ppl] of Object.entries(v.people_by_day)) for (const [name, n] of Object.entries(ppl)) for (let i = 0; i < n; i++) ev.push([Stat.dayStart(day) + 60, name]);
  const wb = byDay(ev, e => e[0], e => e[1], rank(ev, e => e[1]), r);
  x.cWho.set(wb.cats, wb.series); x.who.legend(wb.series); x.who.source(v, "people's turns, by the log folder they are in");
});

// ════════════════════════════════════════════════════════════════════
// LOGS
// ════════════════════════════════════════════════════════════════════
tab("logs", "LOGS", (root, x) => {
  x.vol = card(root, { title: "LINES PER HOUR BY LEVEL", span: 12, h: 120 });
  x.cVol = new Bars(x.vol.plot, { labelW: 70, onHover: null });
  const bar = document.createElement("div"); bar.id = "logbar";
  bar.innerHTML = `<input id="logq" type="search" placeholder="regex filter — e.g. GUARD|TOKEN_DEBUG" spellcheck="false">
    <div class="seg" id="loglvl" style="margin:0">${["ALL", "INFO", "WARNING", "ERROR"].map(l => `<button data-l="${l}" class="${l === "ALL" ? "on" : ""}">${l === "ALL" ? "ALL" : l + "+"}</button>`).join("")}</div>
    <button class="btn" id="logfollow">FOLLOW</button><span id="followflag">paused</span>
    <select id="logboot"><option value="">jump to boot…</option></select>
    <button class="btn" id="logmore">OLDER</button><span class="dim" id="logcount"></span>`;
  root.appendChild(bar);
  const view = document.createElement("div"); view.id = "logview"; root.appendChild(view);
  x.errs = card(root, { title: "ERROR SHAPES · ALL OF THE LOG", span: 12, noPlot: true });
  Object.assign(x, { view, q: "", lvl: "", follow: true, oldest: 0, newest: 0 });
  const reload = () => loadLogs(x, true);
  let deb; $("#logq").oninput = e => { clearTimeout(deb); deb = setTimeout(() => { x.q = e.target.value; reload(); }, 250); };
  $("#loglvl").onclick = e => { const l = e.target.dataset.l; if (!l) return; x.lvl = l === "ALL" ? "" : l; $("#loglvl").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.l === l)); reload(); };
  $("#logfollow").onclick = () => { x.follow = !x.follow; followUI(x); if (x.follow) reload(); };
  $("#logmore").onclick = () => loadLogs(x, false, true);
  $("#logboot").onchange = e => { const t = +e.target.value; if (!t) return; x.follow = false; followUI(x); x.until = t + 600; x.since = t - 60; loadLogs(x, true).then(() => { x.until = x.since = 0; }); };
  view.addEventListener("scroll", () => { const atEnd = view.scrollTop + view.clientHeight >= view.scrollHeight - 30; if (!atEnd && x.follow) { x.follow = false; followUI(x); } });
  followUI(x);
  x.timer = setInterval(() => { if (CUR?.id === "logs" && x.follow) loadLogs(x, false); }, 1500);
}, async x => {
  const ls = await logstats(true), r = range();
  const hours = ls.levels_hour.filter(([h]) => inRange(h, r));
  const lv = ["DEBUG", "INFO", "SUCCESS", "ACTION", "WARNING", "ERROR"];
  const colors = { DEBUG: OTHER(), INFO: PAL()[5], SUCCESS: PAL()[4], ACTION: PAL()[0], WARNING: PAL()[2], ERROR: PAL()[1] };
  x.cVol.set(hours.map(([h]) => ({ label: new Date(h * 1000).getHours() === 0 ? Fmt.day(h) : String(new Date(h * 1000).getHours()).padStart(2, "0"), title: Fmt.t(h) })), lv.map(l => ({ name: l, color: colors[l], values: hours.map(([, c]) => (c[l] || 0) + (l === "ERROR" ? (c.CRITICAL || 0) : 0)) })), { labelW: 40 });
  x.vol.legend(lv.map(l => ({ name: l, color: colors[l] }))); x.vol.source(ls, `${Fmt.n(ls.lines)} lines parsed`);
  const sel = $("#logboot"); sel.innerHTML = `<option value="">jump to boot…</option>` + ls.boots.slice().reverse().map(b => `<option value="${b[0]}">${Fmt.ts(b[0])}${b[1] ? "" : " (not a boot)"}${b[2] ? " · fixtures" : ""}</option>`).join("");
  x.errs.body.innerHTML = tableHTML([{ h: "level" }, { h: "count", n: 1 }, { h: "first" }, { h: "last" }, { h: "shape", w: 1 }, { h: "latest example", w: 1 }], ls.errors.map(e => [e.level, e.n, Fmt.t(e.first), Fmt.t(e.last), e.shape, e.example]).reverse());
  x.errs.source(ls);
  if (!x.newest) await loadLogs(x, true);
});
function followUI(x) { $("#logfollow").classList.toggle("on", x.follow); const f = $("#followflag"); f.textContent = x.follow ? "following" : "paused"; f.classList.toggle("on", x.follow); }
function hl(text, q) {
  const t = esc(text); if (!q) return t;
  try { return t.replace(new RegExp(`(${q})`, "gi"), "<mark>$1</mark>"); } catch (e) { return t; }
}
function lineHTML(l, q) {
  const [seq, ts, level, text] = l;
  if (!level) return `<div class="ll c"><span class="x">${hl(text, q)}</span></div>`;
  const boot = text.includes("Unified logging system initialized") ? " boot" : "";
  return `<div class="ll${boot}" data-seq="${seq}"><span class="t">${ts ? Fmt.ts(ts) : ""}</span><span class="l L-${level}">${level}</span><span class="x L-${level === "DEBUG" ? "DEBUG" : ""}">${hl(text, q)}</span></div>`;
}
async function loadLogs(x, reset, older) {
  const p = new URLSearchParams({ limit: older ? 1500 : reset ? 1500 : 500 });
  if (x.q) p.set("q", x.q); if (x.lvl) p.set("level", x.lvl);
  if (x.since) p.set("since", x.since); if (x.until) p.set("until", x.until);
  if (older) p.set("before", x.oldest); else if (!reset && x.newest) p.set("after", x.newest);
  const d = await get("/api/logs?" + p);
  const v = x.view, html = d.lines.map(l => lineHTML(l, x.q)).join("");
  if (reset) { v.innerHTML = html; x.oldest = d.lines.length ? d.lines[0][0] : 0; x.newest = d.lines.length ? d.lines[d.lines.length - 1][0] : d.seq; x.since || x.until ? (v.scrollTop = 0) : (v.scrollTop = v.scrollHeight); }
  else if (older) { const h0 = v.scrollHeight; v.insertAdjacentHTML("afterbegin", html); if (d.lines.length) x.oldest = d.lines[0][0]; v.scrollTop += v.scrollHeight - h0; }
  else if (d.lines.length) { v.insertAdjacentHTML("beforeend", html); x.newest = d.lines[d.lines.length - 1][0]; while (v.childElementCount > 6000) v.firstElementChild.remove(); if (x.follow) v.scrollTop = v.scrollHeight; }
  else x.newest = Math.max(x.newest, d.seq);
  $("#logcount").textContent = `${Fmt.n(v.childElementCount)} lines shown · viewer holds the newest ${Fmt.n(d.seq - d.kept_from + 1)} of ${Fmt.n(d.seq)}`;
}

// ════════════════════════════════════════════════════════════════════
// PIPELINE — latency, tokens, retrieval, guards, GPU queue
// ════════════════════════════════════════════════════════════════════
tab("pipe", "PIPELINE", (root, x) => {
  x.lat = card(root, { title: "REPLY LATENCY · EACH TURN, ROLLING P50 / P90", span: 8, h: 220 });
  x.cLat = new TimeChart(x.lat.plot, { y: { min: 0, fmt: v => v + "s", tip: Fmt.s } });
  x.lath = card(root, { title: "REPLY LATENCY · DISTRIBUTION", span: 4, h: 220 });
  x.cLath = new Hist(x.lath.plot, { min: 0, bins: 40, fmt: v => v.toFixed(0) + "s" });
  x.tok = card(root, { title: "PROMPT TOKENS PER TURN · AGAINST THE CONTEXT WINDOW", span: 8, h: 220 });
  x.cTok = new TimeChart(x.tok.plot, { y: { min: 0, fmt: Fmt.k, tip: v => Fmt.n(v) + " tokens" } });
  x.toh = card(root, { title: "REPLY TOKENS (EVAL_COUNT) · DISTRIBUTION", span: 4, h: 220 });
  x.cToh = new Hist(x.toh.plot, { min: 0, bins: 40, fmt: v => Fmt.n(v) });
  x.ret = card(root, { title: "RETRIEVAL CONFIDENCE · EACH RETRIEVAL, ROLLING P50", span: 8, h: 200 });
  x.cRet = new TimeChart(x.ret.plot, { y: { min: 0, max: 1, fmt: v => v.toFixed(1) } });
  x.reth = card(root, { title: "RETRIEVAL CONFIDENCE · DISTRIBUTION", span: 4, h: 200 });
  x.cReth = new Hist(x.reth.plot, { min: 0, max: 1, bins: 25, fmt: v => v.toFixed(2) });
  sect(root, "GUARDS", "log lines carrying each guard's tag — a guard may log more than one line per reply");
  x.guard = card(root, { title: "GUARD LINES · TAG × DAY", span: 8, h: 330 });
  x.cGuard = new Heat(x.guard.plot, { labelW: 190, colLabelW: 44 });
  x.guardr = card(root, { title: "GUARD LINES PER 100 REPLIES · IN RANGE", span: 4, h: 330 });
  x.cGuardr = new HBars(x.guardr.plot, { labelW: 170, fmt: v => v.toFixed(1) });
  sect(root, "GPU QUEUE", "every run_with_gpu_guard task, '[task_xxxxxxxx] Finished in Ns'");
  x.gpu = card(root, { title: "GPU TASK DURATION · BY TASK (LOG SCALE)", span: 7, h: 360 });
  x.cGpu = new Strips(x.gpu.plot, { log: true, labelW: 170, fmt: v => v < 10 ? v.toFixed(1) + "s" : Math.round(v) + "s" });
  x.gpud = card(root, { title: "GPU BUSY SECONDS PER DAY · BY TASK", span: 5, h: 360 });
  x.cGpud = new Bars(x.gpud.plot, { y: { fmt: v => Fmt.dur(v), tip: v => Fmt.dur(v) } });
  x.intent = card(root, { title: "FAST-PATH INTENTS · IN RANGE", span: 4, h: 200 });
  x.cIntent = new HBars(x.intent.plot, { labelW: 160 });
  x.gen = card(root, { title: "REPLY LENGTH (CHARS) · GENERATION LOG", span: 4, h: 200 });
  x.cGen = new Hist(x.gen.plot, { min: 0, bins: 40, fmt: v => Fmt.k(v) });
  x.slow = card(root, { title: "SLOW ON_MESSAGE HANDLING", span: 4, h: 200 });
  x.cSlow = new TimeChart(x.slow.plot, { y: { min: 0, fmt: v => v + "s", tip: Fmt.s } });
}, async x => {
  const [ls, cfg, gen] = await Promise.all([logstats(true), src("config"), src("generation")]);
  const r = range(), P = PAL();
  const lat = ls.latency.filter(p => inRange(p[0], r));
  x.cLat.set([{ name: "turn", color: P[0], type: "dots", r: 2, data: lat }, { name: "rolling p50 (50 turns)", color: P[2], data: rollN(lat, 50, .5) }, { name: "rolling p90 (50 turns)", color: P[1], data: rollN(lat, 50, .9) }], { range: r });
  x.lat.legend([{ name: "turn", color: P[0] }, { name: "rolling p50 (50 turns)", color: P[2] }, { name: "rolling p90 (50 turns)", color: P[1] }]);
  x.lat.source(ls, `${Fmt.n(lat.length)} turns in range ('TOTAL processing for …')`);
  x.lat.table([{ h: "time" }, { h: "seconds", n: 1 }], lat.map(p => [Fmt.ts(p[0]), p[1].toFixed(2)]));
  x.cLath.set(lat.map(p => p[1]), { color: P[0], max: Math.max(10, Stat.q(lat.map(p => p[1]), .995) || 0) }); x.lath.source(ls);
  const tok = ls.tokens.filter(p => inRange(p[0], r)); const ctx = tok.length ? Math.max(...tok.map(p => p[3])) : null;
  const budget = cfg.flags?.["performance.max_context_tokens"];
  const th = []; if (ctx) th.push({ y: ctx, label: `num_ctx ${Fmt.n(ctx)} (logged)` }); if (budget && budget !== ctx) th.push({ y: budget, label: `max_context_tokens ${Fmt.n(budget)} (config)`, color: CSSV("--yellow") });
  x.cTok.set([{ name: "prompt_eval_count", color: P[3], type: "dots", r: 2.2, data: tok.map(p => [p[0], p[1]]) }], { range: r, thresholds: th });
  const over = budget ? tok.filter(p => p[1] > budget).length : 0;
  x.tok.sub(`p50 <b>${Fmt.n(Stat.q(tok.map(p => p[1]), .5))}</b> · p90 <b>${Fmt.n(Stat.q(tok.map(p => p[1]), .9))}</b> · max <b>${Fmt.n(tok.length ? Math.max(...tok.map(p => p[1])) : null)}</b>${budget ? ` · over the configured budget: <b>${over}</b> of ${tok.length}` : ""}`);
  x.tok.source(ls, "[TOKEN_DEBUG] lines; the budget line is read from config, the num_ctx line from the log");
  x.tok.table([{ h: "time" }, { h: "prompt", n: 1 }, { h: "reply", n: 1 }, { h: "num_ctx", n: 1 }], tok.map(p => [Fmt.ts(p[0]), p[1], p[2], p[3]]));
  x.cToh.set(tok.map(p => p[2]), { color: P[5] }); x.toh.source(ls);
  const ret = ls.retrieval.filter(p => inRange(p[0], r));
  x.cRet.set([{ name: "retrieval", color: P[4], type: "dots", r: 2, data: ret.map(p => [p[0], p[1], p[2] + " nodes"]) }, { name: "rolling p50 (50)", color: P[2], data: rollN(ret, 50, .5) }], { range: r });
  x.ret.legend([{ name: "retrieval", color: P[4] }, { name: "rolling p50 (50)", color: P[2] }]); x.ret.source(ls, `${Fmt.n(ret.length)} retrievals`);
  x.cReth.set(ret.map(p => p[1]), { color: P[4] }); x.reth.source(ls);
  // guards
  const g = ls.guards.filter(p => inRange(p[0], r)), tags = rank(ls.guards, e => e[1]);
  const t0 = r[0] ?? Math.min(...ls.guards.map(e => e[0])), days = daysBetween(t0, r[1] ?? Date.now() / 1000), di = new Map(days.map((d, i) => [d.key, i]));
  const cells = tags.map(t => { const row = new Array(days.length).fill(0); for (const e of g) if (e[1] === t) { const i = di.get(Stat.dayKey(e[0])); if (i != null) row[i]++; } return row; });
  const keep = tags.map((t, i) => [t, cells[i]]).filter(([, row]) => row.some(Boolean));
  x.cGuard.set(keep.map(k => k[0]), days.map(d => ({ label: d.label, title: d.title })), keep.map(k => k[1]), { fmt: v => Fmt.n(v) + " lines", hue: [255, 47, 209] });
  x.guard.source(ls, `${Fmt.n(g.length)} tagged lines in range`);
  x.guard.table([{ h: "tag" }, ...days.map(d => ({ h: d.label, n: 1 }))], keep.map(([t, row]) => [t, ...row]));
  const replies = Math.max(1, lat.length);
  x.cGuardr.set(keep.map(([t, row]) => ({ label: t, value: 100 * row.reduce((a, b) => a + b, 0) / replies, color: P[1], note: `${row.reduce((a, b) => a + b, 0)} lines / ${lat.length} replies` })).sort((a, b) => b.value - a.value));
  x.guardr.source(ls, "per 100 'TOTAL processing' turns in the same range");
  // gpu
  const gp = ls.gpu.filter(p => inRange(p[0], r)), gtop = rank(ls.gpu, e => e[1]), gcol = palette(gtop);
  x.cGpu.set(rank(gp, e => e[1]).slice(0, 14).map(k => ({ name: k, color: gcol(k), values: gp.filter(e => e[1] === k).map(e => e[2]) })));
  x.gpu.sub("each dot one task · white tick p50 · grey tick p90"); x.gpu.source(ls, `${Fmt.n(gp.length)} tasks in range`);
  x.gpu.table([{ h: "time" }, { h: "task" }, { h: "seconds", n: 1 }], gp.map(e => [Fmt.ts(e[0]), e[1], e[2].toFixed(2)]));
  const gb = byDay(gp, e => e[0], e => e[1], gtop, r);
  const secs = gb.series.map(s => ({ ...s, values: s.values.map(() => 0) }));
  const idx = new Map(gb.cats.map((c, i) => [c.key, i]));
  for (const e of gp) { const own = gtop.slice(0, 6).includes(e[1]) ? e[1] : REST; const s = secs.find(s => s.name === own); const i = idx.get(Stat.dayKey(e[0])); if (s && i != null) s.values[i] += e[2]; }
  x.cGpud.set(gb.cats, secs); x.gpud.legend(secs); x.gpud.source(ls);
  const it = ls.intents.filter(p => inRange(p[0], r)), itop = rank(it, e => e[1]);
  x.cIntent.set(itop.map(k => ({ label: k, value: it.filter(e => e[1] === k).length, color: P[0] }))); x.intent.source(ls, "'Fast-path intent: X (category)'");
  const gr = gen.rows.filter(g => inRange(g[0], r));
  x.cGen.set(gr.map(g => g[5]), { color: P[2], max: Math.max(100, Stat.q(gr.map(g => g[5]), .995) || 0) }); x.gen.source(gen, `${Fmt.n(gr.length)} replies in range`);
  const sl = ls.slow.filter(p => inRange(p[0], r));
  x.cSlow.set([{ name: "on_message", color: P[1], type: "dots", r: 3, data: sl }], { range: r }); x.slow.source(ls, `${sl.length} 'Slow response' lines`);
});
function rollN(pts, n, q) { const out = []; for (let i = n - 1; i < pts.length; i += Math.max(1, Math.floor(n / 10))) out.push([pts[i][0], Stat.q(pts.slice(i - n + 1, i + 1).map(p => p[1]), q)]); return out; }

// ════════════════════════════════════════════════════════════════════
// MACHINE — GPU, Ollama residency, memory, processes
// ════════════════════════════════════════════════════════════════════
tab("mach", "MACHINE", (root, x) => {
  sect(root, "LIVE · MEASURED BY THIS DASHBOARD", "sampled every 3 s while it runs; kept 24 h; no history from before it started");
  const mk = (title, span = 3) => { const c = card(root, { title, span, h: 120 }); c.ch = new TimeChart(c.plot, { pad: { l: 40, b: 18 } }); return c; };
  x.l = { cpu: mk("CPU %"), mem: mk("MEMORY USED · GB"), vram: mk("VRAM USED · MB"), util: mk("GPU UTILISATION %"), temp: mk("GPU TEMPERATURE · °C"), pow: mk("GPU POWER · W"), brss: mk("BOT RSS · MB"), bcpu: mk("BOT CPU %") };
  x.models = card(root, { title: "OLLAMA · RESIDENT NOW", span: 4, noPlot: true });
  x.spikes = card(root, { title: "TRANSIENT HEAVY PROCESSES · OVER 150% CPU OR 4 GB", span: 8, noPlot: true });
  sect(root, "HISTORY · FROM THE LOGS");
  x.loads = card(root, { title: "MODEL LOADS · CONTEXT SIZE AT EACH LOAD", span: 8, h: 220 });
  x.cLoads = new TimeChart(x.loads.plot, { y: { min: 0, fmt: Fmt.k, tip: v => "n_ctx " + Fmt.n(v) } });
  x.loadn = card(root, { title: "LOADS PER MODEL · IN RANGE", span: 4, h: 220 });
  x.cLoadn = new HBars(x.loadn.plot, { labelW: 170 });
  x.rss = card(root, { title: "BOT RSS · 15-MINUTE MEMORY AUDIT", span: 8, h: 220 });
  x.cRss = new TimeChart(x.rss.plot, { y: { min: 0, fmt: v => Fmt.k(v), tip: v => Fmt.n(v) + " MB" } });
  x.trim = card(root, { title: "MALLOC_TRIM RETURNED · MB PER AUDIT", span: 4, h: 220 });
  x.cTrim = new Hist(x.trim.plot, { min: 0, bins: 30, fmt: v => Fmt.n(v) });
  x.late = card(root, { title: "VOICE THREAD LATE FRAMES · RECORDS SETS", span: 12, h: 160 });
  x.cLate = new TimeChart(x.late.plot, { y: { min: 0, fmt: v => v + " ms", tip: v => v + " ms late" } });
}, async x => {
  const [ring, ls, jr] = await Promise.all([get("/api/ring"), logstats(true), src("journal")]);
  D.ring = ring; const P = PAL(), L = D.live || {}, g = L.system?.gpu;
  const col = (i, k, c, opt = {}) => { const pts = ring.rows.map(r => [r[0], r[i]]); x.l[k].ch.set([{ name: k, color: c, data: pts }], opt); x.l[k].source(ring, `${pts.length} samples`); };
  col(1, "cpu", P[0], { y: { min: 0, max: 100, fmt: v => v + "%" }, thresholds: [{ y: 90, label: "90%" }] });
  col(2, "mem", P[5], { y: { min: 0, max: L.system?.mem_total_gb, fmt: v => v.toFixed(0) } });
  col(4, "vram", P[3], { y: { min: 0, max: g?.vram_total_mb, fmt: Fmt.k }, thresholds: g ? [{ y: g.vram_total_mb * .97, label: "97% of card" }] : [] });
  col(5, "util", P[2], { y: { min: 0, max: 100, fmt: v => v + "%" } });
  col(6, "temp", P[1], { y: { min: 20, max: 95, fmt: v => v + "°" }, thresholds: [{ y: 83, label: "83°C" }] });
  col(7, "pow", P[4], { y: { min: 0, fmt: v => v + "W" } });
  col(8, "brss", P[0], { y: { min: 0, fmt: Fmt.k } });
  col(9, "bcpu", P[2], { y: { min: 0, fmt: v => v + "%" } });
  const ms = L.ollama?.models || [];
  x.models.body.innerHTML = ms.length ? tableHTML([{ h: "model" }, { h: "VRAM", n: 1 }, { h: "size", n: 1 }, { h: "ctx", n: 1 }, { h: "expires" }], ms.map(m => [m.name, Fmt.n(m.vram_mb) + " MB", Fmt.n(m.size_mb) + " MB", Fmt.n(m.ctx), m.expires && parseInt(m.expires, 10) > 2200 ? "never (keep_alive -1)" : (m.expires || "").replace("T", " ").slice(0, 19)]).reverse()) : `<div class="dim" style="padding:8px 10px">${L.ollama?.up ? "nothing resident" : "Ollama is not answering"}</div>`;
  x.models.foot.innerHTML = srcLine({ source: ["http://127.0.0.1:11434/api/ps"] });
  x.spikes.body.innerHTML = ring.spikes.length ? tableHTML([{ h: "time" }, { h: "pid", n: 1 }, { h: "name" }, { h: "CPU %", n: 1 }, { h: "RSS MB", n: 1 }, { h: "command", w: 1 }], ring.spikes.map(s => [Fmt.ts(s[0]), s[1], s[2], s[3], s[4], s[5]])) : `<div class="dim" style="padding:8px 10px">none since ${new Date(ring.started * 1000).toTimeString().slice(0, 5)} — every running process is compared between samples; Ollama and the bot are left out for size, not for CPU</div>`;
  x.spikes.source(ring, "processes seen in two consecutive samples");
  const r = range(); const mtop = rank(jr.loads, l => l[1]), mcol = palette(mtop);
  x.cLoads.set(mtop.map(m => ({ name: m, color: mcol(m), type: "dots", r: 3.5, data: jr.loads.filter(l => l[1] === m).map(l => [l[0], l[2]]) })), { range: r });
  x.loads.legend(mtop.slice(0, 6).map(m => ({ name: m, color: mcol(m) })));
  x.loads.sub("a load of the chat model at a different n_ctx than the last is a reload a turn paid for (CLAUDE.md §4)");
  x.loads.source(jr, `${jr.loads.length} loads in 14 days of journal`);
  x.loads.table([{ h: "time" }, { h: "model" }, { h: "n_ctx", n: 1 }], jr.loads.filter(l => inRange(l[0], r)).map(l => [Fmt.ts(l[0]), l[1], l[2]]));
  x.cLoadn.set(mtop.map(m => ({ label: m, value: jr.loads.filter(l => l[1] === m && inRange(l[0], r)).length, color: mcol(m) })).filter(i => i.value)); x.loadn.source(jr);
  const rs = ls.rss.filter(p => inRange(p[0], r));
  x.cRss.set([{ name: "RSS after the audit", color: P[0], data: rs.map(p => [p[0], p[1] - p[2]]), gap: 3600 }, { name: "RSS before malloc_trim", color: P[3], type: "dots", r: 2, data: rs.filter(p => p[2]).map(p => [p[0], p[1]]) }], { range: r, marks: ls.boots.filter(b => b[1]).map(b => ({ t: b[0], color: CSSV("--pink") })) });
  x.rss.legend([{ name: "RSS after trim", color: P[0] }, { name: "before trim", color: P[3] }, { name: "boot", color: CSSV("--pink") }]); x.rss.source(ls, `${rs.length} audits`);
  x.rss.table([{ h: "time" }, { h: "RSS MB", n: 1 }, { h: "trim gave back MB", n: 1 }], rs.map(p => [Fmt.ts(p[0]), p[1], p[2]]));
  x.cTrim.set(rs.filter(p => p[2]).map(p => p[2]), { color: P[3] }); x.trim.source(ls);
  const lt = ls.voice_late.filter(p => inRange(p[0], r));
  x.cLate.set([{ name: "late frame", color: P[1], type: "dots", r: 3, data: lt }], { range: r }); x.late.source(ls, `${lt.length} '[records] voice thread N ms' lines in range`);
});

// ════════════════════════════════════════════════════════════════════
// WORLD — unprompted, boards, forum
// ════════════════════════════════════════════════════════════════════
tab("world", "WORLD", (root, x) => {
  x.unp = card(root, { title: "UNPROMPTED POSTS PER DAY · BY SOURCE", span: 8, h: 210 });
  x.cUnp = new Bars(x.unp.plot);
  x.lab = card(root, { title: "LABELS WORN · IN RANGE", span: 4, h: 210 });
  x.cLab = new HBars(x.lab.plot, { labelW: 170 });
  x.uhr = card(root, { title: "UNPROMPTED · HOUR OF DAY × SOURCE (IN RANGE)", span: 12, h: 150 });
  x.cUhr = new Heat(x.uhr.plot, { labelW: 100, colLabelW: 26 });
  sect(root, "AGENT BOARDS");
  x.brd = card(root, { title: "BOARD EVENTS PER DAY", span: 8, h: 200 });
  x.cBrd = new Bars(x.brd.plot);
  x.brdw = card(root, { title: "POSTS WRITTEN · BY BOARD (IN RANGE)", span: 4, h: 200 });
  x.cBrdw = new HBars(x.brdw.plot, { labelW: 130 });
  x.brde = card(root, { title: "RECENT BOARD ERRORS AND HOLDS", span: 12, noPlot: true });
  sect(root, "FORUM");
  x.frm = card(root, { title: "FORUM MODERATION · DRAFTS DECIDED PER DAY", span: 8, h: 190 });
  x.cFrm = new Bars(x.frm.plot);
  x.frmt = card(root, { title: "ACCEPT RATE · ALL TIME", span: 4, noPlot: true });
}, async x => {
  const [ls, soc] = await Promise.all([logstats(true), src("social")]);
  const r = range(), P = PAL();
  const utop = ["proactive", "quip", "observation", "monologue", "overnight", ...rank(ls.unprompted, e => e[1])].filter((v, i, a) => a.indexOf(v) === i);
  const ub = byDay(ls.unprompted, e => e[0], e => e[1], utop, r);
  x.cUnp.set(ub.cats, ub.series); x.unp.legend(ub.series); x.unp.source(ls, `${Fmt.n(ub.n)} posts in range`);
  x.unp.table([{ h: "time" }, { h: "source" }, { h: "label" }], ls.unprompted.filter(e => inRange(e[0], r)).map(e => [Fmt.ts(e[0]), e[1], e[2]]));
  const u = ls.unprompted.filter(e => inRange(e[0], r));
  x.cLab.set(rank(u, e => e[2]).map(k => ({ label: k, value: u.filter(e => e[2] === k).length, color: P[0] }))); x.lab.source(ls);
  const ucol = palette(utop);
  const srcs = utop.filter(s => u.some(e => e[1] === s));
  x.cUhr.set(srcs, Array.from({ length: 24 }, (_, h) => ({ label: String(h).padStart(2, "0"), title: `${h}:00–${h}:59` })), srcs.map(s => Array.from({ length: 24 }, (_, h) => u.filter(e => e[1] === s && new Date(e[0] * 1000).getHours() === h).length)), { fmt: v => v + " posts" });
  x.uhr.source(ls);
  const b = soc.boards.filter(e => e[2] !== "registered"), etop = ["wrote", "read", "held", "error", "verify_failed", "verify_skipped"];
  const bcol = { wrote: P[0], read: P[5], held: P[2], error: P[1], verify_failed: P[3], verify_skipped: OTHER() };
  const bb = byDay(b, e => e[0], e => e[2], etop, r);
  bb.series.forEach(s => s.color = bcol[s.name] || OTHER());
  x.cBrd.set(bb.cats, bb.series); x.brd.legend(bb.series); x.brd.source(soc, `${Fmt.n(bb.n)} events in range ('read' counts a fetch, not posts read)`);
  const w = b.filter(e => e[2] === "wrote" && inRange(e[0], r));
  x.cBrdw.set(rank(w, e => e[1]).map(k => ({ label: k, value: w.filter(e => e[1] === k).length, color: P[0] }))); x.brdw.source(soc);
  const be = soc.boards.filter(e => ["error", "held", "verify_failed"].includes(e[2])).slice(-40);
  x.brde.body.innerHTML = tableHTML([{ h: "time" }, { h: "board" }, { h: "event" }, { h: "detail", w: 1 }], be.map(e => [Fmt.ts(e[0]), e[1], e[2], e[4]]));
  x.brde.source(soc);
  const f = soc.forum.filter(e => e[0]);
  const fb = byDay(f, e => e[0], e => e[1], ["accepted", "approved", "rejected", ...rank(f, e => e[1])].filter((v, i, a) => a.indexOf(v) === i), r);
  x.cFrm.set(fb.cats, fb.series); x.frm.legend(fb.series); x.frm.source(soc);
  x.frm.table([{ h: "time" }, { h: "action" }, { h: "forum" }, { h: "thread", w: 1 }], f.filter(e => inRange(e[0], r)).map(e => [Fmt.ts(e[0]), e[1], e[2], e[3]]));
  const acts = rank(f, e => e[1]);
  x.frmt.body.innerHTML = `<div class="kv">${acts.map(a => `<div>${esc(a)}</div><div>${f.filter(e => e[1] === a).length} <span class="dim">(${Fmt.pct(100 * f.filter(e => e[1] === a).length / f.length)})</span></div>`).join("")}<div>total decided</div><div>${f.length}</div></div>`;
  x.frmt.source(soc);
});

// ════════════════════════════════════════════════════════════════════
// RADIO — the local scanner
// ════════════════════════════════════════════════════════════════════
tab("radio", "RADIO", (root, x) => {
  x.day = card(root, { title: "SCANNER CATCHES PER DAY · BY CLASS", span: 8, h: 210 });
  x.cDay = new Bars(x.day.plot);
  x.kind = card(root, { title: "CATCHES BY CLASS · IN RANGE", span: 4, h: 210 });
  x.cKind = new HBars(x.kind.plot, { labelW: 80 });
  x.clock = card(root, { title: "WHEN THE BAND IS BUSY · VOICE + DATA, DAY × HOUR", span: 8, h: 260 });
  x.cClock = new Heat(x.clock.plot, { labelW: 64, colLabelW: 26, hue: [0, 240, 255] });
  x.dur = card(root, { title: "VOICE CATCH LENGTH · SECONDS", span: 4, h: 260 });
  x.cDur = new Hist(x.dur.plot, { min: 0, bins: 30, fmt: v => v.toFixed(0) + "s" });
  x.ch = card(root, { title: "BUSIEST CHANNELS · HITS (LEDGER)", span: 6, h: 380 });
  x.cCh = new HBars(x.ch.plot, { labelW: 230 });
  x.band = card(root, { title: "CATCHES BY BAND · IN RANGE", span: 6, h: 180 });
  x.cBand = new HBars(x.band.plot, { labelW: 120 });
  x.tx = card(root, { title: "TRANSCRIBED SHARE OF VOICE CATCHES", span: 6, noPlot: true });
}, async x => {
  const rd = await src("radio"); const r = range(), P = PAL();
  const kc = { voice: P[0], data: P[2], carrier: P[5], seen: P[3], noise: OTHER() }, order = ["voice", "data", "carrier", "seen", "noise"];
  const db = byDay(rd.events, e => e[0], e => e[3], order, r); db.series.forEach(s => s.color = kc[s.name] || OTHER());
  x.cDay.set(db.cats, db.series); x.day.legend(db.series); x.day.source(rd, `${Fmt.n(db.n)} of ${Fmt.n(rd.events.length)} events in range`);
  const ev = rd.events.filter(e => inRange(e[0], r));
  x.day.table([{ h: "time" }, { h: "MHz", n: 1 }, { h: "seconds", n: 1 }, { h: "class" }, { h: "transcript" }], ev.map(e => [Fmt.ts(e[0]), (e[1] / 1e6).toFixed(4), e[2]?.toFixed(1), e[3], e[4] ? "yes" : ""]));
  x.cKind.set(order.map(k => ({ label: k, value: ev.filter(e => e[3] === k).length, color: kc[k] }))); x.kind.source(rd);
  const busy = ev.filter(e => e[3] === "voice" || e[3] === "data");
  const t0 = r[0] ?? (busy.length ? busy[0][0] : Date.now() / 1000), days = daysBetween(Math.max(t0, Date.now() / 1000 - 30 * DAY), Date.now() / 1000);
  const di = new Map(days.map((d, i) => [d.key, i])); const cells = days.map(() => new Array(24).fill(0));
  for (const e of busy) { const i = di.get(Stat.dayKey(e[0])); if (i != null) cells[i][new Date(e[0] * 1000).getHours()]++; }
  x.cClock.set(days.map(d => d.label), Array.from({ length: 24 }, (_, h) => ({ label: String(h).padStart(2, "0"), title: `${h}:00–${h}:59` })), cells, { fmt: v => v + " catches" });
  x.clock.source(rd, "at most the last 30 days"); x.clock.table([{ h: "day" }, ...Array.from({ length: 24 }, (_, h) => ({ h: String(h).padStart(2, "0"), n: 1 }))], days.map((d, i) => [d.label, ...cells[i]]));
  const voice = ev.filter(e => e[3] === "voice");
  x.cDur.set(voice.map(e => e[2]), { color: P[0] }); x.dur.source(rd);
  x.cCh.set(rd.channels.slice(0, 24).map(c => ({ label: `${(c[0] / 1e6).toFixed(4)} ${c[3] || c[2] || c[1] || ""}`.trim(), value: c[4], color: c[5] ? P[0] : c[6] ? P[2] : P[5], note: `voice ${c[5]} · data ${c[6]} · band ${c[1]}` })));
  x.ch.legend([{ name: "has voice", color: P[0] }, { name: "data only", color: P[2] }, { name: "neither", color: P[5] }]);
  x.ch.source(rd, "channels table, all time"); x.ch.table([{ h: "MHz", n: 1 }, { h: "band" }, { h: "service" }, { h: "label" }, { h: "hits", n: 1 }, { h: "voice", n: 1 }, { h: "data", n: 1 }], rd.channels.map(c => [(c[0] / 1e6).toFixed(4), c[1], c[2], c[3], c[4], c[5], c[6]]).reverse());
  const bandOf = hz => { const m = hz / 1e6; return m < 30 ? "HF" : m < 54 ? "6 m" : m < 88 ? "VHF low" : m < 108 ? "FM bcast" : m < 137 ? "airband" : m < 148 ? "2 m" : m < 174 ? "VHF high" : m < 420 ? "220/UHF" : m < 450 ? "70 cm" : m < 470 ? "UHF biz/GMRS" : "UHF high"; };
  const bands = rank(ev, e => bandOf(e[1]));
  x.cBand.set(bands.map(b => ({ label: b, value: ev.filter(e => bandOf(e[1]) === b).length, color: P[5] }))); x.band.source(rd, "bands bucketed by frequency in this page");
  const tr = voice.filter(e => e[4]).length;
  x.tx.body.innerHTML = `<div class="kv"><div>voice catches in range</div><div>${voice.length}</div><div>with a transcript</div><div>${tr} (${Fmt.pct(voice.length ? 100 * tr / voice.length : null)})</div><div>EAMs on file (eam.watch)</div><div>${rd.eam_count}</div></div>`;
  x.tx.source(rd);
});

// ════════════════════════════════════════════════════════════════════
// STAGE — records and art
// ════════════════════════════════════════════════════════════════════
tab("stage", "STAGE", (root, x) => {
  x.tr = card(root, { title: "TRANSITIONS PLANNED PER DAY · BY KIND", span: 8, h: 200 });
  x.cTr = new Bars(x.tr.plot);
  x.oc = card(root, { title: "HOW PLANS ENDED · ALL TIME", span: 4, h: 200 });
  x.cOc = new HBars(x.oc.plot, { labelW: 140 });
  x.lk = card(root, { title: "MEASURED LOCK · BLENDS PLANNED PER DAY", span: 8, h: 190 });
  x.cLk = new Bars(x.lk.plot);
  x.src = card(root, { title: "WHO PICKED THE RECORD · IN RANGE", span: 4, h: 190 });
  x.cSrc = new HBars(x.src.plot, { labelW: 110 });
  x.deg = card(root, { title: "PARTNER GRAPH · PARTNERS PER RECORD", span: 6, h: 190 });
  x.cDeg = new Hist(x.deg.plot, { min: 0, bins: 30, fmt: v => v.toFixed(0) });
  x.sets = card(root, { title: "SETS · LENGTH (SUM OF RECORD LENGTHS)", span: 6, h: 190 });
  x.cSets = new Bars(x.sets.plot, { y: { fmt: v => v + "m" } });
  sect(root, "ART");
  x.art = card(root, { title: "PIECES ON FILE", span: 12, noPlot: true });
}, async x => {
  const [rec, art] = await Promise.all([src("records"), src("art")]); const r = range(), P = PAL();
  const kc = { blend: P[0], cut: P[1], fade: P[2], echo: P[3], out: P[4] };
  const tb = byDay(rec.planned, e => e[0], e => e[1], ["blend", "cut", "fade", "echo", "out"], r); tb.series.forEach(s => s.color = kc[s.name] || OTHER());
  x.cTr.set(tb.cats, tb.series); x.tr.legend(tb.series);
  const lastPlan = rec.planned.length ? rec.planned[rec.planned.length - 1][0] : null;
  x.tr.sub(lastPlan ? `newest planned transition ${Fmt.ago(lastPlan)} (${Fmt.t(lastPlan)})` : "no transitions on file"); x.tr.source(rec, `${Fmt.n(tb.n)} planned in range`);
  x.tr.table([{ h: "time" }, { h: "kind" }, { h: "mode" }, { h: "picked by" }, { h: "lock" }, { h: "beats", n: 1 }, { h: "from", w: 1 }, { h: "to", w: 1 }], rec.planned.filter(e => inRange(e[0], r)).map(e => [Fmt.ts(e[0]), e[1], e[2], e[3], e[4], e[5], e[6], e[7]]));
  const oc = rec.outcomes.slice().sort((a, b) => b[2] - a[2]);
  x.cOc.set(oc.map(o => ({ label: `${o[0]} · ${o[1].replace("_", " ")}`, value: o[2], color: o[1] === "done" ? P[0] : OTHER() }))); x.oc.source(rec);
  const bl = rec.planned.filter(e => e[1] === "blend");
  const lb = byDay(bl, e => e[0], e => e[4] || "not measured", ["locked", "not locked", "not measured"], r);
  lb.series.forEach(s => s.color = s.name === "locked" ? P[0] : s.name === "not locked" ? P[1] : OTHER());
  x.cLk.set(lb.cats, lb.series); x.lk.legend(lb.series); x.lk.source(rec, "the mixcheck verdict on each planned blend");
  const pr = rec.planned.filter(e => inRange(e[0], r));
  x.cSrc.set(rank(pr, e => e[3] || "her pick").map(k => ({ label: k, value: pr.filter(e => (e[3] || "her pick") === k).length, color: P[5] }))); x.src.source(rec, "blank source = her own pick");
  x.cDeg.set(rec.degree, { color: P[4] }); x.deg.sub(`${rec.records} records · ${rec.with_partner} with a partner · ${Fmt.n(rec.edges)} measured pairs · method ${rec.method} · built ${Fmt.ago(rec.built)}`); x.deg.source(rec);
  x.cSets.set(rec.sets.map((s, i) => ({ label: String(i + 1), title: `set ${i + 1}: ${s.n} records` })), [{ name: "minutes", color: P[3], values: rec.sets.map(s => s.minutes) }], { labelW: 20 }); x.sets.source(rec, "before transition overlaps");
  x.art.body.innerHTML = `<div class="gallery">${art.pieces.slice().reverse().map(p => `<figure>${p.image ? `<img loading="lazy" src="/art/${esc(p.id)}.png" alt="${esc(p.title || p.id)}">` : ""}<figcaption>${esc(p.title || "untitled")}<span>${esc(p.palette || "")} · k=${p.symmetry ?? "?"} · ${p.render_s != null ? p.render_s.toFixed(1) + " s" : ""} · ${Fmt.t(p.ts)}</span></figcaption></figure>`).join("")}</div>`;
  x.art.source(art, `${art.pieces.length} pieces in memory/art`);
});

// ════════════════════════════════════════════════════════════════════
// CORPUS — knowledge base, index, dreams, TTRPG
// ════════════════════════════════════════════════════════════════════
tab("corpus", "CORPUS", (root, x) => {
  x.f = card(root, { title: "KNOWLEDGE BASE · FILES PER FOLDER", span: 6, h: 330 });
  x.cF = new HBars(x.f.plot, { labelW: 130 });
  x.mb = card(root, { title: "KNOWLEDGE BASE · MB PER FOLDER", span: 6, h: 330 });
  x.cMb = new HBars(x.mb.plot, { labelW: 130, fmt: v => v.toFixed(1) + " MB" });
  x.dr = card(root, { title: "DREAM FILES PER NIGHT · BY FOLDER", span: 8, h: 200 });
  x.cDr = new Bars(x.dr.plot);
  x.idx = card(root, { title: "RAG STORAGE · MB PER INDEX", span: 4, h: 200 });
  x.cIdx = new HBars(x.idx.plot, { labelW: 120, fmt: v => v.toFixed(1) + " MB" });
  x.tt = card(root, { title: "AETHELGARD · CHARACTERS", span: 12, noPlot: true });
}, async x => {
  const [c, tt] = await Promise.all([src("corpus"), src("ttrpg")]); const r = range(), P = PAL();
  const fo = Object.entries(c.folders).sort((a, b) => b[1].files - a[1].files);
  x.cF.set(fo.map(([k, v]) => ({ label: k, value: v.files, color: v.indexed ? P[0] : OTHER(), note: v.indexed ? "indexed" : "not indexed (leading _ or .)" })));
  x.f.legend([{ name: "indexed", color: P[0] }, { name: "not indexed", color: OTHER() }]); x.f.sub(`file manifest: <b>${Fmt.n(c.manifest_entries)}</b> entries`); x.f.source(c);
  x.f.table([{ h: "folder" }, { h: "files", n: 1 }, { h: "MB", n: 1 }, { h: "indexed" }], fo.map(([k, v]) => [k, v.files, v.mb, v.indexed ? "yes" : "no"]).reverse());
  x.cMb.set(fo.slice().sort((a, b) => b[1].mb - a[1].mb).map(([k, v]) => ({ label: k, value: v.mb, color: v.indexed ? P[0] : OTHER() }))); x.mb.source(c);
  const dev = []; for (const [day, fs] of Object.entries(c.dreams_by_day)) for (const [f, n] of Object.entries(fs)) for (let i = 0; i < n; i++) dev.push([Stat.dayStart(day) + 60, f]);
  const db = byDay(dev, e => e[0], e => e[1], rank(dev, e => e[1]), r);
  x.cDr.set(db.cats, db.series); x.dr.legend(db.series); x.dr.source(c, "dated by the dream_YYYYMMDD filename, else the file's mtime");
  x.cIdx.set(Object.entries(c.rag_mb).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ label: k, value: v, color: P[3] }))); x.idx.source(c);
  x.tt.body.innerHTML = tableHTML([{ h: "character" }, { h: "player" }, { h: "class" }, { h: "level", n: 1 }, { h: "location" }, { h: "gil", n: 1 }, { h: "deaths", n: 1 }, { h: "last played" }], tt.characters.slice().sort((a, b) => (a.level || 0) - (b.level || 0)).map(ch => [ch.name, ch.player, ch.class, ch.level, ch.location, Fmt.n(ch.gil), ch.deaths, Fmt.t(typeof ch.updated === "number" ? ch.updated : null)]));
  x.tt.source(tt, `${tt.fishing_records} fishing records`);
}, { noRange: false });

// ════════════════════════════════════════════════════════════════════
// CHECKS — read-only diagnostics, config switches, the source index
// ════════════════════════════════════════════════════════════════════
tab("checks", "CHECKS", (root, x) => {
  x.run = card(root, { title: "DIAGNOSTICS · READ-ONLY, NICED, ONE AT A TIME", span: 8, noPlot: true });
  x.cfg = card(root, { title: "SWITCHES · AS CONFIGURED", span: 4, noPlot: true });
  x.idx = card(root, { title: "SOURCE INDEX · EVERYTHING THIS DASHBOARD READS", span: 12, noPlot: true });
}, async x => {
  const [chk, cfg] = await Promise.all([get("/api/checks"), src("config")]);
  if (!x.wired) {
    x.wired = true;
    x.run.body.innerHTML = `<div style="display:flex;gap:8px;flex-wrap:wrap;padding:6px 10px">${Object.entries(chk.checks).map(([k, v]) => `<button class="btn big go" data-k="${k}">${esc(v)}</button>`).join("")}</div><pre class="out" id="runout">pick a check. none of them writes anything; output appears here.</pre>`;
    x.run.body.onclick = async e => {
      const k = e.target.dataset.k; if (!k) return;
      const btns = x.run.body.querySelectorAll("button"); btns.forEach(b => b.disabled = true);
      const out = $("#runout"); out.textContent = `running ${chk.checks[k]} …`;
      try { const r = await fetch(`/api/run/${k}`, { method: "POST" }).then(r => r.json()); out.textContent = r.error ? r.error : `$ ${r.cmd}\nexit ${r.rc} · ${r.seconds} s\n\n${r.stdout}${r.stderr ? "\n── stderr ──\n" + r.stderr : ""}`; }
      catch (err) { out.textContent = String(err); }
      btns.forEach(b => b.disabled = false);
    };
    x.run.foot.innerHTML = "runs: <code>tools/maintenance/audit_knowledge_base.py</code> · <code>clean_kaia_turns.py --show 15</code> (no --apply) · <code>health_check.py</code>";
  }
  const fl = cfg.flags || {}, us = cfg.unprompted_sources || {};
  const fv = v => v === true ? '<span class="on-c">● on</span>' : v === false ? '<span class="off-c">○ off</span>' : esc(v ?? "—");
  x.cfg.body.innerHTML = `<div class="kv">${Object.entries(fl).map(([k, v]) => `<div>${esc(k)}</div><div>${fv(v)}</div>`).join("")}${Object.entries(us).map(([k, v]) => `<div>unprompted.sources.${esc(k)}</div><div>${fv(v)}</div>`).join("")}</div>`;
  x.cfg.source(cfg, "defaults merged with kaia.yaml, read-only");
  const names = ["mood", "desires", "beliefs", "anchors", "growth", "relationships", "monologue", "self", "checks", "generation", "voice", "corpus", "social", "radio", "records", "art", "ttrpg", "journal", "git", "config"];
  const all = await Promise.all(names.map(n => src(n).catch(() => null)));
  const ls = D.logstats || await logstats();
  const rows = [["logstats", (ls.source || []).join(", "), Fmt.n(ls.lines) + " lines", ls.read_s * 1000, Date.now() / 1000]].concat(names.map((n, i) => { const v = all[i]; if (!v) return [n, "—", "error", null, null]; const size = Object.entries(v).filter(([k, a]) => Array.isArray(a) && !["source"].includes(k)).map(([k, a]) => `${k} ${Fmt.n(a.length)}`).join(" · "); return [n, (v.source || []).join(", "), v.error || size, v.read_ms, v.as_of]; }));
  x.idx.body.innerHTML = tableHTML([{ h: "reader" }, { h: "files", w: 1 }, { h: "rows" }, { h: "read ms", n: 1 }, { h: "as of" }], rows.map(r => [r[0], r[1], r[2], r[3] != null ? Fmt.n(r[3], 1) : "", r[4] ? new Date(r[4] * 1000).toTimeString().slice(0, 8) : ""]).reverse());
  x.idx.foot.innerHTML = "readers are cached until a source file's mtime or size changes; code: <code>utils/admin/sources.py</code>, <code>utils/admin/logscan.py</code>";
}, { noRange: true });

// ── boot ────────────────────────────────────────────────────────────
nav();
tickLive().then(() => { const want = (location.hash || "").slice(1) || (() => { try { return localStorage.getItem("ops.tab"); } catch (e) { return null; } })(); show(want || "ov"); });
setInterval(tickLive, 3000);
// Re-read the current tab every 30 s; readers on the server answer from cache unless a file changed.
setInterval(() => { if (!CUR || CUR.id === "logs" || document.hidden) return; D.src = {}; Promise.resolve(CUR.refresh(CUR.ctx)).catch(oops); }, 30000);
