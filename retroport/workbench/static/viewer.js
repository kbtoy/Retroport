"use strict";
// The workbench's model viewer (WebGL2): models as /api/preview and /api/body send them, skinned on
// the GPU and playing their Stand animation - bones, texture animations (scrolling, turning UVs),
// colour and transparency tracks, particle emitters and ribbons - each batch drawn with the client's
// texture combiner for its shader (glows, environment maps, masks; see shaderOf). What the client swings
// with physics hangs as it rests (settle); a mount's state kit shades it (a gradient, a dissolve). A scene
// is parts: a body, models attached to its points (helm, shoulders, buckle, a kit's banner), collection
// pieces driven by its bones, or loose models. Left-drag turns, right-drag pans, the wheel zooms,
// double-click resets.

// uCoord: which coordinates each of a batch's three textures reads - 0 the first UVs, 1 the second,
// 2 an environment map (the reflection of the view off the surface); uEdge fades it at grazing angles.
// vModel: the skinned point in the model's own space (a dissolve's projection), vHeight: up the model
// over its reach (a gradient's fade), vFacing: the surface's facing to the eye (|cos|: their rims)
const VS = `#version 300 es
in vec3 aPos; in vec3 aNrm; in vec2 aUv; in vec2 aUv2; in vec4 aW; in uvec4 aB;
uniform mat4 uMvp; uniform mat4 uView; uniform mat4 uModel; uniform highp sampler2D uBones; uniform bool uSkinned;
uniform mat4 uUvMat; uniform mat4 uUv2Mat; uniform mat4 uUv3Mat; uniform ivec3 uCoord; uniform bool uEdge;
uniform vec4 uGradAxis;
out vec3 vN; out vec2 vUv; out vec2 vUv2; out vec2 vUv3; out float vEdge;
out vec3 vModel; out float vHeight; out float vFacing;
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
  vec4 mp = skin * vec4(aPos, 1.0);
  mat4 m = uModel * skin;
  vec4 wp = uModel * mp;
  vN = mat3(m) * aNrm;
  vec3 e = normalize((uView * wp).xyz), n = normalize(mat3(uView) * vN);
  vec3 r = e - n * (2.0 * dot(e, n));
  vec2 env = normalize(vec3(r.xy, r.z + 1.0)).xy * 0.5 + 0.5;
  float f = clamp(abs(dot(e, n)), 0.0, 1.0);
  vEdge = uEdge ? clamp(2.7 * f * f - 0.4, 0.0, 1.0) : 1.0;
  vFacing = f;
  vModel = mp.xyz;
  vHeight = dot(mp.xyz, uGradAxis.xyz) + uGradAxis.w;
  vUv = (uUvMat * vec4(coord(uCoord.x, env), 0.0, 1.0)).xy;
  vUv2 = (uUv2Mat * vec4(coord(uCoord.y, env), 0.0, 1.0)).xy;
  vUv3 = (uUv3Mat * vec4(coord(uCoord.z, env), 0.0, 1.0)).xy;
  gl_Position = uMvp * wp;
}`;
// uPs: the batch's pixel combiner (PS below) - how its textures make a lit colour (d), an unlit glow
// added on top (sp) and an opacity (a). uWgt: the weights of its three textures.
// uFx: a state kit's shading in place of the combiner, as the x64 client's own programs draw it
// (Engine/Source/Gx/ShaderContainer: Gradient.ps.hlsl, Dissolve.ps.hlsl; CM2SceneRender sets their values)
const FS = `#version 300 es
precision highp float;
in vec3 vN; in vec2 vUv; in vec2 vUv2; in vec2 vUv3; in float vEdge;
in vec3 vModel; in float vHeight; in float vFacing;
uniform sampler2D uTex; uniform bool uHasTex; uniform sampler2D uTex2; uniform sampler2D uTex3;
uniform int uPs; uniform vec3 uWgt; uniform bool uKeyTex;
uniform float uAlphaRef; uniform bool uUnlit; uniform bool uOpaque; uniform bool uPremul;
uniform vec3 uLight; uniform vec4 uTint;
uniform int uFx;
uniform vec4 uFxModes;                                   // 1: the texture's alpha is the opacity; the alpha key (0: none)
uniform vec3 uRamp0; uniform vec3 uRamp1; uniform vec3 uRamp2;
uniform vec4 uGShape;                                    // middle value, rim power, 1: no height fade, 1: an additive batch
uniform vec4 uGEdge;                                     // edge colour, the effect's weight
uniform sampler2D uMask; uniform sampler2D uSecond; uniform sampler2D uThird;
uniform vec4 uL0; uniform vec4 uL1; uniform vec4 uL2;    // each layer's scale (uv) and scroll so far (uv)
uniform vec4 uModX; uniform vec4 uDTint;                 // the set's ModX; the tint times its intensity
uniform vec4 uDShape;                                    // projection, ramp, dissolve value, fresnel power
uniform vec4 uDExtra;                                    // the projection's scale, 1: the blend style
out vec4 outColor;
vec2 project(vec3 p, vec2 uv) {
  float type = uDShape.x;
  if (type > 6.5) return uv;
  if (type > 5.5) return vec2(dot(p.xy, vec2(0.70710678, -0.70710678)), dot(p, vec3(0.57735027)));
  if (type > 4.5) return vec2((atan(p.x, p.y) + 1.5707963) * 0.31830989, p.z);
  if (type > 3.5) return vec2((atan(p.x, p.z) + 1.5707963) * 0.31830989, p.y);
  if (type > 2.5) return vec2((atan(p.y, p.z) + 1.5707963) * 0.31830989, p.x);
  if (type > 1.5) return p.xy;
  if (type > 0.5) return p.xz;
  return p.yz;
}
void main() {
  vec4 t0 = uHasTex ? texture(uTex, vUv) : vec4(0.55, 0.55, 0.58, 1.0);
  float l = uUnlit ? 1.0 : 0.42 + 0.75 * abs(dot(normalize(vN), uLight));
  if (uFx > 0) {
    vec4 colour = vec4(vec3(l) * uTint.rgb, uTint.a);
    vec4 lit = t0 * colour;
    float opacity = uFxModes.x > 0.5 ? lit.a : colour.a;
    if (opacity < uFxModes.y) discard;                   // an alpha key: by its own opacity
    vec4 o;
    if (uFx == 1) {
      float lum = dot(lit.rgb, vec3(0.299, 0.587, 0.114));
      float mid = clamp(uGShape.x, 0.001, 0.999);
      vec3 low = mix(uRamp0, uRamp1, clamp(lum / mid, 0.0, 1.0));
      vec3 high = mix(uRamp1, uRamp2, clamp((lum - mid) / (1.0 - mid), 0.0, 1.0));
      vec3 g = lum < mid ? low : high;
      g = mix(g, uGEdge.rgb, pow(clamp(1.0 - vFacing, 0.0, 1.0), max(uGShape.y, 0.001)));
      g *= uGShape.w > 0.5 ? lum : 1.0;
      float h = clamp(vHeight * 1.667, 0.0, 0.9);
      float fade = uGShape.z > 0.5 ? 1.0 : h * h;
      o = vec4(mix(lit.rgb, g, uGEdge.w), opacity * mix(1.0, fade, uGEdge.w));
    } else {
      vec2 at = project(vModel * uDExtra.x, vUv);
      float weight = texture(uMask, at * uL0.xy + uL0.zw).a;
      vec4 layers = texture(uSecond, at * uL1.xy + uL1.zw) * texture(uThird, at * uL2.xy + uL2.zw);
      vec3 over; float cover;
      if (uDExtra.y > 0.5) {
        vec4 blended = layers * uModX * (2.0 * weight * uDShape.z);
        float edge = 1.0 - vFacing, rim = 2.0 * edge * edge;
        float towards = uDShape.w > 0.0 ? pow(max(rim, 1e-4), uDShape.w) : 0.0;
        over = blended.rgb * layers.a + uDTint.rgb * towards;
        cover = max(blended.a, towards * uDTint.a * opacity);
        over *= clamp(cover, 0.0, 1.0);
      } else {
        float d = 1.0 + weight * uDShape.y - uDShape.z * (uDShape.y + 1.0);
        float band = d < 1.0 ? clamp(d, 0.0, 1.0) : clamp(1.0 - 2.0 * (d - 1.0), 0.0, 1.0);
        cover = band;
        over = layers.rgb * 4.0 * band;
      }
      cover = clamp(cover, 0.0, 1.0);
      o = vec4(lit.rgb * (1.0 - cover) + over, opacity);
    }
    if (uPremul) o.rgb *= o.a;
    outColor = o;
    return;
  }
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
  vec4 o = vec4(d * l * uTint.rgb + sp, uOpaque ? 1.0 : a);
  if (uPremul) o.rgb *= o.a;
  outColor = o;
}`;
// particles and ribbons: a colour, one texture (or a multi-texture emitter's three - uMulti: 1 two colour
// textures and a third's alpha, 2 all three), as WebWowViewerCpp's m2ParticleShader combines them
const PVS = `#version 300 es
in vec3 aPos; in vec2 aUv; in vec4 aCol; in vec2 aUv2; in vec2 aUv3;
uniform mat4 uMvp;
out vec2 vUv; out vec4 vCol; out vec2 vUv2; out vec2 vUv3;
void main() { vUv = aUv; vCol = aCol; vUv2 = aUv2; vUv3 = aUv3; gl_Position = uMvp * vec4(aPos, 1.0); }`;
const PFS = `#version 300 es
precision mediump float;
in vec2 vUv; in vec4 vCol; in vec2 vUv2; in vec2 vUv3;
uniform sampler2D uTex; uniform sampler2D uTex2; uniform sampler2D uTex3; uniform int uMulti;
uniform float uAlphaRef; uniform bool uPremul;
out vec4 outColor;
void main() {
  vec4 t = texture(uTex, vUv);
  if (t.a < uAlphaRef) discard;
  vec4 c;
  if (uMulti == 1) { vec4 m = t * texture(uTex2, vUv2); c = vec4(vCol.rgb * m.rgb, m.a * texture(uTex3, vUv3).a * vCol.a); }
  else if (uMulti == 2) { vec4 m = t * texture(uTex2, vUv2) * texture(uTex3, vUv3); c = vec4(vCol.rgb * m.rgb, m.a * vCol.a); }
  else c = vec4(t.rgb * vCol.rgb, t.a * vCol.a);
  if (c.a < uAlphaRef) discard;
  if (uPremul) c.rgb *= c.a;
  outColor = c;
}`;
const MAX_PARTICLES = 600;
const PSTRIDE = 13;                          // a particle vertex: position 3, uv 2, colour 4, uv2 2, uv3 2

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
    const r = Q.mat(q);
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
  // rotation q about the point a, then m: T(a) R(q) T(-a) m
  about(a, q, m) {
    const r = M4.bone(a, [0, 0, 0], q, [1, 1, 1], new Float32Array(16));
    return M4.mul(r, m);
  },
  inv(m) {
    const o = new Float32Array(16);
    const [a00, a01, a02, a03, a10, a11, a12, a13, a20, a21, a22, a23, a30, a31, a32, a33] = m;
    const b00 = a00 * a11 - a01 * a10, b01 = a00 * a12 - a02 * a10, b02 = a00 * a13 - a03 * a10, b03 = a01 * a12 - a02 * a11;
    const b04 = a01 * a13 - a03 * a11, b05 = a02 * a13 - a03 * a12, b06 = a20 * a31 - a21 * a30, b07 = a20 * a32 - a22 * a30;
    const b08 = a20 * a33 - a23 * a30, b09 = a21 * a32 - a22 * a31, b10 = a21 * a33 - a23 * a31, b11 = a22 * a33 - a23 * a32;
    let det = b00 * b11 - b01 * b10 + b02 * b09 + b03 * b08 - b04 * b07 + b05 * b06;
    if (!det) return M4.ident();
    det = 1 / det;
    o[0] = (a11 * b11 - a12 * b10 + a13 * b09) * det; o[1] = (a02 * b10 - a01 * b11 - a03 * b09) * det;
    o[2] = (a31 * b05 - a32 * b04 + a33 * b03) * det; o[3] = (a22 * b04 - a21 * b05 - a23 * b03) * det;
    o[4] = (a12 * b08 - a10 * b11 - a13 * b07) * det; o[5] = (a00 * b11 - a02 * b08 + a03 * b07) * det;
    o[6] = (a32 * b02 - a30 * b05 - a33 * b01) * det; o[7] = (a20 * b05 - a22 * b02 + a23 * b01) * det;
    o[8] = (a10 * b10 - a11 * b08 + a13 * b06) * det; o[9] = (a01 * b08 - a00 * b10 - a03 * b06) * det;
    o[10] = (a30 * b04 - a31 * b02 + a33 * b00) * det; o[11] = (a21 * b02 - a20 * b04 - a23 * b00) * det;
    o[12] = (a11 * b07 - a10 * b09 - a12 * b06) * det; o[13] = (a00 * b09 - a01 * b07 + a02 * b06) * det;
    o[14] = (a31 * b01 - a30 * b03 - a32 * b00) * det; o[15] = (a20 * b03 - a21 * b01 + a22 * b00) * det;
    return o;
  },
  // a rotation about each axis (radians), as a matrix
  rotX(a) { const c = Math.cos(a), s = Math.sin(a); return new Float32Array([1, 0, 0, 0, 0, c, s, 0, 0, -s, c, 0, 0, 0, 0, 1]); },
  rotY(a) { const c = Math.cos(a), s = Math.sin(a); return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]); },
  rotZ(a) { const c = Math.cos(a), s = Math.sin(a); return new Float32Array([c, s, 0, 0, -s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]); },
};
// quaternions [x, y, z, w]
const Q = {
  mul(a, b) {
    return [a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1], a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
            a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3], a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]];
  },
  conj: q => [-q[0], -q[1], -q[2], q[3]],
  axis(v, angle) { const s = Math.sin(angle / 2); return [v[0] * s, v[1] * s, v[2] * s, Math.cos(angle / 2)]; },
  // the shortest turn taking unit a onto unit b
  arc(a, b) {
    const d = dot(a, b);
    if (d < -0.999999) {
      const o = Math.abs(a[0]) < 0.9 ? [1, 0, 0] : [0, 1, 0];
      return [...norm(cross(a, o)), 0];
    }
    const c = cross(a, b), q = [c[0], c[1], c[2], 1 + d], l = Math.hypot(...q);
    return q.map(x => x / l);
  },
  rot(q, v) { const r = Q.mat(q); return [0, 1, 2].map(k => r[k] * v[0] + r[3 + k] * v[1] + r[6 + k] * v[2]); },
  angle: q => 2 * Math.acos(Math.min(1, Math.abs(q[3]))),
  // column-major 3x3
  mat(q) {
    const [x, y, z, w] = q;
    return [1 - 2 * (y * y + z * z), 2 * (x * y + z * w), 2 * (x * z - y * w),
            2 * (x * y - z * w), 1 - 2 * (x * x + z * z), 2 * (y * z + x * w),
            2 * (x * z + y * w), 2 * (y * z - x * w), 1 - 2 * (x * x + y * y)];
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

// -- particles, as the client makes and draws them (WebWowViewerCpp's ParticleEmitter and generators: a
// reading of the client's) ----------------------------------------------------------------------------
// An emitter's frame is its bone's, at its position, turned a quarter about Z (particleCoordinatesFix):
// its particles start there - on a plane (type 1), a sphere (2) or along a spline (3) - and live in the
// world, or in that frame with flag 0x10 (they move with it: a candle's flame stays on its wick).
const PFIX = new Float32Array([0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
const TWINKLE = Float32Array.from({length: 128}, () => Math.random());
const PF = {ALIGN: 0x4, LOCAL: 0x10, INHERIT_SCALE: 0x20, UP: 0x100, FLIP_SPIN: 0x200, TAIL_GROWS: 0x400,
            XY_QUAD: 0x1000, GROUND: 0x2000, RANDOM_CELL: 0x10000, HEAD: 0x20000, TAIL: 0x40000, SCALE_XY: 0x80000,
            MULTI: 0x10000000, REFRACT: 0x100000};
const fp69 = x => { const v = (x & 0x1FF) / 512 + ((x >> 9) & 0x3F); return x & 0x8000 ? -v : v; };
const cellSize = x => (x & 0x1F) / 32 + (x >> 5);

// a cubic Bezier spline's point and direction at s (0..1 along its length): points in fours sharing ends
function splineAt(points, s) {
  const segs = Math.floor(points.length / 3);
  if (!points.length) return {pos: [0, 0, 0], dir: [0, 0, 1]};
  if (segs < 1 || points.length < 4) return {pos: points[0].slice(), dir: [0, 0, 1]};
  const at = (seg, t) => {
    const p = points.slice(seg * 3, seg * 3 + 4), u = 1 - t;
    const w = [u * u * u, 3 * t * u * u, 3 * t * t * u, t * t * t], dw = [-3 * u * u, 3 * u * u - 6 * t * u, 6 * t * u - 3 * t * t, 3 * t * t];
    return {pos: [0, 1, 2].map(k => p.reduce((sum, q, i) => sum + q[k] * w[i], 0)),
            dir: [0, 1, 2].map(k => p.reduce((sum, q, i) => sum + q[k] * dw[i], 0))};
  };
  const lens = [];
  for (let i = 0; i < segs; i++) {
    let len = 0, prev = at(i, 0).pos;
    for (let k = 1; k <= 20; k++) { const q = at(i, k / 20).pos; len += Math.hypot(...sub(q, prev)); prev = q; }
    lens.push(len);
  }
  const total = lens.reduce((a, b) => a + b, 0);
  if (s <= 0) return at(0, 0);
  if (s >= 1) return at(segs - 1, 1);
  let want = total * s, seg = 0;
  while (seg < segs - 1 && want >= lens[seg]) { want -= lens[seg]; seg++; }
  return at(seg, lens[seg] > 0 ? want / lens[seg] : 0);
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
                     "uPremul", "uLight", "uTint", "uGradAxis", "uFx", "uFxModes", "uRamp0", "uRamp1", "uRamp2", "uGShape",
                     "uGEdge", "uMask", "uSecond", "uThird", "uL0", "uL1", "uL2", "uModX", "uDTint", "uDShape", "uDExtra"])
      this.u[n] = gl.getUniformLocation(this.prog, n);
    this.a = {};
    for (const n of ["aPos", "aNrm", "aUv", "aUv2", "aW", "aB"]) this.a[n] = gl.getAttribLocation(this.prog, n);
    this.pprog = program(PVS, PFS);
    this.pu = {mvp: gl.getUniformLocation(this.pprog, "uMvp"), tex: gl.getUniformLocation(this.pprog, "uTex"),
               tex2: gl.getUniformLocation(this.pprog, "uTex2"), tex3: gl.getUniformLocation(this.pprog, "uTex3"),
               multi: gl.getUniformLocation(this.pprog, "uMulti"), ref: gl.getUniformLocation(this.pprog, "uAlphaRef"),
               premul: gl.getUniformLocation(this.pprog, "uPremul")};
    this.pvao = gl.createVertexArray(); this.pbuf = gl.createBuffer();
    gl.bindVertexArray(this.pvao); gl.bindBuffer(gl.ARRAY_BUFFER, this.pbuf);
    const pattr = (name, size, offset) => {
      const loc = gl.getAttribLocation(this.pprog, name);
      if (loc < 0) return;
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, false, PSTRIDE * 4, offset * 4);
    };
    pattr("aPos", 3, 0); pattr("aUv", 2, 3); pattr("aCol", 4, 5); pattr("aUv2", 2, 9); pattr("aUv3", 2, 11);
    gl.bindVertexArray(null);
    // a white texel: a dissolve's layer it has no texture for, as the client's
    this.white = {tex: gl.createTexture(), ready: true};
    gl.bindTexture(gl.TEXTURE_2D, this.white.tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, new Uint8Array([255, 255, 255, 255]));
    gl.generateMipmap(gl.TEXTURE_2D);
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
  //   bodyOf: part (a collection: driven by that part's bones), attach: {part, id, scale, local, root} (local:
  //   a matrix in the point's frame - a state kit's model's place; root: the part's root without the point),
  //   tint: [r,g,b,a], particle: the display's ParticleColor colours (particleColored), ghost: left out of the
  //   framing (a glow), fx: a state kit's shading {gradient, dissolve} (as the mount catalog has them)}
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
    const part = {vao, buffers, mesh, bones, opts, offset: opts.offset || [0, 0, 0], world: [], mats: null, positions, indices, skin, orient: null,
                  boneTex: gl.createTexture(), nb: Math.max(1, bones.length), visible: opts.visible || (() => true),
                  tint: opts.tint || [1, 1, 1, 1], uvMats: [], colors: [], weights: [], physLocal: null, physGravity: null};
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
    const tex = fdid => { const u = url(fdid); return u ? this.texture(u) : null; };
    part.batches = mesh.batches.map(b => {
      const src = b.texture ? url(b.texture) : (opts.types || {})[b.texture_type];
      const sh = shaderOf(b), need = PS_TEXTURES(sh.ps), layers = b.layers || [];
      const extra = layers.slice(0, need - 1).map(l => tex(l.texture));
      return {...b, tex: src ? this.texture(src) : null, missing: !src && b.texture_type !== 0, sh, extra};
    });
    // drawn as the client draws a model's batches: by priority plane, lowest first (a hood's glowing eyes,
    // priority 4, over its dark inside, priority 0, whatever order the file lists them in)
    part.batches.sort((a, b) => (a.priority || 0) - (b.priority || 0));
    part.emitters = (mesh.particles || []).filter(d => !(d.flags & PF.REFRACT && !(d.flags & PF.MULTI))).map(d => ({
      def: particleColored(d, opts.particle), list: [], acc: 0, tex: tex(d.texture),
      more: (d.textures || []).map(f => tex(f) || this.white)}));
    part.ribbons = (mesh.ribbons || []).map(d => ({def: d, edges: [], acc: 0, prev: null, layers: d.layers.map(l => ({...l, tex: tex(l.texture)}))}));
    const dz = (opts.fx || {}).dissolve;
    if (dz) part.dissolveTex = dz.layers.map(l => tex(l.texture) || this.white);
    this.parts.push(part);
    return part;
  }

  animated() {
    return this.parts.some(p => p.bones.some(b => b.t || b.r || b.s) || p.opts.bodyOf || p.opts.attach || p.emitters.length ||
                                p.ribbons.length || (p.opts.fx || {}).dissolve ||
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

  // the bind-pose bounds of what a part draws (a shared collection shows only some of its parts) - where
  // physics hangs some of it, as it hangs (each point on its heaviest bone)
  drawnBounds(p) {
    const own = p.mesh.bounds;
    if (!own || !p.batches.length || own[0][0] > own[1][0]) return null;    // nothing drawn (a kit's particles alone)
    if (!p.opts.visible && !p.physLocal) return own;
    const lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
    let any = false;
    for (const b of p.batches) {
      if (b.missing || !p.visible(b.geoset)) continue;
      for (let i = b.start; i < b.start + b.count; i++) {
        const v = p.indices[i];
        let c = [p.positions[v * 3], p.positions[v * 3 + 1], p.positions[v * 3 + 2]];
        if (p.physLocal) {
          const s = p.skin, o = v * 8;
          let k = 0;
          for (let j = 1; j < 4; j++) if (s[o + j] > s[o + k]) k = j;
          const w = p.world[s[o + 4 + k]];
          if (w) c = M4.apply(w, c);
        }
        for (let a = 0; a < 3; a++) { if (c[a] < lo[a]) lo[a] = c[a]; if (c[a] > hi[a]) hi[a] = c[a]; }
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
  // att: {part, id, scale?, local?, root?} - the part's attachment point id; on a part that is itself placed
  // (an item on a body, a held item stood up) in that part's frame; scaled (an item glow's size); then local
  // (a state kit model's place in the point's frame). root: on the part's root where it hasn't the point (a
  // state kit's model on the base, 19, as the client's InstallStateVisuals hangs it)
  attachMatrix(att) {
    const body = att.part, a = (body.mesh.attachments || []).find(x => x[0] === att.id);
    let m;
    if (!a) {
      if (!att.root) return null;
      m = this.modelMatrix(body);
      if (!m) return null;
    } else {
      const bm = body.world[a[1]] || IDENT;
      m = M4.translate(bm, [a[2], a[3], a[4]]);
      if (body.opts.attach || body.orient || body.offset.some(c => c)) {
        const base = this.modelMatrix(body);
        if (!base) return null;
        m = M4.mul(base, m);
      }
    }
    if (att.scale && att.scale !== 1) {
      m = new Float32Array(m);
      for (let k = 0; k < 12; k++) if (k % 4 !== 3) m[k] *= att.scale;
    }
    if (att.local) m = M4.mul(m, att.local);
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
      this.pose(p, now, eye, p.physLocal);
      if (m.phys) this.physics(p, now, eye);
    }
    for (const p of this.parts) {
      if (!p.opts.bodyOf) continue;
      const body = p.opts.bodyOf;
      p.map.forEach((bi, i) => { p.mats.set(bi >= 0 && body.world[bi] ? body.world[bi] : IDENT, i * 16); });
    }
  }

  // the part's bones at ``now``: each its keyframes' (or ``fixed``'s: what physics hangs) under its parent's
  pose(p, now, eye, fixed) {
    const m = p.mesh, n = p.bones.length;
    for (let i = 0; i < n; i++) {
      const b = p.bones[i];
      let local = fixed && fixed.get(i);
      if (!local) {
        const t = sample(b.t, now, m.duration, m.globals, 3) || [0, 0, 0];
        const r = sample(b.r, now, m.duration, m.globals, 4) || [0, 0, 0, 1];
        const s = sample(b.s, now, m.duration, m.globals, 3) || [1, 1, 1];
        local = M4.bone(b.v, t, r, s, new Float32Array(16));
      }
      const w = b.p >= 0 && p.world[b.p] ? M4.mul(p.world[b.p], local) : new Float32Array(local);
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

  // -- physics: what the client swings (its .phys: physics.py), hung as it rests ------------------
  // The client simulates a model's dynamic bodies with Jolt every frame; the preview settles them once
  // under gravity - each body, with all it carries, turned about its joint so their weight hangs as low as
  // its joint lets it (a shoulder's swing cone and twist, a revolute's hinge and limits; a weld or a
  // spring to the rest pose holds) - and keeps that pose, settling again when the part's place turns.
  physics(p, now, eye) {
    const model = this.modelMatrix(p);
    if (!model) return;
    // gravity (the world's down) in the part's own space
    const g = norm([model[2], model[6], model[10]].map(c => -c));
    if (p.physGravity && dot(g, p.physGravity) > 0.996) return;
    p.physGravity = g;
    this.pose(p, now, eye, null);                        // the rest pose: the keyframes alone
    p.physLocal = this.settle(p, g);
    if (p.physLocal) this.pose(p, now, eye, p.physLocal);
  }

  settle(p, g) {
    const ph = p.mesh.phys, B = ph.bodies, n = B.length;
    const rest = B.map(b => p.world[b.bone] || IDENT);
    const X = rest.map(m => new Float32Array(m)), D = B.map(() => [0, 0, 0, 1]);
    const fixed = B.map(b => b.type !== 1 || !(b.mass > 0) || b.bone >= p.bones.length);
    // the joints from what holds still outwards: each dynamic body's joint to the body it hangs from
    const links = B.map(() => []);
    ph.joints.forEach(j => { links[j.a].push(j); links[j.b].push(j); });
    const hang = new Array(n).fill(null), order = [], seen = fixed.slice(), queue = B.map((_b, i) => i).filter(i => fixed[i]);
    while (queue.length) {
      const u = queue.shift();
      for (const j of links[u]) {
        const v = j.a === u ? j.b : j.a;
        if (seen[v]) continue;
        seen[v] = true;
        const mine = j.a === u;
        hang[v] = {from: u, j, anchor: mine ? j.anchor_a : j.anchor_b, axis: mine ? j.axis_a : j.axis_b};
        order.push(v); queue.push(v);
      }
    }
    if (!order.length) return null;
    const kids = B.map(() => []);
    order.forEach(v => kids[hang[v].from].push(v));
    const subtree = v => { const out = [v]; for (let i = 0; i < out.length; i++) out.push(...kids[out[i]]); return out; };
    const trees = new Map(order.map(v => [v, subtree(v)]));
    const at = (i, local) => [B[i].position[0] + local[0], B[i].position[1] + local[1], B[i].position[2] + local[2]];
    const restAxis = (i, axis) => norm(M4.rotate(rest[i], axis));
    for (let pass = 0; pass < 24; pass++) {
      let moved = 0;
      for (const v of order) {
        const h = hang[v], u = h.from, j = h.j;
        const a = M4.apply(X[u], at(u, h.anchor));
        let w = 0;
        const c = [0, 0, 0];
        for (const s of trees.get(v)) {
          const ws = B[s].mass * (B[s].gravity || 0);
          if (!(ws > 0)) continue;
          const q = M4.apply(X[s], at(s, B[s].com));
          for (let k = 0; k < 3; k++) c[k] += ws * q[k];
          w += ws;
        }
        if (!(w > 0)) continue;
        const d = sub(c.map(x => x / w), a);
        if (Math.hypot(...d) < 1e-6) continue;
        // turned to hang its weight straight down, then held to its joint (in the rest pose's frame)
        let rel = Q.mul(Q.conj(D[u]), Q.mul(Q.arc(norm(d), g), D[v]));
        const motor = j.motor === 1;
        if (j.kind === 2 || j.kind === 4 || motor) rel = [0, 0, 0, 1];
        else if (j.kind === 3) {
          const hinge = restAxis(u, h.axis);
          let turn = 2 * Math.atan2(dot([rel[0], rel[1], rel[2]], hinge), rel[3]);
          if (turn > Math.PI) turn -= 2 * Math.PI;
          if (j.upper > j.lower) turn = Math.min(j.upper, Math.max(j.lower, turn));
          rel = Q.axis(hinge, turn);
        } else if (j.kind === 1) {
          const twistAxis = restAxis(u, h.axis), moved_ = Q.rot(rel, twistAxis);
          let swing = Q.arc(twistAxis, norm(moved_));
          const twist = Q.mul(Q.conj(swing), rel);
          if (Q.angle(swing) > j.cone) {
            const ax = norm([swing[0], swing[1], swing[2]]);
            swing = Q.axis(ax, j.cone);
          }
          let tw = 2 * Math.atan2(dot([twist[0], twist[1], twist[2]], twistAxis), twist[3]);
          if (tw > Math.PI) tw -= 2 * Math.PI;
          if (j.upper > j.lower) tw = Math.min(j.upper, Math.max(j.lower, tw));
          rel = Q.mul(swing, Q.axis(twistAxis, tw));
        }
        const next = Q.mul(D[u], rel), turn = Q.mul(next, Q.conj(D[v]));
        if (Q.angle(turn) < 1e-5) continue;
        moved++;
        for (const s of trees.get(v)) { X[s] = M4.about(a, turn, X[s]); D[s] = Q.mul(turn, D[s]); }
      }
      if (!moved) break;
    }
    // each hung body's bone where it rests, its bones below carried along: as locals under their parents
    const out = new Map(), world = p.world.map(m => m);
    const hung = new Map();
    order.forEach(v => { if (!hung.has(B[v].bone)) hung.set(B[v].bone, X[v]); });
    for (let i = 0; i < p.bones.length; i++) {
      const b = p.bones[i], parent = b.p >= 0 ? world[b.p] : null;
      if (hung.has(i)) {
        world[i] = hung.get(i);
        out.set(i, parent ? M4.mul(M4.inv(parent), world[i]) : new Float32Array(world[i]));
      } else if (parent && parent !== p.world[b.p]) {
        world[i] = M4.mul(parent, M4.mul(M4.inv(p.world[b.p]), p.world[i]));
      }
    }
    return out.size ? out : null;
  }

  // -- particles -----------------------------------------------------------------------------
  // An emitter's frame: model x bone x its position x the quarter turn (PFIX)
  emitterFrame(p, model, d) {
    return M4.mul(M4.translate(M4.mul(model, p.world[d.bone] || IDENT), d.pos), PFIX);
  }

  // a new particle in the emitter's own space (the generators: plane, sphere, spline)
  spawn(d, m, now, dt) {
    const state = rnd(), life = Math.max(0.001, value(d.life, now, m, 1) + state * (d.life_var || 0));
    const speed = value(d.speed, now, m, 0) * (1 + value(d.speed_var, now, m, 0) * rnd());
    const vr = value(d.vrange, now, m, 0), hr = value(d.hrange, now, m, 0), zs = value(d.z_source, now, m, 0);
    const areaX = value(d.length, now, m, 0), areaY = value(d.width, now, m, 0);
    let pos, vel;
    const fromSource = () => { const r0 = sub(pos, [0, 0, zs]), l = Math.hypot(...r0); return l > 1e-4 ? r0.map(c => c / l * speed) : [0, 0, 0]; };
    if (d.type === 2) {                                  // a sphere: from its shell between two radii
      const radius = areaX + (areaY - areaX) * Math.random(), polar = vr * rnd(), az = hr * rnd(), cp = Math.cos(polar);
      const dir = [cp * Math.cos(az), cp * Math.sin(az), Math.sin(polar)];
      pos = dir.map(c => c * radius);
      vel = Math.abs(zs) < 1e-6 ? (d.flags & PF.UP ? [0, 0, speed] : dir.map(c => c * speed)) : fromSource();
    } else if (d.type === 3) {                           // a spline: along it, between two fractions of its length
      const lo = Math.min(1, Math.max(0, areaX)), hi = Math.min(1, Math.max(0, areaY));
      const s = lo + (hi - lo) * Math.random(), sp = splineAt(d.spline || [], s);
      pos = sp.pos;
      if (zs > 0.001) vel = fromSource();
      else if (vr) {
        const tangent = norm(sp.dir), q = Q.axis(tangent, rnd() * vr);
        vel = Q.rot(q, [0, 0, 1]).map(c => c * speed);
      } else vel = [0, 0, speed];
    } else {                                             // a plane: from its rectangle
      pos = [rnd() * areaX * 0.5, rnd() * areaY * 0.5, 0];
      if (zs < 0.001) {
        const polar = vr * rnd(), az = hr * rnd(), sp = Math.sin(polar);
        vel = [Math.cos(az) * sp * speed, Math.sin(az) * sp * speed, Math.cos(polar) * speed];
      } else vel = fromSource();
    }
    const q = {p: pos, v: vel, age: (dt * Math.random()) % life, life, seed: (Math.random() * 65536) | 0,
               r: [rnd(), rnd(), rnd(), rnd()], cell: Math.random()};
    if (d.multi) {
      q.tp = [[Math.random(), Math.random()], [Math.random(), Math.random()]];
      q.tv = [0, 1].map(i => [fp69(d.multi[1][2 * i]) + fp69(d.multi[2][2 * i]) * rnd(),
                              fp69(d.multi[1][2 * i + 1]) + fp69(d.multi[2][2 * i + 1]) * rnd()]);
    }
    return q;
  }

  // Particles: born at their emitter's rate, moved by their speed, the wind, gravity and drag, living their
  // lifespan - in the world, or in the emitter's frame (0x10)
  particles(now, dt) {
    for (const p of this.parts) {
      if (!p.emitters.length) continue;
      const model = this.modelMatrix(p);
      if (!model) continue;
      const m = p.mesh;
      for (const em of p.emitters) {
        const d = em.def;
        em.frame = this.emitterFrame(p, model, d);
        em.scale = Math.hypot(em.frame[0], em.frame[1], em.frame[2]);
        let grav = sample(d.gravity, now, m.duration, m.globals, d.gravity && d.gravity.v.length > d.gravity.t.length ? 3 : 1) || [0];
        grav = grav.length === 3 ? grav : [0, 0, -grav[0]];
        const drag = Math.min(1, (d.drag || 0) * dt), wind = d.wind || [0, 0, 0];
        for (const q of em.list) {
          q.age += dt;
          for (let k = 0; k < 3; k++) {
            q.v[k] += wind[k] * dt;
            const step = q.v[k] * dt;
            q.v[k] = (q.v[k] + grav[k] * dt) * (1 - drag);
            q.p[k] += step + grav[k] * dt * dt * 0.5;
          }
          if (q.tp) for (let i = 0; i < 2; i++) for (let k = 0; k < 2; k++) { const s = q.tp[i][k] + dt * q.tv[i][k]; q.tp[i][k] = s - Math.floor(s); }
        }
        em.list = em.list.filter(q => q.age < q.life);
        if (d.enabled && d.enabled.t.length && value(d.enabled, now, m, 1) < 0.5) continue;
        const rate = Math.max(0, value(d.rate, now, m, 0) + rnd() * (d.rate_var || 0));
        em.acc += rate * dt;
        while (em.acc > 1) {
          em.acc -= 1;
          if (em.list.length >= MAX_PARTICLES) continue;
          const q = this.spawn(d, m, now, dt);
          if (!(d.flags & PF.LOCAL)) {
            q.p = M4.apply(em.frame, q.p); q.v = M4.rotate(em.frame, q.v);
            if (d.flags & PF.GROUND) q.p[2] = 0;
          }
          em.list.push(q);
        }
      }
    }
  }

  // Each particle as the client draws it: a quad facing you (or lying in its frame's XY plane: 0x1000;
  // along its flight: 0x4) - its head (0x20000) - and a streak behind it (0x40000), coloured, faded and sized
  // over its life (by twinkle too, and its frame's scale with 0x20), a sprite-sheet cell each.
  particleQuads(em, view) {
    const d = em.def, out = [];
    const toView = d.flags & PF.LOCAL ? M4.mul(view, em.frame) : view;
    const R = [view[0], view[4], view[8]], U = [view[1], view[5], view[9]], F = [view[2], view[6], view[10]];
    const worldOf = v => [0, 1, 2].map(k => R[k] * v[0] + U[k] * v[1] + F[k] * v[2]);   // a view-space direction in the world
    const cols = d.cols, rows = d.rows, cells = cols * rows, maxLife = value(d.life, 0, {duration: 0, globals: []}, 1) + (d.life_var || 0);
    const tw = d.twinkle || [0, 1, 1, 1], twVary = tw[3] - tw[2];
    const px = d.multi ? [cellSize(d.multi[0][0]), cellSize(d.multi[0][1])] : [1, 1];
    for (const q of em.list) {
      let idx = 0;
      if (tw[1] < 1 || twVary) idx = (Math.floor(q.age * tw[0]) + q.seed) & 0x7f;
      if (tw[1] < TWINKLE[idx] || q.age > maxLife) continue;
      const t = Math.min(1, Math.max(0, q.age / Math.max(1e-3, maxLife)));
      const col = lifeValue(d.color, t, 3) || [1, 1, 1], a = (lifeValue(d.alpha, t, 1) || [1])[0];
      let [sx, sy] = lifeValue(d.scale, t, 2) || [1, 1];
      const sv = d.scale_var || [0, 0];
      if (d.flags & PF.SCALE_XY) { sx *= Math.max(1 + q.r[0] * sv[0], 1e-4); sy *= Math.max(1 + q.r[1] * sv[1], 1e-4); }
      else { const k = Math.max(1 + q.r[0] * sv[0], 1e-4); sx *= k; sy *= k; }
      const weight = twVary * TWINKLE[idx] + tw[2];
      sx *= weight; sy *= weight;
      if (d.flags & PF.INHERIT_SCALE) { sx *= em.scale; sy *= em.scale; }
      const center = d.flags & PF.LOCAL ? M4.apply(em.frame, q.p) : q.p;
      const quad = (axisX, axisY, cell, c0) => {
        const u0 = (cell % cols) / cols, v0 = Math.floor(cell / cols) / rows;
        out.push({c: c0, x: axisX, y: axisY, u0, v0, du: 1 / cols, dv: 1 / rows, col, a, q, px});
      };
      const cellOf = (track, def) => {
        let c = track && track.t.length ? Math.floor((lifeValue(track, t, 1) || [0])[0]) : def;
        return ((c % cells) + cells) % cells;
      };
      if (d.flags & PF.HEAD) {
        const base = (d.base_spin || 0) + q.r[2] * (d.base_spin_var || 0), spin = (d.spin || 0) + q.r[3] * (d.spin_var || 0);
        let theta = base + spin * q.age;
        if (d.flags & PF.FLIP_SPIN && q.seed & 1) theta = -theta;
        const spun = d.spin || d.spin_var || d.base_spin || d.base_spin_var;
        let ax, ay;
        const fast = Math.hypot(...q.v) > 5e-4;
        if (d.flags & PF.ALIGN && fast && !(d.flags & PF.XY_QUAD)) {
          // along its flight as you see it
          const vv = norm(M4.rotate(toView, q.v.map(c => -c)));
          ax = worldOf(vv.map(c => c * sx)); ay = worldOf([vv[1] * sy, -vv[0] * sy, 0]);
        } else if (d.flags & PF.XY_QUAD) {
          // flat in its frame's XY plane (the world's, for particles in the world)
          let qx = d.flags & PF.LOCAL ? norm([em.frame[0], em.frame[1], em.frame[2]]) : [1, 0, 0];
          let qy = d.flags & PF.LOCAL ? norm([em.frame[4], em.frame[5], em.frame[6]]) : [0, 1, 0];
          const qz = norm(cross(qx, qy));
          if (d.flags & PF.ALIGN && fast) {
            const mv = norm([-q.v[0], -q.v[1], 0]);
            [qx, qy] = [[0, 1, 2].map(k => qx[k] * mv[0] + qy[k] * mv[1]), [0, 1, 2].map(k => -qx[k] * mv[1] + qy[k] * mv[0])];
          }
          if (spun) { const r = Q.axis(qz, theta); qx = Q.rot(r, qx); qy = Q.rot(r, qy); }
          ax = qx.map(c => c * sx); ay = qy.map(c => c * sy);
        } else {
          const c = Math.cos(spun ? theta : 0), s = Math.sin(spun ? theta : 0);
          ax = worldOf([c * sx, s * sx, 0]); ay = worldOf([-s * sy, c * sy, 0]);
        }
        quad(ax, ay, cellOf(d.cells, d.flags & PF.RANDOM_CELL ? Math.floor(q.cell * cells) : 0), center);
      }
      if (d.flags & PF.TAIL) {
        const trail = d.flags & PF.TAIL_GROWS ? Math.min(q.age, d.tail_length || 0) : (d.tail_length || 0);
        const vv = M4.rotate(toView, q.v.map(c => -c * trail));
        const screen = Math.hypot(vv[0], vv[1]);
        let ax, ay, c0 = center;
        if (screen * screen > 1e-4) {
          const k = [sx / screen, sy / screen], s2 = [vv[0] * k[0], vv[1] * k[1]];
          ay = worldOf([-s2[1], s2[0], 0]); ax = worldOf(vv.map(c => c * 0.5));
          c0 = [0, 1, 2].map(i => center[i] + ax[i]);
        } else { ax = worldOf([sx * 0.05, 0, 0]); ay = worldOf([0, sy * 0.05, 0]); }
        quad(ax, ay, cellOf(d.tail_cells, 0), c0);
      }
    }
    return out;
  }

  // particles' and ribbons' vertices: [{c (centre), x, y (half axes), u0, v0, du, dv, col, a, q, px}] as
  // two triangles each - corners (-1,1), (-1,-1), (1,1), (1,-1) - or a ribbon's triangles as they come
  drawQuads(quads, multi) {
    const data = new Float32Array(quads.length * 6 * PSTRIDE);
    let o = 0;
    const vx = [-1, -1, 1, 1], vy = [1, -1, 1, -1], tx = [0, 0, 1, 1], ty = [0, 1, 0, 1];
    for (const k of quads) {
      for (const i of [0, 1, 2, 2, 1, 3]) {
        for (let a = 0; a < 3; a++) data[o++] = k.c[a] + k.x[a] * vx[i] + k.y[a] * vy[i];
        data[o++] = k.u0 + tx[i] * k.du; data[o++] = k.v0 + ty[i] * k.dv;
        data[o++] = k.col[0]; data[o++] = k.col[1]; data[o++] = k.col[2]; data[o++] = k.a;
        const tp = multi && k.q.tp;
        data[o++] = tp ? tx[i] * k.px[0] + tp[0][0] : 0; data[o++] = tp ? ty[i] * k.px[0] + tp[0][1] : 0;
        data[o++] = tp ? tx[i] * k.px[1] + tp[1][0] : 0; data[o++] = tp ? ty[i] * k.px[1] + tp[1][1] : 0;
      }
    }
    return data;
  }

  // a particle emitter's or ribbon's blend, as the client's: opaque and alpha-keyed write depth, the rest don't
  effectBlend(mode) {
    const gl = this.gl;
    this.blend(mode);
    gl.depthMask(mode <= 1);
    gl.uniform1f(this.pu.ref, mode === 0 ? -1 : (mode === 1 ? 0.502 : 0.0039));
    gl.uniform1i(this.pu.premul, mode === 7 ? 1 : 0);
  }

  drawParticles(mvp, view) {
    const gl = this.gl;
    gl.useProgram(this.pprog);
    gl.uniformMatrix4fv(this.pu.mvp, false, mvp);
    gl.uniform1i(this.pu.tex, 0); gl.uniform1i(this.pu.tex2, 1); gl.uniform1i(this.pu.tex3, 2);
    gl.bindVertexArray(this.pvao);
    for (const p of this.parts) for (const em of p.emitters) {
      if (!em.list.length || !em.tex || !em.tex.ready || !em.frame) continue;
      const d = em.def, multi = d.flags & PF.MULTI ? (d.flags & 0x40000000 ? 2 : 1) : 0;
      if (multi && em.more.some(t => !t.ready)) continue;
      const quads = this.particleQuads(em, view);
      if (!quads.length) continue;
      const data = this.drawQuads(quads, multi);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.pbuf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      this.effectBlend(d.blend);
      gl.uniform1i(this.pu.multi, multi);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, em.tex.tex);
      if (multi) em.more.forEach((t, i) => this.bindTexture(i ? gl.TEXTURE2 : gl.TEXTURE1, t, [true, true]));
      gl.drawArrays(gl.TRIANGLES, 0, data.length / PSTRIDE);
    }
    gl.bindVertexArray(null);
  }

  // -- ribbons, as the client lays them (WebWowViewerCpp's CRibbonEmitter): an edge across the bone's Y at
  // the emitter (its height above and below) laid down at its rate as it moves, each living its lifetime
  // and sinking by its gravity, the texture running along them from the newest; drawn by each of its layers
  ribbons(now, dt) {
    for (const p of this.parts) {
      if (!p.ribbons.length) continue;
      const model = this.modelMatrix(p);
      if (!model) continue;
      const m = p.mesh;
      for (const rb of p.ribbons) {
        const d = rb.def, X = M4.translate(M4.mul(model, p.world[d.bone] || IDENT), d.pos);
        const pos = [X[12], X[13], X[14]], up = [X[4], X[5], X[6]];
        const above = value(d.above, now, m, 0), below = value(d.below, now, m, 0);
        const col = [...(sample(d.color, now, m.duration, m.globals, 3) || [1, 1, 1]), value(d.alpha, now, m, 1)];
        const life = Math.max(0.25, d.life || 0), rate = Math.ceil(Math.max(1, d.edges || 1));
        const edge = (at, upv, age) => ({lo: at.map((c, k) => c - upv[k] * below), hi: at.map((c, k) => c + upv[k] * above), age, col});
        for (const e of rb.edges) {
          const dz = (d.gravity || 0) * (2 * e.age * dt + dt * dt);
          e.lo[2] += dz; e.hi[2] += dz; e.age += dt;
        }
        rb.edges = rb.edges.filter(e => e.age <= life);
        const shown = !d.visible || !d.visible.t.length || value(d.visible, now, m, 1) > 0;
        if (shown && rb.prev && dt > 0) {
          rb.acc += dt * rate;
          const n = Math.floor(rb.acc);
          rb.acc -= n;
          for (let i = 1; i <= Math.min(n, 64); i++) {
            const f = i / n, at = rb.prev.pos.map((c, k) => c + (pos[k] - c) * f);
            const upv = rb.prev.up.map((c, k) => c + (up[k] - c) * f);
            rb.edges.push(edge(at, upv, (1 - f) * dt));
          }
        }
        rb.prev = {pos, up};
        rb.tip = shown ? edge(pos, up, 0) : null;
        rb.slot = Math.max(0, Math.floor(value(d.slot, now, m, 0)));
        rb.uv = d.uvanim >= 0 && p.uvMats[d.uvanim] ? p.uvMats[d.uvanim] : null;
      }
    }
  }

  drawRibbons(mvp) {
    const gl = this.gl;
    gl.useProgram(this.pprog);
    gl.uniformMatrix4fv(this.pu.mvp, false, mvp);
    gl.uniform1i(this.pu.tex, 0); gl.uniform1i(this.pu.multi, 0);
    gl.bindVertexArray(this.pvao);
    for (const p of this.parts) for (const rb of p.ribbons) {
      const edges = rb.tip ? [...rb.edges, rb.tip] : rb.edges;
      if (edges.length < 2) continue;
      const d = rb.def, life = Math.max(0.25, d.life || 0), du = 1 / d.cols, dv = 1 / d.rows;
      const u0 = (rb.slot % d.cols) * du, v0 = Math.floor(rb.slot / d.cols) % d.rows * dv;
      const data = new Float32Array((edges.length - 1) * 6 * PSTRIDE);
      let o = 0;
      const put = (pt, e, v) => {
        let u = u0 + du * e.age / life, w = v;
        if (rb.uv) { const t = M4.apply(rb.uv, [u, w, 0]); u = t[0]; w = t[1]; }
        data.set([pt[0], pt[1], pt[2], u, w, e.col[0], e.col[1], e.col[2], e.col[3], 0, 0, 0, 0], o); o += PSTRIDE;
      };
      for (let i = 0; i + 1 < edges.length; i++) {
        const a = edges[i], b = edges[i + 1];
        put(a.lo, a, v0); put(a.hi, a, v0 + dv); put(b.lo, b, v0);
        put(b.lo, b, v0); put(a.hi, a, v0 + dv); put(b.hi, b, v0 + dv);
      }
      gl.bindBuffer(gl.ARRAY_BUFFER, this.pbuf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      for (const l of rb.layers) {
        if (!l.tex || !l.tex.ready) continue;
        // a ribbon is see-through at least (an opaque material is drawn by alpha)
        this.effectBlend(l.blend === 0 ? 2 : l.blend);
        if (l.mflags & 0x8) gl.disable(gl.DEPTH_TEST); else gl.enable(gl.DEPTH_TEST);
        gl.depthMask(!(l.mflags & 0x10));
        this.bindTexture(gl.TEXTURE0, l.tex, [true, true]);
        gl.drawArrays(gl.TRIANGLES, 0, o / PSTRIDE);
      }
      gl.enable(gl.DEPTH_TEST);
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

  // A state kit's shading for a part (opts.fx), as CM2SceneRender::SetGradientConstants and
  // SetDissolveConstants give it: the gradient's ramp, rim and edge, its height up the model's reach (from its
  // feet; the fade the other way with flag 8); the dissolve's three layers scaled and scrolled, its tint,
  // projection, ramp and value - its end value, the kit there whole.
  fxUniforms(p, now) {
    const gl = this.gl, fx = p.opts.fx || {};
    if (fx.gradient) {
      const g = fx.gradient, reach = p.mesh.reach || p.mesh.bounds, bz = reach[0][2], h = reach[1][2] - bz || 1;
      let axis = [0, 0, 1 / h, -bz / h];
      if ((g.flags || 0) & 8) axis = [0, 0, -1 / h, 1 + bz / h];
      gl.uniform4fv(this.u.uGradAxis, axis);
      gl.uniform3fv(this.u.uRamp0, g.low); gl.uniform3fv(this.u.uRamp1, g.middle); gl.uniform3fv(this.u.uRamp2, g.high);
      gl.uniform4fv(this.u.uGEdge, [...g.edge, 1]);
      return 1;
    }
    if (fx.dissolve && p.dissolveTex) {
      const d = fx.dissolve, s = now / 1000;
      [this.u.uL0, this.u.uL1, this.u.uL2].forEach((u, k) => {
        const l = d.layers[k], su = l.scroll[0] * s, sv = l.scroll[1] * s;
        gl.uniform4fv(u, [l.scale[0], l.scale[1], su - Math.floor(su), sv - Math.floor(sv)]);
      });
      gl.uniform4fv(this.u.uModX, d.modx);
      gl.uniform4fv(this.u.uDTint, d.tint.map(c => c * d.intensity));
      gl.uniform4fv(this.u.uDShape, [d.projection, d.ramp, d.end, d.fresnel]);
      gl.uniform4fv(this.u.uDExtra, [d.scale || 1, d.flags & 0x2000 ? 1 : 0, 0, 0]);
      p.dissolveTex.forEach((t, k) => this.bindTexture([gl.TEXTURE4, gl.TEXTURE5, gl.TEXTURE6][k], t.ready ? t : this.white, [true, true]));
      return 2;
    }
    return 0;
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
    this.ribbons(now, dt);
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
    gl.uniform1i(this.u.uMask, 4); gl.uniform1i(this.u.uSecond, 5); gl.uniform1i(this.u.uThird, 6);
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
        const fx = this.fxUniforms(p, now);
        gl.uniform1i(this.u.uFx, fx);
        gl.bindVertexArray(p.vao);
        for (const b of p.batches) {
          if (b.missing || !p.visible(b.geoset)) continue;
          const col = b.color >= 0 && p.colors[b.color] ? p.colors[b.color] : [1, 1, 1, 1];
          const wgt = b.weight >= 0 && p.weights[b.weight] !== undefined ? p.weights[b.weight] : 1;
          const tint = [p.tint[0] * col[0], p.tint[1] * col[1], p.tint[2] * col[2], p.tint[3] * col[3] * wgt];
          if (tint[3] <= 0.003) continue;
          // a gradient blends its opaque and alpha-keyed batches by alpha, so its height fade shows
          const blended = b.blend >= 2 || tint[3] < 1 || fx === 1;
          if (blended !== (pass === 1)) continue;
          const mode = (tint[3] < 1 || fx === 1) && b.blend < 2 ? 2 : b.blend;
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
          if (!t && blended && !fx) continue;
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
          gl.uniform1i(this.u.uOpaque, mode === 0 && tint[3] >= 1 ? 1 : 0);
          if (fx) {
            // the texture's alpha is the opacity of any but an opaque batch; an alpha key cuts at its reference
            gl.uniform4fv(this.u.uFxModes, [b.blend ? 1 : 0, b.blend === 1 ? 0.5 : 0, 0, 0]);
            if (fx === 1) gl.uniform4fv(this.u.uGShape, [p.opts.fx.gradient.split, p.opts.fx.gradient.rim,
              (p.opts.fx.gradient.flags || 0) & 1 ? 1 : 0, b.blend === 3 || b.blend === 4 ? 1 : 0]);
          }
          gl.drawElements(gl.TRIANGLES, b.count, gl.UNSIGNED_INT, b.start * 4);
        }
      }
    }
    gl.bindVertexArray(null);
    gl.disable(gl.CULL_FACE); gl.enable(gl.DEPTH_TEST); gl.frontFace(gl.CCW);   // particles face the camera
    this.drawRibbons(mvp);
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

// A state kit model's place in its attachment point's frame (EnchantModelTimeline's Placement, the client's
// CEffect::ApplyModelAttachRecToMatrix): scaled, turned roll (X), pitch (Y), then the yaw backwards (Z), and
// moved by its offset with Y turned round.
Viewer.kitMatrix = s => {
  let m = M4.ident();
  for (let k = 0; k < 3; k++) m[k * 5] = s.scale || 1;
  const [yaw, pitch, roll] = s.rotation || [0, 0, 0];
  if (roll) m = M4.mul(M4.rotX(roll), m);
  if (pitch) m = M4.mul(M4.rotY(pitch), m);
  if (yaw) m = M4.mul(M4.rotZ(-yaw), m);
  const off = s.offset || [0, 0, 0];
  m[12] = off[0]; m[13] = -off[1]; m[14] = off[2];
  return m;
};
window.Viewer = Viewer;
