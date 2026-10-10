/**
 * KAIA // CODEC RENDERER (WebGL2)
 *
 * Pipeline per frame (see kaia-shaders.js):
 *   scene (full res)  ->  bright (1/4)  ->  blur H (1/4)  ->  blur V (1/4)  ->  composite (screen)
 *
 * Stateless with respect to animation: every frame takes the flat parameter
 * object produced by KaiaAnimator.
 */

const RIG_KEYS = [
  'eyeR_outer', 'eyeR_inner', 'eyeR_top', 'eyeR_bot',
  'eyeL_outer', 'eyeL_inner', 'eyeL_top', 'eyeL_bot',
  'irisR', 'irisL',
  'browR_inner', 'browR_mid', 'browR_outer',
  'browL_inner', 'browL_mid', 'browL_outer',
  'mouth_R', 'mouth_L', 'lip_upper_in', 'lip_bot',
  'chin', 'nose_tip', 'forehead', 'lip_top',
];

const RAIN_GLYPHS = 'ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜ0123456789Z:.=*+<>|';
const DENSITY_CANDIDATES = ' .`\'-,:_;~^"=+<>!ilrcvx*?()1jtfz7LJ23sYTnuoeaZ5SPXk4hdpbqwmGOQDHAKUVRBNE8&%#M@W';

class KaiaRenderer {
  constructor(canvas, { image, rig, maxDpr = 2 }) {
    this.canvas = canvas;
    this.maxDpr = maxDpr;
    const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, premultipliedAlpha: false, powerPreference: 'high-performance' });
    if (!gl) throw new Error('WebGL2 unavailable');
    this.gl = gl;

    const G = window.KAIA_GLSL;
    this.progs = {
      scene: this._program(G.vert, G.scene),
      bright: this._program(G.vert, G.bright),
      blur: this._program(G.vert, G.blur),
      composite: this._program(G.vert, G.composite),
    };

    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    this.aspect = image.naturalWidth / image.naturalHeight;
    this.rig = rig;
    this.texKaia = this._texture(image, gl.LINEAR);
    this.texAtlas = this._texture(this._buildAtlas(), gl.LINEAR);

    const pts = [];
    RIG_KEYS.forEach((k) => pts.push(rig[k][0], rig[k][1]));
    const irisR = Math.hypot(rig.irisR_edge[0] - rig.irisR[0], rig.irisR_edge[1] - rig.irisR[1]);
    const sp = this.progs.scene;
    gl.useProgram(sp.p);
    gl.uniform2fv(sp.u.uRig, new Float32Array(pts));
    gl.uniform1f(sp.u.uIrisR, irisR);
    gl.uniform1f(sp.u.uExposure, this._autoExposure(image, rig));
    const faceW = Math.abs(rig.cheekL[0] - rig.cheekR[0]);
    const faceH = rig.chin[1] - rig.forehead[1];
    gl.uniform4f(sp.u.uFace, faceW, faceH, faceW / 0.4, 0);

    this.targets = {};
    this.resize();

    // Optional GPU timing (EXT_disjoint_timer_query_webgl2), enabled by enableProfiling().
    this.timerExt = null;
    this.gpuMs = null;
    this._queries = [];
  }

  enableProfiling() {
    this.timerExt = this.gl.getExtension('EXT_disjoint_timer_query_webgl2');
    return !!this.timerExt;
  }

  _pollQueries() {
    const gl = this.gl, ext = this.timerExt;
    while (this._queries.length) {
      const q = this._queries[0];
      if (!gl.getQueryParameter(q, gl.QUERY_RESULT_AVAILABLE)) break;
      if (!gl.getParameter(ext.GPU_DISJOINT_EXT)) {
        const ms = gl.getQueryParameter(q, gl.QUERY_RESULT) / 1e6;
        this.gpuMs = this.gpuMs === null ? ms : this.gpuMs * 0.9 + ms * 0.1;
      }
      gl.deleteQuery(q);
      this._queries.shift();
    }
  }

  // ------------------------------------------------------------ GL helpers
  _program(vs, fs) {
    const gl = this.gl;
    const mk = (type, src) => {
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, mk(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, mk(gl.FRAGMENT_SHADER, fs));
    gl.bindAttribLocation(p, 0, 'aPos');
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    const u = {};
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) {
      const name = gl.getActiveUniform(p, i).name.replace('[0]', '');
      u[name] = gl.getUniformLocation(p, name);
    }
    return { p, u };
  }

  _texture(source, filter) {
    const gl = this.gl;
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
    this._params(filter);
    return t;
  }

  _params(filter) {
    const gl = this.gl;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filter);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  }

  _target(name, w, h) {
    const gl = this.gl;
    let t = this.targets[name];
    if (t && t.w === w && t.h === h) return t;
    if (t) { gl.deleteTexture(t.tex); gl.deleteFramebuffer(t.fbo); }
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    this._params(gl.LINEAR);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    t = { tex, fbo, w, h };
    this.targets[name] = t;
    return t;
  }

  /**
   * 16x8 atlas of 32px cells.
   *   rows 0-3: 64 rain glyphs (half-width katakana, digits, symbols; some mirrored)
   *   row 4:    16 ASCII glyphs sorted by measured ink density (SHODAN shading ramp)
   */
  _buildAtlas() {
    const cell = 32;
    const c = document.createElement('canvas');
    c.width = cell * 16;
    c.height = cell * 8;
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    const font = (px) => `bold ${px}px "Share Tech Mono", "JetBrains Mono", monospace`;

    ctx.font = font(cell * 0.8);
    for (let i = 0; i < 64; i++) {
      ctx.save();
      ctx.translate((i % 16) * cell + cell / 2, Math.floor(i / 16) * cell + cell / 2);
      if (i % 3 === 0) ctx.scale(-1, 1);
      ctx.fillText(RAIN_GLYPHS[i % RAIN_GLYPHS.length], 0, 0);
      ctx.restore();
    }

    // Measure ink coverage of each candidate, then pick 16 spanning the range.
    const probe = document.createElement('canvas');
    probe.width = probe.height = cell;
    const pc = probe.getContext('2d', { willReadFrequently: true });
    pc.font = font(cell * 0.92);
    pc.textAlign = 'center';
    pc.textBaseline = 'middle';
    const measured = [...DENSITY_CANDIDATES].map((ch) => {
      pc.fillStyle = '#000';
      pc.fillRect(0, 0, cell, cell);
      pc.fillStyle = '#fff';
      pc.fillText(ch, cell / 2, cell / 2);
      const d = pc.getImageData(0, 0, cell, cell).data;
      let ink = 0;
      for (let k = 0; k < d.length; k += 4) ink += d[k];
      return { ch, ink };
    }).sort((a, b) => a.ink - b.ink);
    const maxInk = measured[measured.length - 1].ink;
    const ramp = [];
    for (let i = 0; i < 16; i++) {
      const target = (i / 15) * maxInk;
      let best = measured[0];
      for (const m of measured) if (Math.abs(m.ink - target) < Math.abs(best.ink - target)) best = m;
      ramp.push(best.ch);
    }
    ctx.font = font(cell * 0.92);
    ramp.forEach((ch, i) => ctx.fillText(ch, i * cell + cell / 2, 4 * cell + cell / 2));
    return c;
  }

  /**
   * Normalise portraits shot under different lighting: measure mean luma of the
   * face box (cheek-to-cheek, forehead-to-chin) and scale it toward a common target.
   */
  _autoExposure(image, rig) {
    const c = document.createElement('canvas');
    const W = (c.width = 256), H = (c.height = Math.round(256 / this.aspect));
    const ctx = c.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(image, 0, 0, W, H);
    const x0 = Math.floor(rig.cheekR[0] * W), x1 = Math.ceil(rig.cheekL[0] * W);
    const y0 = Math.floor(rig.forehead[1] * H), y1 = Math.ceil(rig.chin[1] * H);
    const d = ctx.getImageData(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0)).data;
    let sum = 0, n = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 128) continue;
      sum += (0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2]) / 255;
      n++;
    }
    const mean = n ? sum / n : 0.5;
    this.exposure = Math.min(1.6, Math.max(0.75, 0.36 / mean));  // 0.36 ≈ k28 face mean, the look the filter was tuned on
    return this.exposure;
  }

  // ------------------------------------------------------------ frame
  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, this.maxDpr);
    const rect = this.canvas.getBoundingClientRect();
    const w = Math.max(2, Math.round(rect.width * dpr));
    const h = Math.max(2, Math.round(rect.height * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.dpr = dpr;
    this._target('scene', w, h);
    const qw = Math.max(1, w >> 2), qh = Math.max(1, h >> 2);
    this._target('bloomA', qw, qh);
    this._target('bloomB', qw, qh);
  }

  /** Portrait rect in screen uv: fills the panel height, neck runs off the bottom. */
  _portRect(offsetX) {
    const W = this.canvas.width, H = this.canvas.height;
    const h = 1.08;
    const w = (h * this.aspect * H) / W;
    return [0.5 - w / 2 + offsetX, 1.0 - h + 0.06, w, h];
  }

  _pass(prog, target, w, h) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.fbo : null);
    gl.viewport(0, 0, w, h);
    gl.useProgram(prog.p);
    gl.uniform2f(prog.u.uRes, w, h);
  }

  _bind(prog, name, unit, tex) {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.uniform1i(prog.u[name], unit);
  }

  render(s) {
    const gl = this.gl;
    let query = null;
    if (this.timerExt) {
      this._pollQueries();
      query = gl.createQuery();
      gl.beginQuery(this.timerExt.TIME_ELAPSED_EXT, query);
    }
    const W = this.canvas.width, H = this.canvas.height;
    const T = this.targets;
    gl.bindVertexArray(this.vao);
    const port = this._portRect(s.offsetX || 0);

    // 1. scene
    const sc = this.progs.scene;
    this._pass(sc, T.scene, W, H);
    this._bind(sc, 'uKaia', 0, this.texKaia);
    const u = sc.u;
    gl.uniform1f(u.uTime, s.time);
    gl.uniform4fv(u.uPort, port);
    gl.uniform1f(u.uZoom, s.zoom);
    gl.uniform4f(u.uBrow, s.browRaise, s.browInner, s.browAsym, 0);
    gl.uniform4f(u.uEye, s.lidR, s.lidL, s.wide, s.squint);
    gl.uniform4f(u.uGaze, s.gazeX, s.gazeY, 0, 0);
    gl.uniform4f(u.uMouth, s.smile, s.smileAsym, s.mouthOpen, 0);
    gl.uniform4f(u.uHead, s.roll, s.yaw, s.pitch, s.breath);
    gl.uniform4f(u.uFx, s.glow, s.flowPhase, s.flowDir, s.tears);
    gl.uniform4f(u.uGlyph, s.glyph, s.sweepPos, s.sweepStrength, 0);
    gl.uniform4f(u.uReticle, s.reticleScale, s.reticleDouble, s.reticle, s.pulse);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    // 2. bloom
    const br = this.progs.bright, bl = this.progs.blur;
    this._pass(br, T.bloomA, T.bloomA.w, T.bloomA.h);
    this._bind(br, 'uScene', 0, T.scene.tex);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    this._pass(bl, T.bloomB, T.bloomB.w, T.bloomB.h);
    this._bind(bl, 'uSrc', 0, T.bloomA.tex);
    gl.uniform2f(bl.u.uDir, 1, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    this._pass(bl, T.bloomA, T.bloomA.w, T.bloomA.h);
    this._bind(bl, 'uSrc', 0, T.bloomB.tex);
    gl.uniform2f(bl.u.uDir, 0, 1);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    // 3. composite
    const cp = this.progs.composite;
    this._pass(cp, null, W, H);
    this._bind(cp, 'uScene', 0, T.scene.tex);
    this._bind(cp, 'uBloom', 1, T.bloomA.tex);
    this._bind(cp, 'uAtlas', 2, this.texAtlas);
    const c = cp.u;
    gl.uniform1f(c.uTime, s.time);
    gl.uniform1f(c.uDpr, this.dpr);
    gl.uniform1f(c.uCell, Math.round(9 * this.dpr));
    gl.uniform4f(c.uLevel, s.brightness, s.open, s.rainPhase, s.grain);
    gl.uniform4f(c.uPost, s.glitch, s.signal, s.aberration, s.dither);
    gl.uniform4f(c.uConduit, s.conduit, s.conduitPhase, s.conduitFlash, 0);
    const nose = this.rig.nose_tip, fh = this.rig.forehead;
    gl.uniform2f(c.uHeadC, port[0] + nose[0] * port[2], port[1] + ((nose[1] + fh[1]) / 2) * port[3]);
    gl.uniform1f(c.uBloomAmt, s.bloom);
    gl.uniform3f(c.uTint, s.tintR, s.tintG, s.tintB);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    if (query) {
      gl.endQuery(this.timerExt.TIME_ELAPSED_EXT);
      this._queries.push(query);
    }
  }
}

window.KaiaRenderer = KaiaRenderer;
