/**
 * KAIA // CODEC VIEWPORT
 *
 * Mounts the animated Kaia codec into a container element:
 *   const codec = await KaiaCodec.mount(stageEl);
 *   codec.setMood('happy'); codec.speak('Handshake captured.'); codec.react('capture');
 */

class KaiaCodec {
  static async mount(container, opts = {}) {
    const codec = new KaiaCodec(container, opts);
    await codec._init();
    return codec;
  }

  constructor(container, { assets = '/static/assets/kaia', portrait = KaiaCodec.DEFAULT_PORTRAIT, maxFps = 60, still = false } = {}) {
    this.container = container;
    this.assets = `${assets}/${portrait}`;
    this.frameInterval = 1000 / maxFps;
    this.animator = new window.KaiaAnimator();
    this.animator.still = still;
    this.renderer = null;
    this._last = 0;
  }

  async _init() {
    const img = new Image();
    img.src = `${this.assets}/kaia_codec.webp`;
    const [rig] = await Promise.all([
      fetch(`${this.assets}/kaia_rig.json`).then((r) => r.json()),
      img.decode(),
      document.fonts ? document.fonts.ready : null,
    ]);

    const canvas = document.createElement('canvas');
    canvas.className = 'kaia-codec-canvas';
    this.container.appendChild(canvas);

    try {
      this.renderer = new window.KaiaRenderer(canvas, { image: img, rig });
    } catch (err) {
      console.warn('[KaiaCodec] WebGL2 unavailable, using static fallback:', err);
      canvas.remove();
      img.className = 'kaia-codec-fallback';
      this.container.appendChild(img);
      return;
    }

    new ResizeObserver(() => this.renderer.resize()).observe(canvas);
    if (!this.animator.still) this.animator.boot();
    requestAnimationFrame((t) => this._frame(t));
  }

  _frame(now) {
    requestAnimationFrame((t) => this._frame(t));
    if (this._last && now - this._last < this.frameInterval - 1) return;
    const dt = this._last ? (now - this._last) / 1000 : 0;
    this._last = now;
    const t0 = performance.now();
    this.renderer.render(this.animator.update(dt));
    if (this.stats) {
      const st = this.stats;
      st.frames++;
      st.cpu = st.cpu * 0.9 + (performance.now() - t0) * 0.1;
      if (now - st.since >= 1000) {
        st.fps = (st.frames * 1000) / (now - st.since);
        st.frames = 0;
        st.since = now;
        st.gpu = this.renderer.gpuMs;
        if (st.onUpdate) st.onUpdate(st);
      }
    }
  }

  /** Frame statistics: fps, CPU ms per frame, GPU ms (if the timer extension exists). */
  profile(onUpdate) {
    const gpu = this.renderer && this.renderer.enableProfiling();
    this.stats = { frames: 0, since: performance.now(), cpu: 0, fps: 0, gpu: null, gpuAvailable: gpu, onUpdate };
  }

  setMood(mood) { this.animator.setMood(mood); }

  react(kind) { this.animator.react(kind); }

  speak(text) { this.animator.speak(text); }

  setLink(ok) { this.animator.setLink(ok); }
}

/** Portrait folders under assets/kaia/ (each: kaia_codec.webp + kaia_rig.json). */
KaiaCodec.PORTRAITS = ['k60', 'k59', 'k28', 't1', 't2', 't3'];
KaiaCodec.DEFAULT_PORTRAIT = 'k60';

window.KaiaCodec = KaiaCodec;
