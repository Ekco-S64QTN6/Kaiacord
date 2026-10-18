// KAIA // OPS charts: canvas marks, crisp text, one shared tooltip.
// Every chart takes plain arrays; nothing here fetches or invents data.
(() => {
"use strict";

const CSSV = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const clip = (s, px) => { s = String(s ?? ""); const n = Math.max(4, Math.floor(px / 6.2)); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const DPR = () => Math.max(1, window.devicePixelRatio || 1);
const FONT = '10px "JetBrains Mono", "DejaVu Sans Mono", monospace';

const Fmt = {
  n(v, d = 0) { if (v == null || !isFinite(v)) return "—"; return Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }); },
  k(v) { if (v == null) return "—"; const a = Math.abs(v); return a >= 1e6 ? (v / 1e6).toFixed(1) + "M" : a >= 1e4 ? (v / 1e3).toFixed(0) + "k" : a >= 1e3 ? (v / 1e3).toFixed(1) + "k" : String(Math.round(v * 100) / 100); },
  pct(v, d = 0) { return v == null ? "—" : Fmt.n(v, d) + "%"; },
  s(v) { return v == null ? "—" : v < 10 ? v.toFixed(2) + " s" : v.toFixed(1) + " s"; },
  t(ts) { if (!ts) return "—"; const d = new Date(ts * 1000); return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " + d.toTimeString().slice(0, 5); },
  ts(ts) { if (!ts) return "—"; const d = new Date(ts * 1000); return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " + d.toTimeString().slice(0, 8); },
  day(ts) { const d = new Date(ts * 1000); return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }); },
  ago(ts) { if (!ts) return "—"; const s = Date.now() / 1000 - ts; if (s < 0) return "now"; if (s < 90) return Math.round(s) + "s ago"; if (s < 5400) return Math.round(s / 60) + "m ago"; if (s < 172800) return (s / 3600).toFixed(1) + "h ago"; return Math.round(s / 86400) + "d ago"; },
  dur(s) { if (s == null) return "—"; if (s < 90) return Math.round(s) + "s"; if (s < 5400) return Math.round(s / 60) + "m"; if (s < 172800) return (s / 3600).toFixed(1) + "h"; return (s / 86400).toFixed(1) + "d"; },
};

const Stat = {
  q(arr, p) { if (!arr.length) return null; const a = Float64Array.from(arr).sort(); const i = (a.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return a[lo] + (a[hi] - a[lo]) * (i - lo); },
  mean(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : null; },
  dayKey(ts) { const d = new Date(ts * 1000); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); },
  dayStart(key) { const [y, m, d] = key.split("-").map(Number); return new Date(y, m - 1, d).getTime() / 1000; },
  // rolling quantile over a time window, evaluated at each point
  rolling(points, windowS, p) {
    const out = []; let lo = 0; const buf = [];
    for (let i = 0; i < points.length; i++) {
      while (points[lo][0] < points[i][0] - windowS) lo++;
      const vals = []; for (let j = lo; j <= i; j++) vals.push(points[j][1]);
      if (vals.length >= 3) out.push([points[i][0], Stat.q(vals, p)]);
    }
    return out;
  },
};

// ── tooltip ─────────────────────────────────────────────────────────
const Tip = {
  el: null,
  show(x, y, html) {
    if (!this.el) { this.el = document.createElement("div"); this.el.id = "tip"; document.body.appendChild(this.el); }
    this.el.innerHTML = html; this.el.style.display = "block";
    const r = this.el.getBoundingClientRect(), W = innerWidth, H = innerHeight;
    let left = x + 14, top = y + 12;
    if (left + r.width > W - 8) left = x - r.width - 14;
    if (top + r.height > H - 8) top = y - r.height - 12;
    this.el.style.left = Math.max(4, left) + "px"; this.el.style.top = Math.max(4, top) + "px";
  },
  hide() { if (this.el) this.el.style.display = "none"; },
};
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const sw = c => `<i class="sw" style="background:${c}"></i>`;

// ── base ────────────────────────────────────────────────────────────
class Chart {
  constructor(el, opt = {}) {
    this.el = el; this.opt = opt;
    this.cv = document.createElement("canvas"); el.appendChild(this.cv);
    this.ctx = this.cv.getContext("2d");
    this.pad = Object.assign({ l: 46, r: 12, t: 10, b: 20 }, opt.pad || {});
    this.ro = new ResizeObserver(() => this.draw()); this.ro.observe(el);
    this.cv.addEventListener("mousemove", e => this._hover(e));
    this.cv.addEventListener("mouseleave", () => { this.hoverX = null; Tip.hide(); this.draw(); });
  }
  size() {
    const w = this.el.clientWidth, h = this.opt.height || this.el.clientHeight || 160, d = DPR();
    if (this.cv.width !== Math.round(w * d) || this.cv.height !== Math.round(h * d)) {
      this.cv.width = Math.round(w * d); this.cv.height = Math.round(h * d);
      this.cv.style.width = w + "px"; this.cv.style.height = h + "px";
    }
    this.ctx.setTransform(d, 0, 0, d, 0, 0);
    this.W = w; this.H = h; return w > 10;
  }
  clear() { this.ctx.clearRect(0, 0, this.W, this.H); }
  visible() { return this.el.offsetParent !== null; }
  text(s, x, y, color, align = "left", base = "middle") {
    const c = this.ctx; c.font = FONT; c.fillStyle = color || CSSV("--dim"); c.textAlign = align; c.textBaseline = base; c.fillText(s, x, y);
  }
  empty(msg) { this.clear(); this.text(msg || "no data in this range", this.W / 2, this.H / 2, CSSV("--dim"), "center"); }
  _hover() {}
}

function niceTicks(lo, hi, n = 4) {
  if (hi <= lo) hi = lo + 1;
  const raw = (hi - lo) / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw) || mag * 10;
  const out = []; for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}
function timeTicks(lo, hi, px) {
  const span = hi - lo, want = Math.max(2, Math.floor(px / 90));
  const steps = [300, 900, 1800, 3600, 3 * 3600, 6 * 3600, 12 * 3600, 86400, 2 * 86400, 7 * 86400, 14 * 86400, 30 * 86400];
  const step = steps.find(s => span / s <= want) || 30 * 86400;
  const tz = new Date().getTimezoneOffset() * 60;
  const out = []; for (let t = Math.ceil((lo - tz) / step) * step + tz; t <= hi; t += step) out.push(t);
  return { ticks: out, step };
}
function tickLabel(t, step) {
  const d = new Date(t * 1000);
  if (step >= 86400) return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  if (d.getHours() === 0 && d.getMinutes() === 0) return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return d.toTimeString().slice(0, 5);
}

// ── time series ─────────────────────────────────────────────────────
// series: [{name, color, type: line|dots|step|area|bars, data: [[t, y], …], width, fmt}]
// opt: y: {min, max, fmt, label}, thresholds: [{y, label, color}], marks: [{t, label}], range: [t0, t1]
class TimeChart extends Chart {
  set(series, opt = {}) { this.series = series; Object.assign(this.opt, opt); this.draw(); }
  draw() {
    if (!this.series || !this.size()) return;
    const { pad } = this, c = this.ctx, o = this.opt;
    this.clear();
    const [r0, r1] = o.range || [null, null];
    const vis = this.series.map(s => ({ ...s, pts: s.data.filter(p => p[1] != null && (r0 == null || p[0] >= r0) && (r1 == null || p[0] <= r1)) }));
    const all = vis.flatMap(s => s.pts);
    if (!all.length) return this.empty(o.emptyMsg);
    let x0 = r0 ?? Math.min(...all.map(p => p[0])), x1 = r1 ?? Math.max(...all.map(p => p[0]));
    if (x1 - x0 < 60) { x0 -= 1800; x1 += 1800; }
    let y0 = o.y?.min, y1 = o.y?.max;
    const ys = all.map(p => p[1]).concat((o.thresholds || []).map(t => t.y));
    if (y0 == null) y0 = Math.min(0, ...ys);
    if (y1 == null) { y1 = Math.max(...ys); y1 = y1 + (y1 - y0) * 0.08 || 1; }
    const X = t => pad.l + (t - x0) / (x1 - x0) * (this.W - pad.l - pad.r);
    const Y = v => this.H - pad.b - (v - y0) / (y1 - y0) * (this.H - pad.t - pad.b);
    Object.assign(this, { X, Y, x0, x1, y0, y1, vis });
    // grid
    c.strokeStyle = CSSV("--grid"); c.lineWidth = 1;
    const yt = niceTicks(y0, y1, Math.max(2, Math.floor((this.H - pad.t - pad.b) / 34)));
    const yf = o.y?.fmt || Fmt.k;
    for (const v of yt) { const y = Math.round(Y(v)) + .5; c.beginPath(); c.moveTo(pad.l, y); c.lineTo(this.W - pad.r, y); c.stroke(); this.text(yf(v), pad.l - 6, y, null, "right"); }
    const { ticks, step } = timeTicks(x0, x1, this.W - pad.l - pad.r);
    for (const t of ticks) { const x = Math.round(X(t)) + .5; c.beginPath(); c.moveTo(x, pad.t); c.lineTo(x, this.H - pad.b); c.stroke(); this.text(tickLabel(t, step), x, this.H - pad.b + 11, null, "center"); }
    // marks (commits, boots)
    for (const m of o.marks || []) {
      if (m.t < x0 || m.t > x1) continue; const x = Math.round(X(m.t)) + .5;
      c.strokeStyle = m.color || CSSV("--faint"); c.setLineDash([2, 3]); c.beginPath(); c.moveTo(x, pad.t); c.lineTo(x, this.H - pad.b); c.stroke(); c.setLineDash([]);
    }
    // series
    for (const s of vis) {
      const col = s.color; c.strokeStyle = col; c.fillStyle = col; c.lineWidth = s.width || 2; c.lineJoin = "round";
      const pts = s.pts; if (!pts.length) continue;
      if (s.type === "dots") {
        const r = s.r || 2; c.globalAlpha = s.alpha ?? .75;
        for (const p of pts) { c.beginPath(); c.arc(X(p[0]), Y(p[1]), r, 0, 7); c.fill(); }
        c.globalAlpha = 1;
      } else if (s.type === "bars") {
        const bw = Math.max(1, (s.barS ? (X(x0 + s.barS) - X(x0)) : 3) - 2);
        for (const p of pts) { const x = X(p[0]), y = Y(p[1]), y0p = Y(Math.max(y0, 0)); c.fillRect(x, Math.min(y, y0p), bw, Math.abs(y0p - y)); }
      } else {
        c.beginPath();
        pts.forEach((p, i) => {
          const x = X(p[0]), y = Y(p[1]);
          if (i === 0) c.moveTo(x, y);
          else if (s.type === "step") { c.lineTo(x, Y(pts[i - 1][1])); c.lineTo(x, y); }
          else if (s.gap && p[0] - pts[i - 1][0] > s.gap) c.moveTo(x, y);
          else c.lineTo(x, y);
        });
        c.stroke();
        if (s.type === "area") { c.lineTo(X(pts[pts.length - 1][0]), Y(Math.max(y0, 0))); c.lineTo(X(pts[0][0]), Y(Math.max(y0, 0))); c.closePath(); c.globalAlpha = .12; c.fill(); c.globalAlpha = 1; }
      }
    }
    // thresholds: the neon line means "this is the limit"
    for (const th of o.thresholds || []) {
      if (th.y < y0 || th.y > y1) continue; const y = Math.round(Y(th.y)) + .5; const col = th.color || CSSV("--pink");
      c.save(); c.strokeStyle = col; c.lineWidth = 1; c.setLineDash([5, 4]); c.shadowColor = col; c.shadowBlur = 6;
      c.beginPath(); c.moveTo(pad.l, y); c.lineTo(this.W - pad.r, y); c.stroke(); c.restore();
      this.text(th.label, this.W - pad.r - 2, y - 7, col, "right");
    }
    if (o.y?.label) this.text(o.y.label, pad.l, pad.t - 1, CSSV("--dim"), "left", "top");
    // crosshair
    if (this.hoverX != null) {
      const x = Math.round(this.hoverX) + .5; c.strokeStyle = CSSV("--cyan"); c.globalAlpha = .5; c.lineWidth = 1;
      c.beginPath(); c.moveTo(x, pad.t); c.lineTo(x, this.H - pad.b); c.stroke(); c.globalAlpha = 1;
      for (const h of this.hits || []) { c.beginPath(); c.arc(X(h.p[0]), Y(h.p[1]), 4, 0, 7); c.fillStyle = h.s.color; c.fill(); c.strokeStyle = CSSV("--panel"); c.lineWidth = 2; c.stroke(); }
    }
  }
  _hover(e) {
    if (!this.vis) return;
    const r = this.cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top;
    if (mx < this.pad.l || mx > this.W - this.pad.r) { this.hoverX = null; Tip.hide(); return this.draw(); }
    const t = this.x0 + (mx - this.pad.l) / (this.W - this.pad.l - this.pad.r) * (this.x1 - this.x0);
    const hits = [];
    for (const s of this.vis) {
      if (!s.pts.length || s.noTip) continue;
      let lo = 0, hi = s.pts.length - 1;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (s.pts[m][0] < t) lo = m; else hi = m; }
      let best = Math.abs(s.pts[lo][0] - t) < Math.abs(s.pts[hi][0] - t) ? lo : hi;
      if (s.type === "dots") { // nearest in 2-D among close-by x
        let bd = 1e9; for (let i = Math.max(0, best - 60); i < Math.min(s.pts.length, best + 60); i++) { const dx = this.X(s.pts[i][0]) - mx, dy = this.Y(s.pts[i][1]) - my, d = dx * dx + dy * dy; if (d < bd) { bd = d; best = i; } }
        if (bd > 400) continue;
      } else if (Math.abs(this.X(s.pts[best][0]) - mx) > 40) continue;
      hits.push({ s, p: s.pts[best] });
    }
    this.hoverX = hits.length ? this.X(hits[0].p[0]) : mx; this.hits = hits; this.draw();
    if (!hits.length) return Tip.hide();
    const yf = this.opt.y?.tip || this.opt.y?.fmt || (v => Fmt.n(v, 2));
    const html = `<b>${Fmt.ts(hits[0].p[0])}</b>` + hits.map(h => `<div>${sw(h.s.color)}${esc(h.s.name)} <b>${(h.s.fmt || yf)(h.p[1])}</b>${h.p[2] != null ? ` <span class="dim">${esc(h.p[2])}</span>` : ""}</div>`).join("");
    Tip.show(e.clientX, e.clientY, html);
  }
}

// ── stacked bars by category (days, hours, tags) ────────────────────
// cats: [label…]; series: [{name, color, values: [n per cat]}]
class Bars extends Chart {
  set(cats, series, opt = {}) { this.cats = cats; this.series = series; Object.assign(this.opt, opt); this.draw(); }
  draw() {
    if (!this.cats || !this.size()) return;
    const { pad } = this, c = this.ctx, o = this.opt; this.clear();
    if (!this.cats.length) return this.empty();
    const tot = this.cats.map((_, i) => this.series.reduce((a, s) => a + (s.values[i] || 0), 0));
    const y1 = o.y?.max ?? (Math.max(...tot, ...(o.thresholds || []).map(t => t.y)) * 1.08 || 1);
    const n = this.cats.length, iw = this.W - pad.l - pad.r, bw = iw / n;
    const Y = v => this.H - pad.b - v / y1 * (this.H - pad.t - pad.b);
    c.strokeStyle = CSSV("--grid"); c.lineWidth = 1;
    for (const v of niceTicks(0, y1, Math.max(2, Math.floor((this.H - pad.t - pad.b) / 34)))) { const y = Math.round(Y(v)) + .5; c.beginPath(); c.moveTo(pad.l, y); c.lineTo(this.W - pad.r, y); c.stroke(); this.text((o.y?.fmt || Fmt.k)(v), pad.l - 6, y, null, "right"); }
    const every = Math.max(1, Math.ceil(n / Math.max(1, iw / (o.labelW || 52))));
    this.rects = [];
    for (let i = 0; i < n; i++) {
      const x = pad.l + i * bw + (bw > 6 ? 1 : 0), w = Math.max(1, bw - (bw > 6 ? 2 : 0.5));
      let acc = 0;
      this.series.forEach((s, si) => {
        const v = s.values[i] || 0; if (!v) return;
        const yTop = Y(acc + v), yBot = Y(acc); c.fillStyle = s.color;
        const gap = bw > 6 && acc > 0 ? 1 : 0;
        const isTop = this.series.slice(si + 1).every(s2 => !(s2.values[i] || 0));
        if (isTop && w > 6) { const r = Math.min(3, w / 2); c.beginPath(); c.moveTo(x, yBot - gap); c.lineTo(x, yTop + r); c.quadraticCurveTo(x, yTop, x + r, yTop); c.lineTo(x + w - r, yTop); c.quadraticCurveTo(x + w, yTop, x + w, yTop + r); c.lineTo(x + w, yBot - gap); c.closePath(); c.fill(); }
        else c.fillRect(x, yTop, w, yBot - yTop - gap);
        this.rects.push({ x, w, y: yTop, h: yBot - yTop, i, s, v });
        acc += v;
      });
      if (i % every === 0) this.text(this.cats[i].label ?? this.cats[i], x + w / 2, this.H - pad.b + 11, null, "center");
    }
    for (const th of o.thresholds || []) { const y = Math.round(Y(th.y)) + .5, col = th.color || CSSV("--pink"); c.save(); c.strokeStyle = col; c.setLineDash([5, 4]); c.shadowColor = col; c.shadowBlur = 6; c.beginPath(); c.moveTo(pad.l, y); c.lineTo(this.W - pad.r, y); c.stroke(); c.restore(); this.text(th.label, this.W - pad.r - 2, y - 7, col, "right"); }
    if (this.hi != null) { const x = pad.l + this.hi * bw; c.fillStyle = "rgba(0,240,255,.07)"; c.fillRect(x, pad.t, bw, this.H - pad.t - pad.b); }
    this.bw = bw; this.tot = tot;
  }
  _hover(e) {
    if (!this.cats || !this.cats.length) return;
    const r = this.cv.getBoundingClientRect(), mx = e.clientX - r.left;
    const i = Math.floor((mx - this.pad.l) / this.bw);
    if (i < 0 || i >= this.cats.length) { this.hi = null; Tip.hide(); return this.draw(); }
    this.hi = i; this.draw();
    const cat = this.cats[i], f = this.opt.y?.tip || this.opt.y?.fmt || Fmt.n;
    const rows = this.series.filter(s => s.values[i]).map(s => `<div>${sw(s.color)}${esc(s.name)} <b>${f(s.values[i])}</b></div>`).reverse().join("");
    Tip.show(e.clientX, e.clientY, `<b>${esc(cat.title ?? cat.label ?? cat)}</b>${this.series.length > 1 ? `<div class="dim">total ${f(this.tot[i])}</div>` : ""}${rows || '<div class="dim">none</div>'}`);
    if (this.opt.onHover) this.opt.onHover(i);
  }
}

// ── histogram ───────────────────────────────────────────────────────
class Hist extends Chart {
  set(values, opt = {}) { this.values = values.filter(v => v != null && isFinite(v)); Object.assign(this.opt, opt); this.draw(); }
  draw() {
    if (!this.values || !this.size()) return;
    const { pad } = this, c = this.ctx, o = this.opt; this.clear();
    const v = this.values; if (!v.length) return this.empty();
    const lo = o.min ?? Math.min(...v), hi = o.max ?? Math.max(...v);
    const nb = o.bins || 30, bw = (hi - lo) / nb || 1;
    const counts = new Array(nb).fill(0); for (const x of v) counts[Math.min(nb - 1, Math.max(0, Math.floor((x - lo) / bw)))]++;
    const y1 = Math.max(...counts) * 1.1;
    const X = x => pad.l + (x - lo) / (hi - lo || 1) * (this.W - pad.l - pad.r), Y = n => this.H - pad.b - n / y1 * (this.H - pad.t - pad.b);
    c.strokeStyle = CSSV("--grid");
    for (const t of niceTicks(0, y1, 3)) { const y = Math.round(Y(t)) + .5; c.beginPath(); c.moveTo(pad.l, y); c.lineTo(this.W - pad.r, y); c.stroke(); this.text(Fmt.k(t), pad.l - 6, y, null, "right"); }
    for (const t of niceTicks(lo, hi, Math.max(2, Math.floor((this.W - pad.l - pad.r) / 70)))) this.text((o.fmt || Fmt.k)(t), X(t), this.H - pad.b + 11, null, "center");
    c.fillStyle = o.color || CSSV("--s1");
    counts.forEach((n, i) => { if (!n) return; const x = X(lo + i * bw) + 1, w = Math.max(1, X(lo + (i + 1) * bw) - X(lo + i * bw) - 2); const y = Y(n); const r = Math.min(3, w / 2, (Y(0) - y) / 2); c.beginPath(); c.moveTo(x, Y(0)); c.lineTo(x, y + r); c.quadraticCurveTo(x, y, x + r, y); c.lineTo(x + w - r, y); c.quadraticCurveTo(x + w, y, x + w, y + r); c.lineTo(x + w, Y(0)); c.fill(); });
    const marks = [["p50", Stat.q(v, .5)], ["p90", Stat.q(v, .9)]];
    for (const [lbl, q] of marks) { const x = Math.round(X(q)) + .5; c.strokeStyle = CSSV("--text"); c.globalAlpha = .55; c.setLineDash([2, 3]); c.beginPath(); c.moveTo(x, pad.t + 8); c.lineTo(x, this.H - pad.b); c.stroke(); c.setLineDash([]); c.globalAlpha = 1; this.text(lbl, x + 3, pad.t + 6, CSSV("--mid")); }
    for (const th of o.thresholds || []) { if (th.x < lo || th.x > hi) continue; const x = Math.round(X(th.x)) + .5, col = th.color || CSSV("--pink"); c.save(); c.strokeStyle = col; c.setLineDash([5, 4]); c.shadowColor = col; c.shadowBlur = 6; c.beginPath(); c.moveTo(x, pad.t); c.lineTo(x, this.H - pad.b); c.stroke(); c.restore(); this.text(th.label, x - 4, pad.t + 18, col, "right"); }
    Object.assign(this, { counts, lo, bw, X });
  }
  _hover(e) {
    if (!this.counts) return; const r = this.cv.getBoundingClientRect(), mx = e.clientX - r.left;
    const i = Math.floor((mx - this.pad.l) / (this.W - this.pad.l - this.pad.r) * this.counts.length);
    if (i < 0 || i >= this.counts.length) return Tip.hide();
    const f = this.opt.fmt || (x => Fmt.n(x, 2));
    Tip.show(e.clientX, e.clientY, `<b>${f(this.lo + i * this.bw)} – ${f(this.lo + (i + 1) * this.bw)}</b><div>${Fmt.n(this.counts[i])} of ${Fmt.n(this.values.length)} <span class="dim">(${Fmt.pct(100 * this.counts[i] / this.values.length, 1)})</span></div>`);
  }
}

// ── heatmap: rows × cols, one hue dim → bright ─────────────────────
class Heat extends Chart {
  set(rows, cols, cells, opt = {}) { this.rows = rows; this.cols = cols; this.cells = cells; Object.assign(this.opt, opt); this.draw(); }
  draw() {
    if (!this.rows || !this.size()) return;
    const c = this.ctx, o = this.opt; this.clear();
    if (!this.rows.length || !this.cols.length) return this.empty();
    const pad = this.pad; pad.l = o.labelW ?? 120;
    const cw = (this.W - pad.l - pad.r) / this.cols.length, rh = (this.H - pad.t - pad.b) / this.rows.length;
    let mx = 0; for (const r of this.cells) for (const v of r) if (v > mx) mx = v;
    const hue = o.hue || [0, 240, 255];
    const scale = o.log ? (v => Math.log1p(v) / Math.log1p(mx || 1)) : (v => v / (mx || 1));
    this.rows.forEach((rw, ri) => {
      this.text(clip(rw, pad.l - 10), pad.l - 6, pad.t + ri * rh + rh / 2, CSSV("--mid"), "right");
      this.cols.forEach((_, ci) => {
        const v = this.cells[ri][ci] || 0; const x = pad.l + ci * cw, y = pad.t + ri * rh;
        if (!v) { c.fillStyle = CSSV("--cell0"); }
        else { const a = 0.14 + 0.86 * scale(v); c.fillStyle = `rgba(${hue[0]},${hue[1]},${hue[2]},${a.toFixed(3)})`; }
        c.fillRect(x + (cw > 4 ? 1 : 0), y + 1, Math.max(1, cw - (cw > 4 ? 2 : 0)), Math.max(1, rh - 2));
      });
    });
    const every = Math.max(1, Math.ceil(this.cols.length / ((this.W - pad.l - pad.r) / (o.colLabelW || 46))));
    this.cols.forEach((cl, ci) => { if (ci % every === 0) this.text(cl.label ?? cl, pad.l + ci * cw + cw / 2, this.H - pad.b + 11, null, "center"); });
    Object.assign(this, { cw, rh, mx });
  }
  _hover(e) {
    if (!this.cw) return; const r = this.cv.getBoundingClientRect();
    const ci = Math.floor((e.clientX - r.left - this.pad.l) / this.cw), ri = Math.floor((e.clientY - r.top - this.pad.t) / this.rh);
    if (ci < 0 || ri < 0 || ci >= this.cols.length || ri >= this.rows.length) return Tip.hide();
    const col = this.cols[ci], f = this.opt.fmt || Fmt.n;
    Tip.show(e.clientX, e.clientY, `<b>${esc(this.rows[ri])}</b><div>${esc(col.title ?? col.label ?? col)}: <b>${f(this.cells[ri][ci] || 0)}</b></div>`);
  }
}

// ── strip plot: a distribution per category (dots + median + p90) ───
class Strips extends Chart {
  set(groups, opt = {}) { this.groups = groups; Object.assign(this.opt, opt); this.draw(); }  // [{name, values}]
  draw() {
    if (!this.groups || !this.size()) return;
    const c = this.ctx, o = this.opt, pad = this.pad; pad.l = o.labelW ?? 130; this.clear();
    const g = this.groups.filter(x => x.values.length); if (!g.length) return this.empty();
    const all = g.flatMap(x => x.values); const lo = o.log ? Math.max(0.05, Math.min(...all)) : 0, hi = Math.max(...all) * 1.05;
    const T = o.log ? (v => Math.log10(Math.max(v, lo))) : (v => v);
    const X = v => pad.l + (T(v) - T(lo)) / (T(hi) - T(lo) || 1) * (this.W - pad.l - pad.r);
    const rh = (this.H - pad.t - pad.b) / g.length;
    const ticks = o.log ? [0.1, 0.3, 1, 3, 10, 30, 100, 300, 1000].filter(t => t >= lo && t <= hi) : niceTicks(lo, hi, 5);
    c.strokeStyle = CSSV("--grid"); for (const t of ticks) { const x = Math.round(X(t)) + .5; c.beginPath(); c.moveTo(x, pad.t); c.lineTo(x, this.H - pad.b); c.stroke(); this.text((o.fmt || Fmt.k)(t), x, this.H - pad.b + 11, null, "center"); }
    let seed = 7; const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
    g.forEach((grp, i) => {
      const yc = pad.t + i * rh + rh / 2;
      this.text(clip(`${grp.name} · ${grp.values.length}`, pad.l - 12), pad.l - 8, yc, CSSV("--mid"), "right");
      c.fillStyle = grp.color || CSSV("--s1"); c.globalAlpha = Math.max(0.12, Math.min(0.7, 40 / grp.values.length));
      for (const v of grp.values) { c.beginPath(); c.arc(X(v), yc + (rnd() - .5) * rh * .6, 1.8, 0, 7); c.fill(); }
      c.globalAlpha = 1;
      const m = Stat.q(grp.values, .5), p9 = Stat.q(grp.values, .9);
      c.fillStyle = CSSV("--text"); c.fillRect(X(m) - 1, yc - rh * .38, 2, rh * .76);
      c.fillStyle = CSSV("--mid"); c.fillRect(X(p9) - .5, yc - rh * .25, 1, rh * .5);
    });
    Object.assign(this, { g, rh, X });
  }
  _hover(e) {
    if (!this.g) return; const r = this.cv.getBoundingClientRect(); const i = Math.floor((e.clientY - r.top - this.pad.t) / this.rh);
    const grp = this.g[i]; if (!grp) return Tip.hide(); const f = this.opt.fmt || Fmt.n, v = grp.values;
    Tip.show(e.clientX, e.clientY, `<b>${esc(grp.name)}</b><div>n <b>${Fmt.n(v.length)}</b></div><div>p50 <b>${f(Stat.q(v, .5))}</b> · p90 <b>${f(Stat.q(v, .9))}</b> · max <b>${f(Math.max(...v))}</b></div>${grp.note ? `<div class="dim">${esc(grp.note)}</div>` : ""}`);
  }
}

// ── horizontal bars (ranked categories) ─────────────────────────────
class HBars extends Chart {
  set(items, opt = {}) { this.items = items; Object.assign(this.opt, opt); this.draw(); }  // [{label, value, color, note}]
  draw() {
    if (!this.items || !this.size()) return;
    const c = this.ctx, o = this.opt, pad = this.pad; pad.l = o.labelW ?? 140; this.clear();
    if (!this.items.length) return this.empty();
    const mx = o.max ?? (Math.max(...this.items.map(i => i.value)) || 1), rh = (this.H - pad.t - pad.b) / this.items.length;
    this.items.forEach((it, i) => {
      const y = pad.t + i * rh, w = (it.value / mx) * (this.W - pad.l - pad.r - 54), h = Math.min(rh - 3, 14);
      this.text(clip(it.label, pad.l - 12), pad.l - 8, y + rh / 2, CSSV("--mid"), "right");
      c.fillStyle = it.color || CSSV("--s1"); const r = Math.min(3, h / 2, w / 2);
      if (w > 0) { c.beginPath(); c.moveTo(pad.l, y + (rh - h) / 2); c.lineTo(pad.l + w - r, y + (rh - h) / 2); c.quadraticCurveTo(pad.l + w, y + (rh - h) / 2, pad.l + w, y + (rh - h) / 2 + r); c.lineTo(pad.l + w, y + (rh + h) / 2 - r); c.quadraticCurveTo(pad.l + w, y + (rh + h) / 2, pad.l + w - r, y + (rh + h) / 2); c.lineTo(pad.l, y + (rh + h) / 2); c.fill(); }
      this.text((o.fmt || Fmt.n)(it.value), pad.l + w + 6, y + rh / 2, CSSV("--text"));
    });
    this.rh = rh;
  }
  _hover(e) {
    if (!this.items) return; const r = this.cv.getBoundingClientRect(); const it = this.items[Math.floor((e.clientY - r.top - this.pad.t) / this.rh)];
    if (!it) return Tip.hide(); Tip.show(e.clientX, e.clientY, `<b>${esc(it.label)}</b><div>${(this.opt.fmt || Fmt.n)(it.value)}</div>${it.note ? `<div class="dim">${esc(it.note)}</div>` : ""}`);
  }
}

// ── sparkline (in tiles; no axes, hover for value) ─────────────────
class Spark extends Chart {
  constructor(el, opt) { super(el, Object.assign({ pad: { l: 1, r: 1, t: 3, b: 3 } }, opt)); }
  set(data, opt = {}) { this.data = data.filter(p => p[1] != null); Object.assign(this.opt, opt); this.draw(); }
  draw() {
    if (!this.data || !this.size()) return; const c = this.ctx, o = this.opt, pad = this.pad; this.clear();
    const d = this.data; if (d.length < 2) return;
    const x0 = d[0][0], x1 = d[d.length - 1][0]; const ys = d.map(p => p[1]);
    const y0 = o.min ?? Math.min(...ys), y1 = o.max ?? Math.max(...ys) * 1.02 + 1e-9;
    const X = t => pad.l + (t - x0) / (x1 - x0 || 1) * (this.W - pad.l - pad.r), Y = v => this.H - pad.b - (v - y0) / (y1 - y0 || 1) * (this.H - pad.t - pad.b);
    c.strokeStyle = o.color || CSSV("--s1"); c.lineWidth = 1.5; c.beginPath(); d.forEach((p, i) => i ? c.lineTo(X(p[0]), Y(p[1])) : c.moveTo(X(p[0]), Y(p[1]))); c.stroke();
    c.lineTo(X(x1), this.H - pad.b); c.lineTo(X(x0), this.H - pad.b); c.closePath(); c.fillStyle = o.color || CSSV("--s1"); c.globalAlpha = .1; c.fill(); c.globalAlpha = 1;
    if (o.threshold != null && o.threshold <= y1) { const y = Y(o.threshold); c.save(); c.strokeStyle = CSSV("--pink"); c.setLineDash([3, 3]); c.beginPath(); c.moveTo(pad.l, y); c.lineTo(this.W - pad.r, y); c.stroke(); c.restore(); }
    Object.assign(this, { X, x0, x1 });
  }
  _hover(e) {
    if (!this.data || this.data.length < 2) return; const r = this.cv.getBoundingClientRect(); const t = this.x0 + (e.clientX - r.left) / this.W * (this.x1 - this.x0);
    let best = this.data[0]; for (const p of this.data) if (Math.abs(p[0] - t) < Math.abs(best[0] - t)) best = p;
    Tip.show(e.clientX, e.clientY, `<b>${Fmt.ts(best[0])}</b><div>${(this.opt.fmt || (v => Fmt.n(v, 1)))(best[1])}</div>`);
  }
}

window.KC = { Fmt, Stat, Tip, esc, sw, TimeChart, Bars, Hist, Heat, Strips, HBars, Spark, CSSV };
})();
