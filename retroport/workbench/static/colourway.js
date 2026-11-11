"use strict";
// Colourways: a player's own colours for a version of an item or a set (colour.js has the maths). The editor -
// a hue wheel drawn in the colours it gives, Brightness and Dye, named presets, and which parts take the
// colour (armor, glows, particles, ribbons: each the colourway's colour, its own, or as Blizzard made it) -
// recolours the 3D view as it changes. Saved, a colourway is a basket entry of its own (``colour``): Install
// makes it an extra item beside the version it was made from, and the client recolours it as the preview does.

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

// The editor. way: the colourway edited (changed in place); onChange(way): the preview follows it.
// Returns the element; ``refresh()`` redraws it for a colourway changed from outside.
function colourEditor(way, onChange) {
  let target = "all";                       // what the wheel edits: the colourway's colour, or a part's own
  const box = el("div", {class: "cw-editor"});
  const partMode = part => { const v = (way.parts || {})[part]; return v === "off" ? "off" : v && typeof v === "object" ? "own" : "same"; };
  const editing = () => target === "all" || partMode(target) !== "own" ? way.colour : way.parts[target];
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
      const k2 = part === "all" ? way.colour : Colour.partColour(way, part);
      dot.style.background = k2 ? Colour.css(k2) : "";
    }
  };
  const changed = () => { onChange(way); sync(); };
  const setColour = k => {
    if (target !== "all" && partMode(target) === "own") way.parts[target] = k; else way.colour = k;
    changed();
  };
  const wheel = colourWheel(176, () => editing(), setColour);
  const draw = () => {
    const k = editing();
    ui.dots = {all: el("i", {class: "cw-dot"})};
    const owns = target !== "all" && partMode(target) === "own";
    const parts = el("div", {class: "cw-parts", role: "group", "aria-label": "Parts"},
      el("button", {class: "chip" + (target === "all" ? " on" : ""), onclick: () => { target = "all"; draw(); }},
        ui.dots.all, "Everything"),
      Colour.PARTS.map(([part, label]) => {
        const m = partMode(part);
        ui.dots[part] = el("i", {class: "cw-dot"});
        return el("button", {class: "chip" + (target === part ? " on" : "") + (m === "off" ? " off" : ""),
                             title: m === "off" ? `${label}: as Blizzard made them` : m === "own" ? `${label}: their own colour` :
                                    `${label}: the colourway's colour`, onclick: () => { target = part; draw(); }},
          ui.dots[part], label);
      }));
    const mode = target === "all" ? null : el("div", {class: "cw-mode"},
      [["same", "The colourway's colour"], ["own", "Their own colour"], ["off", "As Blizzard made them"]].map(([m, label]) =>
        el("label", {class: "cw-radio"}, (() => {
          const r = el("input", {type: "radio", name: "cw-mode", checked: partMode(target) === m});
          r.addEventListener("change", () => {
            way.parts = way.parts || {};
            if (m === "same") delete way.parts[target];
            else way.parts[target] = m === "off" ? "off" : {...(Colour.partColour(way, target) || way.colour)};
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
    box.replaceChildren(
      el("div", {class: "cw-top"},
        el("div", {class: "cw-wheel-box" + (dim ? " dim" : "")}, wheel),
        el("div", {class: "cw-side"},
          el("label", {class: "cw-field"}, el("span", {}, "Name"), name),
          el("div", {class: "cw-swatch-row"}, ui.big,
            el("span", {class: "muted small"}, target === "all" ? "The colourway's colour" :
              owns ? `${Colour.PARTS.find(p => p[0] === target)[1]}: their own colour` :
              partMode(target) === "off" ? "As Blizzard made them" : "The colourway's colour (pick Their own colour to change it)")),
          ui.light, ui.dye, presets)),
      el("div", {class: "cw-parts-row"}, el("span", {class: "muted small"}, "Colours"), parts),
      mode);
    sync();
  };
  draw();
  box.refresh = () => { target = "all"; draw(); };
  return box;
}

// The Colour section of an item's or a set's panel. o: {what (its name), version (the version's name, "" for
// the default), current() (the colourway shown: null for none), show(way) (the preview takes it), entry(way)
// (the basket entry a colourway makes), saved() (this version's colourways in the basket)}.
function colourSection(o) {
  const body = el("div", {class: "cw"});
  let way = null, editingKey = null;                // the colourway edited, and its basket entry's key when saved
  const render = () => {
    const saved = o.saved();
    const chips = saved.length ? el("div", {class: "cw-saved"}, el("span", {class: "muted small"}, "In your basket:"),
      saved.map(e => el("button", {class: "chip" + (editingKey === keyOf(e) ? " on" : ""), title: "Show it - and change it",
        onclick: () => { way = copyWay(e.colour); editingKey = keyOf(e); o.show(way); render(); }},
        el("i", {class: "cw-dot", style: `background:${Colour.css(e.colour.colour)}`}), e.colour.name || "Custom"))) : null;
    if (!way) {
      body.replaceChildren(chips || "", el("div", {class: "cw-start"},
        el("button", {class: "btn", onclick: () => { way = newWay(); editingKey = null; o.show(way); render(); }},
          `Make a colourway of ${o.version() || "this look"}`),
        el("span", {class: "muted small"}, "Your own colours for its armor, glows, particles and ribbons - an extra version in game, beside the " +
                                            "one it's made from.")));
      return;
    }
    const editor = colourEditor(way, w => o.show(w));
    const add = () => {
      if (!(way.name || "").trim()) way.name = "Custom";
      const entry = o.entry(way);
      const k = keyOf(entry);
      if (editingKey && editingKey !== k) S.basket = S.basket.filter(e => keyOf(e) !== editingKey);
      const i = S.basket.findIndex(e => keyOf(e) === k);
      if (i >= 0) S.basket[i] = entry; else S.basket.push(entry);
      editingKey = k;
      saveBasket(); toast(i >= 0 ? `Saved ${entry.name}` : `Added ${entry.name}`); render();
    };
    const actions = el("div", {class: "cw-actions"},
      el("button", {class: "btn", onclick: add}, editingKey ? "Save the colourway" : "Add to basket"),
      editingKey ? el("button", {class: "btn ghost", onclick: () => { way = {...copyWay(way), key: newWay().key}; editingKey = null; add(); }},
                      "Save as a new one") : null,
      editingKey ? el("button", {class: "btn ghost", onclick: () => {
        S.basket = S.basket.filter(e => keyOf(e) !== editingKey); saveBasket();
        toast(`Removed ${way.name || "the colourway"}`); way = null; editingKey = null; o.show(null); render();
      }}, "Remove it") : null,
      el("button", {class: "btn ghost", onclick: () => { way = null; editingKey = null; o.show(null); render(); }}, "Close"));
    body.replaceChildren(chips || "", el("div", {class: "muted small cw-for"}, `A colourway of ${o.what}` +
      (o.version() ? ` (${o.version()})` : "")), editor, actions);
  };
  render();
  // switched(): another version is shown - the colourway being made stays on it, a saved one is its old version's
  return Object.assign(section("Colours", body), {reset: () => { way = null; editingKey = null; render(); }, render,
                                                  switched: () => { if (editingKey) way = {...copyWay(way), key: newWay().key}; editingKey = null; render(); }});
}
