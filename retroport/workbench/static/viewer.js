"use strict";
// The workbench's model viewer (WebGL2): models as /api/preview and /api/body send them, skinned on
// the GPU and playing their Stand animation - bones, texture animations (scrolling, turning UVs),
// colour and transparency tracks, and particle emitters - each batch drawn with the client's texture
// combiner for its shader (glows, environment maps, masks; see shaderOf). A scene is
// parts: a body, models attached to its points (helm, shoulders, buckle), collection pieces driven by
// its bones, or loose models. Left-drag turns, right-drag pans, the wheel zooms, double-click resets.

// uCoord: which coordinates each of a batch's three textures reads - 0 the first UVs, 1 the second,
// 2 an environment map (the reflection of the view off the surface); uEdge fades it at grazing angles
const VS = `#version 300 es
in vec3 aPos; in vec3 aNrm; in vec2 aUv; in vec2 aUv2; in vec4 aW; in uvec4 aB;
uniform mat4 uMvp; uniform mat4 uView; uniform mat4 uModel; uniform highp sampler2D uBones; uniform bool uSkinned;
uniform mat4 uUvMat; uniform mat4 uUv2Mat; uniform mat4 uUv3Mat; uniform ivec3 uCoord; uniform bool uEdge;
out vec3 vN; out vec2 vUv; out vec2 vUv2; out vec2 vUv3; out float vEdge;
mat4 bone(uint i) {
  int x = int(i) * 4;
  return mat4(texelFetch(uBones, ivec2(x, 0), 0), texelFetch(uBones, ivec2(x + 1, 0), 0),
              texelFetch(uBones, ivec2(x + 2, 0), 0), texelFetch(uBones, ivec2(x + 3, 0), 0));
}
vec2 coord(int c, vec2 env) { return c == 1 ? aUv2 : (c == 2 ? env : aUv); }
void main() {
  mat4 skin = mat4(1.0);
  float s = aW.x + aW.y + aW.z + aW.w;
  if (uSkinned && s > 0.001)
    skin = (aW.x * bone(aB.x) + aW.y * bone(aB.y) + aW.z * bone(aB.z) + aW.w * bone(aB.w)) / s;
  mat4 m = uModel * skin;
  vec4 wp = m * vec4(aPos, 1.0);
  vN = mat3(m) * aNrm;
  vec3 e = normalize((uView * wp).xyz), n = normalize(mat3(uView) * vN);
  vec3 r = e - n * (2.0 * dot(e, n));
  vec2 env = normalize(vec3(r.xy, r.z + 1.0)).xy * 0.5 + 0.5;
  float f = clamp(abs(dot(e, n)), 0.0, 1.0);
  vEdge = uEdge ? clamp(2.7 * f * f - 0.4, 0.0, 1.0) : 1.0;
  vUv = (uUvMat * vec4(coord(uCoord.x, env), 0.0, 1.0)).xy;
  vUv2 = (uUv2Mat * vec4(coord(uCoord.y, env), 0.0, 1.0)).xy;
  vUv3 = (uUv3Mat * vec4(coord(uCoord.z, env), 0.0, 1.0)).xy;
  gl_Position = uMvp * wp;
}`;
// uPs: the batch's pixel combiner (PS below) - how its textures make a lit colour (d), an unlit glow
// added on top (sp) and an opacity (a). uWgt: the weights of its three textures.
const FS = `#version 300 es
precision mediump float;
in vec3 vN; in vec2 vUv; in vec2 vUv2; in vec2 vUv3; in float vEdge;
uniform sampler2D uTex; uniform bool uHasTex; uniform sampler2D uTex2; uniform sampler2D uTex3;
uniform int uPs; uniform vec3 uWgt; uniform bool uKeyTex;
uniform float uAlphaRef; uniform bool uUnlit; uniform bool uOpaque; uniform bool uPremul;
uniform vec3 uLight; uniform vec4 uTint;
out vec4 outColor;
void main() {
  vec4 t0 = uHasTex ? texture(uTex, vUv) : vec4(0.55, 0.55, 0.58, 1.0);
  vec4 t1 = texture(uTex2, vUv2), t2 = texture(uTex3, vUv3);
  vec3 d = t0.rgb, sp = vec3(0.0);
  float a = 1.0;
  switch (uPs) {
    case 1: case 31: case 33: a = t0.a; break;
    case 2: d = t0.rgb * t1.rgb; a = t1.a; break;
    case 3: d = t0.rgb * t1.rgb * 2.0; a = t1.a * 2.0; break;
    case 4: d = t0.rgb * t1.rgb * 2.0; break;
    case 5: d = t0.rgb * t1.rgb; break;
    case 6: case 36: d = t0.rgb * t1.rgb; a = t0.a * t1.a; break;
    case 7: d = t0.rgb * t1.rgb * 2.0; a = t0.a * t1.a * 2.0; break;
    case 8: a = t0.a + t1.a; sp = t1.rgb; break;
    case 9: d = t0.rgb * t1.rgb * 2.0; a = t0.a; break;
    case 10: a = t0.a; sp = t1.rgb; break;
    case 11: d = t0.rgb * t1.rgb; a = t0.a; break;
    case 12: d = mix(t0.rgb * t1.rgb * 2.0, t0.rgb, t0.a); break;
    case 13: sp = t1.rgb * t1.a; break;
    case 14: sp = t1.rgb * t1.a * (1.0 - t0.a); break;
    case 15: d = mix(t0.rgb * t1.rgb * 2.0, t0.rgb, t0.a); sp = t2.rgb * t2.a * uWgt.z; break;
    case 16: a = t0.a; sp = t1.rgb * t1.a; break;
    case 17: a = t0.a + t1.a * dot(t1.rgb, vec3(0.3, 0.59, 0.11)); sp = t1.rgb * t1.a * (1.0 - t0.a); break;
    case 18: d = mix(mix(t0.rgb, t1.rgb, t1.a), t0.rgb, t0.a); break;
    case 19: d = mix(t0.rgb * t1.rgb * 2.0, t2.rgb, t2.a); break;
    case 20: sp = t1.rgb * t1.a * uWgt.y; break;
    case 21: a = t0.a + t1.a; sp = t1.rgb * (1.0 - t0.a); break;
    case 22: d = mix(t0.rgb * t1.rgb, t0.rgb, t0.a); break;
    case 23: a = t0.a; sp = t1.rgb * t1.a * uWgt.y; break;
    case 24: d = mix(t0.rgb, t1.rgb, t1.a); sp = t0.rgb * t0.a * uWgt.x; break;
    case 25: { float g = clamp(t2.a * uWgt.z, 0.0, 1.0);
               d = mix(t0.rgb * t1.rgb * 2.0, t0.rgb, t0.a) * (1.0 - g); sp = t2.rgb * g; break; }
    case 26: case 28: { vec4 x = mix(mix(t0, t1, clamp(uWgt.y, 0.0, 1.0)), t2, clamp(uWgt.z, 0.0, 1.0));
               d = x.rgb; a = x.a; break; }
    case 27: d = mix(mix(t0.rgb * t1.rgb * 2.0, t2.rgb, t2.a), t0.rgb, t0.a); break;
    case 29: d = mix(t0.rgb, t1.rgb, t1.a); break;
    case 30: a = t0.a; break;
    case 35: { vec4 x = t0 * t1 * t2; d = x.rgb; a = x.a; break; }
    default: break;
  }
  if (uKeyTex) a = t0.a;                     // an alpha-keyed batch with an opaque combiner: cut by its texture
  a = clamp(a * vEdge, 0.0, 1.0) * uTint.a;
  if (a < uAlphaRef) discard;
  float l = uUnlit ? 1.0 : 0.42 + 0.75 * abs(dot(normalize(vN), uLight));
  vec4 o = vec4(d * l * uTint.rgb + sp, uOpaque ? 1.0 : a);
  if (uPremul) o.rgb *= o.a;
  outColor = o;
}`;
const PVS = `#version 300 es
in vec3 aPos; in vec2 aUv; in vec4 aCol;
uniform mat4 uMvp;
out vec2 vUv; out vec4 vCol;
void main() { vUv = aUv; vCol = aCol; gl_Position = uMvp * vec4(aPos, 1.0); }`;
const PFS = `#version 300 es
precision mediump float;
in vec2 vUv; in vec4 vCol;
uniform sampler2D uTex; uniform float uAlphaRef;
out vec4 outColor;
void main() { vec4 c = texture(uTex, vUv) * vCol; if (c.a < uAlphaRef) discard; outColor = c; }`;
const MAX_PARTICLES = 600;

// -- small matrix helpers (column-major, like GL) --------------------------------------------
const M4 = {
  ident: () => new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]),
  mul(a, b, o = new Float32Array(16)) {
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
      o[i * 4 + j] = a[j] * b[i * 4] + a[4 + j] * b[i * 4 + 1] + a[8 + j] * b[i * 4 + 2] + a[12 + j] * b[i * 4 + 3];
    }
    return o;
  },
  persp(fovy, aspect, near, far) {
    const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]);
  },
  look(eye, at, up) {
    const z = norm(sub(eye, at)), x = norm(cross(up, z)), y = cross(z, x);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0,
                             -dot(x, eye), -dot(y, eye), -dot(z, eye), 1]);
  },
  // T(pivot + t) * R(q) * S(s) * T(-pivot)
  bone(p, t, q, s, o) {
    const [x, y, z, w] = q;
    const r = [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
               2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
               2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)];
    for (let c = 0; c < 3; c++) for (let k = 0; k < 3; k++) o[c * 4 + k] = r[c * 3 + k] * s[c];
    o[3] = o[7] = o[11] = 0; o[15] = 1;
    for (let k = 0; k < 3; k++) {
      o[12 + k] = p[k] + t[k] - (o[k] * p[0] + o[4 + k] * p[1] + o[8 + k] * p[2]);
    }
    return o;
  },
  translate(m, v) {
    const o = new Float32Array(m);
    for (let k = 0; k < 3; k++) o[12 + k] = m[k] * v[0] + m[4 + k] * v[1] + m[8 + k] * v[2] + m[12 + k];
    return o;
  },
  apply(m, v) {
    return [0, 1, 2].map(k => m[k] * v[0] + m[4 + k] * v[1] + m[8 + k] * v[2] + m[12 + k]);
  },
  rotate(m, v) {
    return [0, 1, 2].map(k => m[k] * v[0] + m[4 + k] * v[1] + m[8 + k] * v[2]);
  },
};
const IDENT = M4.ident();
function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function norm(v) { const l = Math.hypot(v[0], v[1], v[2]) || 1; return [v[0] / l, v[1] / l, v[2] / l]; }
function cross(a, b) { return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]; }
function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
function b64(s, Type) {
  const bin = atob(s), u8 = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
  return new Type(u8.buffer);
}
const rnd = () => Math.random() * 2 - 1;

// One keyframe track at a time (ms): step or linear, quaternions normalised.
function sample(track, now, duration, globals, size) {
  if (!track || !track.t.length) return null;
  const loop = track.g >= 0 ? (globals[track.g] || 0) : duration;
  const t = loop > 0 ? now % loop : 0, times = track.t, v = track.v;
  if (times.length === 1 || t <= times[0]) return v.slice(0, size);
  const last = times.length - 1;
  if (t >= times[last]) return v.slice(last * size, last * size + size);
  let lo = 0, hi = last;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] <= t) lo = mid; else hi = mid; }
  const a = lo * size, b = hi * size;
  if (track.i === 0) return v.slice(a, a + size);
  const f = (t - times[lo]) / ((times[hi] - times[lo]) || 1), out = new Array(size);
  let sign = 1;
  if (size === 4) { let d = 0; for (let k = 0; k < 4; k++) d += v[a + k] * v[b + k]; if (d < 0) sign = -1; }
  for (let k = 0; k < size; k++) out[k] = v[a + k] + (sign * v[b + k] - v[a + k]) * f;
  if (size === 4) { const l = Math.hypot(...out) || 1; for (let k = 0; k < 4; k++) out[k] /= l; }
  return out;
}
// a particle's over-its-life track at t in 0..1
function lifeValue(track, t, size) {
  if (!track || !track.t.length) return null;
  const times = track.t, v = track.v, last = times.length - 1;
  if (t <= times[0] || last === 0) return v.slice(0, size);
  if (t >= times[last]) return v.slice(last * size, last * size + size);
  let k = 0;
  while (k < last - 1 && times[k + 1] <= t) k++;
  const f = (t - times[k]) / ((times[k + 1] - times[k]) || 1), out = new Array(size);
  for (let i = 0; i < size; i++) out[i] = v[k * size + i] + (v[(k + 1) * size + i] - v[k * size + i]) * f;
  return out;
}
const value = (track, now, m, fallback) => (sample(track, now, m.duration, m.globals, 1) || [fallback])[0];

// The client's model shaders. A batch's shader id picks a pixel combiner (how its up to three textures
// mix - FS's uPs) and a vertex shader (which coordinates each texture reads). Ids with 0x8000 index
// the client's table; the others say it in bits (0x70: the first texture modulates, low 3 bits: how
// the second combines, 0x80/0x8: the first/second is an environment map, 0x4000: the second UVs).
const PS = {Opaque: 0, Mod: 1, Opaque_Mod: 2, Opaque_Mod2x: 3, Opaque_Mod2xNA: 4, Opaque_Opaque: 5, Mod_Mod: 6,
            Mod_Mod2x: 7, Mod_Add: 8, Mod_Mod2xNA: 9, Mod_AddNA: 10, Mod_Opaque: 11, Opaque_Mod2xNA_Alpha: 12,
            Opaque_AddAlpha: 13, Opaque_AddAlpha_Alpha: 14, Opaque_Mod2xNA_Alpha_Add: 15, Mod_AddAlpha: 16,
            Mod_AddAlpha_Alpha: 17, Opaque_Alpha_Alpha: 18, Opaque_Mod2xNA_Alpha_3s: 19, Opaque_AddAlpha_Wgt: 20,
            Mod_Add_Alpha: 21, Opaque_ModNA_Alpha: 22, Mod_AddAlpha_Wgt: 23, Opaque_Mod_Add_Wgt: 24,
            Opaque_Mod2xNA_Alpha_UnshAlpha: 25, Mod_Dual_Crossfade: 26, Opaque_Mod2xNA_Alpha_Alpha: 27,
            Mod_Masked_Dual_Crossfade: 28, Opaque_Alpha: 29, Guild: 30, Guild_NoBorder: 31, Guild_Opaque: 32,
            Mod_Depth: 33, Illum: 34, Mod_Mod_Mod_Const: 35, Mod_Mod_Depth: 36};
// vertex shaders: [coordinates of textures 1-3 (0 first UVs, 1 second, 2 environment), edge fade]
const U1 = 0, U2 = 1, ENV = 2;
const VSH = {T1: [[U1]], Env: [[ENV]], T2: [[U2]], T1_T2: [[U1, U2]], T1_Env: [[U1, ENV]], Env_T1: [[ENV, U1]],
             Env_Env: [[ENV, ENV]], T1_T1: [[U1, U1]], T1_Env_T1: [[U1, ENV, U1]], T1_Env_T2: [[U1, ENV, U2]],
             T1_T2_T1: [[U1, U2, U1]], T1_T2_T3: [[U1, U2, U1]], Color_T1_T2_T3: [[U2, U1, U1]],
             EdgeFade_T1: [[U1], true], EdgeFade_T1_T2: [[U1, U2], true], EdgeFade_Env: [[ENV], true]};
const SHADER_TABLE = [
  ["Opaque_Mod2xNA_Alpha", "T1_Env"], ["Opaque_AddAlpha", "T1_Env"], ["Opaque_AddAlpha_Alpha", "T1_Env"],
  ["Opaque_Mod2xNA_Alpha_Add", "T1_Env_T1"], ["Mod_AddAlpha", "T1_Env"], ["Opaque_AddAlpha", "T1_T1"],
  ["Mod_AddAlpha", "T1_T1"], ["Mod_AddAlpha_Alpha", "T1_Env"], ["Opaque_Alpha_Alpha", "T1_Env"],
  ["Opaque_Mod2xNA_Alpha_3s", "T1_Env_T1"], ["Opaque_AddAlpha_Wgt", "T1_T1"], ["Mod_Add_Alpha", "T1_Env"],
  ["Opaque_ModNA_Alpha", "T1_Env"], ["Mod_AddAlpha_Wgt", "T1_Env"], ["Mod_AddAlpha_Wgt", "T1_T1"],
  ["Opaque_AddAlpha_Wgt", "T1_T2"], ["Opaque_Mod_Add_Wgt", "T1_Env"], ["Opaque_Mod2xNA_Alpha_UnshAlpha", "T1_Env_T1"],
  ["Mod_Dual_Crossfade", "T1"], ["Mod_Depth", "EdgeFade_T1"], ["Opaque_Mod2xNA_Alpha_Alpha", "T1_Env_T2"],
  ["Mod_Mod", "EdgeFade_T1_T2"], ["Mod_Masked_Dual_Crossfade", "T1_T2"], ["Opaque_Alpha", "T1_T1"],
  ["Opaque_Mod2xNA_Alpha_UnshAlpha", "T1_Env_T2"], ["Mod_Depth", "EdgeFade_Env"], ["Guild", "T1_T2_T1"],
  ["Guild_NoBorder", "T1_T2"], ["Guild_Opaque", "T1_T2_T1"], ["Illum", "T1_T1"], ["Mod_Mod_Mod_Const", "T1_T2_T3"],
  ["Mod_Mod_Mod_Const", "Color_T1_T2_T3"], ["Opaque", "T1"], ["Mod_Mod2x", "EdgeFade_T1_T2"],
  ["Mod", "EdgeFade_T1"], ["Mod_Mod_Depth", "EdgeFade_T1_T2"],
];
// how many textures a combiner reads
const PS_TEXTURES = ps => [0, 1, 33, 34].includes(ps) ? 1 : ([15, 19, 25, 26, 27, 28, 30, 32, 35].includes(ps) ? 3 : 2);
// with a texture short, a combiner falls back to its first texture alone (opaque, or cut by its alpha)
const PS_MOD = new Set([1, 6, 7, 8, 9, 10, 11, 16, 17, 21, 23, 26, 28, 30, 31, 33, 35, 36]);
function shaderOf(b) {
  const s = b.shader || 0, n = 1 + (b.layers || []).length;
  if (s & 0x8000) {
    const row = SHADER_TABLE[s & 0x7FFF];
    if (row) { const v = VSH[row[1]]; return {ps: PS[row[0]], coords: v[0], edge: !!v[1]}; }
    return {ps: PS.Mod, coords: [U1], edge: false};
  }
  if (n < 2) return {ps: s & 0x70 ? PS.Mod : PS.Opaque, coords: [s & 0x80 ? ENV : (s & 0x4000 ? U2 : U1)], edge: false};
  const mod = [PS.Mod_Mod2x, PS.Mod_Mod, PS.Mod_Mod2xNA, PS.Mod_AddNA, PS.Mod_Opaque, PS.Mod_Mod, PS.Mod_Mod, PS.Mod_Add];
  const opaque = [PS.Opaque_Mod2x, PS.Opaque_Mod, PS.Opaque_Mod2xNA, PS.Opaque_AddAlpha_Alpha, PS.Opaque_Opaque,
                  PS.Opaque_Mod, PS.Opaque_Mod, PS.Opaque_AddAlpha_Alpha];
  const ps = (s & 0x70 ? mod : opaque)[((s & 0xFF) ^ 4) & 7];
  const coords = s & 0x80 ? [ENV, s & 0x8 ? ENV : U1] : [U1, s & 0x8 ? ENV : (s & 0x4000 ? U2 : U1)];
  return {ps, coords, edge: false};
}

// An emitter of colour slot 11-13 with the display's ParticleColor row (``colors``: start, middle and end of
// slots 11, 12, 13 - nine ARGB numbers) takes that slot's three colours over its particles' life, as the
// client gives them (CCharacterComponent's ReplaceParticleColor); a missing row the client draws green.
function particleColored(d, colors) {
  const slot = (d.color_index || 0) - 11;
  if (slot < 0 || slot > 2 || !colors || colors.length !== 9) return d;
  const rgb = v => [(v >>> 16 & 255) / 255, (v >>> 8 & 255) / 255, (v & 255) / 255];
  const times = d.color && d.color.t.length === 3 ? d.color.t : [0, 0.5, 1];
  return {...d, color: {t: times, v: [...rgb(colors[slot]), ...rgb(colors[3 + slot]), ...rgb(colors[6 + slot])]}};
}

class Viewer {
  constructor(canvas) {
    this.canvas = canvas;
    // no alpha in the drawing buffer: what a see-through batch leaves in it would let the page show
    // through the model (a robe's flaps flickering as it turned) - the client's window is opaque
    const gl = this.gl = canvas.getContext("webgl2", {antialias: true, alpha: false, preserveDrawingBuffer: false});
    if (!gl) throw new Error("WebGL2 is not available in this browser");
    const program = (vs, fs) => {
      const sh = (type, src) => {
        const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
        return s;
      };
      const p = gl.createProgram();
      gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p);
      if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
      return p;
    };
    this.prog = program(VS, FS);
    this.u = {};
    for (const n of ["uMvp", "uView", "uModel", "uBones", "uSkinned", "uTex", "uHasTex", "uTex2", "uTex3", "uPs", "uWgt",
                     "uKeyTex", "uUvMat", "uUv2Mat", "uUv3Mat", "uCoord", "uEdge", "uAlphaRef", "uUnlit", "uOpaque",
                     "uPremul", "uLight", "uTint"])
      this.u[n] = gl.getUniformLocation(this.prog, n);
    this.a = {};
    for (const n of ["aPos", "aNrm", "aUv", "aUv2", "aW", "aB"]) this.a[n] = gl.getAttribLocation(this.prog, n);
    this.pprog = program(PVS, PFS);
    this.pu = {mvp: gl.getUniformLocation(this.pprog, "uMvp"), tex: gl.getUniformLocation(this.pprog, "uTex"),
               ref: gl.getUniformLocation(this.pprog, "uAlphaRef")};
    this.pa = {pos: gl.getAttribLocation(this.pprog, "aPos"), uv: gl.getAttribLocation(this.pprog, "aUv"),
               col: gl.getAttribLocation(this.pprog, "aCol")};
    this.pvao = gl.createVertexArray(); this.pbuf = gl.createBuffer();
    gl.bindVertexArray(this.pvao); gl.bindBuffer(gl.ARRAY_BUFFER, this.pbuf);
    gl.enableVertexAttribArray(this.pa.pos); gl.vertexAttribPointer(this.pa.pos, 3, gl.FLOAT, false, 36, 0);
    gl.enableVertexAttribArray(this.pa.uv); gl.vertexAttribPointer(this.pa.uv, 2, gl.FLOAT, false, 36, 12);
    gl.enableVertexAttribArray(this.pa.col); gl.vertexAttribPointer(this.pa.col, 4, gl.FLOAT, false, 36, 20);
    gl.bindVertexArray(null);
    this.parts = []; this.textures = new Map(); this.start0 = performance.now(); this.last = 0;
    this.view = {yaw: 0.35, pitch: 0.12, dist: 3, center: [0, 0, 0]};
    this.home = {...this.view};
    let drag = null;
    canvas.addEventListener("contextmenu", e => e.preventDefault());
    canvas.addEventListener("pointerdown", e => { drag = {x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey}; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointermove", e => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      drag.x = e.clientX; drag.y = e.clientY;
      const v = this.view;
      if (drag.pan) {
        const s = v.dist * 0.0018, cy = Math.cos(v.yaw), sy = Math.sin(v.yaw), sp = Math.sin(v.pitch), cp = Math.cos(v.pitch);
        const right = [-sy, cy, 0], up = [-sp * cy, -sp * sy, cp];
        for (let k = 0; k < 3; k++) v.center[k] += (-dx * right[k] + dy * up[k]) * s;
      } else {
        v.yaw -= dx * 0.01;
        v.pitch = Math.max(-1.45, Math.min(1.45, v.pitch + dy * 0.01));
      }
      this.draw();
    });
    canvas.addEventListener("pointerup", () => { drag = null; });
    canvas.addEventListener("wheel", e => { e.preventDefault(); this.view.dist *= Math.exp(e.deltaY * 0.001); this.draw(); }, {passive: false});
    canvas.addEventListener("dblclick", () => { this.view = {...this.home, center: [...this.home.center]}; this.draw(); });
  }

  // -- scene ------------------------------------------------------------------------------
  clear() {
    const gl = this.gl;
    for (const p of this.parts) {
      gl.deleteVertexArray(p.vao); p.buffers.forEach(b => gl.deleteBuffer(b)); gl.deleteTexture(p.boneTex);
    }
    this.parts = [];
  }

  texture(src) {
    // src: a url, or a canvas (the body's composited skin)
    if (this.textures.has(src)) return this.textures.get(src);
    const gl = this.gl, t = {tex: gl.createTexture(), ready: false};
    this.textures.set(src, t);
    const upload = img => {
      gl.bindTexture(gl.TEXTURE_2D, t.tex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.generateMipmap(gl.TEXTURE_2D);
      t.ready = true; this.draw();
    };
    if (typeof src === "string") {
      const img = new Image();
      img.onload = () => upload(img);
      img.onerror = () => { t.failed = true; };
      img.src = src;
    } else {
      upload(src);
    }
    return t;
  }

  // mesh: as the server sends it. opts: {texUrl(fdid), types: {textureType: url|canvas}, offset, visible(geoset),
  //   bodyOf: part (a collection: driven by that part's bones), attach: {part, id, scale}, tint: [r,g,b,a],
  //   particle: the display's ParticleColor colours (particleColored), ghost: left out of the framing (a glow)}
  add(mesh, opts = {}) {
    const gl = this.gl, vao = gl.createVertexArray(), buffers = [];
    gl.bindVertexArray(vao);
    const attr = (loc, data, size, type = gl.FLOAT, normalized = false, integer = false, stride = 0, offset = 0, buf = null) => {
      if (loc < 0) return buf;
      let b = buf;
      if (!b) { b = gl.createBuffer(); buffers.push(b); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); }
      else gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.enableVertexAttribArray(loc);
      if (integer) gl.vertexAttribIPointer(loc, size, type, stride, offset);
      else gl.vertexAttribPointer(loc, size, type, normalized, stride, offset);
      return b;
    };
    const positions = b64(mesh.positions, Float32Array);
    attr(this.a.aPos, positions, 3);
    attr(this.a.aNrm, b64(mesh.normals, Float32Array), 3);
    attr(this.a.aUv, b64(mesh.uvs, Float32Array), 2);
    attr(this.a.aUv2, b64(mesh.uvs2 || mesh.uvs, Float32Array), 2);
    const skin = b64(mesh.skin, Uint8Array);
    const sb = attr(this.a.aW, skin, 4, gl.UNSIGNED_BYTE, true, false, 8, 0);
    attr(this.a.aB, skin, 4, gl.UNSIGNED_BYTE, false, true, 8, 4, sb);
    const ib = gl.createBuffer(); buffers.push(ib);
    const indices = b64(mesh.indices, Uint32Array);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, indices, gl.STATIC_DRAW);
    gl.bindVertexArray(null);
    const bones = mesh.bones || [];
    const part = {vao, buffers, mesh, bones, opts, offset: opts.offset || [0, 0, 0], world: [], mats: null, positions, indices, orient: null,
                  boneTex: gl.createTexture(), nb: Math.max(1, bones.length), visible: opts.visible || (() => true),
                  tint: opts.tint || [1, 1, 1, 1], uvMats: [], colors: [], weights: []};
    part.mats = new Float32Array(part.nb * 16);
    for (let i = 0; i < part.nb; i++) part.mats.set(IDENT, i * 16);
    gl.bindTexture(gl.TEXTURE_2D, part.boneTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA32F, part.nb * 4, 1, 0, gl.RGBA, gl.FLOAT, part.mats);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    // a collection follows its body's bones, matched by bone name hash, else key bone
    if (opts.bodyOf) {
      const body = opts.bodyOf.bones, byCrc = new Map(), byKey = new Map();
      body.forEach((b, i) => { if (b.c) byCrc.set(b.c, i); if (b.k >= 0) byKey.set(b.k, i); });
      part.map = bones.map(b => (b.c && byCrc.has(b.c)) ? byCrc.get(b.c) : (b.k >= 0 && byKey.has(b.k) ? byKey.get(b.k) : -1));
    }
    const url = fdid => fdid && opts.texUrl ? opts.texUrl(fdid) : null;
    part.batches = mesh.batches.map(b => {
      const src = b.texture ? url(b.texture) : (opts.types || {})[b.texture_type];
      const sh = shaderOf(b), need = PS_TEXTURES(sh.ps), layers = b.layers || [];
      const extra = layers.slice(0, need - 1).map(l => { const u = url(l.texture); return u ? this.texture(u) : null; });
      return {...b, tex: src ? this.texture(src) : null, missing: !src && b.texture_type !== 0, sh, extra};
    });
    // drawn as the client draws a model's batches: by priority plane, lowest first (a hood's glowing eyes,
    // priority 4, over its dark inside, priority 0, whatever order the file lists them in)
    part.batches.sort((a, b) => (a.priority || 0) - (b.priority || 0));
    part.emitters = (mesh.particles || []).map(d => ({def: particleColored(d, opts.particle), list: [], acc: 0,
                                                       tex: this.texture(url(d.texture))}));
    this.parts.push(part);
    return part;
  }

  animated() {
    return this.parts.some(p => p.bones.some(b => b.t || b.r || b.s) || p.opts.bodyOf || p.opts.attach || p.emitters.length ||
                                (p.mesh.uvanims || []).some(u => u.t || u.r || u.s) ||
                                (p.mesh.colors || []).length || (p.mesh.weights || []).some(w => w && w.t.length > 1));
  }

  // -- framing ------------------------------------------------------------------------------
  bounds() {
    let lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
    for (const p of this.parts) {
      if (p.opts.ghost) continue;
      const m = p.opts.attach ? this.attachMatrix(p.opts.attach) : p.orient;
      const b = this.drawnBounds(p), corners = [];
      if (!b) continue;
      for (const x of [0, 1]) for (const y of [0, 1]) for (const z of [0, 1]) corners.push([b[x][0], b[y][1], b[z][2]]);
      for (let c of corners) {
        if (m) c = M4.apply(m, c);
        for (let a = 0; a < 3; a++) { lo[a] = Math.min(lo[a], c[a] + p.offset[a]); hi[a] = Math.max(hi[a], c[a] + p.offset[a]); }
      }
    }
    if (lo[0] > hi[0]) { lo = [-1, -1, -1]; hi = [1, 1, 1]; }
    return [lo, hi];
  }

  // view: "front" (the model's +X faces you), "back" (its back: a cloak), "held" (a weapon or shield
  // stood up: see orientHeld)
  fit(view = "front", slot = 0) {
    this.update(0);
    let yaw = 0.35, pitch = 0.12;
    for (const p of this.parts) p.orient = null;
    if (view === "back") yaw = Math.PI - 0.35;
    if (view === "held") { this.orientHeld(slot); yaw = 0.2; pitch = 0.05; }
    const [lo, hi] = this.bounds(), ext = [0, 1, 2].map(a => hi[a] - lo[a]);
    const center = lo.map((v, a) => (v + hi[a]) / 2), r = Math.max(0.05, Math.hypot(...ext) / 2);
    this.view = {yaw, pitch, dist: r * 2.5, center};
    this.home = {...this.view, center: [...center]};
  }

  // the bind-pose bounds of what a part draws (a shared collection shows only some of its parts)
  drawnBounds(p) {
    if (!p.opts.visible) return p.mesh.bounds;
    const lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
    let any = false;
    for (const b of p.batches) {
      if (b.missing || !p.visible(b.geoset)) continue;
      for (let i = b.start; i < b.start + b.count; i++) {
        const v = p.indices[i] * 3;
        for (let a = 0; a < 3; a++) { const c = p.positions[v + a]; if (c < lo[a]) lo[a] = c; if (c > hi[a]) hi[a] = c; }
        any = true;
      }
    }
    return any ? [lo, hi] : null;
  }

  // the covariance of what the parts draw (bind pose), each triangle weighted by its area: a shield's
  // face counts, not the many small triangles of its chains or ribbons
  drawnCovariance() {
    let n = 0;
    const s = [0, 0, 0], ss = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
    const at = (p, i) => { const v = p.indices[i] * 3; return [p.positions[v], p.positions[v + 1], p.positions[v + 2]]; };
    for (const p of this.parts) for (const b of p.opts.ghost ? [] : p.batches) {
      if (b.missing || !p.visible(b.geoset)) continue;
      for (let i = b.start; i + 2 < b.start + b.count; i += 3) {
        const A = at(p, i), B = at(p, i + 1), C = at(p, i + 2);
        const u = [B[0] - A[0], B[1] - A[1], B[2] - A[2]], w = [C[0] - A[0], C[1] - A[1], C[2] - A[2]];
        const area = 0.5 * Math.hypot(...cross(u, w));
        const x = [0, 1, 2].map(a => (A[a] + B[a] + C[a]) / 3);
        for (let a = 0; a < 3; a++) { s[a] += area * x[a]; for (let c = 0; c < 3; c++) ss[a][c] += area * x[a] * x[c]; }
        n += area;
      }
    }
    n = n || 1;
    return ss.map((row, a) => row.map((v, c) => v / n - (s[a] / n) * (s[c] / n)));
  }

  // A held item stood up: weapons and shields are modelled from the grip at the origin along +X (an
  // axe's head, a staff's crown, a shield's top), so +X goes up, and you face the flat side - the
  // thinner of Y and Z (a shield's front is +Y). Guns, bows and crossbows stay level, barrel along
  // the screen. Some shields and off-hands (Shadowlands' PvP ones, lanterns) are modelled along Z
  // instead: their long side stands up, +Z on top.
  orientHeld(slot) {
    let lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
    for (const p of this.parts) {
      const b = p.opts.ghost ? null : this.drawnBounds(p);
      if (b) for (let a = 0; a < 3; a++) { lo[a] = Math.min(lo[a], b[0][a]); hi[a] = Math.max(hi[a], b[1][a]); }
    }
    if (lo[0] > hi[0]) return;
    const thin = (hi[1] - lo[1]) <= (hi[2] - lo[2]) ? 1 : 2;
    // a shield's front is +Y; another item shows the side it reaches further out on
    const side = slot === 14 && thin === 1 ? 1 : (hi[thin] >= -lo[thin] ? 1 : -1);
    const f = [0, 0, 0]; f[thin] = side;                       // model axis that faces the camera
    const ranged = [15, 26].includes(slot);
    let up = ranged ? (thin === 2 ? [0, 1, 0] : [0, 0, 1]) : [1, 0, 0];
    if (slot === 14 || slot === 23) {
      // the long axis of the face (X and the other of Y and Z), from what the item draws
      const o2 = 3 - thin, c = this.drawnCovariance();
      const cxx = c[0][0], coo = c[o2][o2], cxo = c[0][o2], th = 0.5 * Math.atan2(2 * cxo, cxx - coo);
      const half = (cxx + coo) / 2, disc = Math.sqrt(Math.max(0, half * half - (cxx * coo - cxo * cxo)));
      const ratio = (half + disc) / Math.max(1e-9, half - disc), axis = [0, 0, 0];
      axis[0] = Math.cos(th); axis[o2] = Math.sin(th);
      if (slot === 14 && ratio > 1.4 && Math.abs(th) < Math.PI / 4) {
        up = axis;                                     // a shield modelled leaning, as it sits on the arm: its +X end on top
      } else if (ratio > 1.2 && Math.abs(th) > Math.PI / 4) {
        // modelled along the other axis: that axis up (the model's own, square to its face - horns or
        // spikes sticking out don't tilt it), its + end on top: a shield's top, the grip of an off-hand
        // that hangs from the hand (a lantern from its handle, a skull totem from its cord)
        up = [0, 0, 0];
        up[o2] = 1;
      }                                                // a round shield keeps +X up
    }
    const right = cross(up, f);
    const o = M4.ident();                                      // rows: view X = f, view Y = right, view Z = up
    for (let k = 0; k < 3; k++) { o[k * 4] = f[k]; o[k * 4 + 1] = right[k]; o[k * 4 + 2] = up[k]; }
    const mid = lo.map((v, a) => (v + hi[a]) / 2), c = M4.apply(o, mid);
    o[12] = mid[0] - c[0]; o[13] = mid[1] - c[1]; o[14] = mid[2] - c[2];
    for (const p of this.parts) p.orient = o;
  }

  // -- animation ----------------------------------------------------------------------------
  // att: {part, id, scale?} - the part's attachment point id; on a part that is itself placed (an item
  // on a body, a held item stood up) in that part's frame; scaled (an item glow's size)
  attachMatrix(att) {
    const body = att.part, a = (body.mesh.attachments || []).find(x => x[0] === att.id);
    if (!a) return null;
    const bm = body.world[a[1]] || IDENT;
    let m = M4.translate(bm, [a[2], a[3], a[4]]);
    if (body.opts.attach || body.orient || body.offset.some(c => c)) {
      const base = this.modelMatrix(body);
      if (!base) return null;
      m = M4.mul(base, m);
    }
    if (att.scale && att.scale !== 1) {
      m = new Float32Array(m);
      for (let k = 0; k < 12; k++) if (k % 4 !== 3) m[k] *= att.scale;
    }
    return m;
  }

  modelMatrix(p) {
    let model = p.opts.attach ? this.attachMatrix(p.opts.attach) : (p.orient || IDENT);
    if (!model) return null;
    if (p.offset[0] || p.offset[1] || p.offset[2]) model = M4.translate(model, p.offset);
    return model;
  }

  update(now) {
    const eye = this.eye();
    for (const p of this.parts) {
      const m = p.mesh;
      // texture animations, colours and transparency
      p.uvMats = (m.uvanims || []).map(u => M4.bone([0.5, 0.5, 0], sample(u.t, now, m.duration, m.globals, 3) || [0, 0, 0],
        sample(u.r, now, m.duration, m.globals, 4) || [0, 0, 0, 1], sample(u.s, now, m.duration, m.globals, 3) || [1, 1, 1],
        new Float32Array(16)));
      p.colors = (m.colors || []).map(c => [...(sample(c.c, now, m.duration, m.globals, 3) || [1, 1, 1]),
                                            (sample(c.a, now, m.duration, m.globals, 1) || [1])[0]]);
      p.weights = (m.weights || []).map(w => (sample(w, now, m.duration, m.globals, 1) || [1])[0]);
      if (p.opts.bodyOf) continue;                       // bones after its body
      const n = p.bones.length;
      for (let i = 0; i < n; i++) {
        const b = p.bones[i];
        const t = sample(b.t, now, m.duration, m.globals, 3) || [0, 0, 0];
        const r = sample(b.r, now, m.duration, m.globals, 4) || [0, 0, 0, 1];
        const s = sample(b.s, now, m.duration, m.globals, 3) || [1, 1, 1];
        const local = M4.bone(b.v, t, r, s, new Float32Array(16));
        const w = b.p >= 0 && p.world[b.p] ? M4.mul(p.world[b.p], local) : local;
        if (b.f & 0x8) {                                   // a spherical billboard: turn it to the camera
          const pos = M4.apply(w, b.v), f = norm(sub(eye, pos)), rt = norm(cross([0, 0, 1], f)), up = cross(f, rt);
          const sc = [0, 1, 2].map(c => Math.hypot(w[c * 4], w[c * 4 + 1], w[c * 4 + 2]));
          [f, rt, up].forEach((ax, c) => { for (let k = 0; k < 3; k++) w[c * 4 + k] = ax[k] * sc[c]; });
          for (let k = 0; k < 3; k++) w[12 + k] = pos[k] - (w[k] * b.v[0] + w[4 + k] * b.v[1] + w[8 + k] * b.v[2]);
        }
        p.world[i] = w;
        p.mats.set(w, i * 16);
      }
    }
    for (const p of this.parts) {
      if (!p.opts.bodyOf) continue;
      const body = p.opts.bodyOf;
      p.map.forEach((bi, i) => { p.mats.set(bi >= 0 && body.world[bi] ? body.world[bi] : IDENT, i * 16); });
    }
  }

  // Particles: born at their emitter (on its bone) at its rate, flying out within its spread at its
  // speed, pulled by gravity and drag, living their lifespan; drawn as camera-facing sprites coloured,
  // faded and sized along their life, a sprite-sheet cell each.
  particles(now, dt) {
    for (const p of this.parts) {
      if (!p.emitters.length) continue;
      const model = this.modelMatrix(p);
      if (!model) continue;
      const m = p.mesh;
      for (const em of p.emitters) {
        const d = em.def;
        for (const q of em.list) {
          q.age += dt;
          const g = q.grav;
          for (let k = 0; k < 3; k++) q.v[k] += g[k] * dt;
          const drag = Math.max(0, 1 - d.drag * dt);
          for (let k = 0; k < 3; k++) { q.v[k] *= drag; q.p[k] += q.v[k] * dt; }
        }
        em.list = em.list.filter(q => q.age < q.life);
        if (d.enabled && value(d.enabled, now, m, 1) < 0.5) continue;
        const rate = Math.max(0, value(d.rate, now, m, 0) + rnd() * d.rate_var);
        em.acc += rate * dt;
        let n = Math.min(Math.floor(em.acc), 60);
        em.acc -= Math.floor(em.acc);
        if (!n || em.list.length >= MAX_PARTICLES) continue;
        const frame = M4.mul(model, p.world[d.bone] || IDENT);
        const len = value(d.length, now, m, 0), wid = value(d.width, now, m, 0);
        const vr = value(d.vrange, now, m, 0), hr = value(d.hrange, now, m, 0);
        const speed = value(d.speed, now, m, 0), speedVar = value(d.speed_var, now, m, 0);
        const life = value(d.life, now, m, 1);
        let grav = sample(d.gravity, now, m.duration, m.globals, d.gravity && d.gravity.v.length > d.gravity.t.length ? 3 : 1) || [0];
        grav = grav.length === 3 ? M4.rotate(model, grav) : M4.rotate(model, [0, 0, -grav[0]]);
        while (n-- > 0 && em.list.length < MAX_PARTICLES) {
          const polar = Math.random() * vr, az = hr > 0 ? rnd() * hr : Math.random() * Math.PI * 2;
          const dir = [Math.sin(polar) * Math.cos(az), Math.sin(polar) * Math.sin(az), Math.cos(polar)];
          let local;
          if (d.type === 2) {                              // a sphere: from its surface, outward
            const r = len + Math.random() * Math.max(0, wid - len);
            local = [d.pos[0] + dir[0] * r, d.pos[1] + dir[1] * r, d.pos[2] + dir[2] * r];
          } else {                                         // a plane (and the rest): from its rectangle
            local = [d.pos[0] + rnd() * len / 2, d.pos[1] + rnd() * wid / 2, d.pos[2]];
          }
          const v = norm(M4.rotate(frame, dir)), sp = speed * (1 + rnd() * speedVar);
          em.list.push({p: M4.apply(frame, local), v: v.map(c => c * sp), age: 0, grav,
                        life: Math.max(0.03, life + rnd() * d.life_var), r: Math.random(), r2: Math.random(),
                        spin: d.base_spin + rnd() * d.base_spin_var});
        }
      }
    }
  }

  drawParticles(mvp, view) {
    const gl = this.gl;
    const right = [view[0], view[4], view[8]], up = [view[1], view[5], view[9]];
    gl.useProgram(this.pprog);
    gl.uniformMatrix4fv(this.pu.mvp, false, mvp);
    gl.uniform1i(this.pu.tex, 0);
    gl.bindVertexArray(this.pvao);
    gl.depthMask(false); gl.enable(gl.BLEND);
    for (const p of this.parts) for (const em of p.emitters) {
      if (!em.list.length || !em.tex || !em.tex.ready) continue;
      const d = em.def, data = new Float32Array(em.list.length * 6 * 9);
      const cells = d.rows * d.cols, tw = [d.twinkle[2] > 0 ? d.twinkle[2] : 1, d.twinkle[3] > 0 ? d.twinkle[3] : 1];
      let o = 0;
      for (const q of em.list) {
        const t = q.age / q.life;
        const col = lifeValue(d.color, t, 3) || [1, 1, 1], a = (lifeValue(d.alpha, t, 1) || [1])[0];
        const sc = lifeValue(d.scale, t, 2) || [0.1, 0.1];
        const mul = (1 + (q.r * 2 - 1) * (d.scale_var[0] || 0)) * (tw[0] + (tw[1] - tw[0]) * q.r2);
        const sx = Math.max(0, sc[0] * mul), sy = Math.max(0, sc[1] * mul);
        const cell = Math.floor((lifeValue(d.cells, t, 1) || [0])[0]) % cells;
        const u0 = (cell % d.cols) / d.cols, v0 = Math.floor(cell / d.cols) / d.rows, u1 = u0 + 1 / d.cols, v1 = v0 + 1 / d.rows;
        const ang = q.spin + d.spin * q.age * 1000, ca = Math.cos(ang), sa = Math.sin(ang);
        const rx = right.map((c, k) => (c * ca + up[k] * sa) * sx), ry = up.map((c, k) => (c * ca - right[k] * sa) * sy);
        const corner = (i, j, u, v) => {
          for (let k = 0; k < 3; k++) data[o++] = q.p[k] + rx[k] * i + ry[k] * j;
          data[o++] = u; data[o++] = v;
          data[o++] = col[0]; data[o++] = col[1]; data[o++] = col[2]; data[o++] = a;
        };
        corner(-1, -1, u0, v1); corner(1, -1, u1, v1); corner(1, 1, u1, v0);
        corner(-1, -1, u0, v1); corner(1, 1, u1, v0); corner(-1, 1, u0, v0);
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, this.pbuf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      if (d.blend === 2 || d.blend === 1 || d.blend === 0) gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
      else gl.blendFunc(gl.SRC_ALPHA, gl.ONE);           // add, blend-add: glows, sparks, flames
      gl.uniform1f(this.pu.ref, d.blend === 1 ? 0.5 : 0.004);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, em.tex.tex);
      gl.drawArrays(gl.TRIANGLES, 0, o / 9);
    }
    gl.bindVertexArray(null);
  }

  eye() {
    const v = this.view, cp = Math.cos(v.pitch);
    return [v.center[0] + v.dist * cp * Math.cos(v.yaw), v.center[1] + v.dist * cp * Math.sin(v.yaw),
            v.center[2] + v.dist * Math.sin(v.pitch)];
  }

  play() {
    if (this._loop) return;
    const tick = () => {
      if (!this.canvas.isConnected || !this.animated()) { this._loop = 0; return; }
      this._draw(); this._loop = requestAnimationFrame(tick);
    };
    this._loop = requestAnimationFrame(tick);
  }

  draw() {
    if (this.animated()) return this.play();
    if (this._pending) return;
    this._pending = requestAnimationFrame(() => { this._pending = 0; this._draw(); });
  }

  bindTexture(unit, t, wrap) {
    const gl = this.gl;
    gl.activeTexture(unit);
    gl.bindTexture(gl.TEXTURE_2D, t.tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap[0] ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrap[1] ? gl.REPEAT : gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  }

  _draw() {
    const gl = this.gl, c = this.canvas, dpr = window.devicePixelRatio || 1;
    const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
    if (!w || !h) return;
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    const now = performance.now() - this.start0, dt = this.last ? Math.min(0.1, (now - this.last) / 1000) : 0;
    this.last = now;
    this.update(now);
    this.particles(now, dt);
    gl.viewport(0, 0, w, h);
    gl.clearColor(0.07, 0.08, 0.1, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST); gl.cullFace(gl.BACK);
    const v = this.view, view = M4.look(this.eye(), v.center, [0, 0, 1]);
    const mvp = M4.mul(M4.persp(0.7, w / h, v.dist / 200, v.dist * 30), view);
    gl.useProgram(this.prog);
    gl.uniformMatrix4fv(this.u.uMvp, false, mvp);
    gl.uniformMatrix4fv(this.u.uView, false, view);
    gl.uniform3f(this.u.uLight, Math.cos(v.yaw + 0.6) * 0.6, Math.sin(v.yaw + 0.6) * 0.6, 0.53);
    gl.uniform1i(this.u.uTex, 0); gl.uniform1i(this.u.uBones, 1); gl.uniform1i(this.u.uTex2, 2); gl.uniform1i(this.u.uTex3, 3);
    const uvMat = (p, i) => i >= 0 && p.uvMats[i] ? p.uvMats[i] : IDENT;
    for (const pass of [0, 1]) {
      for (const p of this.parts) {
        const model = this.modelMatrix(p);
        if (!model) continue;
        gl.uniformMatrix4fv(this.u.uModel, false, model);
        // a mirrored part's triangles wind the other way round: its outside still faces front
        const det = model[0] * (model[5] * model[10] - model[6] * model[9]) - model[4] * (model[1] * model[10] - model[2] * model[9]) +
                    model[8] * (model[1] * model[6] - model[2] * model[5]);
        gl.frontFace(det < 0 ? gl.CW : gl.CCW);
        gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, p.boneTex);
        gl.texSubImage2D(gl.TEXTURE_2D, 0, 0, 0, p.nb * 4, 1, gl.RGBA, gl.FLOAT, p.mats);
        gl.uniform1i(this.u.uSkinned, 1);
        gl.bindVertexArray(p.vao);
        for (const b of p.batches) {
          if (b.missing || !p.visible(b.geoset)) continue;
          const col = b.color >= 0 && p.colors[b.color] ? p.colors[b.color] : [1, 1, 1, 1];
          const wgt = b.weight >= 0 && p.weights[b.weight] !== undefined ? p.weights[b.weight] : 1;
          const tint = [p.tint[0] * col[0], p.tint[1] * col[1], p.tint[2] * col[2], p.tint[3] * col[3] * wgt];
          if (tint[3] <= 0.003) continue;
          const blended = b.blend >= 2 || tint[3] < 1;
          if (blended !== (pass === 1)) continue;
          const mode = tint[3] < 1 && b.blend < 2 ? 2 : b.blend;
          this.blend(mode);
          // as the client sets them per material (CM2SceneRender::SetupMaterial): the back culled unless
          // the material is two-sided (0x4), depth tested unless 0x8, written unless 0x10 - whatever the
          // blend: a glow shell drawn from both sides adds twice, and a robe's inside shows through
          const mf = b.mflags ?? (b.two_sided ? 4 : 0);
          if (mf & 0x4) gl.disable(gl.CULL_FACE); else gl.enable(gl.CULL_FACE);
          if (mf & 0x8) gl.disable(gl.DEPTH_TEST); else gl.enable(gl.DEPTH_TEST);
          gl.depthMask(!(mf & 0x10));
          gl.uniform1i(this.u.uPremul, mode === 7 ? 1 : 0);
          gl.uniform4fv(this.u.uTint, tint);
          const t = b.tex && b.tex.ready ? b.tex : null;
          // a see-through batch waits for its texture: drawn without one it's a solid card (a mantle's
          // light rays as two grey slabs while their texture loads - or forever, when it can't)
          if (!t && blended) continue;
          gl.uniform1i(this.u.uHasTex, t ? 1 : 0);
          if (t) this.bindTexture(gl.TEXTURE0, t, b.wrap);
          // the combiner, or the first texture alone while one of the others is missing or loading
          const sh = b.sh, full = b.extra.length === PS_TEXTURES(sh.ps) - 1 && b.extra.every(x => x && x.ready);
          const ps = full ? sh.ps : (PS_MOD.has(sh.ps) ? PS.Mod : PS.Opaque);
          gl.uniform1i(this.u.uPs, ps);
          gl.uniform1i(this.u.uKeyTex, b.blend === 1 && !PS_MOD.has(ps) ? 1 : 0);
          gl.uniform3i(this.u.uCoord, sh.coords[0], sh.coords[1] ?? U1, sh.coords[2] ?? U1);
          gl.uniform1i(this.u.uEdge, sh.edge ? 1 : 0);
          const layers = b.layers || [], wt = i => i >= 0 && p.weights[i] !== undefined ? p.weights[i] : 1;
          gl.uniform3f(this.u.uWgt, wt(b.weight), wt(layers[0] ? layers[0].weight : -1), wt(layers[1] ? layers[1].weight : -1));
          // a texture animation belongs to the coordinates, not the texture: the first UVs move by the
          // batch's first transform, the second UVs by its second, an environment map by none - so two
          // textures on the first UVs move together (a weapon's leaves don't slide a second texture sheet
          // across themselves because the batch's next transform scrolls a glow elsewhere)
          const m0 = uvMat(p, b.uvanim), m1 = uvMat(p, layers[0] ? layers[0].uvanim : -1);
          const matOf = c => c === U1 ? m0 : c === U2 ? m1 : IDENT;
          gl.uniformMatrix4fv(this.u.uUvMat, false, matOf(sh.coords[0]));
          gl.uniformMatrix4fv(this.u.uUv2Mat, false, matOf(sh.coords[1] ?? U1));
          gl.uniformMatrix4fv(this.u.uUv3Mat, false, matOf(sh.coords[2] ?? U1));
          if (full) b.extra.forEach((x, i) => this.bindTexture(i ? gl.TEXTURE3 : gl.TEXTURE2, x, layers[i].wrap));
          gl.uniform1f(this.u.uAlphaRef, b.blend === 1 ? 0.5 : (b.blend >= 2 ? 0.004 : -1));
          gl.uniform1i(this.u.uUnlit, b.unlit ? 1 : 0);
          gl.uniform1i(this.u.uOpaque, b.blend === 0 && tint[3] >= 1 ? 1 : 0);
          gl.drawElements(gl.TRIANGLES, b.count, gl.UNSIGNED_INT, b.start * 4);
        }
      }
    }
    gl.bindVertexArray(null);
    gl.disable(gl.CULL_FACE); gl.enable(gl.DEPTH_TEST); gl.frontFace(gl.CCW);   // particles face the camera
    this.drawParticles(mvp, view);
    gl.depthMask(true); gl.disable(gl.BLEND);
  }

  // M2 blend modes: 0 opaque, 1 alpha key, 2 alpha, 3 add (no alpha), 4 add, 5 modulate, 6 modulate x2,
  // 7 blend-add (premultiplied: the colour is added over what the alpha leaves). Depth writes follow the
  // material's flags, not the blend (see _draw).
  blend(mode) {
    const gl = this.gl;
    if (mode <= 1) { gl.disable(gl.BLEND); return; }
    gl.enable(gl.BLEND);
    if (mode === 2) gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    else if (mode === 3) gl.blendFunc(gl.ONE, gl.ONE);
    else if (mode === 4) gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    else if (mode === 5) gl.blendFunc(gl.DST_COLOR, gl.ZERO);
    else if (mode === 6) gl.blendFunc(gl.DST_COLOR, gl.SRC_COLOR);
    else gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  }
}
window.Viewer = Viewer;
