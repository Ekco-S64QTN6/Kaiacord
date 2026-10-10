/**
 * KAIA // ANIMATOR
 *
 * Turns Kaiagotchi moods and events into the per-frame parameter set that
 * KaiaRenderer draws. Every expression is a point in one continuous parameter
 * space; each parameter chases its target through a critically damped spring,
 * so a transition between ANY two moods is smooth by construction.
 *
 * Layers summed each frame:
 *   mood preset (springs) + idle life (breath, heartbeat, blinks, saccades, sway)
 *   + speech (mouth flaps) + reactions (capture, discovery, alert)
 *   + transition FX (glyph resync sweep riding on a blink)
 */

// Spring stiffness per parameter group (rad/s). Higher = snappier.
const OMEGA = { face: 5.5, head: 2.6, color: 2.2, gaze: 20, talk: 30, fx: 6 };

const PARAMS = {
  browRaise: 'face', browInner: 'face', browAsym: 'face',
  lid: 'face', lidAsym: 'face', wide: 'face', squint: 'face',
  smile: 'face', smileAsym: 'face', mouthOpen: 'face',
  gazeX: 'gaze', gazeY: 'gaze',
  roll: 'head', yaw: 'head', pitch: 'head', zoom: 'head',
  glow: 'color', flowSpeed: 'color', flowDir: 'color', brightness: 'color',
  tintR: 'color', tintG: 'color', tintB: 'color',
  glyph: 'color', conduit: 'color', bloom: 'color', dither: 'color', tears: 'color',
  reticle: 'fx', reticleScale: 'fx', reticleDouble: 'fx',
  glitch: 'fx', grain: 'fx', aberration: 'fx',
};

const GREEN = [0.32, 1.0, 0.5];
const NEUTRAL = {
  browRaise: 0, browInner: 0, browAsym: 0, lid: 0.06, lidAsym: 0, wide: 0, squint: 0,
  smile: 0, smileAsym: 0, mouthOpen: 0, gazeX: 0, gazeY: 0,
  roll: 0, yaw: 0, pitch: 0, zoom: 1,
  glow: 1, flowSpeed: 1, flowDir: 1, brightness: 1,
  tintR: GREEN[0], tintG: GREEN[1], tintB: GREEN[2],
  glyph: 0.42, conduit: 0.7, bloom: 0.55, dither: 0.35, tears: 0,
  reticle: 0.35, reticleScale: 1, reticleDouble: 0,
  glitch: 0, grain: 0.06, aberration: 0,
  // behaviour knobs (not springs)
  breathRate: 0.24, breathAmp: 1, pulseRate: 1.0, blinkMin: 2.4, blinkMax: 5.5, blinkSpeed: 1,
  energy: 1, saccade: 1, microGlitch: 0, flicker: 0, strobe: 0,
  kick: null,  // spring velocity impulses applied on entering the mood, e.g. { pitch: -0.6 }
};

const tint = (r, g, b) => ({ tintR: r, tintG: g, tintB: b });

/** Mood presets: deltas over NEUTRAL. Keys match kaiagotchi.core.automata.AgentMood. */
const MOODS = {
  neutral: {},
  awake: { browRaise: 0.35, wide: 0.35, glow: 1.15, flowSpeed: 1.3, glyph: 0.7, reticle: 0.6 },
  happy: {
    smile: 1.0, squint: 0.55, browRaise: 0.3, roll: 0.035, pitch: -0.1,
    glow: 1.4, flowSpeed: 2.6, flowDir: 1, conduit: 0.85, bloom: 0.8, glyph: 0.45,
    breathAmp: 1.1, pulseRate: 1.3, energy: 1.2,
  },
  curious: {
    wide: 0.85, browRaise: 0.7, browAsym: 0.22, lid: 0, roll: -0.05, yaw: 0.25, pitch: 0.12, zoom: 1.045,
    mouthOpen: 0.08, glow: 1.2, flowSpeed: 2.0, reticle: 0.85, reticleScale: 1.5,
    blinkMin: 3.5, blinkMax: 7, saccade: 1.6, energy: 1.3,
  },
  bored: {
    lid: 0.42, gazeX: 0.6, gazeY: 0.22, browAsym: 0.18, smile: -0.12, smileAsym: -0.15, roll: -0.04,
    glow: 0.35, flowSpeed: 0.4, conduit: 0.3, glyph: 0.6, reticle: 0.2,
    breathRate: 0.18, blinkMin: 3, blinkMax: 6, blinkSpeed: 0.55, saccade: 0.4, energy: 0.6,
  },
  sad: {
    browInner: 0.9, browRaise: -0.1, lid: 0.3, gazeY: 0.55, gazeX: -0.12, smile: -0.5, pitch: 0.55, roll: 0.03,
    glow: 0.55, flowSpeed: 0.7, flowDir: -1, tears: 1, conduit: 0.3, brightness: 0.88, reticle: 0.2,
    breathRate: 0.17, breathAmp: 1.25, pulseRate: 0.8, blinkSpeed: 0.75, saccade: 0.5, energy: 0.5,
    ...tint(0.3, 0.86, 0.95),
  },
  frustrated: {
    browInner: -0.75, lid: 0.18, squint: 0.2, smile: -0.35, smileAsym: 0.12, pitch: 0.1,
    glow: 0.95, flowSpeed: 1.4, grain: 0.09, microGlitch: 1, breathRate: 0.32, pulseRate: 1.35,
    saccade: 1.4, ...tint(0.66, 1.0, 0.4),
  },
  sleepy: {
    lid: 0.64, browRaise: -0.05, gazeY: 0.25, pitch: 0.35, roll: 0.07, mouthOpen: 0.05,
    glow: 0.2, flowSpeed: 0.3, brightness: 0.72, conduit: 0.18, glyph: 0.4, dither: 0.5, reticle: 0.1,
    breathRate: 0.12, breathAmp: 1.5, pulseRate: 0.5,
    blinkMin: 3.5, blinkMax: 7, blinkSpeed: 0.4, saccade: 0.25, energy: 0.35,
  },
  confident: {
    smile: 0.35, smileAsym: 0.4, lid: 0.16, browAsym: 0.15, pitch: -0.18, roll: -0.03,
    glow: 1.6, flowSpeed: 1.6, conduit: 1.4, bloom: 1.0, reticle: 0.95, reticleDouble: 1, reticleScale: 0.95,
    saccade: 0.45, energy: 0.9,
  },
  broken: {
    wide: 0.55, browInner: 0.55, mouthOpen: 0.22, gazeX: 0.2,
    glitch: 0.5, grain: 0.16, aberration: 1, glyph: 0.85, dither: 0.6, conduit: 1.0,
    glow: 0.8, flowSpeed: 3.2, brightness: 0.92, saccade: 2.2, energy: 1.6, flicker: 1,
    ...tint(0.6, 0.95, 0.66),
  },
  angry: {
    browInner: -1.0, browRaise: -0.3, lid: 0.24, squint: 0.35, smile: -0.55, pitch: 0.18,
    glow: 1.5, flowSpeed: 2.5, conduit: 0.9, bloom: 0.8, glitch: 0.03, grain: 0.08,
    breathRate: 0.34, breathAmp: 1.2, pulseRate: 1.6, saccade: 0.5, energy: 1.3,
    ...tint(0.95, 0.55, 0.36),
  },
  debug: {
    wide: 0.3, glow: 2.0, flowSpeed: 4.2, glyph: 1.0, conduit: 1.2, dither: 0.5,
    glitch: 0.12, reticle: 0.9, reticleScale: 1.25, saccade: 2.5, energy: 1.5, ...tint(0.55, 1.0, 0.6),
  },
};

const REACTIONS = {
  // Passive handshake capture: conduit surge + confident flash + double lock.
  capture: { dur: 3.4, smile: 0.55, smileAsym: 0.25, wide: 0.35, browRaise: 0.35, glow: 1.2, flowSpeed: 2.5,
    conduitFlash: 2.2, reticleDouble: 1, reticle: 0.6, bloom: 0.6, sweep: true, signal: 0.18 },
  discovery: { dur: 1.4, wide: 0.3, browRaise: 0.25, glow: 0.35, reticleScale: 0.3, reticle: 0.3 },
  alert: { dur: 1.6, wide: 0.6, browInner: -0.3, glow: 0.4, glitch: 0.12 },
};

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const rand = (a, b) => a + Math.random() * (b - a);

/** Exact critically damped spring step (stable for any dt). */
function springStep(s, w, dt) {
  const x0 = s.x - s.t;
  const e = Math.exp(-w * dt);
  const k = s.v + w * x0;
  s.x = s.t + (x0 + k * dt) * e;
  s.v = (s.v - w * k * dt) * e;
}

/** Lub-dub heartbeat envelope, phase in [0,1). */
function heartbeat(ph) {
  return Math.exp(-Math.pow(ph * 14, 2)) + 0.55 * Math.exp(-Math.pow((ph - 0.17) * 14, 2));
}

class KaiaAnimator {
  constructor() {
    this.springs = {};
    for (const k of Object.keys(PARAMS)) this.springs[k] = { x: NEUTRAL[k], v: 0, t: NEUTRAL[k] };
    this.preset = { ...NEUTRAL };
    this.mood = 'neutral';
    this.offsets = {};                             // setOffsets(): continuous nudges on top of the mood
    this.still = false;

    this.time = 0;
    this.breathPhase = 0;
    this.beatPhase = 0;
    this.flowPhase = 0;
    this.rainPhase = 0;
    this.conduitPhase = 0;

    this.blink = { next: rand(1, 3), start: -1, double: false };
    this.sacc = { next: 0.5, x: 0, y: 0 };
    this.mouth = { x: 0, v: 0, t: 0 };
    this.look = null;                              // lookAt(): a gaze target that overrides the mood's
    this.lookYaw = { x: 0, v: 0, t: 0 };           // ...and turns the head a little toward it
    this.speech = { text: '', i: 0, acc: 0, cps: 30, done: true };
    this.reactions = [];
    this.sweep = -1;
    this.signal = 0;
    this.linkOk = true;
    this.open = 1;
    this.opening = false;
  }

  static get moods() { return Object.keys(MOODS); }

  /**
   * Register (or replace) a mood/state preset so a host project can map its own
   * states onto the shared engine, e.g. a security dashboard's 'LockdownMode'.
   * `preset` holds deltas over the neutral pose (same keys as MOODS entries).
   */
  static registerMood(name, preset) {
    MOODS[String(name).toLowerCase()] = { ...preset };
  }

  /** Codec "call open": window expands from a line while static resolves. */
  boot() {
    this.open = 0;
    this.opening = true;
    this.signal = 1;
    this.sweep = 0;
  }

  setMood(name) {
    const key = String(name || 'neutral').toLowerCase();
    const preset = MOODS[key] ? key : 'neutral';
    if (preset === this.mood) return;
    this.mood = preset;
    this.preset = { ...NEUTRAL, ...MOODS[preset] };
    this._retarget();
    // Expression changes ride on a blink, a small head re-settle and a glyph
    // resync sweep down the face.
    this._scheduleBlink(0.06);
    this.springs.pitch.v += 0.25;
    if (this.preset.kick) {
      for (const [k, v] of Object.entries(this.preset.kick)) if (this.springs[k]) this.springs[k].v += v;
    }
    this.sweep = 0;
    this.signal = Math.max(this.signal, 0.08);
  }

  _retarget() {
    for (const k of Object.keys(PARAMS)) this.springs[k].t = this.preset[k] + (this.offsets[k] || 0);
  }

  /**
   * Continuous expression nudges added to the current mood's targets, e.g. a
   * smile that follows a valence reading. Replaces the previous offsets; the
   * springs carry the change smoothly. Keys are the PARAMS names.
   */
  setOffsets(offsets) {
    this.offsets = { ...(offsets || {}) };
    this._retarget();
  }

  /** Change behaviour knobs (pulseRate, breathRate, saccade, ...) without a mood transition. */
  setBehavior(knobs) {
    for (const [k, v] of Object.entries(knobs || {})) if (!(k in PARAMS) && typeof v === 'number') this.preset[k] = v;
  }

  /** Mouth flaps for a transmitted line (no subtitle; the line goes to chatter). */
  speak(text) {
    const t = String(text || '').slice(0, 140);
    this.speech = { text: t, i: 0, acc: 0, cps: 30, done: !t };
  }

  react(kind) {
    const R = REACTIONS[kind];
    if (!R) return;
    this.reactions.push({ ...R, t: 0 });
    if (R.sweep) this.sweep = 0;
    if (R.signal) this.signal = Math.max(this.signal, R.signal);
    if (kind === 'discovery') {
      this.sacc.x = rand(-0.5, 0.5);
      this.sacc.y = rand(-0.2, 0.1);
      this.sacc.next = this.time + 0.9;
    }
  }

  /**
   * Direct her gaze at something on screen, e.g. a sweep moving across a dial.
   * x, y in gaze units (-1 left/up .. 1 right/down; ~±0.6 reads naturally).
   * Call it every frame while it applies; it lapses `holdS` after the last call.
   */
  lookAt(x, y = 0, holdS = 0.5) {
    this.look = { x: clamp(x, -1, 1), y: clamp(y, -1, 1), until: this.time + holdS };
  }

  setLink(ok) {
    if (ok && !this.linkOk) this.signal = 0.6;
    this.linkOk = ok;
  }

  _scheduleBlink(delay) { this.blink.next = this.time + delay; }

  _blinkAmount() {
    const b = this.blink;
    if (b.start < 0) return 0;
    const sp = this.preset.blinkSpeed;
    const close = 0.07 / sp, hold = 0.035 / sp, open = 0.16 / sp;
    const t = this.time - b.start;
    if (t < close) return Math.pow(t / close, 2);
    if (t < close + hold) return 1;
    if (t < close + hold + open) return 1 - Math.pow((t - close - hold) / open, 0.6);
    if (b.double) {
      b.double = false;
      b.start = this.time + 0.05;
      return 0;
    }
    b.start = -1;
    return 0;
  }

  _speechStep(dt) {
    const s = this.speech;
    if (s.done) { this.mouth.t = 0; return; }
    s.acc += dt * s.cps;
    while (s.acc >= 1 && s.i < s.text.length) {
      s.acc -= 1;
      const ch = s.text[s.i++];
      if (/[aeiouy]/i.test(ch)) this.mouth.t = rand(0.5, 0.9);
      else if (/[a-z0-9]/i.test(ch)) this.mouth.t = rand(0.1, 0.35);
      else this.mouth.t = 0;
      if (ch === ' ' && Math.random() < 0.3) this.springs.pitch.v += rand(0.03, 0.08);
    }
    if (s.i >= s.text.length) { s.done = true; this.mouth.t = 0; }
  }

  settle() {
    for (const s of Object.values(this.springs)) { s.x = s.t; s.v = 0; }
    this.open = 1;
    this.signal = 0;
    this.sweep = -1;
  }

  update(dtRaw) {
    if (this.still) return this._stillFrame();
    const dt = clamp(dtRaw, 0, 0.1);
    this.time += dt;
    const P = this.preset;

    for (const [k, grp] of Object.entries(PARAMS)) springStep(this.springs[k], OMEGA[grp], dt);
    const S = (k) => this.springs[k].x;

    // reactions (fast attack, smooth release)
    const add = {};
    this.reactions = this.reactions.filter((r) => {
      r.t += dt;
      const env = Math.max(0, Math.min(1, r.t / 0.2) * (1 - Math.max(0, (r.t - r.dur * 0.35) / (r.dur * 0.65))));
      for (const [k, v] of Object.entries(r)) if (typeof v === 'number' && k !== 'dur' && k !== 't') add[k] = (add[k] || 0) + v * env;
      return r.t < r.dur;
    });
    const A = (k) => add[k] || 0;

    // breathing + heartbeat (60 BPM neutral, 30 BPM sleepy)
    this.breathPhase += dt * Math.PI * 2 * P.breathRate;
    const breath = (Math.sin(this.breathPhase) + 0.22 * Math.sin(this.breathPhase * 2 - 0.6)) * P.breathAmp;
    this.beatPhase = (this.beatPhase + dt * P.pulseRate) % 1;
    const beat = heartbeat(this.beatPhase);

    // slow organic sway scaled by energy
    const tt = this.time, e = P.energy;
    const swayYaw = (Math.sin(tt * 0.31) * 0.6 + Math.sin(tt * 0.73 + 1.3) * 0.4) * 0.09 * e;
    const swayRoll = (Math.sin(tt * 0.23 + 2.1) * 0.6 + Math.sin(tt * 0.57) * 0.4) * 0.018 * e;
    const swayPitch = Math.sin(tt * 0.19 + 0.7) * 0.07 * e;

    // saccades
    if (this.time >= this.sacc.next) {
      const glance = Math.random() < 0.18 * P.saccade;
      const r = glance ? 0.45 : 0.12;
      this.sacc.x = rand(-r, r);
      this.sacc.y = rand(-r * 0.5, r * 0.5);
      this.sacc.next = this.time + (glance ? rand(0.6, 1.4) : rand(0.5, 2.6) / Math.max(0.3, P.saccade));
    }
    const look = this.look && this.time < this.look.until ? this.look : null;
    const saccW = look ? 0.3 : 1;                  // fixations stay small while she watches something
    this.springs.gazeX.t = (look ? look.x : P.gazeX) + this.sacc.x * saccW;
    this.springs.gazeY.t = (look ? look.y : P.gazeY) + this.sacc.y * saccW;
    this.lookYaw.t = look ? look.x * 0.18 : 0;
    springStep(this.lookYaw, OMEGA.head, dt);

    // blinks
    if (this.blink.start < 0 && this.time >= this.blink.next) {
      this.blink.start = this.time;
      this.blink.double = Math.random() < 0.14;
      this.blink.next = this.time + rand(P.blinkMin, P.blinkMax);
    }
    const blink = this._blinkAmount();

    this._speechStep(dt);
    springStep(this.mouth, OMEGA.talk, dt);

    // codec open, signal, glyph sweep
    if (this.opening) {
      this.open = Math.min(1, this.open + dt * 2.2);
      if (this.open >= 1) this.opening = false;
    }
    if (!this.linkOk) this.signal = Math.max(this.signal, 0.32 + 0.1 * Math.sin(tt * 7));
    else this.signal = Math.max(0, this.signal - dt * (this.opening ? 0.6 : 1.6));
    let sweepPos = -1, sweepStrength = 0;
    if (this.sweep >= 0) {
      this.sweep += dt / 0.75;
      sweepPos = -0.1 + 1.25 * this.sweep;
      sweepStrength = 1 - Math.max(0, this.sweep - 0.8) * 5;
      if (this.sweep >= 1) this.sweep = -1;
    }

    const flowSpeed = S('flowSpeed') + A('flowSpeed');
    this.flowPhase += dt * 6 * flowSpeed;
    this.rainPhase += dt * (0.6 + 0.25 * flowSpeed);
    this.conduitPhase += dt * (0.8 + 0.6 * flowSpeed);

    // micro-glitches (frustrated) and conduit flicker (broken)
    const micro = P.microGlitch && Math.random() < 0.035 ? rand(0.1, 0.3) : 0;
    const spike = S('glitch') > 0.3 && Math.random() < 0.04 ? rand(0.2, 0.6) : 0;
    const flicker = P.flicker ? (Math.random() < 0.25 ? rand(-0.6, 1.8) : 0) : 0;
    const strobe = P.strobe ? 1 - P.strobe * (Math.sin(tt * Math.PI * 2 * 3.2) > 0.2 ? 0 : 0.55) : 1;

    const gy = S('gazeY');
    const baseLid = clamp(S('lid') + Math.max(0, gy) * 0.22 - A('wide') * 0.1, 0, 0.95);
    const lid = baseLid + (1 - baseLid) * blink;
    const asym = S('lidAsym');

    return {
      time: this.time,
      browRaise: S('browRaise') + A('browRaise'),
      browInner: S('browInner') + A('browInner'),
      browAsym: S('browAsym'),
      lidR: clamp(lid + asym, 0, 1),
      lidL: clamp(lid - asym, 0, 1),
      wide: S('wide') + A('wide'),
      squint: S('squint') + A('squint'),
      smile: S('smile') + A('smile'),
      smileAsym: S('smileAsym') + A('smileAsym'),
      mouthOpen: clamp(S('mouthOpen') + Math.max(0, this.mouth.x), 0, 1),
      gazeX: S('gazeX'),
      gazeY: gy,
      roll: S('roll') + swayRoll,
      yaw: S('yaw') + swayYaw + this.lookYaw.x,
      pitch: S('pitch') + swayPitch,
      zoom: S('zoom'),
      breath,
      glow: Math.max(0, (S('glow') + A('glow')) * (0.88 + 0.12 * beat)),
      flowPhase: this.flowPhase,
      flowDir: S('flowDir'),
      tears: S('tears'),
      glyph: clamp(S('glyph') + (this.linkOk ? 0 : 0.3), 0, 1),
      sweepPos,
      sweepStrength,
      reticle: S('reticle') + A('reticle'),
      reticleScale: S('reticleScale') + A('reticleScale'),
      reticleDouble: clamp(S('reticleDouble') + A('reticleDouble'), 0, 1),
      pulse: beat,
      conduit: Math.max(0, S('conduit') * (0.85 + 0.15 * beat) + flicker * S('conduit')),
      conduitPhase: this.conduitPhase,
      conduitFlash: A('conduitFlash'),
      bloom: S('bloom') + A('bloom'),
      glitch: clamp(S('glitch') + A('glitch') + spike + micro, 0, 1),
      signal: this.signal,
      aberration: S('aberration'),
      dither: S('dither'),
      brightness: S('brightness') * strobe,
      open: this.open,
      rainPhase: this.rainPhase,
      grain: S('grain'),
      tintR: S('tintR'), tintG: S('tintG'), tintB: S('tintB'),
    };
  }

  /** Deterministic pose for the current mood: no idle motion or blinks. */
  _stillFrame() {
    this.settle();
    const S = (k) => this.springs[k].x;
    const lid = this.forceLid ?? clamp(S('lid') + Math.max(0, S('gazeY')) * 0.22, 0, 0.95);
    return {
      time: 1.0, browRaise: S('browRaise'), browInner: S('browInner'), browAsym: S('browAsym'),
      lidR: clamp(lid + S('lidAsym'), 0, 1), lidL: clamp(lid - S('lidAsym'), 0, 1),
      wide: S('wide'), squint: S('squint'), smile: S('smile'), smileAsym: S('smileAsym'),
      mouthOpen: S('mouthOpen') + (this.forceOpen || 0), gazeX: S('gazeX'), gazeY: S('gazeY'),
      roll: S('roll') + (this.forcePose ? this.forcePose[0] : 0),
      yaw: S('yaw') + (this.forcePose ? this.forcePose[1] : 0),
      pitch: S('pitch') + (this.forcePose ? this.forcePose[2] : 0),
      zoom: S('zoom'), breath: 0,
      glow: S('glow'), flowPhase: 3.0, flowDir: S('flowDir'), tears: S('tears'),
      glyph: S('glyph'), sweepPos: -1, sweepStrength: 0,
      reticle: S('reticle'), reticleScale: S('reticleScale'), reticleDouble: S('reticleDouble'), pulse: 0.5,
      conduit: S('conduit'), conduitPhase: 2.0, conduitFlash: 0, bloom: S('bloom'),
      glitch: S('glitch'), signal: 0, aberration: S('aberration'), dither: S('dither'),
      brightness: S('brightness'), open: 1, rainPhase: 20, grain: S('grain'),
      tintR: S('tintR'), tintG: S('tintG'), tintB: S('tintB'),
    };
  }
}

window.KaiaAnimator = KaiaAnimator;
