"use strict";
// Colourways: a player's own colours for a version of an item or a set (colour.js has the maths). The editor -
// a hue wheel drawn in the colours it gives, Brightness and Dye, named presets, and which parts take the
// colour (armor, glows, particles, ribbons: each the colourway's colour, its own, or as Blizzard made it) -
// recolours the 3D view as it changes; its Paint tab (studio.js) paints inside the piece, and each of its effects
// can take a colour of its own. Saved, a colourway is a basket entry of its own (``colour``) - or, for a piece of
// a collection of yours, kept with the piece: Install makes it an extra item beside the version it was made from,
// with its paint baked into copies of the textures, and the client recolours it as the preview does.

const DEFAULT_COLOUR = {hue: 270, sat: 1, light: 128, dye: 0};
function newWay(colour = DEFAULT_COLOUR, name = "Custom") {
  return {key: "c" + Date.now().toString(36) + Math.floor(Math.random() * 1296).toString(36), name,
          colour: {...colour}, parts: {}};
}
const copyWay = w => JSON.parse(JSON.stringify(w));

// The wheel: hue round it, saturation out from a silver middle, every point drawn as the colour it gives
// at the colour's brightness. get(): the colour; set(k): a new one.
function colourWheel(size, get, set) {
  const c = el("canvas", {class: "cw-wheel", width: size, height: size});
  const R = size / 2 - 3;
  let base = null, baseLight = null;
  const paint = () => {
    const x = c.getContext("2d"), k = get();
    if (!base || baseLight !== k.light) {
      base = x.createImageData(size, size);
      const memo = new Map();
      for (let py = 0; py < size; py++) for (let px = 0; px < size; px++) {
        const dx = px - size / 2, dy = py - size / 2, r = Math.hypot(dx, dy) / R, o = (py * size + px) * 4;
        if (r > 1) continue;
        const hue = Math.round(((Math.atan2(-dy, dx) * 180 / Math.PI) + 360) % 360), sat = Math.round(r * 40) / 40;
        const key = hue * 64 + sat * 40;
        let rgb = memo.get(key);
        if (!rgb) { rgb = Colour.swatch({hue, sat, light: k.light}); memo.set(key, rgb); }
        base.data[o] = rgb[0]; base.data[o + 1] = rgb[1]; base.data[o + 2] = rgb[2];
        base.data[o + 3] = r > 0.985 ? Math.round(255 * (1 - r) / 0.015) : 255;
      }
      baseLight = k.light;
    }
    x.clearRect(0, 0, size, size);
    x.putImageData(base, 0, 0);
    const a = k.hue * Math.PI / 180, mx = size / 2 + Math.cos(a) * k.sat * R, my = size / 2 - Math.sin(a) * k.sat * R;
    x.lineWidth = 2; x.strokeStyle = "#000"; x.beginPath(); x.arc(mx, my, 7, 0, Math.PI * 2); x.stroke();
    x.strokeStyle = "#fff"; x.beginPath(); x.arc(mx, my, 5.5, 0, Math.PI * 2); x.stroke();
  };
  let drag = false;
  const pick = ev => {
    const r = c.getBoundingClientRect(), dx = (ev.clientX - r.left) * size / r.width - size / 2;
    const dy = (ev.clientY - r.top) * size / r.height - size / 2;
    set({...get(), hue: Math.round(((Math.atan2(-dy, dx) * 180 / Math.PI) + 360) % 360), sat: Math.min(1, Math.hypot(dx, dy) / R)});
  };
  c.addEventListener("pointerdown", ev => { drag = true; c.setPointerCapture(ev.pointerId); pick(ev); });
  c.addEventListener("pointermove", ev => { if (drag) pick(ev); });
  c.addEventListener("pointerup", () => { drag = false; });
  c.paint = paint;
  return c;
}

// A slider of 0..max with its label and value, and a hint under it; ``put(v)`` moves it from outside.
function cwSlider(label, max, value, set, hint, show) {
  const out = el("span", {class: "cw-val"}, show(value));
  const r = el("input", {type: "range", min: 0, max, value, "aria-label": label});
  r.addEventListener("input", () => { out.textContent = show(+r.value); set(+r.value); });
  const box = el("label", {class: "cw-slider", title: hint || ""}, el("span", {class: "cw-lab"}, label, out), r);
  box.put = v => { if (+r.value !== v) r.value = v; out.textContent = show(v); };
  return box;
}

// The editor. way: the colourway edited (changed in place); onChange(way): the preview follows it. o: {pb (the
// preview box: its effects listed, and the Paint tab paints on it), paint(fdid, list) (the preview takes the paint
// again: previewPaint)}. Returns the element; ``refresh()`` redraws it for a colourway changed from outside,
// ``dispose()`` lets the preview go (the studio's tool off it).
function colourEditor(way, onChange, o = {}) {
  let target = "all";                       // what the wheel edits: the colourway's colour, a part's own, an effect's own
  let tab = "colours", studio = null;
  const box = el("div", {class: "cw-editor"});
  // an effect's target is "fx:<its texture's FileDataID>"
  const fxOf = t => t && t.startsWith("fx:") ? +t.slice(3) : 0;
  const effects = () => o.pb && window.Studio ? Studio.effectsOf(o.pb) : [];
  const fxKind = f => (effects().find(e => e.fdid === f) || {}).kind || "glow";
  const partMode = part => {
    const f = fxOf(part), v = f ? (way.fx || {})[f] : (way.parts || {})[part];
    return v === "off" ? "off" : v && typeof v === "object" ? "own" : "same";
  };
  // what a part or an effect is drawn in: its own colour, its part's (an effect's), the colourway's, or none
  const shownColour = part => {
    const f = fxOf(part);
    if (!f) return part === "all" ? way.colour : Colour.partColour(way, part);
    const v = (way.fx || {})[f];
    return v === "off" ? null : v && typeof v === "object" ? v : Colour.partColour(way, Studio.FX_PART[fxKind(f)]);
  };
  const editing = () => target === "all" || partMode(target) !== "own" ? way.colour :
    fxOf(target) ? way.fx[fxOf(target)] : way.parts[target];
  // a colour change shows where it shows (the wheel, the swatch, the sliders, the parts' dots) - the
  // editor isn't drawn again under a slider or the wheel being dragged
  const ui = {};
  const sync = () => {
    const k = editing();
    wheel.paint();
    if (ui.big) ui.big.style.background = target !== "all" && partMode(target) === "off" ? "" : Colour.css(k);
    if (ui.light) ui.light.put(k.light ?? 128);
    if (ui.dye) ui.dye.put(Math.round((k.dye || 0) * 255));
    for (const [part, dot] of Object.entries(ui.dots || {})) {
      const k2 = shownColour(part);
      dot.style.background = k2 ? Colour.css(k2) : "";
    }
  };
  const changed = () => { onChange(way); sync(); };
  const setColour = k => {
    if (target !== "all" && partMode(target) === "own") {
      if (fxOf(target)) way.fx[fxOf(target)] = k; else way.parts[target] = k;
    } else way.colour = k;
    changed();
  };
  const wheel = colourWheel(176, () => editing(), setColour);
  const chip = (key, label, title, extra = null) => {
    const m = key === "all" ? "same" : partMode(key);
    ui.dots[key] = el("i", {class: "cw-dot"});
    return el("button", {class: "chip" + (target === key ? " on" : "") + (m === "off" ? " off" : ""), title,
                         onclick: () => { target = key; draw(); }}, extra, ui.dots[key], label);
  };
  const draw = () => {
    ui.dots = {};
    const tabs = o.pb && window.Studio ? el("div", {class: "cw-tabs", role: "tablist"},
      [["colours", "Colours"], ["paint", "Paint"]].map(([k, label]) => el("button", {class: "tab" + (tab === k ? " on" : ""), role: "tab",
        "aria-selected": tab === k, onclick: () => { if (tab !== k) { tab = k; draw(); } }}, label))) : null;
    if (tab === "paint") {
      // the studio's pane, kept while the editor lives (its tool and its undo with it)
      if (!studio) studio = Studio.panel({way: () => way, pb: o.pb, changed: () => {}, paint: (f, list) => o.paint && o.paint(f, list)});
      box.replaceChildren(tabs, studio);
      return;
    }
    if (studio) { studio.dispose(); studio = null; }
    const k = editing();
    const owns = target !== "all" && partMode(target) === "own";
    const parts = el("div", {class: "cw-parts", role: "group", "aria-label": "Parts"},
      chip("all", "Everything", "The colourway's colour"),
      Colour.PARTS.map(([part, label]) => {
        const m = partMode(part);
        return chip(part, label, m === "off" ? `${label}: as Blizzard made them` : m === "own" ? `${label}: their own colour` :
                                 `${label}: the colourway's colour`);
      }));
    // each glow, spark and trail of what's shown: a colour of its own (by its texture), its part's, or as made
    const fx = effects(), seen = {};
    const fxRow = fx.length ? el("div", {class: "cw-parts-row"}, el("span", {class: "muted small"}, "Effects"),
      el("div", {class: "cw-parts", role: "group", "aria-label": "Effects"}, fx.map(e => {
        seen[e.kind] = (seen[e.kind] || 0) + 1;
        const n = fx.filter(x => x.kind === e.kind).length;
        return chip(`fx:${e.fdid}`, `${Studio.FX_NAMES[e.kind]}${n > 1 ? " " + seen[e.kind] : ""}`, `${Studio.FX_NAMES[e.kind]} · texture ${e.fdid}`,
                    el("img", {class: "cw-fx-thumb", src: e.url, alt: ""}));
      }))) : null;
    const f = fxOf(target), fxPart = f ? Colour.PARTS.find(p => p[0] === Studio.FX_PART[fxKind(f)])[1] : "";
    const modes = f ? [["same", `Its part's colour (${fxPart})`], ["own", "Its own colour"], ["off", "As Blizzard made it"]] :
      [["same", "The colourway's colour"], ["own", "Their own colour"], ["off", "As Blizzard made them"]];
    const mode = target === "all" ? null : el("div", {class: "cw-mode"},
      modes.map(([m, label]) =>
        el("label", {class: "cw-radio"}, (() => {
          const r = el("input", {type: "radio", name: "cw-mode", checked: partMode(target) === m});
          r.addEventListener("change", () => {
            if (f) {
              way.fx = way.fx || {};
              if (m === "same") delete way.fx[f];
              else way.fx[f] = m === "off" ? "off" : {...(shownColour(target) || way.colour)};
            } else {
              way.parts = way.parts || {};
              if (m === "same") delete way.parts[target];
              else way.parts[target] = m === "off" ? "off" : {...(Colour.partColour(way, target) || way.colour)};
            }
            onChange(way); draw();
          });
          return r;
        })(), label)));
    const name = el("input", {class: "cw-name", value: way.name || "", placeholder: "Its name, e.g. Crimson", maxlength: 24});
    name.addEventListener("input", () => { way.name = name.value; onChange(way); });
    const presets = el("div", {class: "cw-presets"}, Colour.PRESETS.map(p => el("button", {class: "cw-preset", title: p.name,
      style: `background:${Colour.css(p.colour)}`, onclick: () => {
        // a colourway still named after a preset (or not named yet) takes the new one's name
        if (target === "all" && (!(way.name || "").trim() || way.name === "Custom" || Colour.PRESETS.some(q => q.name === way.name))) {
          way.name = p.name; name.value = p.name;
        }
        setColour({...p.colour, dye: editing().dye});
      }})));
    const dim = target !== "all" && !owns;
    ui.big = el("i", {class: "cw-big"});
    ui.light = cwSlider("Brightness", 255, k.light ?? 128, v => setColour({...editing(), light: v}), "Darker to the left, brighter to the right",
                        v => v === 128 ? "as made" : `${Math.round(Colour.lightMul(v) * 100)}%`);
    ui.dye = cwSlider("Dye", 255, Math.round((k.dye || 0) * 255), v => setColour({...editing(), dye: v / 255}),
                      "Left: only the glowing and coloured parts change. Right: the whole piece takes the colour",
                      v => v ? `${Math.round(v / 2.55)}%` : "glows only");
    if (dim) { ui.light.querySelector("input").disabled = true; ui.dye.querySelector("input").disabled = true; }
    const what = target === "all" ? "The colourway's colour" :
      f ? (owns ? `${Studio.FX_NAMES[fxKind(f)]}: its own colour` : partMode(target) === "off" ? "As Blizzard made it" :
           `${fxPart}' colour (pick Its own colour to change it)`) :
      owns ? `${Colour.PARTS.find(p => p[0] === target)[1]}: their own colour` :
      partMode(target) === "off" ? "As Blizzard made them" : "The colourway's colour (pick Their own colour to change it)";
    const painted = (way.paint || []).length;
    box.replaceChildren(tabs || "",
      el("div", {class: "cw-top"},
        el("div", {class: "cw-wheel-box" + (dim ? " dim" : "")}, wheel),
        el("div", {class: "cw-side"},
          el("label", {class: "cw-field"}, el("span", {}, "Name"), name),
          el("div", {class: "cw-swatch-row"}, ui.big, el("span", {class: "muted small"}, what)),
          ui.light, ui.dye, presets)),
      el("div", {class: "cw-parts-row"}, el("span", {class: "muted small"}, "Colours"), parts),
      fxRow || "",
      mode || "",
      painted ? el("div", {class: "muted small"}, `Painted: ${plural(painted, "stroke")} (the Paint tab), over the armor's colour`) : "");
    sync();
  };
  draw();
  box.refresh = () => { target = "all"; draw(); };
  // the preview's effects came in (a model loaded): listed
  box.effectsChanged = () => { if (tab === "colours") draw(); };
  box.dispose = () => { if (studio) { studio.dispose(); studio = null; } };
  return box;
}

// The Colour section of an item's or a set's panel. o: {what (its name), version (the version's name, "" for
// the default), show(way) (the preview takes it), entry(way) (the basket entry a colourway makes), saved() (this
// version's colourways in the basket), pb (the preview box: its effects and the Paint tab), store() (a piece of a
// collection of yours: {name, get(), put(way)} - its colourway is kept there, not in the basket - else null)}.
function colourSection(o) {
  const body = el("div", {class: "cw"});
  let way = null, editingKey = null;                // the colourway edited, and its basket entry's key when saved
  let editor = null;
  const drop = () => { if (editor) { editor.dispose(); editor = null; } if (o.pb) o.pb.editor = null; };
  const keyFor = e => e.store ? "store" : keyOf(e);
  const render = () => {
    drop();
    const store = o.store ? o.store() : null;
    const saved = store ? (store.get() ? [{store: true, colour: store.get()}] : []) : o.saved();
    const chips = saved.length ? el("div", {class: "cw-saved"}, el("span", {class: "muted small"}, store ? `In ${store.name}:` : "In your basket:"),
      saved.map(e => el("button", {class: "chip" + (editingKey === keyFor(e) ? " on" : ""), title: "Show it - and change it",
        onclick: () => { way = copyWay(e.colour); editingKey = keyFor(e); o.show(way); render(); }},
        el("i", {class: "cw-dot", style: `background:${Colour.css(e.colour.colour)}`}), e.colour.name || "Custom"))) : null;
    if (!way) {
      body.replaceChildren(chips || "", el("div", {class: "cw-start"},
        el("button", {class: "btn", onclick: () => { way = newWay(); editingKey = null; o.show(way); render(); }},
          store ? `Give it colours of its own in ${store.name}` : `Make a colourway of ${o.version() || "this look"}`),
        el("span", {class: "muted small"}, store ? "Its own colours, paint and effects - this piece only, in your collection." :
          "Your own colours for its armor, glows, particles and ribbons - and paint inside it - an extra version in game, " +
          "beside the one it's made from.")));
      return;
    }
    editor = colourEditor(way, w => o.show(w), {pb: o.pb, paint: (f, list) => o.pb && previewPaint(o.pb, way, f, list)});
    if (o.pb) o.pb.editor = editor;
    const add = () => {
      if (!(way.name || "").trim()) way.name = "Custom";
      if (store) {
        store.put(copyWay(way)); editingKey = "store";
        toast(`Saved ${way.name} in ${store.name}`); render();
        return;
      }
      const entry = o.entry(way);
      const k = keyOf(entry);
      if (editingKey && editingKey !== k) S.basket = S.basket.filter(e => keyOf(e) !== editingKey);
      const i = S.basket.findIndex(e => keyOf(e) === k);
      if (i >= 0) S.basket[i] = entry; else S.basket.push(entry);
      editingKey = k;
      saveBasket(); toast(i >= 0 ? `Saved ${entry.name}` : `Added ${entry.name}`); render();
    };
    const remove = () => {
      if (store) store.put(null);
      else { S.basket = S.basket.filter(e => keyOf(e) !== editingKey); saveBasket(); }
      toast(`Removed ${way.name || "the colourway"}`); way = null; editingKey = null; o.show(null); render();
    };
    const actions = el("div", {class: "cw-actions"},
      el("button", {class: "btn", onclick: add}, store ? (editingKey ? "Save" : `Save in ${store.name}`) : editingKey ? "Save the colourway" : "Add to basket"),
      editingKey && !store ? el("button", {class: "btn ghost", onclick: () => { way = {...copyWay(way), key: newWay().key}; editingKey = null; add(); }},
                                "Save as a new one") : null,
      editingKey ? el("button", {class: "btn ghost", onclick: remove}, "Remove it") : null,
      el("button", {class: "btn ghost", onclick: () => { way = null; editingKey = null; o.show(null); render(); }}, "Close"));
    body.replaceChildren(chips || "", el("div", {class: "muted small cw-for"}, (store ? `${o.what} in ${store.name}` : `A colourway of ${o.what}`) +
      (o.version() ? ` (${o.version()})` : "")), editor, actions);
  };
  render();
  // switched(): another version is shown - the colourway being made stays on it, a saved one is its old version's
  return Object.assign(section("Colours", body), {reset: () => { way = null; editingKey = null; render(); }, render,
                                                  switched: () => { if (editingKey) way = {...copyWay(way), key: newWay().key}; editingKey = null; render(); }});
}
