/**
 * KAIA // GLSL (WebGL2)
 *
 * SCENE      portrait rig -> RGBA8: r = luma (premul, /1.5), g = data emission (/2),
 *            b = glyph mask (premul), a = alpha
 * BRIGHT     scene -> 1/4-res bloom source
 * BLUR       separable 9-tap gaussian (direction uniform)
 * COMPOSITE  rain + conduits + glyph-mosaic Kaia + bloom + codec CRT
 */

const KAIA_GLSL = {};

KAIA_GLSL.vert = `#version 300 es
in vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

const COMMON = `
float hash11(float p) { p = fract(p * 0.1031); p *= p + 33.33; p *= p + p; return fract(p); }
float hash21(vec2 p) { vec3 p3 = fract(vec3(p.xyx) * 0.1031); p3 += dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
float G(vec2 p, vec2 c, vec2 r) { vec2 d = (p - c) / r; return exp(-dot(d, d)); }
`;

// ---------------------------------------------------------------- SCENE
KAIA_GLSL.scene = `#version 300 es
precision highp float;
${COMMON}
uniform vec2  uRes;
uniform float uTime;
uniform sampler2D uKaia;
uniform vec4  uPort;
uniform vec2  uRig[24];
uniform float uIrisR;
uniform float uZoom;
uniform float uExposure;
uniform vec4  uFace;   // faceW, faceH (portrait uv), FS = faceW / 0.40 (rig tuning reference), -

uniform vec4 uBrow;    // raise, inner, asym, -
uniform vec4 uEye;     // lidR, lidL, wide, squint
uniform vec4 uGaze;    // gx, gy, -, -
uniform vec4 uMouth;   // smile, smileAsym, open, -
uniform vec4 uHead;    // roll, yaw, pitch, breath
uniform vec4 uFx;      // glow, flowPhase, flowDir, tears
uniform vec4 uGlyph;   // amount, sweepPos, sweepStrength, -
uniform vec4 uReticle; // scale, double, intensity, pulse
out vec4 outColor;

float quad3(float x, vec2 a, vec2 b, vec2 c) {
  float la = (x - b.x) * (x - c.x) / ((a.x - b.x) * (a.x - c.x));
  float lb = (x - a.x) * (x - c.x) / ((b.x - a.x) * (b.x - c.x));
  float lc = (x - a.x) * (x - b.x) / ((c.x - a.x) * (c.x - b.x));
  return a.y * la + b.y * lb + c.y * lc;
}

vec2 eyeRig(vec2 q, vec2 outer, vec2 inner, vec2 top, vec2 bot, float closure,
            float gx, float gy, inout float lash, inout float eyeMask) {
  float FS = uFace.z;
  float xmin = min(outer.x, inner.x), xmax = max(outer.x, inner.x);
  if (q.x < xmin - 0.01 * FS || q.x > xmax + 0.01 * FS) return q;
  float mx = smoothstep(xmin - 0.002 * FS, xmin + 0.008 * FS, q.x) * smoothstep(xmax + 0.002 * FS, xmax - 0.008 * FS, q.x);
  float topY = quad3(q.x, outer, top, inner) - 0.002 * FS;
  float botY = quad3(q.x, outer, bot, inner);
  float lidY = mix(topY, botY, closure);
  float band = 0.022 * FS;
  float bandTop = topY - band;
  if (q.y > bandTop && q.y < lidY) {
    float sy = bandTop + (q.y - bandTop) * band / max(lidY - bandTop, 1e-4);
    q.y = mix(q.y, sy, mx);
  } else if (q.y >= lidY && q.y < botY) {
    float inEye = mx * smoothstep(lidY, lidY + 0.004 * FS, q.y) * smoothstep(botY + 0.001 * FS, botY - 0.004 * FS, q.y);
    q.x -= gx * uIrisR * 0.55 * inEye;
    q.y -= gy * uIrisR * 0.30 * inEye;
    eyeMask = max(eyeMask, inEye);
  }
  lash += mx * smoothstep(0.08, 0.45, closure) * exp(-pow((q.y - lidY) / (0.0035 * FS), 2.0)) * 0.55;
  return q;
}

// HUD reticle ring(s) around an iris, in source space.
float reticle(vec2 q, vec2 c) {
  vec2 d = (q - c);
  float r = length(d) / uIrisR;
  float s = uReticle.x;
  float w = 0.07;
  float ring = smoothstep(w, 0.0, abs(r - 0.92 * s));
  // tick marks on the ring, rotating slowly
  float ang = atan(d.y, d.x) + uTime * 0.6;
  ring *= 0.55 + 0.45 * step(0.5, fract(ang * 6.0 / 6.2832));
  float inner = uReticle.y * smoothstep(w, 0.0, abs(r - 0.52 * s));
  float cross = uReticle.y * smoothstep(0.04, 0.0, min(abs(d.x), abs(d.y)) / uIrisR) * step(r, 0.42 * s) * step(0.2, r);
  return (ring + inner + cross) * uReticle.z * (0.75 + 0.25 * uReticle.w);
}

void main() {
  vec2 frag = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 uv = frag / uRes;
  vec2 p = (uv - uPort.xy) / uPort.zw;
  vec2 chin = uRig[20], nose = uRig[21];
  p = nose + (p - nose) / uZoom;
  if (p.x < -0.02 || p.x > 1.02 || p.y < -0.02 || p.y > 1.02) { outColor = vec4(0.0); return; }

  // Face geometry from landmarks; all rig radii/magnitudes scale with face size (FS).
  float FS = uFace.z, faceW = uFace.x, faceH = uFace.y;
  vec2 fc = vec2(nose.x, 0.5 * (uRig[22].y + chin.y));
  // Head mask: face + hair + neck move; shoulders, hands and body stay put.
  vec2 hc = vec2(fc.x, fc.y - 0.12 * faceH);
  // Below the chin the moving region narrows to the neck, so shoulders (and hair
  // tips resting on them) stay planted on off-axis poses.
  float neckZone = smoothstep(chin.y - 0.15 * faceH, chin.y + 0.1 * faceH, p.y);
  float hd = length((p - hc) / vec2(mix(1.05, 0.42, neckZone) * faceW, faceH));
  float wHead = 1.0 - smoothstep(1.0, mix(1.45, 1.25, neckZone), hd);
  float wFace = G(p, fc, vec2(0.52 * faceW, 0.54 * faceH)) * wHead;
  float wCore = G(p, nose, vec2(0.32 * faceW, 0.35 * faceH));

  // head rig: tilt pivots at the base of her neck
  vec2 pivot = vec2(chin.x, chin.y + 0.4 * faceH);
  float ang = -uHead.x * wHead;
  vec2 o = p - pivot;
  vec2 q = pivot + vec2(cos(ang) * o.x - sin(ang) * o.y, sin(ang) * o.x + cos(ang) * o.y);
  q.x -= uHead.y * FS * (0.016 * wCore + 0.005 * wHead);
  q.y -= uHead.z * FS * (0.013 * wFace + 0.006 * wHead);
  q.y += uHead.w * 0.0045 * FS * (0.55 + 0.45 * wHead);                       // breathing: whole bust rises
  q.y -= uHead.w * 0.0015 * FS * smoothstep(chin.y + 0.2 * faceH, chin.y + 0.5 * faceH, p.y);

  // feature displacement (content movement); source = q - d
  vec2 d = vec2(0.0);
  float raise = uBrow.x, inner = uBrow.y, asym = uBrow.z;
  d.y -= (raise - asym) * 0.024 * FS * G(q, uRig[11], vec2(0.075, 0.035) * FS);
  d.y -= (raise + asym) * 0.024 * FS * G(q, uRig[14], vec2(0.075, 0.035) * FS);
  float gR = G(q, uRig[10], vec2(0.032, 0.03) * FS);
  float gL = G(q, uRig[13], vec2(0.032, 0.03) * FS);
  d.y -= inner * 0.018 * FS * (gR + gL);
  d.x += min(inner, 0.0) * -0.009 * FS * (gR - gL);
  float wide = uEye.z, squint = uEye.w, smile = uMouth.x;
  d.y -= wide * 0.008 * FS * (G(q, uRig[2] - vec2(0.0, 0.01) * FS, vec2(0.045, 0.02) * FS) + G(q, uRig[6] - vec2(0.0, 0.01) * FS, vec2(0.045, 0.02) * FS));
  float under = G(q, uRig[3] + vec2(0.0, 0.014) * FS, vec2(0.05, 0.02) * FS) + G(q, uRig[7] + vec2(0.0, 0.014) * FS, vec2(0.05, 0.02) * FS);
  d.y -= squint * 0.009 * FS * under;
  float cheeks = G(q, uRig[3] + vec2(-0.01, 0.06) * FS, vec2(0.06, 0.045) * FS) + G(q, uRig[7] + vec2(0.01, 0.06) * FS, vec2(0.06, 0.045) * FS);
  d.y -= max(smile, 0.0) * 0.009 * FS * cheeks;
  float smR = smile - uMouth.y, smL = smile + uMouth.y;
  d += vec2(-max(smR, 0.0) * 0.008, -smR * 0.019) * FS * G(q, uRig[16], vec2(0.04, 0.03) * FS);
  d += vec2( max(smL, 0.0) * 0.008, -smL * 0.019) * FS * G(q, uRig[17], vec2(0.04, 0.03) * FS);
  q -= d;

  // mouth opening
  float mouthInterior = 0.0, teeth = 0.0;
  float open = uMouth.z;
  if (open > 0.001) {
    vec2 mR = uRig[16], mL = uRig[17], mid = uRig[18];
    float lipY = quad3(q.x, mR, mid, mL);
    float cx = (mR.x + mL.x) * 0.5;
    float hw = (mL.x - mR.x) * 0.5 * 0.82;
    float prof = sqrt(max(0.0, 1.0 - pow((q.x - cx) / hw, 2.0)));
    if (q.y > lipY - 0.001 * FS) {
      float depth = smoothstep(lipY, chin.y, q.y);
      float s = open * 0.032 * FS * mix(prof, 1.0, depth) * exp(-pow((q.x - cx) / (0.4 * faceW), 2.0))
              * (1.0 - smoothstep(chin.y + 0.01 * FS, chin.y + 0.06 * FS, q.y));
      float sy = q.y - s;
      if (sy < lipY) {
        float t = (q.y - lipY) / max(s, 1e-4);
        mouthInterior = smoothstep(0.0, 0.25, prof) * smoothstep(0.0, 0.08, t) * smoothstep(1.0, 0.85, t);
        teeth = smoothstep(0.02, 0.1, t) * smoothstep(0.32, 0.18, t) * smoothstep(0.35, 0.7, prof);
        sy = lipY;
      }
      q.y = sy;
    }
  }

  // eyes
  float lash = 0.0, eyeMask = 0.0;
  q = eyeRig(q, uRig[0], uRig[1], uRig[2], uRig[3], uEye.x, uGaze.x, uGaze.y, lash, eyeMask);
  q = eyeRig(q, uRig[4], uRig[5], uRig[6], uRig[7], uEye.y, uGaze.x, uGaze.y, lash, eyeMask);

  vec4 src = texture(uKaia, clamp(q, 0.0, 1.0));
  float inside = step(0.0, q.x) * step(q.x, 1.0) * step(0.0, q.y) * step(q.y, 1.0);
  float a = src.a * inside * smoothstep(1.0, 0.82, p.y);

  float L = dot(src.rgb, vec3(0.299, 0.587, 0.114)) * uExposure;
  L = clamp((pow(L, 0.85) - 0.1) * 1.38, 0.0, 1.25);
  L *= 1.0 - lash;
  L = mix(L, 0.035, mouthInterior);
  L = mix(L, 0.55, teeth * mouthInterior * 0.8);

  // emerald data streams: pulses travel along the strands (flowDir +1 = upward)
  float key = smoothstep(0.06, 0.28, src.g - max(src.r, src.b)) * smoothstep(0.3, 0.75, src.g);
  key *= 1.0 - smoothstep(0.0, 0.3, eyeMask) * 0.85;
  float col = floor(q.x * 150.0);
  float ph = hash11(col * 1.7);
  float pulse = pow(max(0.0, sin(q.y * 26.0 + uFx.z * uFx.y * (0.7 + ph) + ph * 6.283)), 14.0);
  float emission = key * (0.1 + pulse * 0.9) * uFx.x;

  // reticle HUD in the irises (only where the eye is open)
  emission += (reticle(q, uRig[8]) + reticle(q, uRig[9])) * eyeMask;

  // data "tears": packets trailing down from the lower lids
  if (uFx.w > 0.001) {
    for (int i = 0; i < 2; i++) {
      vec2 lid = i == 0 ? uRig[3] : uRig[7];
      float x = lid.x + (i == 0 ? 0.008 : -0.008) * FS;
      float band = exp(-pow((p.x - x) / (0.0035 * FS), 2.0));
      float yy = (p.y - lid.y - 0.012 * FS) / FS;
      float trail = step(0.0, yy) * step(yy, 0.2);
      float drop = pow(fract(-yy * 7.0 + uTime * 0.55 + float(i) * 0.37), 10.0);
      emission += band * trail * drop * (1.0 - yy * 4.0) * uFx.w * 1.4;
    }
  }

  // glyph mask: periphery/hair become code, face core stays photographic
  float core = G(p, fc + vec2(0.0, 0.06 * faceH), vec2(0.475 * faceW, 0.56 * faceH));
  float m = (1.0 - core) * uGlyph.x;
  m = max(m, key * 0.7 * uGlyph.x);
  m = max(m, exp(-pow((p.y - uGlyph.y) / 0.05, 2.0)) * uGlyph.z);
  m = clamp(m, 0.0, 1.0);

  outColor = vec4(clamp(L * a / 1.5, 0.0, 1.0), clamp(emission * a / 2.0, 0.0, 1.0), m * a, a);
}
`;

// ---------------------------------------------------------------- BLOOM
KAIA_GLSL.bright = `#version 300 es
precision highp float;
uniform sampler2D uScene;
uniform vec2 uRes;
out vec4 outColor;
void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec4 s = texture(uScene, uv);
  float v = max(s.r * 1.5 - 0.62, 0.0) * 0.7 + s.g * 2.0;
  outColor = vec4(v, v, v, 1.0);
}
`;

KAIA_GLSL.blur = `#version 300 es
precision highp float;
uniform sampler2D uSrc;
uniform vec2 uRes;
uniform vec2 uDir;
out vec4 outColor;
void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 st = uDir / uRes;
  float w[5] = float[](0.227, 0.194, 0.121, 0.054, 0.016);
  float v = texture(uSrc, uv).r * w[0];
  for (int i = 1; i < 5; i++) {
    v += texture(uSrc, uv + st * float(i) * 1.5).r * w[i];
    v += texture(uSrc, uv - st * float(i) * 1.5).r * w[i];
  }
  outColor = vec4(v, v, v, 1.0);
}
`;

// ---------------------------------------------------------------- COMPOSITE
KAIA_GLSL.composite = `#version 300 es
precision highp float;
${COMMON}
uniform vec2  uRes;
uniform float uTime;
uniform float uDpr;
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform sampler2D uAtlas;
uniform float uCell;     // glyph cell size (device px)
uniform vec4  uLevel;    // brightness, open, rainPhase, grain
uniform vec4  uPost;     // glitch, signal, aberration, dither
uniform vec4  uConduit;  // intensity, phase, flash, -
uniform vec2  uHeadC;    // conduit hub (screen uv)
uniform float uBloomAmt;
uniform vec3  uTint;
out vec4 outColor;

#define PI 3.14159265

// Render targets are stored bottom-up; screen uv here is top-down.
vec2 fl(vec2 uv) { return vec2(uv.x, 1.0 - uv.y); }

float atlasGlyph(float idx, float row0, vec2 local) {
  float gi = idx;
  vec2 g = vec2(mod(gi, 16.0), row0 + floor(gi / 16.0));
  return texture(uAtlas, (g + clamp(local, 0.08, 0.92)) / vec2(16.0, 8.0)).r;
}

float rainLayer(vec2 px, float cell, float speedMul, float phase, float seed) {
  float col = floor(px.x / cell);
  float row = floor(px.y / cell);
  vec2 local = fract(px / cell);
  float rows = uRes.y / cell;
  float h = hash11(col * 7.13 + seed);
  float speed = (5.0 + 13.0 * h) * speedMul;
  float len = 8.0 + 22.0 * hash11(col * 3.71 + seed * 2.0);
  float cycle = rows + len + 4.0;
  float head = mod(phase * speed + h * 97.0, cycle);
  float d = head - row;
  if (d < 0.0 || d > len) return 0.0;
  float trail = pow(1.0 - d / len, 1.5);
  float swap = floor(uTime * (2.0 + 7.0 * hash21(vec2(col, row + seed))) + hash21(vec2(row, col)) * 10.0);
  float gi = floor(hash21(vec2(col * 1.3 + swap, row * 0.7 + seed)) * 64.0);
  float headGlow = d < 1.0 ? 1.8 : 1.0;
  return atlasGlyph(gi, 0.0, local) * trail * headGlow;
}

// SHODAN cables: glyph streams radiating from behind the head, flowing inward.
float conduits(vec2 uv, vec2 px) {
  if (uConduit.x < 0.001) return 0.0;
  float aspect = uRes.x / uRes.y;
  vec2 d = (uv - uHeadC) * vec2(aspect, 1.0);
  float r = length(d);
  if (r < 0.14) return 0.0;
  float ang = atan(d.y, d.x);
  vec2 cellId = floor(px / uCell);
  vec2 local = fract(px / uCell);
  float total = 0.0;
  for (int i = 0; i < 9; i++) {
    float fi = float(i);
    float base = fi * 2.0 * PI / 9.0 + 0.3 + 0.25 * hash11(fi * 3.3);
    if (abs(sin(base)) > 0.93 && sin(base) > 0.0) continue;          // keep the neck clear
    float a = base + 0.18 * sin(r * 4.0 + fi * 1.7) * r;
    float da = abs(mod(ang - a + PI, 2.0 * PI) - PI);
    float distPx = da * r * uRes.y;
    float w = uCell * (0.9 + 0.5 * hash11(fi));
    float band = 1.0 - smoothstep(w * 0.45, w, distPx);
    if (band <= 0.0) continue;
    float flow = fract(r * 5.0 + uConduit.y * (0.25 + 0.15 * hash11(fi * 7.0)) + hash11(fi));
    float pulse = pow(flow, 5.0);
    float g = atlasGlyph(floor(hash21(cellId + floor(uTime * 6.0 + fi)) * 64.0), 0.0, local);
    total += band * g * (0.3 + pulse * (1.3 + uConduit.z)) * smoothstep(0.14, 0.26, r);
  }
  return total * uConduit.x;
}

// Kaia through the glyph mosaic: returns (luma, alpha, emission).
vec3 kaia(vec2 uv, vec2 px) {
  vec4 photo = texture(uScene, fl(uv));
  vec2 cellId = floor(px / uCell);
  vec2 local = fract(px / uCell);
  vec2 cc = (cellId + 0.5) * uCell / uRes;
  vec2 o = vec2(0.25 * uCell) / uRes;
  vec4 c = 0.25 * (texture(uScene, fl(cc + o)) + texture(uScene, fl(cc - o))
                 + texture(uScene, fl(cc + vec2(o.x, -o.y))) + texture(uScene, fl(cc + vec2(-o.x, o.y))));
  float thr = 0.06 + 0.88 * hash21(cellId + floor(uTime * (1.5 + 3.0 * hash21(cellId.yx))) * 0.37);
  // Per-cell decision, faded by the smooth per-pixel mask so code has no hard border.
  float on = smoothstep(thr - 0.06, thr + 0.06, c.b) * smoothstep(0.0, 0.35, photo.b);
  float cellL = c.r * 1.5;
  // Matrix glyphs (same set as the rain), swapping over time.
  float swap = floor(uTime * (1.0 + 3.0 * hash21(cellId)) + hash21(cellId.yx) * 9.0);
  float glyph = atlasGlyph(floor(hash21(cellId * 1.37 + swap) * 64.0), 0.0, local);
  // Brightness wave falling down each column, like the rain behind her.
  float fall = pow(fract(hash11(cellId.x * 1.7) + cellId.y * 0.045 - uTime * 0.35), 3.0);
  float stroke = glyph * on * (0.4 + cellL * 0.7) * (0.55 + 1.1 * fall);
  // Additive strokes over the untouched face: transparent letters, no cell background.
  // Strokes may exceed 1.0 so they glow into the phosphor highlight like rain heads.
  float L = photo.r * 1.5 + stroke;
  return vec3(L, photo.a, photo.g * 2.0);
}

float sampleAll(vec2 uv) {
  vec2 px = uv * uRes;

  // rain backdrop with occasional glitch rows
  vec2 rp = px;
  float rcell = 12.0 * uDpr;
  float grow = floor(rp.y / rcell);
  float gt = floor(uTime * 9.0);
  float glitchRow = step(0.985 - uPost.x * 0.1, hash21(vec2(grow, gt)));
  rp.x += glitchRow * (hash21(vec2(grow * 1.7, gt)) - 0.5) * 120.0 * uDpr;
  float rain = rainLayer(rp, rcell, 1.0, uLevel.z, 1.0) * (0.5 + glitchRow * 0.6)
             + rainLayer(rp + vec2(5.0 * uDpr, 0.0), 8.0 * uDpr, 0.6, uLevel.z, 5.0) * 0.17;
  float bg = 0.025 + rain;

  vec3 k = kaia(uv, px);
  float cond = conduits(uv, px);
  float lum = (bg + cond) * (1.0 - k.y * 0.92) + k.x + k.z;
  lum += texture(uBloom, fl(uv)).r * uBloomAmt;
  return lum;
}

float bayer4(vec2 p) {
  vec2 q = mod(floor(p), 4.0);
  float m[16] = float[](0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
  return m[int(q.y * 4.0 + q.x)] / 16.0;
}

void main() {
  vec2 frag = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y);
  vec2 uv = frag / uRes;

  // CRT curvature
  vec2 cc = uv - 0.5;
  uv = 0.5 + cc * (1.0 + 0.04 * dot(cc, cc) * 4.0) * 0.988;
  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) { outColor = vec4(0.0, 0.0, 0.0, 1.0); return; }

  float openMask = step(abs(uv.y - 0.5), uLevel.y * 0.5 + 0.002);

  // glitch tearing + signal jitter
  float tick = floor(uTime * 18.0);
  float rowId = floor(uv.y * 54.0);
  float tear = step(1.0 - uPost.x * 0.38, hash21(vec2(rowId, tick)));
  uv.x += (hash21(vec2(rowId * 3.1, tick + 7.0)) - 0.5) * 0.09 * uPost.x * tear;
  uv.x += (hash21(vec2(floor(uv.y * 160.0), floor(uTime * 30.0))) - 0.5) * 0.02 * uPost.y;

  vec3 col;
  float lum = sampleAll(uv);
  if (uPost.z > 0.001) {
    vec2 off = vec2(0.006 * uPost.z, 0.0);
    float lr = sampleAll(uv + off), lb = sampleAll(uv - off);
    col = uTint * lum + vec3(lr - lum, 0.0, lb - lum) * 0.9;
  } else {
    col = uTint * lum;
  }

  // crushed phosphor: ordered dither to a few levels
  float levels = mix(48.0, 9.0, uPost.w);
  float b = bayer4(frag / max(1.0, floor(uDpr + 0.5)));
  float lq = floor(lum * levels + b) / levels;
  col *= mix(1.0, lq / max(lum, 1e-4), clamp(uPost.w, 0.0, 1.0));

  float grain = hash21(frag + fract(uTime * 13.7) * 311.0);
  float scan = 0.68 + 0.32 * pow(abs(sin(frag.y * PI / (3.0 * uDpr))), 1.4);
  float post = uLevel.x * scan;
  post *= 0.985 + 0.015 * sin(uTime * 57.0);
  vec2 vg = uv - 0.5;
  post *= 1.0 - dot(vg, vg) * 1.25;
  col *= post;
  col += uTint * (0.045 * exp(-pow((uv.y - fract(uTime * 0.11)) * 9.0, 2.0)) + (grain - 0.5) * uLevel.w);
  col = mix(col, uTint * grain * 0.9, clamp(uPost.y, 0.0, 1.0) * 0.7);
  float hi = max(dot(col, vec3(0.33)) - 0.6, 0.0);
  col += vec3(0.85, 1.0, 0.9) * hi * 0.8 + uTint * 0.01;
  outColor = vec4(col * openMask, 1.0);
}
`;

window.KAIA_GLSL = KAIA_GLSL;
