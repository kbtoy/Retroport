"use strict";
// A look's colourway: the colour a player gives an item or a set - the maths, shared by the page (swatches,
// the body's painted armor) and, as GLSL, by the 3D view (viewer.js). After Kira's Eclipse (its weapon and
// gear colours: a hue wheel, Brightness and Dye, named presets; the recolour in OKLab keeping each texel's
// colourfulness relative to how colourful its lightness and hue can be) - our own code from its findings.
//
// A colour ``k`` is {hue: degrees, sat: 0..1, light: 0..255 (128 the art's own), dye: 0..1}. A texel keeps
// its lightness (scaled by Brightness) and takes the hue; its colourfulness relative to the most its
// lightness and hue allow, times 1.25 and the colour's saturation - so grey steel stays grey and only
// what was coloured (glows, gems, runes, trims) changes - and Dye pushes everything towards the colour's
// own saturation (the whole piece takes it). Near-white stays a little whiter (hot centres), and an
// overbright colour (an additive glow's track over 1) is recoloured at 1 and scaled back.
//
// A colourway: {key, name, colour, parts: {armor, glows, particles, ribbons}}: each part "same" (the
// colourway's colour), "off" (as Blizzard made it) or its own colour.

const Colour = (() => {
  const PARTS = [["armor", "Armor"], ["glows", "Glows"], ["particles", "Particles"], ["ribbons", "Ribbons"]];
  // named starting points (hue, saturation, brightness)
  const PRESETS = [
    ["Crimson", 25, 0.95, 120], ["Ember", 50, 1, 136], ["Gold", 85, 0.9, 150], ["Fel", 140, 1, 136], ["Frost", 230, 0.75, 160],
    ["Arcane", 300, 0.95, 140], ["Void", 285, 0.9, 92], ["Rose", 0, 0.7, 150], ["Silver", 250, 0.08, 150], ["Shadow", 270, 0.35, 64],
  ].map(([name, hue, sat, light]) => ({name, colour: {hue, sat, light, dye: 0}}));

  // sRGB <-> linear <-> OKLab (Björn Ottosson's published matrices)
  const toLin = c => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  const toSrgb = c => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(Math.max(c, 0), 1 / 2.4) - 0.055;
  function linToLab(r, g, b) {
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }
  function labToLin(L, a, b) {
    const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
    const s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3;
    return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
  }
  // the most colourful an sRGB colour of lightness L and hue h (radians) can be (bisection on the gamut)
  function cmax(L, h) {
    const ca = Math.cos(h), sa = Math.sin(h);
    let lo = 0, hi = 0.4;
    for (let i = 0; i < 16; i++) {
      const mid = (lo + hi) / 2, c = labToLin(L, mid * ca, mid * sa);
      if (c[0] >= -1e-4 && c[1] >= -1e-4 && c[2] >= -1e-4 && c[0] <= 1.0001 && c[1] <= 1.0001 && c[2] <= 1.0001) lo = mid; else hi = mid;
    }
    return lo;
  }
  const smooth = (a, b, x) => { const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
  const lightMul = light => light < 128 ? 0.35 + 0.65 * light / 128 : 1 + 0.6 * (light - 128) / 127;

  // one colour (0..1 sRGB, may be over 1) recoloured by k
  function apply(rgb, k) {
    const m = Math.max(1, rgb[0], rgb[1], rgb[2]);
    if (rgb[0] < 0 || rgb[1] < 0 || rgb[2] < 0) return rgb;
    const [L, a, b] = linToLab(toLin(rgb[0] / m), toLin(rgb[1] / m), toLin(rgb[2] / m));
    const C = Math.hypot(a, b), h = Math.atan2(b, a), cm = cmax(L, h);
    const rel = cm > 1e-5 ? C / cm : 0, sat = k.sat;
    const base = Math.min(1, Math.max(0, rel * 1.25 * sat));
    let r = base + (sat - base) * (k.dye || 0);
    r *= 1 - 0.35 * smooth(0.8, 1, L);
    const Lo = Math.min(1, L * lightMul(k.light ?? 128)), ho = (k.hue || 0) * Math.PI / 180;
    const Co = r * cmax(Lo, ho), lin = labToLin(Lo, Co * Math.cos(ho), Co * Math.sin(ho));
    return lin.map(c => Math.min(1, Math.max(0, toSrgb(c))) * m);
  }
  // what the colour looks like: its hue at its saturation, a little under full lightness
  function swatch(k) {
    const L = 0.72 * lightMul(k.light ?? 128), ho = (k.hue || 0) * Math.PI / 180;
    const Lo = Math.min(1, L), Co = (k.sat ?? 1) * cmax(Lo, ho), lin = labToLin(Lo, Co * Math.cos(ho), Co * Math.sin(ho));
    return lin.map(c => Math.round(Math.min(1, Math.max(0, toSrgb(c))) * 255));
  }
  const css = k => { const [r, g, b] = swatch(k); return `rgb(${r},${g},${b})`; };
  // a part's colour in a colourway: its own, the colourway's ("same"), or none ("off")
  function partColour(way, part) {
    if (!way || !way.colour) return null;
    const p = (way.parts || {})[part] ?? "same";
    return p === "off" ? null : p === "same" ? way.colour : p;
  }
  // a whole image recoloured (the body's painted armor, a cloak's cape texture): memoised by colour
  function image(img, k) {
    const c = document.createElement("canvas");
    c.width = img.width; c.height = img.height;
    const x = c.getContext("2d");
    x.drawImage(img, 0, 0);
    const d = x.getImageData(0, 0, c.width, c.height), px = d.data, memo = new Map();
    for (let i = 0; i < px.length; i += 4) {
      const key = (px[i] << 16) | (px[i + 1] << 8) | px[i + 2];
      let out = memo.get(key);
      if (!out) {
        out = apply([px[i] / 255, px[i + 1] / 255, px[i + 2] / 255], k).map(v => Math.round(v * 255));
        memo.set(key, out);
      }
      px[i] = out[0]; px[i + 1] = out[1]; px[i + 2] = out[2];
    }
    x.putImageData(d, 0, 0);
    return c;
  }
  // the uniform the 3D view takes: [hue (radians), saturation, brightness multiplier, dye], or null
  const uniform = k => k ? [(k.hue || 0) * Math.PI / 180, k.sat ?? 1, lightMul(k.light ?? 128), k.dye || 0] : null;
  const same = (a, b) => JSON.stringify(a || null) === JSON.stringify(b || null);
  return {PARTS, PRESETS, apply, swatch, css, partColour, image, uniform, lightMul, same};
})();
window.Colour = Colour;
