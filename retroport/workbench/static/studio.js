"use strict";
// The studio: paint inside a piece, and give each of its effects a colour of its own. After Kira's Eclipse
// Studio (its findings, our own code): a part is the triangles joined to the one clicked; an area grows from the
// texel clicked over art of much the same colour (how far: Reach); the brush lays paint where it's dragged. A
// stroke keeps the art's light and shade relative to what it covers (colour.js paintTexel), so a horn painted red
// keeps its creases and highlights. Each stroke is an operation on one texture of the piece - a mask (a rectangle
// of coverage, saved as runs) and its colour - kept in the colourway (``way.paint``); Install bakes them into new
// copies of the textures (paint.py) and the client draws those for the colourway. An effect - a glow, sparks, a
// trail - takes its own colour by its texture (``way.fx``: FileDataID -> colour, or "off" as made), and the
// client recolours it live as it does the colourway's parts.
//
// Studio.panel(ctx) -> the Paint pane. ctx: {way(), pb (the preview box), changed() (the colourway changed), paint(fdid,
// list) (the preview takes the paint - way.paint, or `list` while a stroke is being drawn - again: only that
// texture's when given)}.

const Studio = (() => {
  const TOOLS = [["part", "Part", "Click a part of the piece: everything joined to it takes the paint"],
                 ["area", "Area", "Click the art: what's of much the same colour around it takes the paint (Reach: how far)"],
                 ["brush", "Brush", "Drag over the piece to paint it"]];
  const art = new Map();                         // url -> Promise<{img, w, h, px, lab}>

  // a texture's art, its pixels and (on first need) their OKLab colours
  function artOf(url) {
    if (!art.has(url)) art.set(url, new Promise((ok, bad) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement("canvas");
        c.width = img.width; c.height = img.height;
        const x = c.getContext("2d", {willReadFrequently: true});
        x.drawImage(img, 0, 0);
        ok({img, w: img.width, h: img.height, px: x.getImageData(0, 0, img.width, img.height).data, lab: null});
      };
      img.onerror = () => { art.delete(url); bad(new Error("texture not readable")); };
      img.src = url;
    }));
    return art.get(url);
  }
  const toLin = c => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  function labOf(a) {
    if (a.lab) return a.lab;
    const n = a.w * a.h, lab = new Float32Array(n * 3), memo = new Map();
    for (let i = 0; i < n; i++) {
      const o = i * 4, key = (a.px[o] << 16) | (a.px[o + 1] << 8) | a.px[o + 2];
      let v = memo.get(key);
      if (!v) {
        const r = toLin(a.px[o] / 255), g = toLin(a.px[o + 1] / 255), b = toLin(a.px[o + 2] / 255);
        const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
        const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
        const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
        v = [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s, 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
             0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
        memo.set(key, v);
      }
      lab[i * 3] = v[0]; lab[i * 3 + 1] = v[1]; lab[i * 3 + 2] = v[2];
    }
    return (a.lab = lab);
  }

  // -- what a click lands on ------------------------------------------------------------------------------------
  // The texture the paint goes on and how the part's UVs map onto its texels: a model's own texture (one the
  // display gives it; one fixed in the model can't be swapped for the colourway) by its UVs, the body's skin
  // through the section a piece's texture is drawn in, a cloak's cape texture by its UVs.
  const frac = x => x - Math.floor(x);
  function targetOf(pb, hit) {
    const p = hit.part, b = hit.batch;
    if (p.opts.ghost) return {why: "That's an item glow: give it a colour under Effects"};
    if (p === pb.bodyPart) {
      if (b.texture_type === 2 && pb.cape) {
        const c = pb.cape;
        return {fdid: c.fdid, url: c.url, map: uv => [frac(uv[0]) * c.w, frac(uv[1]) * c.h]};
      }
      const skin = pb.skin;
      if (b.texture_type !== 1 || !skin) return {why: "That's the body"};
      const L = skin.layout, x = hit.uv[0] * L.width, y = hit.uv[1] * L.height;
      for (let i = skin.layers.length - 1; i >= 0; i--) {
        const l = skin.layers[i];
        if (!l.piece || !l.img) continue;
        const r = l.sec < 0 ? [0, 0, L.width, L.height] : L.sections[l.sec];
        if (!r || x < r[0] || y < r[1] || x >= r[0] + r[2] || y >= r[1] + r[3]) continue;
        const sx = l.img.width / r[2], sy = l.img.height / r[3];
        return {fdid: l.fdid, url: l.url, clip: true, map: uv => [(uv[0] * L.width - r[0]) * sx, (uv[1] * L.height - r[1]) * sy]};
      }
      return {why: "That's the body's own skin - none of the piece is drawn there"};
    }
    if (!b.texture) return {why: "That part has no texture"};
    if (b.texture_type === 0) return {why: "That part's texture is fixed in the model - colour it with the colourway, or under Effects if it glows"};
    const url = p.opts.texUrl(b.texture);
    return {fdid: b.texture, url, map: null};
  }

  // the triangles of a batch joined to triangle `index` - sharing a vertex, so a plate, a strap or a trim the
  // artist cut out on the texture is a part of its own (a UV seam or a hard edge splits vertices) - kept per part
  // and batch
  function joined(p, b, index) {
    p.studioParts = p.studioParts || new Map();
    let comp = p.studioParts.get(b);
    if (!comp) {
      const I = p.indices, n = b.count / 3, parent = new Int32Array(n).map((_, i) => i);
      const find = i => { while (parent[i] !== i) { parent[i] = parent[parent[i]]; i = parent[i]; } return i; };
      const seen = new Map();
      for (let t = 0; t < n; t++) for (let k = 0; k < 3; k++) {
        const key = I[b.start + t * 3 + k];
        const at = seen.get(key);
        if (at === undefined) seen.set(key, t); else { const a = find(at), c = find(t); if (a !== c) parent[a] = c; }
      }
      comp = new Int32Array(n);
      for (let t = 0; t < n; t++) comp[t] = find(t);
      p.studioParts.set(b, comp);
    }
    const me = comp[(index - b.start) / 3], out = [];
    for (let t = 0; t < comp.length; t++) if (comp[t] === me) out.push(b.start + t * 3);
    return out;
  }

  // triangles (first index each) rasterised into a full-size mask in texel space; one texel wider, so the seam
  // between two UV islands doesn't show the art through
  function raster(p, tris, map, w, h, mask) {
    const I = p.indices, uv = p.uvs || (p.uvs = b64(p.mesh.uvs, Float32Array));
    const mapped = i => map ? map([uv[i * 2], uv[i * 2 + 1]]) : [uv[i * 2] * w, uv[i * 2 + 1] * h];
    for (const t of tris) {
      let [a, b, c] = [mapped(I[t]), mapped(I[t + 1]), mapped(I[t + 2])];
      // a triangle wrapped past the texture's edge: moved back by whole textures
      if (!map) {
        const ox = Math.floor(Math.min(a[0], b[0], c[0]) / w) * w, oy = Math.floor(Math.min(a[1], b[1], c[1]) / h) * h;
        a = [a[0] - ox, a[1] - oy]; b = [b[0] - ox, b[1] - oy]; c = [c[0] - ox, c[1] - oy];
      }
      const x0 = Math.max(0, Math.floor(Math.min(a[0], b[0], c[0])) - 1), x1 = Math.min(w - 1, Math.ceil(Math.max(a[0], b[0], c[0])) + 1);
      const y0 = Math.max(0, Math.floor(Math.min(a[1], b[1], c[1])) - 1), y1 = Math.min(h - 1, Math.ceil(Math.max(a[1], b[1], c[1])) + 1);
      if (x0 > x1 || y0 > y1) continue;
      const area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      if (Math.abs(area) < 1e-9) continue;
      // edge distance in texels (signed by the triangle's winding): inside within a texel of the edge counts
      const edge = (p0, p1, x, y) => ((p1[0] - p0[0]) * (y - p0[1]) - (p1[1] - p0[1]) * (x - p0[0])) /
                                     (Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) || 1) * Math.sign(area);
      for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
        const cx = x + 0.5, cy = y + 0.5;
        if (edge(a, b, cx, cy) >= -0.75 && edge(b, c, cx, cy) >= -0.75 && edge(c, a, cx, cy) >= -0.75) mask[y * w + x] = 255;
      }
    }
    return mask;
  }

  // from texel (sx, sy): the texels joined to it of much the same colour as it (OKLab distance under `reach`),
  // within `within` (the texels the part's triangles cover) when given
  function flood(a, sx, sy, reach, within, mask) {
    const lab = labOf(a), w = a.w, h = a.h, s = (sy * w + sx) * 3;
    const L0 = lab[s], A0 = lab[s + 1], B0 = lab[s + 2], r2 = reach * reach;
    const stack = [sy * w + sx], seen = new Uint8Array(w * h);
    seen[sy * w + sx] = 1;
    while (stack.length) {
      const i = stack.pop(), o = i * 3;
      const dL = lab[o] - L0, dA = lab[o + 1] - A0, dB = lab[o + 2] - B0;
      if (dL * dL + dA * dA + dB * dB > r2) continue;
      if (within && !within[i]) continue;
      mask[i] = 255;
      const x = i % w, y = (i - x) / w;
      if (x > 0 && !seen[i - 1]) { seen[i - 1] = 1; stack.push(i - 1); }
      if (x < w - 1 && !seen[i + 1]) { seen[i + 1] = 1; stack.push(i + 1); }
      if (y > 0 && !seen[i - w]) { seen[i - w] = 1; stack.push(i - w); }
      if (y < h - 1 && !seen[i + w]) { seen[i + w] = 1; stack.push(i + w); }
    }
    // a texel round its edge half taken: softer than a stair step
    const out = mask.slice();
    for (let y = 1; y < h - 1; y++) for (let x = 1; x < w - 1; x++) {
      const i = y * w + x;
      if (mask[i] || (within && !within[i])) continue;
      if (mask[i - 1] || mask[i + 1] || mask[i - w] || mask[i + w]) out[i] = 128;
    }
    mask.set(out);
    return mask;
  }

  // a soft round dab of radius r texels at (cx, cy)
  function dab(mask, w, h, cx, cy, r) {
    const x0 = Math.max(0, Math.floor(cx - r)), x1 = Math.min(w - 1, Math.ceil(cx + r));
    const y0 = Math.max(0, Math.floor(cy - r)), y1 = Math.min(h - 1, Math.ceil(cy + r));
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      const d = Math.hypot(x + 0.5 - cx, y + 0.5 - cy);
      if (d > r) continue;
      const v = Math.round(255 * Math.min(1, (r - d) / Math.max(1, r * 0.35)));
      const i = y * w + x;
      if (v > mask[i]) mask[i] = v;
    }
  }

  // a full-size mask as an operation: its rectangle, its runs, the art's mean lightness under it
  function opOf(mask, a, fdid, colour) {
    const w = a.w, h = a.h;
    let x0 = w, y0 = h, x1 = -1, y1 = -1;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (mask[y * w + x]) {
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    if (x1 < 0) return null;
    const rw = x1 - x0 + 1, rh = y1 - y0 + 1, data = new Uint8Array(rw * rh);
    for (let y = 0; y < rh; y++) data.set(mask.subarray((y0 + y) * w + x0, (y0 + y) * w + x0 + rw), y * rw);
    const m = {x: x0, y: y0, w: rw, h: rh, data};
    return {tex: fdid, size: [w, h], rect: [x0, y0, rw, rh], runs: Colour.maskToRuns(m),
            colour: {...colour}, ref: Math.round(Colour.meanL(a.px, w, m) * 1e4) / 1e4};
  }

  // -- effects ---------------------------------------------------------------------------------------------------
  // A preview's effects: each texture its glows (an item glow's model, or a batch that adds itself), particles
  // and ribbons are drawn with - [{fdid, kind, url}], in the order they're found.
  const glowBatch = (p, b) => p.opts.ghost || [3, 4, 7].includes(b.blend) || (b.unlit && b.blend >= 2);
  function effectsOf(pb) {
    const out = new Map();
    const add = (p, fdid, kind) => {
      if (!fdid || out.has(fdid) || !p.opts.texUrl) return;
      out.set(fdid, {fdid, kind, url: p.opts.texUrl(fdid)});
    };
    for (const p of pb.parts || []) {
      for (const b of p.batches) if (glowBatch(p, b)) add(p, b.texture, "glow");
      for (const em of p.emitters || []) add(p, em.def.texture, "particles");
      for (const rb of p.ribbons || []) for (const l of rb.layers) add(p, l.texture, "ribbon");
    }
    return [...out.values()];
  }
  const FX_NAMES = {glow: "Glow", particles: "Sparks", ribbon: "Trail"};
  const FX_PART = {glow: "glows", particles: "particles", ribbon: "ribbons"};

  // -- the pane ---------------------------------------------------------------------------------------------------
  function panel(ctx) {
    const st = {tool: "part", reach: 30, size: 4, colour: {...(ctx.way().colour || {hue: 0, sat: 1, light: 128, dye: 0}), dye: 0},
                undo: [], redo: [], stroke: null, busy: false};
    const box = el("div", {class: "st"});
    const v = ctx.pb.v;
    const ops = () => (ctx.way().paint = ctx.way().paint || []);
    const status = el("div", {class: "muted small st-status"});
    const say = t => { status.textContent = t; };
    const counts = () => {
      const o = ops(), tex = new Set(o.map(x => x.tex)).size;
      return o.length ? `${plural(o.length, "stroke")} on ${plural(tex, "texture")}` : "Nothing painted yet";
    };
    const commit = op => {
      st.undo.push(ops().slice()); st.redo = [];
      ctx.way().paint = [...ops(), op];
      ctx.paint(op.tex); ctx.changed(); sync();
    };

    // what a point of the canvas lands on, for the paint: the target texture, its art, the texel
    const land = async (x, y, quiet) => {
      const hit = v.pick(x, y);
      if (!hit) { if (!quiet) say("Nothing of the piece there"); return null; }
      const t = targetOf(ctx.pb, hit);
      if (!t.fdid) { if (!quiet) say(t.why); return null; }
      let a;
      try { a = await artOf(t.url); } catch (e) { if (!quiet) say(`Its texture isn't readable (${t.fdid})`); return null; }
      const [tx, ty] = t.map ? t.map(hit.uv) : [frac(hit.uv[0]) * a.w, frac(hit.uv[1]) * a.h];
      return {hit, t, a, tx, ty, sx: Math.min(a.w - 1, Math.max(0, Math.floor(tx))), sy: Math.min(a.h - 1, Math.max(0, Math.floor(ty)))};
    };
    // a click: a part, or an area
    const click = async ev => {
      const g = await land(ev.clientX, ev.clientY, false);
      if (!g) return;
      const {hit, t, a} = g, mask = new Uint8Array(a.w * a.h);
      if (st.tool === "part") {
        raster(hit.part, joined(hit.part, hit.batch, hit.index), t.map, a.w, a.h, mask);
      } else {
        // within what the part's batch covers of the texture (an atlas's other pieces stay out)
        const within = t.clip ? null : raster(hit.part, Array.from({length: hit.batch.count / 3}, (_, i) => hit.batch.start + i * 3),
                                              t.map, a.w, a.h, new Uint8Array(a.w * a.h));
        flood(a, g.sx, g.sy, 0.02 + st.reach / 100 * 0.3, within, mask);
      }
      const op = opOf(mask, a, t.fdid, st.colour);
      if (!op) { say("Nothing to paint there"); return; }
      st.undo.push(ops().slice()); st.redo = [];
      ctx.way().paint = [...ops(), op];
      ctx.paint(op.tex); ctx.changed(); sync();
      say(`Painted ${st.tool === "part" ? "a part" : "an area"} · ${counts()}`);
    };
    // the brush: a dab wherever the drag passes on screen (picked every few pixels, so it follows the surface and
    // never jumps across the texture), each texture's dabs one mask; drawn live, kept on letting go
    const brushTo = async (x, y) => {
      const s = st.stroke;
      const from = s.at || [x, y], d = Math.hypot(x - from[0], y - from[1]), n = Math.max(1, Math.ceil(d / 3));
      for (let i = s.at ? 1 : 0; i <= n; i++) {
        const g = await land(from[0] + (x - from[0]) * i / n, from[1] + (y - from[1]) * i / n, true);
        if (!g) { s.last = null; continue; }
        let m = s.masks.get(g.t.fdid);
        if (!m) { m = {mask: new Uint8Array(g.a.w * g.a.h), a: g.a}; s.masks.set(g.t.fdid, m); }
        const r = Math.max(1, st.size / 100 * g.a.w);
        // between two dabs close on the texture too (the same stretch of it): filled in
        const last = s.last && s.last.fdid === g.t.fdid ? s.last : null;
        if (last && Math.hypot(g.tx - last.tx, g.ty - last.ty) < r * 2) {
          const k = Math.ceil(Math.hypot(g.tx - last.tx, g.ty - last.ty) / (r * 0.4));
          for (let j = 1; j <= k; j++) dab(m.mask, g.a.w, g.a.h, last.tx + (g.tx - last.tx) * j / k, last.ty + (g.ty - last.ty) * j / k, r);
        } else dab(m.mask, g.a.w, g.a.h, g.tx, g.ty, r);
        s.last = {fdid: g.t.fdid, tx: g.tx, ty: g.ty};
      }
      s.at = [x, y];
      live();
    };
    // the brush's stroke so far, drawn over what's painted
    let liveTimer = 0;
    const live = () => {
      if (liveTimer) return;
      liveTimer = requestAnimationFrame(() => {
        liveTimer = 0;
        const s = st.stroke;
        if (!s || s.done) return;
        const extra = [...s.masks.entries()].map(([f, m]) => opOf(m.mask, m.a, f, st.colour)).filter(Boolean);
        for (const op of extra) ctx.paint(op.tex, [...ops(), ...extra]);
      });
    };
    v.tool = {
      down: ev => {
        if (st.tool !== "brush") { click(ev); return; }
        const s = st.stroke = {masks: new Map(), at: null, last: null, queue: Promise.resolve()};
        s.queue = s.queue.then(() => brushTo(ev.clientX, ev.clientY));
      },
      move: ev => {
        const s = st.stroke;
        if (st.tool === "brush" && s) s.queue = s.queue.then(() => brushTo(ev.clientX, ev.clientY));
      },
      up: () => {
        const s = st.stroke;
        if (!s) return;
        s.queue.then(() => {
          s.done = true;
          if (st.stroke === s) st.stroke = null;
          const made = [...s.masks.entries()].map(([f, m]) => opOf(m.mask, m.a, f, st.colour)).filter(Boolean);
          if (!made.length) { say("Nothing of the piece there"); return; }
          st.undo.push(ops().slice()); st.redo = [];
          ctx.way().paint = [...ops(), ...made];
          for (const op of made) ctx.paint(op.tex);
          ctx.changed(); sync();
          say(`Painted a stroke · ${counts()}`);
        });
      },
    };
    v.canvas.classList.add("painting");
    v.freeze(true);

    const toolChips = el("div", {class: "chips", role: "group", "aria-label": "Paint with"});
    const reach = cwSlider("Reach", 100, st.reach, x => { st.reach = x; }, "How different a colour the area may grow over", x => `${x}%`);
    const size = cwSlider("Size", 20, st.size, x => { st.size = Math.max(1, x); }, "The brush's width, a share of the texture's", x => `${Math.max(1, x)}%`);
    const wheel = colourWheel(132, () => st.colour, k => { st.colour = k; sync(); });
    const light = cwSlider("Brightness", 255, st.colour.light ?? 128, x => { st.colour = {...st.colour, light: x}; sync(); },
                           "The paint's lightness", x => x === 128 ? "as made" : `${Math.round(Colour.lightMul(x) * 100)}%`);
    const swatch = el("i", {class: "cw-big"});
    const presets = el("div", {class: "cw-presets"}, Colour.PRESETS.map(p => el("button", {class: "cw-preset", title: p.name,
      style: `background:${Colour.css(p.colour)}`, onclick: () => { st.colour = {...p.colour}; light.put(p.colour.light); sync(); }})));
    const undo = el("button", {class: "btn ghost", onclick: () => {
      if (!st.undo.length) return;
      st.redo.push(ops().slice()); ctx.way().paint = st.undo.pop(); ctx.paint(null); ctx.changed(); sync(); say(counts());
    }}, "Undo");
    const redo = el("button", {class: "btn ghost", onclick: () => {
      if (!st.redo.length) return;
      st.undo.push(ops().slice()); ctx.way().paint = st.redo.pop(); ctx.paint(null); ctx.changed(); sync(); say(counts());
    }}, "Redo");
    const clear = el("button", {class: "btn ghost", onclick: () => {
      if (!ops().length) return;
      st.undo.push(ops().slice()); st.redo = []; ctx.way().paint = []; ctx.paint(null); ctx.changed(); sync(); say("Paint cleared");
    }}, "Clear");
    const sync = () => {
      toolChips.replaceChildren(...TOOLS.map(([k, label, hint]) => el("button", {class: "chip" + (st.tool === k ? " on" : ""), title: hint,
        onclick: () => { st.tool = k; sync(); say(hint); }}, label)));
      reach.hidden = st.tool !== "area"; size.hidden = st.tool !== "brush";
      wheel.paint(); swatch.style.background = Colour.css(st.colour);
      undo.disabled = !st.undo.length; redo.disabled = !st.redo.length; clear.disabled = !ops().length;
    };
    box.append(
      el("div", {class: "st-top"},
        el("div", {class: "cw-wheel-box"}, wheel),
        el("div", {class: "cw-side"},
          el("div", {class: "cw-swatch-row"}, swatch, el("span", {class: "muted small"}, "The paint")),
          light, presets)),
      el("div", {class: "st-tools"}, el("span", {class: "muted small"}, "Paint with"), toolChips, reach, size),
      el("div", {class: "st-actions"}, undo, redo, clear),
      el("div", {class: "muted small"}, "Left-click paints · Alt + drag turns the model · right-drag moves it · the pose holds still while you paint"),
      status);
    sync();
    say(`${TOOLS[0][2]} · ${counts()}`);
    box.dispose = () => {
      if (v.tool) v.tool = null;
      v.canvas.classList.remove("painting");
      v.freeze(false);
    };
    return box;
  }

  return {panel, effectsOf, artOf, FX_NAMES, FX_PART, targetOf};
})();
window.Studio = Studio;
