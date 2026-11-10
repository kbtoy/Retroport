"use strict";
// The Stats step, between the basket and Install. Install makes every piece a level-1
// cosmetic copy; here each gets real stats. Item level, required level, quality and binding are set
// for every piece; armor type and the role the stats are for too, unless a piece sets its own;
// classes per piece. Stats are filled in by WotLK's own rules (wotlk.py's tables: the stat budget by
// item level and slot, real items' armor and durability, the weapon damage tables), split the way
// real WotLK items of the role split them - or copied from a WotLK item - and the tooltip shows the
// piece as the 3.3.5 client will, its model in 3D under it. Everything is saved as it changes
// (item-stats.json).

(() => {   // its own scope: nothing here may replace a name of app.js's

const SG = {pieces: [], edits: {global: {}, pieces: {}, sets: []}, opts: null, sel: null, timer: null,
            basketSets: [], loading: false, copyHits: []};
const QCOL = {0: "#9d9d9d", 1: "#ffffff", 2: "#1eff00", 3: "#0070dd", 4: "#a335ee", 5: "#ff8000", 6: "#e6cc80", 7: "#e6cc80"};
const INV_NAMES = {1: "Head", 2: "Neck", 3: "Shoulder", 4: "Shirt", 5: "Chest", 6: "Waist", 7: "Legs", 8: "Feet", 9: "Wrist",
                   10: "Hands", 11: "Finger", 12: "Trinket", 13: "One-Hand", 14: "Off Hand", 15: "Ranged", 16: "Back",
                   17: "Two-Hand", 19: "Tabard", 20: "Chest", 21: "Main Hand", 22: "Off Hand", 23: "Held In Off-hand",
                   25: "Thrown", 26: "Ranged", 28: "Relic"};
const WEAPON_NAMES = {0: "Axe", 1: "Axe", 2: "Bow", 3: "Gun", 4: "Mace", 5: "Mace", 6: "Polearm", 7: "Sword", 8: "Sword",
                      10: "Staff", 13: "Fist Weapon", 14: "Miscellaneous", 15: "Dagger", 16: "Thrown", 18: "Crossbow",
                      19: "Wand", 20: "Fishing Pole"};
const ARMOR_NAMES = {0: "Miscellaneous", 1: "Cloth", 2: "Leather", 3: "Mail", 4: "Plate", 6: "Shield"};
const CLASS_COLORS = {1: "#C79C6E", 2: "#F58CBA", 3: "#ABD473", 4: "#FFF569", 5: "#FFFFFF", 6: "#C41F3B", 7: "#0070DE",
                      8: "#69CCF0", 9: "#9482C9", 11: "#FF7D0A"};
const SOCKET_COLORS = {1: "#c0c0c0", 2: "#d62828", 4: "#e8c331", 8: "#3a7bd5", 14: "#b9b9b9"};
const BASE_TEXT = {0: "Mana", 1: "Health", 3: "Agility", 4: "Strength", 5: "Intellect", 6: "Spirit", 7: "Stamina"};
const EQUIP_TEXT = {
  12: "Increases defense rating by %d.", 13: "Increases your dodge rating by %d.", 14: "Increases your parry rating by %d.",
  15: "Increases your shield block rating by %d.", 16: "Improves melee hit rating by %d.", 17: "Improves ranged hit rating by %d.",
  18: "Improves spell hit rating by %d.", 19: "Improves melee critical strike rating by %d.",
  20: "Improves ranged critical strike rating by %d.", 21: "Improves spell critical strike rating by %d.",
  28: "Improves melee haste rating by %d.", 29: "Improves ranged haste rating by %d.", 30: "Improves spell haste rating by %d.",
  31: "Increases your hit rating by %d.", 32: "Increases your critical strike rating by %d.",
  35: "Increases your resilience rating by %d.", 36: "Increases your haste rating by %d.",
  37: "Increases your expertise rating by %d.", 38: "Increases attack power by %d.", 39: "Increases ranged attack power by %d.",
  43: "Restores %d mana per 5 sec.", 44: "Increases your armor penetration rating by %d.", 45: "Increases spell power by %d.",
  46: "Restores %d health per 5 sec.", 47: "Increases spell penetration by %d.", 48: "Increases the block value of your shield by %d."};
// How real WotLK items of a role spend their budget (measured on ICC gear): the main stats' shares,
// then two secondary ratings - the pair changes from piece to piece, as on a real set.
const PROFILES = {
  str: {label: "Strength (melee DPS)", main: [[4, .39], [7, .25]], sec: [[32, 44], [32, 36], [31, 32], [36, 44], [37, 32]], f: [.20, .16]},
  tank: {label: "Tank", main: [[4, .39], [7, .34]], sec: [[12, 13], [14, 13], [12, 14], [37, 12]], f: [.15, .12]},
  agi: {label: "Agility (melee)", main: [[3, .34], [7, .18], [38, .15]], sec: [[32, 44], [32, 36], [31, 32], [36, 44]], f: [.18, .15]},
  hunter: {label: "Agility (ranged)", main: [[3, .33], [7, .13], [5, .13], [38, .14]], sec: [[32, 44], [31, 32], [36, 32]], f: [.16, .11]},
  caster: {label: "Spell power (damage)", main: [[45, .30], [5, .23], [7, .13]], sec: [[36, 32], [31, 32], [32, 36], [36, 31]], f: [.19, .15]},
  healer: {label: "Spell power (healing)", main: [[45, .30], [5, .23], [7, .13]], sec: [[6, 32], [36, 32], [43, 36], [6, 36]], f: [.17, .17]},
};
const DEFAULT_DELAY = {0: 2600, 1: 3600, 2: 2900, 3: 2800, 4: 2600, 5: 3600, 6: 3600, 7: 2600, 8: 3600, 10: 2900, 13: 2600,
                       15: 1800, 16: 1600, 18: 3000, 19: 1800};
const ARMOUR_SLOTS = [1, 3, 5, 6, 7, 8, 9, 10, 20];

// -- loading and saving ------------------------------------------------------------------------
async function loadStats() {
  if (SG.loading) return;
  SG.loading = true;
  $("#stats-editor").replaceChildren(el("div", {class: "muted"}, "Loading WotLK's item numbers… (the first time downloads them once)"));
  try {
    const [got, opts] = await Promise.all([api("/api/stats"), SG.opts ? SG.opts : api("/api/stats/options")]);
    SG.opts = opts;
    SG.pieces = got.pieces;
    SG.basketSets = got.basket_sets;
    SG.edits = {global: got.edits.global || {}, pieces: got.edits.pieces || {}, sets: got.edits.sets || []};
    if (tidy(SG.edits)) saveStats();
    if (!SG.pieces.some(p => p.display === SG.sel)) SG.sel = SG.pieces.length ? SG.pieces[0].display : null;
    renderStats();
  } catch (e) {
    $("#stats-editor").replaceChildren(el("div", {class: "warnline"}, e.message));
  } finally { SG.loading = false; }
}
function saveStats() {
  clearTimeout(SG.timer);
  SG.timer = setTimeout(async () => {
    try { await post("/api/stats", SG.edits); } catch (e) { toast("Could not save the stats: " + e.message); }
    updateStatsBadge();
  }, 400);
}
// Saved by an earlier version: classes for every piece (now each piece's own - the pieces that had
// none of their own get it), and a piece's own item level, required level, quality and binding (now
// set for every piece only). True when anything changed.
function tidy(edits) {
  let changed = false;
  const g = edits.global;
  if (isSet(g.classes)) {
    for (const p of SG.pieces) { const e = own(p.display); if (!isSet(e.classes)) e.classes = g.classes; }
    delete g.classes; changed = true;
  }
  for (const e of Object.values(edits.pieces))
    for (const f of GLOBAL_ONLY) if (f in e) { delete e[f]; changed = true; }
  return changed;
}
const GLOBAL_ONLY = ["ilvl", "req", "quality", "bonding"];
const piece = d => SG.pieces.find(p => p.display === d);
const own = d => SG.edits.pieces[d] || (SG.edits.pieces[d] = {});
const isSet = v => v !== undefined && v !== null && v !== "";
function eff(p, field, dflt) {
  const mine = (SG.edits.pieces[p.display] || {})[field];
  if (isSet(mine)) return mine;
  const g = SG.edits.global[field];
  return isSet(g) ? g : dflt;
}
const hasStats = p => { const e = SG.edits.pieces[p.display] || {}; return !!((e.stats && e.stats.length) || e.armor || e.dmg_max); };
const touched = p => hasStats(p) || ["ilvl", "req", "quality", "classes", "armor_type", "bonding"].some(f => isSet(eff(p, f)));
function updateStatsBadge() {
  const missing = SG.pieces.filter(p => !touched(p)).length;
  $("#stats-state").textContent = missing || "";
  $("#stats-state").hidden = !missing;
}

// -- what a piece is ---------------------------------------------------------------------------
const isArmorPiece = p => p.cls === 4 && [1, 2, 3, 4].includes(p.sub) && p.inv !== 16;
const subOf = p => isArmorPiece(p) ? +eff(p, "armor_type", p.sub) : p.sub;
const qualityOf = p => +eff(p, "quality", p.quality ?? 4);
const isWeapon = p => p.cls === 2;
function typeName(p) {
  if (isWeapon(p)) return WEAPON_NAMES[p.sub] || "Weapon";
  if (p.inv === 16 || p.inv === 23) return "";
  return ARMOR_NAMES[subOf(p)] || "";
}
const CLASS_PROFILE = {1: "str", 2: "str", 3: "hunter", 4: "agi", 5: "caster", 6: "str", 7: "caster", 8: "caster", 9: "caster", 11: "agi"};
function defaultProfile(p, depth = 0) {
  const mask = +eff(p, "classes", -1);                 // one class: its role
  if (mask > 0) {
    const ids = Object.keys(SG.opts.classes).filter(id => mask & (1 << (id - 1)));
    if (ids.length === 1) return CLASS_PROFILE[ids[0]];
  }
  const sub = subOf(p);
  if (p.cls === 4) {
    if (sub === 6) return "tank";
    if (p.inv === 23) return "caster";
    if (p.inv === 16 && !depth) {                       // a cloak: the role of the armor it comes with
      const mates = SG.pieces.filter(o => o !== p && o.groups[0] === p.groups[0] && isArmorPiece(o));
      const votes = {};
      for (const o of mates) { const r = defaultProfile(o, 1); votes[r] = (votes[r] || 0) + 1; }
      return Object.entries(votes).sort((a, b) => b[1] - a[1])[0]?.[0] || "str";
    }
    return {1: "caster", 2: "agi", 3: "hunter", 4: "str"}[sub] || "str";
  }
  if ([10, 19].includes(p.sub)) return "caster";
  if ([2, 3, 18, 16].includes(p.sub)) return "hunter";
  if ([15, 13].includes(p.sub)) return "agi";
  return "str";
}
const profileOf = p => eff(p, "profile", "") || defaultProfile(p);

// -- WotLK's numbers ---------------------------------------------------------------------------
function slotGroup(inv) {
  if ([1, 5, 7, 17, 20].includes(inv)) return 0;
  if ([3, 6, 8, 10, 12].includes(inv)) return 1;
  if ([2, 9, 11, 14, 16, 23].includes(inv)) return 2;
  if ([13, 21, 22].includes(inv)) return 3;
  return 4;
}
function budget(ilvl, q, group) {
  const r = SG.opts.tables.rpp[ilvl];
  if (!r) return 0;
  const base = q >= 4 ? 0 : q === 3 ? 5 : 10;
  return Math.round(r[base + group] * (q <= 1 ? 0.7 : 1));
}
const cost = t => (SG.opts.stats[t] || [0, 0, 1])[2] || 1;
function autoStats(p, k) {
  const ilvl = +eff(p, "ilvl", 0), q = qualityOf(p), prof = PROFILES[profileOf(p)] || PROFILES.str;
  const B = budget(ilvl, q, slotGroup(p.inv));
  if (!B) return [];
  const total = Math.pow(B * 1.06, 1.5);
  const pair = prof.sec[k % prof.sec.length];
  const parts = [...prof.main, [pair[0], prof.f[0]], [pair[1], prof.f[1]]];
  const out = new Map();
  for (const [t, f] of parts) {
    const v = Math.round(Math.pow(f * total, 2 / 3) / cost(t));
    if (v > 0) out.set(t, (out.get(t) || 0) + v);
  }
  // a caster's weapon carries its power as spell power (Frozen Bonespike, Nibelung: 741 at 264)
  if (isWeapon(p) && ["caster", "healer"].includes(profileOf(p)) && [13, 17, 21].includes(p.inv))
    out.set(45, Math.round(2.41 * budget(ilvl, q, 0)));
  return [...out.entries()];
}
function curveAt(curve, ilvl) {
  if (!curve || !curve.length || !ilvl) return 0;
  if (ilvl <= curve[0][0]) return Math.round(curve[0][1] * ilvl / curve[0][0]);
  for (let i = 1; i < curve.length; i++) {
    const [l0, v0] = curve[i - 1], [l1, v1] = curve[i];
    if (ilvl <= l1) return Math.round(v0 + (v1 - v0) * (ilvl - l0) / (l1 - l0));
  }
  const [lA, vA] = curve.length > 1 ? curve[curve.length - 2] : [0, 0], [lB, vB] = curve[curve.length - 1];
  return Math.round(vB + (lB > lA ? (vB - vA) / (lB - lA) : vB / lB) * (ilvl - lB));
}
function lookup(table, p, sub, q) {
  for (const qq of [q, 4, 3, 2, 1])
    for (const inv of [p.inv, {5: 20, 20: 5, 21: 13, 22: 13, 13: 21, 26: 15, 15: 26}[p.inv]].filter(Boolean)) {
      const v = table[`${p.cls}:${sub}:${inv}:${qq}`];
      if (v !== undefined && (!Array.isArray(v) || v.length)) return v;
    }
  return null;
}
function autoNumbers(p) {
  const ilvl = +eff(p, "ilvl", 0), q = qualityOf(p), sub = subOf(p), t = SG.opts.tables, out = {};
  if (p.cls === 4) out.armor = curveAt(lookup(t.armor, p, sub, q), ilvl);
  out.durability = lookup(t.durability, p, sub, q) ?? 0;
  out.sell = curveAt(lookup(t.price, p, sub, q), ilvl);
  if (isWeapon(p)) {
    const caster = ["caster", "healer"].includes(profileOf(p));
    const name = p.inv === 17 ? (caster ? "ItemDamageTwoHandCaster" : "ItemDamageTwoHand") :
      [13, 21, 22].includes(p.inv) ? (caster ? "ItemDamageOneHandCaster" : "ItemDamageOneHand") :
      p.sub === 19 ? "ItemDamageWand" : "ItemDamageRanged";
    const row = (t.dps[name] || {})[ilvl];
    const dps = row ? row[Math.min(q, 6)] : 0;
    const delay = lookup(t.delay, p, p.sub, q) || DEFAULT_DELAY[p.sub] || 2600;
    const spread = caster || [2, 3, 18, 19, 16].includes(p.sub) ? 0.3 : 0.2;
    const avg = dps * delay / 1000;
    Object.assign(out, {dmg_min: Math.round(avg * (1 - spread)), dmg_max: Math.round(avg * (1 + spread)), delay});
  }
  return out;
}
// fill in a piece's stats and numbers by the rules (``k``: its place, to vary the secondary ratings)
function fillPiece(p, k) {
  if (!+eff(p, "ilvl", 0)) return false;
  Object.assign(own(p.display), {stats: autoStats(p, k)}, autoNumbers(p), {stats_mode: "auto"});
  return true;
}
// a piece whose stats were filled in follows its level, quality, type and role as they change
function refreshAuto() {
  SG.pieces.forEach((p, k) => { if ((SG.edits.pieces[p.display] || {}).stats_mode === "auto") fillPiece(p, k); });
}
const manual = d => { own(d).stats_mode = "manual"; };

// -- the page ----------------------------------------------------------------------------------
function renderStats() {
  keepFocus(() => { renderBulk(); renderList(); renderEditor(); renderTooltip(); renderSets(); updateStatsBadge(); });
  renderPreview();
}
// A redraw replaces the fields: the one being typed in gets the focus and its cursor back (found by its
// place among its panel's fields - typing never changes what comes before it), so 277 is typed in one go.
function keepFocus(draw) {
  const a = document.activeElement;
  const panel = a && a.closest ? a.closest("#stats-bulk, #stats-editor, #stats-sets") : null;
  const fields = el => [...el.querySelectorAll("input, select, textarea")];
  const at = panel ? fields(panel).indexOf(a) : -1;
  let from = null, to = null;
  try { from = a.selectionStart; to = a.selectionEnd; } catch (e) { /* a select */ }
  draw();
  if (at < 0) return;
  const again = fields(document.getElementById(panel.id))[at];
  if (!again) return;
  again.focus();
  try { if (from !== null) again.setSelectionRange(from, to); } catch (e) { /* a select */ }
}
function sel(attrs, options, value, onchange) {
  const s = el("select", attrs, options.map(([v, label]) => el("option", {value: v, selected: String(v) === String(value ?? "")}, label)));
  s.addEventListener("change", () => onchange(s.value));
  return s;
}
// a number field: plain text (a number input can't give its cursor back), digits only
// what AzerothCore's item_template columns hold (a value beyond one and the server refuses the piece)
const INT_MAX = 2147483647, UINT_MAX = 4294967295, SELL_MAX = 4294967295;
function num(attrs, value, onchange) {
  const decimal = attrs.step && attrs.step < 1;
  const {step, min, max, ...rest} = attrs;
  const i = el("input", {type: "text", inputmode: decimal ? "decimal" : "numeric", autocomplete: "off", ...rest,
                         class: ((rest.class || "") + " num").trim(), value: isSet(value) ? value : ""});
  i.addEventListener("input", () => {
    const clean = i.value.replace(decimal ? /[^0-9.]/g : /[^0-9]/g, "");
    if (clean !== i.value) { const c = i.selectionStart - (i.value.length - clean.length); i.value = clean; i.setSelectionRange(c, c); }
    const v = clean === "" || clean === "." ? "" : +clean;
    onchange(max !== undefined && v !== "" ? Math.min(v, max) : v);
  });
  return i;
}
function renderBulk() {
  const g = SG.edits.global, set = (f, v) => { g[f] = v; refreshAuto(); saveStats(); renderStats(); };
  const field = (label, control, hint) => el("label", {class: "bfield", title: hint || ""}, el("span", {}, label), control);
  $("#stats-bulk").replaceChildren(
    el("h3", {}, "For every piece ", el("span", {class: "muted"}, "- armor type and stats a piece can still set for itself")),
    el("div", {class: "bulk-row"},
      field("Armor type", sel({}, [["", "Each piece's own"], ...Object.entries(SG.opts.armour_types)], g.armor_type, v => set("armor_type", v ? +v : "")),
            "Cloth, leather, mail or plate for every armor piece (not cloaks or shields)"),
      field("Item level", num({placeholder: "not set", max: 300}, g.ilvl, v => set("ilvl", v)),
            "What WotLK's numbers are filled in for"),
      field("Required level", num({placeholder: "none", max: 80}, g.req, v => set("req", v))),
      field("Quality", sel({}, [["", "Each piece's own"], ...Object.entries(SG.opts.qualities).filter(([q]) => q <= 5)], g.quality,
                           v => set("quality", v === "" ? "" : +v))),
      field("Binding", sel({}, [["", "No binding"], ...Object.entries(SG.opts.bonding).filter(([b]) => +b)], g.bonding,
                           v => set("bonding", v === "" ? "" : +v))),
      field("Stats for", sel({}, [["", "Each piece's type"], ...Object.entries(PROFILES).map(([k, x]) => [k, x.label])], g.profile,
                             v => set("profile", v)), "The role the stats are chosen for")),
    el("div", {class: "bulk-actions"},
      el("button", {class: "btn", onclick: () => {
        const done = SG.pieces.filter((p, k) => fillPiece(p, k)).length, left = SG.pieces.length - done;
        saveStats(); renderStats();
        toast(left ? "Set the item level first" : `Filled in the stats of ${done} piece${done === 1 ? "" : "s"}`);
      }}, "Fill in stats for every piece"),
      el("span", {class: "muted small"}, "WotLK's budget for the item level, quality and slot, split the way real WotLK items of that role split it; armor, damage and durability as real items have them.")));
}
function renderList() {
  if (!SG.pieces.length) {
    $("#stats-list").replaceChildren(el("div", {class: "empty"}, "The basket is empty. To change the stats of " +
      "something in your game, put it in the basket again (Basket > History)."));
    return;
  }
  const groups = new Map();
  for (const p of SG.pieces) {
    const g = p.groups[0];
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(p);
  }
  $("#stats-list").replaceChildren(...[...groups.entries()].map(([g, ps]) => el("div", {class: "sgroup"},
    el("h4", {}, g, ps[0].in_game ? el("span", {class: "badge dim", title: "Installed already: Install again to give the game " +
                                             "what you change here"}, "in your game") : null), ps.map(p => {
      const lvl = +eff(p, "ilvl", 0);
      return el("div", {class: "srow-p" + (p.display === SG.sel ? " on" : ""), onclick: () => { SG.sel = p.display; renderStats(); }},
        icon(p.icon, qualityOf(p), "sm", p.source),
        el("div", {class: "meta"},
          el("div", {class: "pname", style: `color:${QCOL[qualityOf(p)]}`}, (SG.edits.pieces[p.display] || {}).name || p.name),
          el("div", {class: "sub muted"}, [INV_NAMES[p.inv], typeName(p)].filter(Boolean).join(" · "))),
        hasStats(p) ? el("span", {class: "badge dim"}, lvl ? `ilvl ${lvl}` : "stats") :
                      el("span", {class: "badge warn", title: "A level-1 cosmetic copy until it gets stats"}, "no stats"));
    }))));
}
function renderEditor() {
  const p = piece(SG.sel), box = $("#stats-editor");
  if (!p) { box.replaceChildren(el("div", {class: "muted"}, "Pick a piece.")); return; }
  const e = own(p.display), g = SG.edits.global;
  const ch = (f, v, auto = true) => { e[f] = v; if (auto && e.stats_mode === "auto") fillPiece(p, SG.pieces.indexOf(p)); saveStats(); renderStats(); };
  const row = (...kids) => el("div", {class: "erow"}, ...kids);
  const field = (label, control) => el("label", {class: "efield"}, el("span", {}, label), control);

  // classes: all of them, or the ones picked
  const classChips = el("div", {class: "class-chips"},
    el("button", {class: "chip" + (!isSet(e.classes) || e.classes === -1 ? " on" : ""), onclick: () => ch("classes", "", false)}, "All classes"),
    Object.entries(SG.opts.classes).map(([id, name]) => {
      const bit = 1 << (id - 1), on = isSet(e.classes) && e.classes !== -1 && (e.classes & bit);
      return el("button", {class: "chip cls" + (on ? " on" : ""), style: on ? `color:${CLASS_COLORS[id]};border-color:${CLASS_COLORS[id]}` : "",
        onclick: () => {
          let m = isSet(e.classes) && e.classes !== -1 ? e.classes : 0;
          m ^= bit;
          ch("classes", m || "", false);
        }}, name);
    }));

  // stats rows
  const statsRows = (e.stats || []).map(([t, v], i) => el("div", {class: "statrow"},
    sel({}, Object.entries(SG.opts.stats).map(([id, s]) => [id, s[0]]), t, nv => { e.stats[i][0] = +nv; manual(p.display); saveStats(); renderStats(); }),
    num({max: INT_MAX}, v, nv => { e.stats[i][1] = +nv || 0; manual(p.display); saveStats(); renderTooltip(); renderList(); }),
    el("button", {class: "remove", title: "Remove", onclick: () => { e.stats.splice(i, 1); manual(p.display); saveStats(); renderStats(); }}, "×")));
  const addStat = el("button", {class: "btn ghost small-btn", onclick: () => {
    (e.stats = e.stats || []).push([7, 0]); manual(p.display); saveStats(); renderStats(); }}, "+ Add a stat");

  const filled = e.stats_mode === "auto";
  const statsHead = [el("div", {class: "stats-head"},
    el("span", {}, "Fill in this piece's stats for"),
    sel({title: "The role its stats are chosen for"}, Object.entries(PROFILES).map(([k, x]) => [k, x.label]), profileOf(p),
        v => ch("profile", v)),
    el("button", {class: "btn small-btn", onclick: () => {
      if (!fillPiece(p, SG.pieces.indexOf(p))) return toast("Set the item level first (For every piece, above)");
      saveStats(); renderStats(); }}, filled ? "Fill in again" : "Fill in"),
    el("button", {class: "btn ghost small-btn", onclick: () => { SG.copyOpen = !SG.copyOpen; renderEditor(); }}, "Copy a WotLK item…")),
    el("div", {class: "muted small"}, filled ? `Filled in for ${PROFILES[profileOf(p)].label}, and kept so as the piece changes` :
       e.stats_mode === "manual" ? "Your own numbers" : "None yet")];

  const copyBox = SG.copyOpen ? copyPanel(p) : null;
  const weapon = isWeapon(p) ? row(
    field("Damage", el("span", {class: "pair"}, num({max: INT_MAX}, e.dmg_min, v => { e.dmg_min = v; manual(p.display); saveStats(); renderTooltip(); }),
      " - ", num({max: INT_MAX}, e.dmg_max, v => { e.dmg_max = v; manual(p.display); saveStats(); renderTooltip(); }))),
    field("Speed", num({step: 0.1, min: 0.5, max: 65.5}, e.delay ? +(e.delay / 1000).toFixed(2) : "", v => { e.delay = v ? Math.round(v * 1000) : ""; manual(p.display); saveStats(); renderTooltip(); })),
    el("span", {class: "muted small dps"}, e.dmg_max && e.delay ? `${(((+e.dmg_min || 0) + (+e.dmg_max)) / 2 / (e.delay / 1000)).toFixed(1)} damage per second` : "")) : null;
  const sockets = [0, 1, 2].map(k => sel({}, [["0", "No socket"], ...Object.entries(SG.opts.sockets).map(([c, n]) => [c, n + " socket"])],
    (e.sockets || [])[k] || 0, v => { const s = (e.sockets || []).slice(); s[k] = +v; e.sockets = s.filter(Boolean); saveStats(); renderStats(); }));
  const bonusSel = sel({disabled: !(e.sockets || []).length}, [["0", "No socket bonus"], ...SG.opts.socket_bonuses.map(b => [b.id, b.name])],
    e.socket_bonus || 0, v => { e.socket_bonus = +v; saveStats(); renderTooltip(); });
  if (+e.sell > SELL_MAX) e.sell = SELL_MAX;
  const gold = Math.floor((e.sell || 0) / 10000), silver = Math.floor(((e.sell || 0) % 10000) / 100), copper = (e.sell || 0) % 100;
  const sellIn = (val, mul) => num({class: "coin-in", max: mul === "g" ? Math.floor(SELL_MAX / 10000) : 99}, val, v => {
    const parts = {g: gold, s: silver, c: copper};
    parts[mul] = +v || 0;
    e.sell = Math.min(parts.g * 10000 + parts.s * 100 + parts.c, SELL_MAX); saveStats(); renderTooltip();
  });

  box.replaceChildren(
    el("div", {class: "ehead"}, icon(p.icon, qualityOf(p), "", p.source),
      el("div", {class: "meta"},
        (() => { const i = el("input", {class: "ename", value: e.name || "", placeholder: p.name, style: `color:${QCOL[qualityOf(p)]}`});
                 i.addEventListener("input", () => { e.name = i.value; saveStats(); renderTooltip(); renderList(); }); return i; })(),
        el("div", {class: "sub muted"}, [INV_NAMES[p.inv], typeName(p), p.groups.join(", ")].filter(Boolean).join(" · ")))),
    row(isArmorPiece(p) ? field("Armor type", sel({}, [["", `For every piece (${ARMOR_NAMES[isSet(g.armor_type) ? g.armor_type : p.sub]})`],
          ...Object.entries(SG.opts.armour_types)], e.armor_type, v => ch("armor_type", v ? +v : ""))) : null,
        el("label", {class: "check"}, (() => { const c = el("input", {type: "checkbox", checked: !!e.unique});
          c.addEventListener("change", () => { e.unique = c.checked; saveStats(); renderTooltip(); }); return c; })(), " Unique")),
    el("div", {class: "esec"}, el("h4", {}, "Classes"), classChips),
    el("div", {class: "esec"}, el("h4", {}, "Stats"), ...statsHead, copyBox, el("div", {class: "statrows"}, statsRows), addStat),
    el("div", {class: "esec"}, el("h4", {}, isWeapon(p) ? "Weapon" : "Armor"),
      p.cls === 4 ? row(field("Armor", num({max: UINT_MAX}, e.armor, v => { e.armor = v; manual(p.display); saveStats(); renderTooltip(); })),
                        subOf(p) === 6 ? field("Block", num({max: UINT_MAX}, e.block, v => { e.block = v; saveStats(); renderTooltip(); })) : null) : null,
      weapon),
    el("div", {class: "esec"}, el("h4", {}, "Sockets"), row(...sockets), row(field("Socket bonus", bonusSel))),
    el("div", {class: "esec"}, el("h4", {}, "More"),
      row(field("Durability", num({max: 65535}, e.durability, v => { e.durability = v; saveStats(); renderTooltip(); })),
          field("Sell price", el("span", {class: "pair"}, sellIn(gold, "g"), el("span", {class: "coin g"}), sellIn(silver, "s"),
                                 el("span", {class: "coin s"}), sellIn(copper, "c"), el("span", {class: "coin c"})))),
      row(field("Description", (() => { const i = el("input", {value: e.description || "", placeholder: "the yellow line at the bottom"});
        i.addEventListener("input", () => { e.description = i.value; saveStats(); renderTooltip(); }); return i; })()))));
}

// copy a real WotLK item's numbers onto the piece
function copyPanel(p) {
  const results = el("div", {class: "copy-results"});
  const show = hits => results.replaceChildren(...(hits.length ? hits.map(r => el("div", {class: "copy-hit", onclick: () => {
    const e = own(p.display);
    Object.assign(e, {stats: r.stats.map(x => [...x]), durability: r.durability, sell: r.sell, sockets: r.sockets.slice(),
      socket_bonus: r.socket_bonus, stats_mode: "manual", copied_from: r.name});
    if (p.cls === 4) e.armor = r.cls === 4 && r.sub === subOf(p) ? r.armor : autoNumbers(p).armor;
    if (isWeapon(p) && r.dmg_max) Object.assign(e, {dmg_min: r.dmg_min, dmg_max: r.dmg_max, delay: r.delay});
    SG.copyOpen = false; saveStats(); renderStats(); toast(`Copied ${r.name}`);
  }},
    el("span", {class: "pname", style: `color:${QCOL[r.quality]}`}, r.name),
    el("span", {class: "muted small"}, ` ${r.ilvl} · ${[INV_NAMES[r.inv], r.cls === 2 ? WEAPON_NAMES[r.sub] : ARMOR_NAMES[r.sub]].filter(Boolean).join(" ")} · `,
       r.stats.map(([t, v]) => `${v} ${(SG.opts.stats[t] || ["?"])[0]}`).join(", ")))) :
    [el("div", {class: "muted small"}, "Nothing matches.")]));
  const q = el("input", {type: "search", placeholder: "Search WotLK items of this slot by name, e.g. Scourgelord", spellcheck: "false"});
  const run = debounce(async () => {
    try { show(await api("/api/stats/reference", {q: q.value, inv: p.inv, cls: p.cls, sub: subOf(p)})); }
    catch (err) { results.replaceChildren(el("div", {class: "warnline"}, err.message)); }
  }, 250);
  q.addEventListener("input", run);
  setTimeout(() => { q.focus(); run(); }, 0);
  return el("div", {class: "copy-panel"}, q, results);
}

// -- the tooltip, as the 3.3.5 client draws it -------------------------------------------------
function renderTooltip() {
  const p = piece(SG.sel), tip = $("#stats-tooltip");
  if (!p) { tip.replaceChildren(); return; }
  const e = SG.edits.pieces[p.display] || {}, q = qualityOf(p), L = [];
  const line = (text, cls = "", right = null) => L.push(el("div", {class: "tl " + cls}, el("span", {}, text), right ? el("span", {}, right) : null));
  line(e.name || p.name, "name");
  L[L.length - 1].style.color = QCOL[q];
  const bond = +eff(p, "bonding", 0);
  if (bond) line(SG.opts.bonding[bond]);
  if (e.unique) line("Unique");
  line(INV_NAMES[p.inv] || "", "", typeName(p) || null);
  if (isWeapon(p) && e.dmg_max) {
    line(`${e.dmg_min || 0} - ${e.dmg_max} Damage`, "", `Speed ${((e.delay || 2000) / 1000).toFixed(2)}`);
    line(`(${(((+e.dmg_min || 0) + (+e.dmg_max)) / 2 / ((e.delay || 2000) / 1000)).toFixed(1)} damage per second)`);
  }
  if (+e.armor) line(`${e.armor} Armor`);
  if (+e.block) line(`${e.block} Block`);
  const stats = (e.stats || []).filter(([, v]) => +v);
  for (const [t, v] of stats) if (t in BASE_TEXT) line(`${v > 0 ? "+" : ""}${v} ${BASE_TEXT[t]}`);
  for (const c of e.sockets || []) L.push(el("div", {class: "tl socket"}, el("i", {style: `background:${SOCKET_COLORS[c]}`}),
                                             `${SG.opts.sockets[c]} Socket`));
  if ((e.sockets || []).length && e.socket_bonus) {
    const b = SG.opts.socket_bonuses.find(x => x.id === +e.socket_bonus);
    line(`Socket Bonus: ${b ? b.name : e.socket_bonus}`, "grey");
  }
  if (+e.durability) line(`Durability ${e.durability} / ${e.durability}`);
  const mask = +eff(p, "classes", -1);
  if (mask > 0 && (mask & 1535) !== 1535)
    L.push(el("div", {class: "tl"}, el("span", {}, "Classes: ", ...Object.entries(SG.opts.classes).filter(([id]) => mask & (1 << (id - 1)))
      .flatMap(([id, n], k) => [k ? ", " : "", el("span", {style: `color:${CLASS_COLORS[id]}`}, n)]))));
  const req = +eff(p, "req", 0);
  if (req) line(`Requires Level ${req}`);
  for (const [t, v] of stats) if (!(t in BASE_TEXT)) line("Equip: " + (EQUIP_TEXT[t] || `${(SG.opts.stats[t] || ["?"])[0]} %d.`).replace("%d", v), "green");
  const set = SG.edits.sets.find(s => (s.pieces || []).includes(p.display));
  if (set) {
    L.push(el("div", {class: "tl gap"}));
    line(`${set.name || "Item set"} (0/${set.pieces.length})`, "setname");
    for (const d of set.pieces) { const sp = piece(d); line(sp ? ((SG.edits.pieces[d] || {}).name || sp.name) : `Look ${d}`, "grey indent"); }
    if ((set.bonuses || []).length) L.push(el("div", {class: "tl gap"}));
    for (const [n, spell] of [...(set.bonuses || [])].sort((a, b) => a[0] - b[0])) {
      const b = SG.opts.bonuses.find(x => x.spell === +spell) || SG.spellCache?.[spell];
      line(`(${n}) Set: ${b ? b.text : "spell " + spell}`, "grey");
    }
  }
  if (e.description) line(`"${e.description}"`, "desc");
  if (+e.sell) {
    const s = +e.sell;
    L.push(el("div", {class: "tl"}, el("span", {}, "Sell Price: ",
      Math.floor(s / 10000) ? [String(Math.floor(s / 10000)), el("i", {class: "coin g"}), " "] : "",
      Math.floor((s % 10000) / 100) ? [String(Math.floor((s % 10000) / 100)), el("i", {class: "coin s"}), " "] : "",
      s % 100 ? [String(s % 100), el("i", {class: "coin c"})] : "")));
  }
  tip.replaceChildren(...L);
  const lvl = +eff(p, "ilvl", 0);
  $("#stats-entry").textContent = [lvl ? `Item level ${lvl} (the 3.3.5 tooltip doesn't show it)` : "No item level yet - a level-1 cosmetic copy",
    p.entry ? `in game: item ${p.entry}` : "", e.copied_from ? `stats from ${e.copied_from}` : ""].filter(Boolean).join(" · ");
}

// -- the piece in 3D, under its tooltip ---------------------------------------------------------
// The workbench's one viewer: it comes here from the item panel (and goes back when one opens).
function renderPreview() {
  const box = $("#stats-preview"), p = piece(SG.sel);
  if (!p || typeof previewBox !== "function") { box.replaceChildren(); SG.pb = null; return; }
  if (!SG.pb || !box.contains(SG.pb.box) || (SG.pb.v && !SG.pb.box.contains(SG.pb.v.canvas))) {
    SG.pb = previewBox("stats-pv");
    box.replaceChildren(SG.pb.box);
    SG.shown = null;
  }
  if (!SG.pb.v || SG.shown === p.display) return;
  SG.shown = p.display;
  loadDisplay(SG.pb, p.display, p.inv, p.source);
}

// -- item sets ---------------------------------------------------------------------------------
function renderSets() {
  const box = $("#stats-sets");
  if (!SG.edits.sets.length) {
    box.replaceChildren(el("div", {class: "muted small"}, "No item sets yet."));
    return;
  }
  box.replaceChildren(...SG.edits.sets.map((s, si) => {
    const name = el("input", {class: "set-name", value: s.name || "", placeholder: "Set name"});
    name.addEventListener("input", () => { s.name = name.value; saveStats(); renderTooltip(); });
    const others = SG.pieces.filter(p => !(s.pieces || []).includes(p.display));
    const add = sel({}, [["", "+ Add a piece"], ...others.map(p => [p.display, `${p.name} (${INV_NAMES[p.inv]})`])], "",
                    v => { if (v) { s.pieces.push(v); saveStats(); renderStats(); } });
    const bonuses = (s.bonuses || []).map((b, bi) => el("div", {class: "bonus-row"},
      sel({title: "Pieces needed"}, [1, 2, 3, 4, 5, 6, 7, 8].map(n => [n, `(${n}) pieces`]), b[0], v => { b[0] = +v; saveStats(); renderTooltip(); }),
      bonusPicker(b, () => { saveStats(); renderTooltip(); renderSets(); }),
      el("button", {class: "remove", title: "Remove the bonus", onclick: () => { s.bonuses.splice(bi, 1); saveStats(); renderStats(); }}, "×")));
    return el("div", {class: "set-card"},
      el("div", {class: "set-top"}, name, el("button", {class: "btn ghost small-btn", onclick: () => {
        if (confirm(`Delete the set "${s.name}"?`)) { SG.edits.sets.splice(si, 1); saveStats(); renderStats(); } }}, "Delete set")),
      el("div", {class: "set-pieces"}, (s.pieces || []).map(d => {
        const p = piece(d);
        return el("span", {class: "chip"}, p ? icon(p.icon, qualityOf(p), "xs", p.source) : null, p ? p.name : `Look ${d}`,
          el("button", {class: "copy", title: "Take it out of the set", onclick: () => { s.pieces = s.pieces.filter(x => x !== d); saveStats(); renderStats(); }}, "×"));
      }), others.length ? add : null),
      el("div", {class: "set-bonuses"}, bonuses,
        el("button", {class: "btn ghost small-btn", onclick: () => {
          const used = (s.bonuses || []).map(b => b[0]);
          (s.bonuses = s.bonuses || []).push([[2, 4, 6, 8, 3, 5, 7, 1].find(n => !used.includes(n)) || 2, 0]); saveStats(); renderSets();
        }}, "+ Add a bonus")));
  }));
}
// a set bonus: one of the client's own set bonuses (search their text), or a spell id
function bonusPicker(b, done) {
  const cur = SG.opts.bonuses.find(x => x.spell === +b[1]) || (SG.spellCache || {})[b[1]];
  const input = el("input", {class: "bonus-in", placeholder: "Search bonuses (e.g. attack power), or type a spell id",
                             value: cur ? cur.text : (b[1] ? `spell ${b[1]}` : ""), spellcheck: "false"});
  const list = el("div", {class: "bonus-list", hidden: true});
  const pick = x => { b[1] = x.spell; input.value = x.text; list.hidden = true; done(); };
  const refresh = async () => {
    const q = input.value.trim().toLowerCase();
    if (/^\d+$/.test(q)) {
      try {
        const sp = await api("/api/stats/spell", {id: q});
        (SG.spellCache = SG.spellCache || {})[sp.spell] = sp;
        list.replaceChildren(el("div", {class: "bonus-hit", onmousedown: ev => { ev.preventDefault(); pick(sp); }},
          el("b", {}, `${sp.spell} ${sp.name}`), el("div", {}, sp.text)));
      } catch (e) { list.replaceChildren(el("div", {class: "muted small"}, e.message)); }
      list.hidden = false;
      return;
    }
    const words = q.split(/\s+/).filter(Boolean);
    const hits = SG.opts.bonuses.filter(x => words.every(w => (x.text + " " + x.sets.join(" ")).toLowerCase().includes(w))).slice(0, 40);
    list.replaceChildren(...hits.map(x => el("div", {class: "bonus-hit", onmousedown: ev => { ev.preventDefault(); pick(x); }},
      el("div", {}, x.text), el("div", {class: "muted small"}, `${x.sets.join(", ")} · spell ${x.spell}`))));
    list.hidden = !hits.length;
  };
  input.addEventListener("focus", () => { input.select(); refresh(); });
  input.addEventListener("input", debounce(refresh, 200));
  input.addEventListener("blur", () => setTimeout(() => { list.hidden = true; }, 150));
  return el("div", {class: "bonus-pick"}, input, list);
}

function wireStats() {
  $("#sets-new").addEventListener("click", () => {
    SG.edits.sets.push({key: "s" + Date.now().toString(36), name: "New set", pieces: SG.sel ? [SG.sel] : [], bonuses: []});
    saveStats(); renderStats();
  });
  $("#sets-from-basket").addEventListener("click", () => {
    let made = 0;
    for (const b of SG.basketSets) {
      const key = "basket:" + b.key;
      if (SG.edits.sets.some(s => s.key === key) || !b.pieces.length) continue;
      SG.edits.sets.push({key, name: b.name, pieces: [...new Set(b.pieces)].slice(0, 17), bonuses: []});
      made++;
    }
    saveStats(); renderStats();
    toast(made ? `Made ${made} set${made === 1 ? "" : "s"} - give them bonuses below` : "Every set in the basket has one already");
  });
}
wireStats();

window.loadStats = loadStats;                      // the one name app.js calls
})();
