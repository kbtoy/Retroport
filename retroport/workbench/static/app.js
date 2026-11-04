"use strict";
// Retroport Workbench page: items and sets from the loaded sources, a detail drawer, the basket.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const SHORT_EXP = {0: "Classic", 1: "TBC", 2: "WotLK", 3: "Cata", 4: "MoP", 5: "WoD", 6: "Legion", 7: "BfA",
                   8: "Shadowlands", 9: "Dragonflight", 10: "War Within", 11: "Midnight", 12: "Last Titan"};
const SLOT_LABELS = {head: "Head", shoulder: "Shoulder", back: "Back", chest: "Chest", shirt: "Shirt", tabard: "Tabard",
                     wrist: "Wrist", hands: "Hands", waist: "Waist", legs: "Legs", feet: "Feet",
                     mainhand: "Main hand / two-hand", offhand: "Off hand & shield", held: "Held in off-hand",
                     ranged: "Ranged"};

const S = {
  meta: null, status: null, source: "", view: "items",
  items: {page: 0, total: 0, loading: false, key: ""},
  sets: {kind: "transmog", page: 0, total: 0, loading: false, key: ""},
  mounts: {kind: "", page: 0, total: 0, loading: false, key: ""},
  basket: [], open: null,
};

// ---------------------------------------------------------------------------- helpers
async function api(path, params = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null && v !== false));
  const r = await fetch(path + (qs.toString() ? "?" + qs : ""));
  const body = await r.json();
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}
function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "text") e.textContent = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "style") e.style.cssText = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid.nodeType ? kid : document.createTextNode(kid));
  return e;
}
function qcolor(q) { return (S.meta && S.meta.qualities[q]) ? S.meta.qualities[q].color : "#ffffff"; }
function icon(fdid, quality, size = "", source = S.source) {
  const box = el("span", {class: "icon " + size, style: `border-color:${quality != null ? qcolor(quality) : "#444"}`});
  if (fdid) box.append(el("img", {src: `/icon/${source}/${fdid}.png`, loading: "lazy", alt: "",
                                   onerror: e => e.target.remove()}));
  return box;
}
// a short note at the bottom; with an action (Undo) it stays a little longer
function toast(msg, action = "", fn = null) {
  const t = $("#toast");
  t.replaceChildren(msg, ...(action ? [el("button", {class: "toast-act", onclick: () => { t.classList.remove("show"); fn(); }}, action)] : []));
  t.classList.add("show");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), action ? 5000 : 1800);
}
function copy(text) { navigator.clipboard.writeText(String(text)).then(() => toast(`Copied ${text}`)); }
function classNames(mask) {
  if (!mask || mask === -1) return "All classes";
  const names = Object.entries(S.meta.classes).filter(([b]) => mask & (1 << (b - 1))).map(([, n]) => n);
  return names.length >= 12 ? "All classes" : names.join(", ");
}
function itemKind(r) {
  if (r.cls === 2) return S.meta.weapons[r.sub] || "Weapon";
  if (r.slot === 14) return "Shield";
  if ([4, 16, 19, 23].includes(r.slot) && (r.sub === 0 || r.sub === 1)) return S.meta.slots[r.slot];
  return `${S.meta.armour[r.sub] || ""} ${S.meta.slots[r.slot] || ""}`.trim();
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

// ---------------------------------------------------------------------------- status & sources
async function pollStatus() {
  try {
    S.status = await api("/api/status");
  } catch (e) {
    $("#state").textContent = "server not answering"; $("#state").className = "pill";
    return setTimeout(pollStatus, 3000);
  }
  const st = S.status, ready = st.sources.filter(s => s.state === "ready");
  appState(st);
  $("#log").textContent = [...st.problems.map(p => "! " + p), ...st.log.slice(-12)].join("\n");
  $("#settings-state").hidden = !st.problems.length;
  if (st.setup && !S.setupShown) { S.setupShown = true; show("settings"); }   // first run: where's the client?
  const box = $("#sources");
  box.replaceChildren(...st.sources.map(s => el("button", {
    class: s.key === S.source ? "on" : "", disabled: s.state !== "ready", role: "tab",
    title: `${s.path}\n${s.state}${s.build ? " · " + s.build : ""}`,
    onclick: () => { S.source = s.key; refreshAll(); renderSources(); },
  }, `${s.label}${s.build ? " " + s.build.split(".").slice(0, 3).join(".") : ""}`)));
  const busy = st.sources.some(s => s.state === "loading" || s.state === "waiting");
  const pill = $("#state");
  if (!st.sources.length) { pill.textContent = "no source set"; pill.className = "pill"; }
  else if (busy) { pill.textContent = "loading catalogs…"; pill.className = "pill busy"; }
  else { pill.textContent = st.in_client ? `3.3.5 client: ${st.in_client.toLocaleString()} items` : "ready";
         pill.className = "pill ready"; }
  if (!S.source || !ready.find(s => s.key === S.source)) {
    if (ready.length) { S.source = ready[0].key; refreshAll(); }
  }
  if (busy || !st.sources.length) setTimeout(pollStatus, 1200);
}
function renderSources() { $$("#sources button").forEach((b, i) => b.classList.toggle("on", S.status.sources[i].key === S.source)); }
function refreshAll() { searchItems(true); searchSets(true); searchMounts(true); }

// ---------------------------------------------------------------------------- items
function itemParams() {
  return {source: S.source, q: $("#q").value.trim(), slot: $("#f-slot").value, armour: $("#f-armour").value,
          weapon: $("#f-weapon").value, expansion: $("#f-expansion").value, quality: $("#f-quality").value,
          cls: $("#f-cls").value, looks: $("#f-looks").checked ? 1 : "", sort: $("#f-sort").value,
          junk: $("#f-junk").checked ? 1 : ""};
}
async function searchItems(reset) {
  if (!S.source) return;
  const p = itemParams(), key = JSON.stringify(p);
  if (reset) { S.items.page = 0; S.items.key = key; $("#item-grid").replaceChildren(); $("#item-more").hidden = true; }
  if (S.items.loading && !reset) return;
  const token = S.items.token = (S.items.token || 0) + 1;
  S.items.loading = true;
  try {
    const res = await api("/api/items", {...p, page: S.items.page});
    if (token !== S.items.token) return;
    S.items.total = res.total;
    $("#item-grid").append(...res.items.map(itemCard));
    const shown = $("#item-grid").children.length;
    $("#item-summary").textContent = res.total ? `${res.total.toLocaleString()} items${p.looks ? " (one per look)" : ""}` +
      (shown < res.total ? ` · showing ${shown.toLocaleString()}` : "") : "Nothing matches.";
    $("#item-more").hidden = shown >= res.total;
  } catch (e) { $("#item-summary").textContent = e.message; }
  finally { if (token === S.items.token) S.items.loading = false; }
}
function itemCard(r) {
  const k = `item:${S.source}:${r.id}`;
  return el("div", {class: "card", "data-id": r.id, onclick: () => openItem(r.id)},
    icon(r.icon, r.quality),
    el("div", {class: "meta"},
      el("div", {class: "name", style: `color:${qcolor(r.quality)}`, title: r.name}, r.name),
      el("div", {class: "sub"}, `${itemKind(r)} · ${SHORT_EXP[r.expansion] || ""}`,
         r.in_client ? el("span", {class: "badge", title: "Your 3.3.5 client already has this item id"}, "in 3.3.5") : null)),
    addButton(k, () => ({kind: "item", source: S.source, id: r.id, name: r.name, icon: r.icon, quality: r.quality,
                          sub: itemKind(r)})));
}
async function ensureRaces() {
  if (!PV.races.length) { try { PV.races = await api("/api/races"); } catch (e) { /* the default list */ } }
}
// back: {id, kind, name} - the set the piece was opened from
async function openItem(id, back = null) {
  const [d] = await Promise.all([api("/api/item", {source: S.source, id}), ensureRaces()]);
  S.open = {kind: "item", id};
  PV.step = null;
  markSelected();
  const body = [];
  if (back) body.push(el("button", {class: "btn ghost back", onclick: () => openSet(back.id, back.kind)}, `← Back to ${back.name}`));
  body.push(el("div", {class: "d-head"}, icon(d.icon, d.quality, "lg"),
    el("div", {}, el("h2", {style: `color:${qcolor(d.quality)}`}, d.name),
       el("div", {class: "d-sub"}, `${itemKind(d)} · ${S.meta.expansions[d.expansion] || ""}`),
       el("div", {class: "d-sub"}, [d.item_level ? `Item level ${d.item_level}` : "", d.req_level ? `requires level ${d.req_level}` : ""]
          .filter(Boolean).join(" · "),
          d.in_client ? el("span", {class: "badge"}, "in 3.3.5") : null))));
  // its versions (Normal / Heroic / Mythic, a PvP piece's Gladiator / Elite...) on top, like a set's:
  // each shows in the preview, its ids below
  const ids = el("div", {class: "kv"});
  const showIds = (appearance, display) => ids.replaceChildren(...kv("Item", d.id), ...kv("Appearance", appearance), ...kv("Display", display));
  showIds(d.appearance, d.display);
  const preview = d.display ? itemPreview(d.display, d.slot) : null;
  if (d.appearances.length > 1) {
    const chips = versionChips(d.appearances.map(a => ({
      label: a.label || S.meta.modifiers[a.modifier] || `Modifier ${a.modifier}`, icon: icon(a.icon, d.quality, "xs"),
      title: `appearance ${a.appearance} · display ${a.display}`, on: a.appearance === d.appearance,
      pick: () => { showIds(a.appearance, a.display); if (preview && a.display) loadDisplay(preview.pb, a.display, d.slot); }})));
    if (!(preview && preview.pb.add(chips))) body.push(section("Versions", chips));
  }
  if (preview) body.push(preview);
  body.push(section("Ids", ids));
  if (d.sets.length) {
    body.push(section(`In ${d.sets.length} transmog set${d.sets.length > 1 ? "s" : ""}`, el("div", {class: "plist"},
      d.sets.map(s => el("div", {class: "prow", onclick: () => openSet(s.id)}, icon(s.icon, null, "sm"),
        el("span", {class: "pname"}, s.name), el("span", {class: "slot"}, s.label || SHORT_EXP[s.expansion]))))));
  }
  if (d.item_sets.length) {
    body.push(section("Item set", el("div", {class: "plist"}, d.item_sets.map(s =>
      el("div", {class: "prow", onclick: () => openSet(s.id, "itemset")}, el("span", {class: "pname"}, s.name))))));
  }
  if (d.same_look.length) {
    body.push(section("Same look", el("div", {class: "plist"}, d.same_look.map(o =>
      el("div", {class: "prow", onclick: () => openItem(o.id)}, icon(o.icon, o.quality, "sm"),
        el("span", {class: "pname", style: `color:${qcolor(o.quality)}`}, o.name),
        el("span", {class: "slot"}, SHORT_EXP[o.expansion]))))));
  }
  if (d.classes !== -1) body.push(section("Classes", el("div", {class: "d-sub"}, classNames(d.classes))));
  const k = `item:${S.source}:${d.id}`;
  body.push(el("div", {class: "actions"},
    el("button", {class: "btn", onclick: () => toggleBasket(k, {kind: "item", source: S.source, id: d.id, name: d.name,
      icon: d.icon, quality: d.quality, sub: itemKind(d)})}, inBasket(k) ? "Remove from basket" : "Add to basket"),
    el("a", {class: "btn ghost", href: `https://www.wowhead.com/item=${d.id}`, target: "_blank", rel: "noopener"}, "Wowhead ↗")));
  showDrawer(body);
}

// ---------------------------------------------------------------------------- sets
function setParams() {
  return {source: S.source, kind: S.sets.kind, q: $("#q").value.trim(), expansion: $("#s-expansion").value,
          cls: $("#s-cls").value, armour: $("#s-armour").value};
}
async function searchSets(reset) {
  if (!S.source) return;
  const p = setParams(), key = JSON.stringify(p);
  if (reset) { S.sets.page = 0; S.sets.key = key; $("#set-grid").replaceChildren(); $("#set-more").hidden = true; }
  if (S.sets.loading && !reset) return;
  const token = S.sets.token = (S.sets.token || 0) + 1;
  S.sets.loading = true;
  try {
    const res = await api("/api/sets", {...p, page: S.sets.page});
    if (token !== S.sets.token) return;
    $("#set-grid").append(...res.sets.map(setCard));
    const shown = $("#set-grid").children.length;
    const what = p.kind === "itemset" ? "item sets" : "set families";
    $("#set-summary").textContent = res.total ? `${res.total.toLocaleString()} ${what}` +
      (shown < res.total ? ` · showing ${shown.toLocaleString()}` : "") : "Nothing matches.";
    $("#set-more").hidden = shown >= res.total;
  } catch (e) { $("#set-summary").textContent = e.message; }
  finally { if (token === S.sets.token) S.sets.loading = false; }
}
function setCard(s) {
  const kind = S.sets.kind, k = `${kind === "itemset" ? "itemset" : "set"}:${S.source}:${s.id}`;
  // a class set says whose (one PvP name covers a Hunter's, a Shaman's and an Evoker's looks)
  const few = s.classes && Object.keys(S.meta.classes).filter(c => s.classes & (1 << (c - 1))).length <= 3;
  const sub = kind === "itemset" ? `${s.pieces} pieces · ${SHORT_EXP[s.expansion] || ""}` :
    [s.label, few ? classNames(s.classes) : "", s.group, SHORT_EXP[s.expansion]].filter(Boolean).join(" · ");
  return el("div", {class: "card set-card", "data-id": s.id, "data-root": s.root ?? s.id, onclick: () => openSet(s.id, kind)},
    el("div", {class: "row"},
      el("div", {class: "meta"}, el("div", {class: "name", title: s.name}, s.name), el("div", {class: "sub"}, sub)),
      s.variants > 1 ? el("span", {class: "badge dim"}, `${s.variants} versions`) : null,
      addButton(k, () => ({kind: kind === "itemset" ? "itemset" : "set", source: S.source, id: s.id, name: s.name,
                            icon: s.icon || (s.piece_icons || [])[0], sub, items: s.items}))),
    el("div", {class: "strip"}, (s.piece_icons || []).map(f => icon(f, null, "sm"))));
}
async function openSet(id, kind = "transmog") {
  const [d] = await Promise.all([api("/api/set", {source: S.source, id, kind}), ensureRaces()]);
  S.open = {kind: kind === "itemset" ? "itemset" : "set", id, root: d.root ?? id};   // its family's card stays marked
  PV.step = null;
  markSelected();
  const body = [];
  if (kind === "itemset") {
    body.push(el("div", {class: "d-head"}, el("div", {}, el("h2", {}, d.name), el("div", {class: "d-sub"}, `Item set ${d.id}`))));
  } else {
    body.push(el("div", {class: "d-head"}, icon(d.icon, null, "lg"),
      el("div", {}, el("h2", {}, d.name),
         el("div", {class: "d-sub"}, [d.label, d.group].filter(Boolean).join(" · ")),
         el("div", {class: "d-sub"}, `${S.meta.expansions[d.expansion] || ""} · ${classNames(d.classes)}` +
            (d.armour >= 0 ? ` · ${S.meta.armour[d.armour] || ""}` : "")))));
  }
  // its versions (Normal / Heroic / Mythic, Gladiator / Elite) go under the preview, with race and sex
  const versions = kind !== "itemset" && d.family.length > 1 ? versionChips(d.family.map(f =>
    ({label: f.label || f.name, title: `${f.name} · set ${f.id}`, on: f.id === d.id, pick: () => openSet(f.id)}))) : null;
  const rows = d.pieces.map(p => {
    const also = p.also || [];                      // other items with this look (a Helm and a Faceguard)
    return el("div", {class: "prow", title: also.length ? `Same look: ${also.join(", ")}` : "",
                      onclick: () => openItem(p.item ?? p.id, {id: d.id, kind, name: d.name})},
      el("span", {class: "slot"}, S.meta.slots[p.slot] || ""), icon(p.icon, p.quality, "sm"),
      el("span", {class: "pname", style: `color:${qcolor(p.quality)}`}, p.name || `Item ${p.item ?? p.id}`,
         also.length ? el("span", {class: "also"}, ` +${also.length} same look`) : null),
      p.in_client ? el("span", {class: "badge"}, "3.3.5") : null);
  });
  const list = section(plural(d.pieces.length, "piece"), el("div", {class: "plist"}, rows));
  const k = `${kind === "itemset" ? "itemset" : "set"}:${S.source}:${d.id}`;
  const entry = {kind: kind === "itemset" ? "itemset" : "set", source: S.source, id: d.id, name: d.name, icon: d.icon,
                 sub: kind === "itemset" ? `${d.pieces.length} pieces` : [d.label, d.group].filter(Boolean).join(" · "),
                 items: kind === "itemset" ? d.pieces.map(p => p.id) : undefined};
  const actions = [el("button", {class: "btn", onclick: () => toggleBasket(k, entry)},
                      inBasket(k) ? "Remove from basket" : "Add to basket")];
  if (kind !== "itemset" && d.family.length > 1) {
    actions.push(el("button", {class: "btn ghost", onclick: () => {
      for (const f of d.family) {
        const fk = `set:${S.source}:${f.id}`;
        if (!inBasket(fk)) S.basket.push({kind: "set", source: S.source, id: f.id, name: f.name, icon: f.icon,
          sub: [f.label, f.group].filter(Boolean).join(" · ")});
      }
      saveBasket(); toast(`${d.family.length} versions in the basket`); openSet(d.id);
    }}, `Add all ${d.family.length} versions`));
  }
  actions.push(el("a", {class: "btn ghost", target: "_blank", rel: "noopener",
    href: kind === "itemset" ? `https://www.wowhead.com/item-set=${d.id}` : `https://www.wowhead.com/transmog-set=${d.id}`},
    "Wowhead ↗"));
  // weapons and accessories (a back piece too), or pieces all of one kind (masks, cloaks): one at a time;
  // else on a character
  const shown = d.pieces.map((p, i) => ({display: p.display, slot: p.slot, name: p.name || `Item ${p.item ?? p.id}`, row: rows[i]}))
    .filter(p => p.display);
  const kinds = new Set(shown.map(p => SLOT_KIND[p.slot] ?? p.slot));
  let preview = null;
  if (shown.length && (shown.every(p => HELD.includes(p.slot) || p.slot === BACK) || kinds.size === 1)) {
    preview = carouselSection(shown, shown.map(p => p.row));
  } else {
    const worn = [], slots = new Set();
    for (const p of shown) {                        // the first piece of each slot
      if (slots.has(p.slot)) continue;
      slots.add(p.slot);
      worn.push(p);
    }
    if (worn.length) preview = characterSection(worn);
  }
  // the preview first (its versions under it, so switching keeps it in view), then the pieces
  if (versions && !(preview && preview.pb && preview.pb.add(versions))) body.push(section("Versions", versions));
  if (preview) body.push(preview);
  body.push(list, el("div", {class: "actions"}, actions));
  showDrawer(body);
}
// slots that are one kind of piece: a chest and a robe, a two-hander and a one-hander
const SLOT_KIND = {20: 5, 17: 13, 21: 13, 22: 14, 25: 15, 26: 15};

// ---------------------------------------------------------------------------- mounts
// Retail's mounts (mounts.py): each one is a spell, its creature and the item that teaches it in
// 3.3.5; a mount with several looks rides the one picked here. Mounts of one model in other skins
// are one family: one card, each a version in the drawer, like a set's.
const MOUNT_KINDS = {ground: "Ground mount", flying: "Flying mount"};
function mountParams() {
  return {source: S.source, q: $("#q").value.trim(), kind: S.mounts.kind, junk: $("#m-junk").checked ? 1 : ""};
}
async function searchMounts(reset) {
  if (!S.source) return;
  const p = mountParams(), key = JSON.stringify(p);
  if (reset) { S.mounts.page = 0; S.mounts.key = key; $("#mount-grid").replaceChildren(); $("#mount-more").hidden = true; }
  if (S.mounts.loading && !reset) return;
  const token = S.mounts.token = (S.mounts.token || 0) + 1;
  S.mounts.loading = true;
  try {
    const res = await api("/api/mounts", {...p, page: S.mounts.page});
    if (token !== S.mounts.token) return;
    $("#mount-grid").append(...res.mounts.map(mountCard));
    const shown = $("#mount-grid").children.length;
    $("#mount-summary").textContent = res.total ? plural(res.total, "mount family") +
      (shown < res.total ? ` · showing ${shown.toLocaleString()}` : "") : "Nothing matches.";
    $("#mount-more").hidden = shown >= res.total;
  } catch (e) { $("#mount-summary").textContent = e.message; if (/loading/.test(e.message)) setTimeout(() => S.view === "mounts" && searchMounts(true), 3000); }
  finally { if (token === S.mounts.token) S.mounts.loading = false; }
}
function mountEntry(m, display = 0) {
  return {kind: "mount", source: S.source, id: m.id, name: m.name, icon: m.icon, quality: m.quality, sub: MOUNT_KINDS[m.kind],
          mount_kind: m.kind, display: display || (m.displays || [])[0] || 0};
}
function mountCard(m) {
  const k = `mount:${S.source}:${m.id}`;
  return el("div", {class: "card", "data-id": m.id, "data-root": m.root ?? m.id, onclick: () => openMount(m.id)},
    icon(m.icon, m.quality),
    el("div", {class: "meta"},
      el("div", {class: "name", style: `color:${qcolor(m.quality)}`, title: m.name}, m.name),
      el("div", {class: "sub"}, [MOUNT_KINDS[m.kind], m.source_label].filter(Boolean).join(" · "),
         m.versions > 1 ? el("span", {class: "badge dim", title: "Mounts of this model in other skins"}, `${m.versions} versions`) : null,
         m.displays.length > 1 ? el("span", {class: "badge dim"}, `${m.displays.length} looks`) : null)),
    addButton(k, () => mountEntry(m)));
}
async function openMount(id, display = 0) {
  const m = await api("/api/mount", {source: S.source, id});
  S.open = {kind: "mount", id, root: m.root ?? id};       // its family's card stays marked
  PV.step = null;
  markSelected();
  const k = `mount:${S.source}:${m.id}`;
  const inside = S.basket.find(e => keyOf(e) === k);
  let chosen = display || (inside && inside.display) || m.displays[0];
  const body = [el("div", {class: "d-head"}, icon(m.icon, m.quality, "lg"),
    el("div", {}, el("h2", {style: `color:${qcolor(m.quality)}`}, m.name),
       el("div", {class: "d-sub"}, [MOUNT_KINDS[m.kind], m.source_label].filter(Boolean).join(" · ")),
       m.item_name ? el("div", {class: "d-sub"}, `Taught by ${m.item_name}`) : null))];
  const pb = previewBox();
  const ids = el("div", {class: "kv"});
  const showIds = d => ids.replaceChildren(...kv("Mount", m.id), ...kv("Spell", m.spell), ...kv("Display", d),
                                          ...(m.item ? kv("Item", m.item) : []));
  showIds(chosen);
  // its versions (the other mounts of its model, in other skins) on top, like a set's: each opens here
  const family = m.family || [];
  if (family.length > 1) {
    const chips = versionChips(family.map(f => ({label: f.label, icon: icon(f.icon, f.quality, "xs"),
      title: [f.name, MOUNT_KINDS[f.kind], f.source_label].filter(Boolean).join(" · "), on: f.id === m.id,
      pick: () => openMount(f.id)})));
    if (!pb.add(chips)) body.push(section("Versions", chips));
  }
  if (pb.v) {
    const picker = pb.controls.querySelector(".pv-pick");
    if (picker) picker.hidden = true;                      // a mount alone: no race or sex
    if (m.displays.length > 1) {
      pb.add(versionChips(m.displays.map((d, i) => ({label: `Look ${i + 1}`, title: `display ${d}`, on: d === chosen,
        pick: () => {
          chosen = d; showIds(d); loadMount(pb, d);
          const e = S.basket.find(x => keyOf(x) === k);
          if (e && e.display !== d) { e.display = d; saveBasket(); }     // the basket rides the look picked
        }}))));
    }
    loadMount(pb, chosen);
    body.push(pb.box);
  }
  if (m.description) body.push(section("About", el("div", {class: "d-sub"}, m.description)));
  if (m.source_text) body.push(section("Where retail has it", el("div", {class: "d-sub"}, m.source_text.replace(/\|[cCrR][0-9a-fA-F]{0,8}|\|n/g, " "))));
  body.push(section("Ids", ids));
  body.push(el("div", {class: "muted small"}, "In 3.3.5 it is a mount spell like the epic ones (" +
    (m.kind === "flying" ? "280% flying, 100% on the ground" : "100%") + "), learned from its item."));
  const actions = [el("button", {class: "btn", onclick: () => toggleBasket(k, mountEntry(m, chosen))},
                      inBasket(k) ? "Remove from basket" : "Add to basket")];
  if (family.length > 1) {
    actions.push(el("button", {class: "btn ghost", onclick: () => {
      for (const f of family) {
        if (!inBasket(`mount:${S.source}:${f.id}`)) S.basket.push(mountEntry(f, f.id === m.id ? chosen : 0));
      }
      saveBasket(); toast(`${family.length} versions in the basket`); openMount(m.id, chosen);
    }}, `Add all ${family.length} versions`));
  }
  actions.push(el("a", {class: "btn ghost", href: `https://www.wowhead.com/spell=${m.spell}`, target: "_blank", rel: "noopener"}, "Wowhead ↗"));
  body.push(el("div", {class: "actions"}, actions));
  showDrawer(body);
}
// A mount's look: its model wearing the display's skins, the parts its geoset data picks.
function loadMount(pb, display) {
  pb.load(async () => {
    const v = pb.v, token = ++PV.token;
    pb.info.textContent = "Loading…";
    try {
      const p = await api("/api/mount/preview", {source: S.source, display});
      if (token !== PV.token) return;
      v.clear();
      pb.textures.replaceChildren(...p.textures.map(f => textureThumb(S.source)({fdid: f, name: String(f)})));
      if (p.mesh) {
        v.add(p.mesh, {texUrl: texUrl(S.source), visible: id => {
          const want = p.geosets[Math.floor(id / 100)];
          return want == null || id === want;
        }});
        v.fit("front");
      }
      v.canvas.hidden = !p.mesh;
      v.draw();
      pb.info.textContent = p.mesh ? `${p.mesh.triangles.toLocaleString()} triangles` : "No model found.";
      notes(pb.info, p.problems);
    } catch (e) { if (token === PV.token) pb.info.textContent = e.message; }
  });
}

// ---------------------------------------------------------------------------- drawer
function section(title, ...kids) { return el("div", {class: "d-sec"}, el("h3", {}, title), ...kids); }
function kv(k, v) {
  return [el("span", {class: "k"}, k), el("span", {}, String(v || "–")),
          v ? el("button", {class: "copy", onclick: () => copy(v), title: "Copy"}, "copy") : el("span")];
}
function showDrawer(kids) {
  $("#drawer-body").replaceChildren(...kids);
  document.body.classList.add("drawer-open");
  $("#drawer").setAttribute("aria-hidden", "false");
  $("#drawer").scrollTop = 0;
}
function closeDrawer() {
  PV.step = null;
  document.body.classList.remove("drawer-open");
  $("#drawer").setAttribute("aria-hidden", "true");
  S.open = null; markSelected();
}
function markSelected() {
  $$(".card.sel").forEach(c => c.classList.remove("sel"));
  if (!S.open) return;
  const grid = S.open.kind === "item" ? "#item-grid" : S.open.kind === "mount" ? "#mount-grid" : "#set-grid";
  const same = S.open.kind === "item" ? `[data-id="${S.open.id}"]` : `[data-root="${S.open.root ?? S.open.id}"]`;
  $$(`${grid} .card${same}`).forEach(c => c.classList.add("sel"));
}

// ---------------------------------------------------------------------------- basket
const keyOf = e => `${e.kind}:${e.source}:${e.id}`;
function inBasket(k) { return S.basket.some(e => keyOf(e) === k); }
function addButton(k, make) {
  const b = el("button", {class: "add" + (inBasket(k) ? " in" : ""), "data-key": k, title: "Add to basket",
    onclick: ev => { ev.stopPropagation(); toggleBasket(k, make()); }}, inBasket(k) ? "✓" : "+");
  return b;
}
function toggleBasket(k, entry) {
  if (inBasket(k)) { S.basket = S.basket.filter(e => keyOf(e) !== k); toast(`Removed ${entry.name}`); }
  else { S.basket.push(entry); toast(`Added ${entry.name}`); }
  saveBasket();
  if (S.open) reopen(S.open);
}
function reopen(o) {
  o.kind === "item" ? openItem(o.id) : o.kind === "mount" ? openMount(o.id) : openSet(o.id, o.kind === "itemset" ? "itemset" : "transmog");
}
async function saveBasket() {
  $("#basket-count").textContent = S.basket.length;
  $$(".add[data-key]").forEach(b => { const on = inBasket(b.dataset.key); b.classList.toggle("in", on); b.textContent = on ? "✓" : "+"; });
  // one save at a time, in order: two quick clicks never land the older basket last
  const body = JSON.stringify(S.basket);
  S.saving = (S.saving || Promise.resolve()).then(() =>
    fetch("/api/basket", {method: "POST", headers: {"Content-Type": "application/json"}, body})
      .catch(() => toast("Could not save the basket")));
  await S.saving;
  if (S.view === "basket") renderBasket();
  if (S.view === "backport") loadKit();
}
function basketCounts(entries) {
  const n = kind => entries.filter(e => e.kind === kind).length;
  return [[n("set"), "transmog set"], [n("itemset"), "item set"], [n("item"), "item"], [n("look"), "look"], [n("mount"), "mount"]]
    .filter(([c]) => c).map(([c, w]) => plural(c, w)).join(", ") || "nothing";
}
// an install's time stamp (20261014-193005) as "Oct 14, 19:30"
function when(stamp) {
  const m = /^(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)/.exec(stamp || "");
  if (!m) return stamp || "";
  const d = new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]);
  return `${d.toLocaleDateString(undefined, {month: "short", day: "numeric"})}, ${m[4]}:${m[5]}`;
}
function sourceLabel(key) {
  const s = S.status && S.status.sources.find(x => x.key === key);
  return s ? s.label : key;
}
// an entry or one of its pieces in the drawer, from whichever source it came from
function useSource(key) {
  if (key && key !== S.source && S.status && S.status.sources.some(s => s.key === key && s.state === "ready")) {
    S.source = key; renderSources(); refreshAll();
  }
}
function openEntry(e, itemId = null) {
  useSource(e.source);
  const back = e.kind === "set" ? {id: e.id, kind: "transmog", name: e.name} : e.kind === "itemset" ? {id: e.id, kind: "itemset", name: e.name} : null;
  if (itemId != null) openItem(itemId, back);
  else if (e.kind === "item") openItem(e.id);
  else if (e.kind === "look") { const it = ((e.looks || [])[0] || {}).item; if (it) openItem(it); }
  else if (e.kind === "mount") { show("mounts"); openMount(e.id, (e.mount || {}).display); }
  else openSet(e.id, e.kind === "itemset" ? "itemset" : "transmog");
}
function removeEntries(keys, what) {
  const gone = S.basket.filter(x => keys.includes(keyOf(x)));
  S.basket = S.basket.filter(x => !keys.includes(keyOf(x)));
  saveBasket();
  toast(`Removed ${what}`, "Undo", () => { S.basket.push(...gone.filter(g => !inBasket(keyOf(g)))); saveBasket(); });
}

// which workbench this page talks to; a page whose workbench was replaced by another copy closes
// (or, left open, reloads from the new one)
function appState(st) {
  if (st.app) {
    $("#app-version").textContent = "v" + st.app.version.replace(" (source)", "");
    $("#app-version").title = `Retroport Workbench ${st.app.version}\nrunning from ${st.app.from}`;
  }
  if (S.instance && st.instance && st.instance !== S.instance) return location.reload();
  S.instance = S.instance || st.instance;
  if (st.quitting) {
    $("#updated").textContent = "Another copy of the workbench took over - close this window.";
    $("#updated").hidden = false;
    try { window.close(); } catch (e) { /* not ours to close */ }
    return;
  }
  $("#updated").hidden = !st.updated;
}

// what earlier installs put in the game: every install keeps it, unless it's taken out
function renderGame(plan) {
  const game = plan.in_game || [];
  if (!game.length) { $("#basket-game").replaceChildren(); return; }
  const out = game.filter(e => e.take_out).length;
  const toggle = (e, take) => el("button", {class: "copy", title: take ? "The next install takes it out of your game" :
    "Keep it in your game", onclick: async () => {
      try { await post("/api/basket/take-out", {key: e.key, out: take}); renderBasket(); if (S.view === "backport") loadKit(); }
      catch (err) { toast(err.message); }
    }}, take ? "take out" : "keep");
  $("#basket-game").replaceChildren(el("div", {class: "panel game-list"},
    el("h3", {}, `In your game (${game.length})`),
    el("p", {class: "muted small"}, `What earlier installs put in${plan.installed_at ? ` (the last ${when(plan.installed_at)})` : ""}. ` +
       "Every install keeps it" + (out ? ` - the next one takes out ${plural(out, "entry")}, struck through.` : ".")),
    el("div", {class: "chips"}, game.map(e => el("span", {class: "chip" + (e.take_out ? " out" : ""), title: e.sub || ""},
      icon(e.icon || (e.looks[0] || {}).icon, e.quality, "xs", e.source), e.name, " ", toggle(e, !e.take_out))))));
}

// the last five installs, tried or done, each with what its basket held
function renderHistory(history) {
  const btn = $("#basket-history-btn");
  btn.textContent = history.length ? `History (${history.length})` : "History";
  const rows = history.map(h => {
    const ok = h.result === "installed";
    const back = h.basket.filter(e => !inBasket(keyOf(e)));
    return el("div", {class: "hist-row"},
      el("span", {class: "hist-when"}, when(h.time)),
      el("span", {class: "hist-result " + (ok ? "ok" : "bad")}, ok ? "✓ installed" : h.result === "undone" ? "↶ undone" :
         h.result === "stopped" ? "stopped" : `✗ failed${h.step ? ` at "${stepWords(h.step)}"` : ""}`),
      el("span", {class: "chips"}, h.basket.map(e => el("span", {class: "chip"}, e.name)),
         (h.taken_out || []).map(e => el("span", {class: "chip out", title: "taken out of the game"}, e.name))),
      back.length ? el("button", {class: "btn ghost small-btn", onclick: () => {
        S.basket.push(...back); saveBasket(); toast(`${plural(back.length, "entry")} back in the basket`);
      }}, "Put back in the basket") : null);
  });
  $("#basket-history").replaceChildren(el("h3", {}, "History - the last five installs"),
    ...(rows.length ? rows : [el("div", {class: "muted small"}, "No install yet.")]));
}

// the basket as the server has it now (it changed there: a piece left out or put back)
async function refreshBasket() {
  try { S.basket = await api("/api/basket"); } catch (e) { return; }
  $("#basket-count").textContent = S.basket.length;
  if (S.view === "basket") renderBasket();
  if (S.view === "backport") loadKit();
}

// The basket page: each entry with the looks it brings (the kit builds one per model), what it
// shares with another entry, and what changed since the install in your client.
async function renderBasket() {
  const token = S.planToken = (S.planToken || 0) + 1;
  let plan;
  try { plan = await api("/api/basket/plan"); }
  catch (e) { $("#basket-summary").textContent = e.message; return; }
  if (token !== S.planToken) return;
  const n = plan.entries.length;
  $("#basket-clear").disabled = !n;
  $("#basket-summary").textContent = n
    ? `${basketCounts(plan.entries)}` + (plan.looks ? `: ${plural(plan.looks, "look")} from ${plural(plan.items, "item")}` : "") +
      ". The next install adds these to your game - remove anything you don't want" + (plan.looks ? ", then give them stats." : ".") :
    "The next install adds what you put here to your game.";
  renderGame(plan);
  renderHistory(plan.history || []);
  renderForeign();
  if (!n) {
    $("#basket-list").replaceChildren(el("div", {class: "empty"}, "Nothing picked yet. Use + on any item or set."));
    return;
  }
  const groups = [["set", "Transmog sets"], ["itemset", "Item sets"], ["item", "Items"], ["look", "Looks"], ["mount", "Mounts"]];
  $("#basket-list").replaceChildren(...groups.map(([kind, title]) => {
    const rows = plan.entries.filter(e => e.kind === kind);
    return rows.length ? el("div", {class: "basket-group"}, el("h3", {}, `${title} (${rows.length})`), rows.map(e => basketRow(e, plan))) : null;
  }).filter(Boolean));
  if (plan.entries.some(e => e.state === "loading")) setTimeout(() => { if (S.view === "basket") renderBasket(); }, 1500);
}
// looks the kit's project built outside the workbench (the Backport Helper adds to the same project)
async function renderForeign() {
  let foreign = [];
  try { foreign = await api("/api/basket/foreign"); } catch (e) { /* no project yet */ }
  const box = $("#basket-foreign");
  if (!foreign.length) { box.replaceChildren(); return; }
  box.replaceChildren(el("div", {class: "panel foreign"},
    el("div", {}, el("b", {}, `Your backport project has ${plural(foreign.length, "look")} that aren't in your basket`),
      " - made with the Backport Helper, or put in before the workbench kept track. An install builds what's in the basket, so ",
      "it would take them out of your game. Bring them into the basket to keep them."),
    el("div", {class: "strip"}, foreign.slice(0, 40).map(f => { const b = icon(f.icon, f.quality, "sm", f.source); b.title = f.name; return b; })),
    el("div", {class: "actions"},
      el("button", {class: "btn", onclick: () => {
        for (const f of foreign) if (!inBasket(keyOf(f))) S.basket.push(f);
        saveBasket(); toast(`${plural(foreign.length, "look")} back in the basket`);
      }}, "Bring them into the basket"),
      el("button", {class: "btn ghost", onclick: async () => {
        if (!confirm(`Let ${plural(foreign.length, "look")} go? The next install takes them out of your game.`)) return;
        try { await post("/api/kit/let-go", {looks: foreign.map(f => f.id)}); renderBasket(); } catch (e) { toast(e.message); }
      }}, "Let them go"))));
}
function basketRow(e, plan) {
  const looks = e.looks;
  const status = e.in_game ? el("span", {class: "badge dim", title: "In your game already: the next install builds it again " +
                                                   "with what you changed (pieces left out, say)"}, "in your game") : null;
  const what = e.kind === "mount" ? e.sub || "Mount" :
    e.state === "loading" ? "loading its catalog…" : e.state === "missing" ? `not found in ${sourceLabel(e.source)}` :
    [e.kind !== "itemset" ? e.sub : "", plural(looks.length, "look"), e.items > 1 ? plural(e.items, "item") : ""].filter(Boolean).join(" · ");
  const warn = e.covered ? `Everything in it comes with ${e.shares.join(", ")} already - it adds nothing.`
             : e.shares.length ? `Shares some looks with ${e.shares.join(", ")}.` : "";
  return el("div", {class: "bitem" + (e.covered ? " dupe" : "")},
    icon(e.icon || (looks[0] || {}).icon, e.quality, "sm", e.source),
    el("div", {class: "meta"},
      el("div", {class: "bname"},
        el("a", {href: "#", style: e.quality != null ? `color:${qcolor(e.quality)}` : "", title: "Open it",
                 onclick: ev => { ev.preventDefault(); openEntry(e); }}, e.name), status),
      el("div", {class: "sub muted"}, `${what} · ${sourceLabel(e.source)} #${e.id}`),
      looks.length ? el("div", {class: "strip"}, looks.map(l => {
        const b = icon(l.icon, l.quality, "sm", e.source);
        b.title = [l.name, l.label, S.meta.slots[l.slot], l.also ? `+${l.also} same look` : ""].filter(Boolean).join(" · ");
        b.addEventListener("click", () => openEntry(e, l.item));
        return b;
      })) : null,
      (e.left_out || []).length ? el("div", {class: "left-out muted small"}, "Left out: ", ...e.left_out.flatMap((l, i) => [
        i ? ", " : "", l.name || `look ${l.display}`, " ",
        el("a", {href: "#", onclick: async ev => { ev.preventDefault();
          try { await post("/api/basket/leave-out", {display: l.display, out: false}); await refreshBasket(); }
          catch (err) { toast(err.message); } }}, "put back")])) : null,
      warn ? el("div", {class: "warnline"}, warn) : null),
    el("button", {class: "remove", title: "Remove from the basket", onclick: () => removeEntries([e.key], e.name)}, "×"));
}

// what the kit's audit said: helms that sit a little off (Install goes on), and what stopped it
function renderAudit(a, running) {
  const leave = (g, out) => el("button", {class: "btn ghost small-btn", disabled: running || !g.display, onclick: async () => {
    try { await post("/api/basket/leave-out", {display: g.display, out}); toast(out ? `${g.name} left out - Install again` : `${g.name} put back`);
          await refreshBasket(); } catch (e) { toast(e.message); }
  }}, out ? "Leave this piece out" : "Put it back");
  const row = (g, cls, words) => el("div", {class: "audit-row " + cls},
    el("div", {}, el("b", {}, g.name), " ", el("span", {class: "muted"}, words(g)), " ", g.display ? leave(g, true) : null),
    el("details", {}, el("summary", {class: "muted small"}, "what the kit's audit says"),
      el("pre", {class: "small"}, g.lines.join("\n"))));
  const fails = a.fails || [], warns = a.warnings || [];
  $("#k-audit").replaceChildren(
    ...(fails.length ? [el("div", {class: "warnline"}, `The kit's audit stopped the install: ${plural(fails.length, "piece")} ` +
        "would be broken in game. Leave them out and Install again - or take them out of the basket.")] : []),
    ...fails.map(g => row(g, "bad", g => g.gates.join(", "))),
    ...(warns.length ? [el("div", {class: "muted"}, `The last build has ${plural(warns.length, "warning")} - Install goes on with ` +
        "it: a helm sits a little off on some bodies (look at its picture in the ",
        el("a", {href: "#", onclick: ev => { ev.preventDefault(); openSheets(); }}, "preview pictures folder"),
        "; leave it out if it looks wrong)")] : []),
    ...warns.map(g => row(g, "warn", g => g.bodies.length ? `on ${g.bodies.join(", ")}` : "")));
  $("#k-audit").hidden = !(fails.length || warns.length);
}

// ---------------------------------------------------------------------------- settings
// Where the client, the server and the items are. Browse opens Windows' own picker (the server
// shows it: a page can't ask for a folder's path); each field says what it found there.
const ST = {v: null};
async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const out = await r.json();
  if (!r.ok) throw new Error(out.error || r.statusText);
  return out;
}
async function openSettings() {
  try { ST.v = await api("/api/settings"); } catch (e) { $("#st-note").textContent = e.message; return; }
  renderSettings();
}
function stField(key, label, value, {hint = "", check = key, file = false, patterns = null, placeholder = ""} = {}) {
  const v = ST.v, input = el("input", {id: "st-" + key, value: value || "", spellcheck: "false", placeholder});
  const found = v.checks[check];
  const browse = v.picker ? el("button", {class: "btn ghost", type: "button", onclick: async () => {
    try {
      const r = await post("/api/pick", {folder: !file, title: label, start: input.value, patterns});
      if (r.path) input.value = r.path;
    } catch (e) { toast(e.message); }
  }}, "Browse…") : null;
  return el("div", {class: "field", "data-key": key},
    el("span", {class: "flabel"}, label),
    el("span", {class: "frow"}, input, browse),
    found ? el("span", {class: "fcheck " + (found[0] ? "ok" : "warn")}, (found[0] ? "✓ " : "! ") + found[1]) :
      hint ? el("span", {class: "fhint muted"}, hint) : null);
}
function stChoice(key, title, sub, pathLabel, extra = null) {
  const s = ST.v[key], name = "st-kind-" + key;
  const wago = el("input", {type: "radio", name, value: "wago", checked: s.kind !== "local"});
  const local = el("input", {type: "radio", name, value: "local", checked: s.kind === "local"});
  const path = stField(key + "-path", pathLabel, s.path, {check: key, hint: "the folder that holds .build.info"});
  const sync = () => { path.hidden = !local.checked; stLocalDeps(); };
  wago.addEventListener("change", sync); local.addEventListener("change", sync);
  path.hidden = !local.checked;
  return el("div", {class: "choice"},
    el("div", {class: "flabel"}, title), el("div", {class: "fhint muted"}, sub),
    el("label", {class: "check"}, wago, " wago.tools ", el("span", {class: "muted"}, "- nothing to install; needs the internet")),
    el("label", {class: "check"}, local, " My own install ", el("span", {class: "muted"}, "- faster, and works while wago.tools is down")),
    path, extra);
}
function stLocalDeps() {
  const any = $$("#st-sources input[type=radio][value=local]").some(r => r.checked);
  $$("#st-sources .field[data-key=dbd], #st-sources .field[data-key=listfile]").forEach(f => f.hidden = !any);
}
function renderSettings() {
  const v = ST.v, k = v.kit;
  $("#st-welcome").hidden = !v.first_run;
  $("#st-data").textContent = v.data_dir;
  $("#st-game").replaceChildren(
    stField("client", "3.3.5a client folder", v.client, {hint: "the folder with Wow.exe (or the x64 client's WowClient64.exe) and Data"}),
    stField("server_dbc", "Server dbc folder (optional)", v.server_dbc,
            {hint: "Install adds the new items to Item.dbc and ItemDisplayInfo.dbc here. Empty: the server is left alone.",
             placeholder: "e.g. D:\\AzerothCore\\Data\\dbc"}));
  const route = v.route || "kit", routeCheck = v.checks.route;
  const routeChoice = (val, label, sub) => [el("label", {class: "check"},
    el("input", {type: "radio", name: "st-route", value: val, checked: route === val}), " " + label),
    el("span", {class: "fhint muted route-sub"}, sub)];
  $("#st-route").replaceChildren(el("div", {class: "choice"},
    ...routeChoice("kit", "Backport kit", "Converts each look for any 3.3.5a client, 32-bit or x64 (Equip Plus adds the 3D pieces)."),
    ...routeChoice("direct", "Retail direct", "Retail's own items, as they are, into the x64 client, and item SQL for your " +
                   "server: nothing converted, so nothing to measure or audit."),
    routeCheck ? el("span", {class: "fcheck " + (routeCheck[0] ? "ok" : "warn")}, (routeCheck[0] ? "✓ " : "! ") + routeCheck[1]) :
      el("span", {class: "fhint muted"}, v.direct.x64 ? "Your client is the x64 client: either way works." :
        "Retail direct needs the x64 client (WowClient64.exe) and retail read from your own install."),
    el("span", {class: "fhint muted"}, "Each way keeps its own install and Undo. Retail direct's items show retail's own " +
       "looks, which a 32-bit client can't draw; it builds in " + v.direct.work + ".")));
  const bfaBrowse = el("label", {class: "check"}, el("input", {type: "checkbox", id: "st-bfa-browse", checked: v.bfa.browse}),
                       " Also browse BfA's items (a second tab)");
  $("#st-sources").replaceChildren(
    stChoice("retail", "Retail items", "Everything you browse and backport.", "Retail install folder"),
    stChoice("bfa", "BfA 8.3.7", "The bodies the character view dresses items on.", "BfA 8.3.7 install folder", bfaBrowse),
    stField("dbd", "WoWDBDefs definitions folder", v.dbd, {hint: "a local install's tables are read with these (github.com/wowdev/WoWDBDefs)"}),
    stField("listfile", "Community listfile", v.listfile, {file: true, patterns: [["Listfile", "*.csv;*.txt"]],
            hint: "names a local install's files (github.com/wowdev/wow-listfile)"}));
  stLocalDeps();
  $("#st-kit").replaceChildren(
    stField("work", "Project folder", k.work, {hint: "where the kit builds; Install makes it if it's new"}),
    el("div", {class: "field"}, el("span", {class: "flabel"}, "The kit and Equip Plus's tools"),
      el("span", {class: "fhint muted"}, "The workbench's own copies, the same for everyone - downloaded from their " +
         "authors' GitHub by the first Install, at the commits this workbench is checked with:"),
      ...Object.values(k.own || {}).map(o => el("span", {class: "fcheck " + (o.have ? "ok" : "")},
        `${o.have ? "✓" : "•"} ${o.label} - github.com/${o.repo} at ${o.ref}` + (o.have ? "" : " (Install downloads it)")))),
    el("label", {class: "check"}, el("input", {type: "checkbox", id: "st-local", checked: k.local}),
       " The kit reads retail from my install when its project's build matches"),
    (() => {
      const found = v.checks.equip_plus;
      return el("div", {class: "field"}, el("span", {class: "flabel"}, "3D armor pieces (Equip Plus)"),
        el("span", {class: "frow"}, el("select", {id: "st-equip_plus"},
          [["auto", "When my client has Equip Plus"], ["on", "Always"], ["off", "Never"]].map(([val, label]) =>
            el("option", {value: val, selected: (k.equip_plus || "auto") === val}, label)))),
        found ? el("span", {class: "fcheck " + (found[0] ? "ok" : "warn")}, (found[0] ? "✓ " : "! ") + found[1]) : null);
    })(),
    el("label", {class: "check"}, el("input", {type: "checkbox", id: "st-armor_pieces", checked: k.armor_pieces}),
       " Equip Plus: HD-skinned armor pieces too"),
    (() => {
      const ep = v.equip_plus;
      if (!ep || !ep.installed) return el("div", {class: "fhint muted"},
        "Live physics and better fit are options of Equip Plus in your client - it isn't there.");
      if (ep.builtin) return el("div", {class: "fhint muted"},
        "The x64 client draws Equip Plus's pieces itself; its live physics and fit options aren't in it yet.");
      const box = (id, on, label, hint) => el("label", {class: "check", title: hint},
        el("input", {type: "checkbox", id, checked: on, disabled: id === "st-ep-physics" && !ep.physics}), " " + label);
      return el("div", {class: "field"},
        el("span", {class: "flabel"}, "Equip Plus in your client (saved in its WXLExtendedEquipment.ini)"),
        box("st-ep-physics", ep.options.physics, "Live physics (experimental): plumes, ribbons and chains swing",
            "Retail's own physics engine, as the kit ports it - Equip Plus 1.3.0 runs it; also in its F9 panel in game"),
        box("st-ep-pivots", ep.options.pivots, "Better fit: move retail pieces' parts to the body's matching bones", "[Fit] RetargetPivots"),
        box("st-ep-scale", ep.options.scale, "Better fit: size retail pieces to the body's skeleton", "[Fit] RetargetScale"),
        ep.physics ? el("span", {class: "fhint muted"}, "Pieces get their physics data when they're installed with Equip Plus 1.3.0's tools.")
                   : el("span", {class: "fcheck warn"}, "! Your client's Equip Plus is older than 1.3.0 - live physics needs 1.3.0 " +
                                                       "(github.com/TheDaveCalaz/wxl-equip-plus/releases)"));
    })());
}
async function saveSettings() {
  const val = id => ($("#st-" + id) || {value: ""}).value.trim();
  const kind = key => ($(`input[name=st-kind-${key}]:checked`) || {value: "wago"}).value;
  const body = {client: val("client"), server_dbc: val("server_dbc"),
    retail: {kind: kind("retail"), path: val("retail-path")},
    bfa: {kind: kind("bfa"), path: val("bfa-path"), browse: $("#st-bfa-browse").checked},
    dbd: val("dbd"), listfile: val("listfile"),
    route: ($("input[name=st-route]:checked") || {value: "kit"}).value,
    kit: {work: val("work"), local: $("#st-local").checked,
          armor_pieces: $("#st-armor_pieces").checked, equip_plus: $("#st-equip_plus").value}};
  if ($("#st-ep-physics")) body.equip_plus_options = {physics: $("#st-ep-physics").checked, pivots: $("#st-ep-pivots").checked,
                                                       scale: $("#st-ep-scale").checked};
  $("#st-save").disabled = true;
  try {
    ST.v = await post("/api/settings", body);
    renderSettings();
    $("#st-note").textContent = "Saved. A source you changed is being read again.";
    PV.races = []; PV.bodies.clear();
    pollStatus();
  } catch (e) { $("#st-note").textContent = e.message; }
  finally { $("#st-save").disabled = false; }
}

// ---------------------------------------------------------------------------- backport (the kit)
// One button: Install builds what the basket needs (the kit's steps, only those not done for it)
// and installs it. Settings and the steps themselves are folded away below.
const K = {status: null, since: 0, follow: true, timer: null, logLoaded: false, was: false};
async function loadKit() {
  try { K.status = await api("/api/kit"); }
  catch (e) { $("#k-data").textContent = e.message; return scheduleKit(); }
  if (!K.logLoaded) { K.logLoaded = true; await pollKitLog(); }
  const running = kitRunning();
  if (K.was && !running) {                         // a job just ended
    const j = K.status.job;
    toast(j.name === "go" ? (j.state === "ok" ? "Installed" : `Install ${j.state}`) : `${j.name}: ${j.state}`);
    if (S.view === "basket") renderBasket();
  }
  K.was = running;
  renderKit();
  scheduleKit();
}
function kitRunning() { return !!(K.status && K.status.job && K.status.job.state === "running"); }
function scheduleKit() {
  clearTimeout(K.timer);
  if (kitRunning() || S.view === "backport")
    K.timer = setTimeout(async () => { await pollKitLog(); loadKit(); }, kitRunning() ? 900 : 5000);
}
async function pollKitLog() {
  try {
    const r = await api("/api/kit/log", {since: K.since});
    if (r.lines.length) {
      const pre = $("#k-log");
      pre.textContent = (pre.textContent + r.lines.join("\n") + "\n").slice(-400000);
      if (K.follow) pre.scrollTop = pre.scrollHeight;
    }
    K.since = r.next;
  } catch (e) { /* the status poll reports it */ }
}
const slash = p => p.replace(/\\/g, "/");
function stepWords(step) {
  if (step === "install") return "Put the patch in your client";
  if (step === "create") return "Create the kit's project";
  const x = K.status && K.status.steps.find(x => x.step === step);
  return x ? x.words : step;
}
function renderKit() {
  const st = K.status, c = st.settings, running = kitRunning(), j = st.job, direct = st.route === "direct";
  const pl = st.plan || {basket: S.basket.length, adds: S.basket.length, in_game: 0, take_out: 0, builds: S.basket.length};
  const n = pl.builds, last = st.last_install;

  // what Install does now
  const parts = [pl.adds ? `adds ${plural(pl.adds, "entry")} from the basket` : "",
                 pl.basket - pl.adds ? `changes ${pl.basket - pl.adds}` : "",
                 pl.take_out ? `takes out ${pl.take_out}` : "",
                 pl.in_game - pl.take_out - (pl.basket - pl.adds) > 0 ? `keeps ${pl.in_game - pl.take_out - (pl.basket - pl.adds)} in your game` : ""]
    .filter(Boolean);
  const state = !n ? "" : st.installed ? "Your client has all of it already." :
    st.built ? "Built - Install puts it in." :
    last ? "Install builds what's new, then puts it in." : "Install builds it, then puts it in.";
  $("#k-what").replaceChildren(
    el("div", {class: "install-line"}, !n ? "The basket is empty - add items or sets first." :
       parts.length ? `Install ${parts.join(", ")}.` : "Install builds what's in your game again."),
    el("div", {class: "muted"}, state, " ",
      el("a", {href: "#", onclick: ev => { ev.preventDefault(); show("basket"); }}, n ? "Review the basket" : "Go to the basket")));
  const toSettings = text => el("a", {href: "#", onclick: ev => { ev.preventDefault(); show("settings"); }}, text);
  $("#k-where").replaceChildren(
    el("div", {}, el("span", {class: "k"}, "Way"), direct ? "Retail direct - retail's own items into the x64 client" :
      "Backport kit - converted for any 3.3.5a client", " ", toSettings("change")),
    el("div", {}, el("span", {class: "k"}, "Client"), c.client_data || el("span", {class: "warn"}, "not set"), " ", toSettings("change")),
    direct ? el("div", {}, el("span", {class: "k"}, "Server"), el("span", {class: "muted"}, "item SQL for you to apply (its dbc folder is left alone)")) :
    el("div", {}, el("span", {class: "k"}, "Server"), c.server_dbc ||
      el("span", {class: "muted"}, "left alone - set its dbc folder in Settings to add the items there too"),
      c.server_dbc ? " " : "", c.server_dbc ? toSettings("change") : ""));
  const notes = [];
  if (direct) {
    if (st.retail_build) notes.push(`<span class="ok">✓</span> Retail ${st.retail_build}'s own tables and files, straight from ` +
      `your local install into ${st.patch_name} - nothing converted.`);
    const sm = st.summary || {};
    if (sm.files) notes.push(`Last build: ${plural(sm.items || 0, "item")}, ${plural(sm.files, "file")} (${sm.mb} MB)` +
      (sm.unreadable ? `, <span class="warn">${sm.unreadable} unreadable from your install</span>` : "") + ".");
    const cc = sm.client_check;
    if (cc) notes.push((cc.failed.length ? `<span class="warn">!</span> ` : `<span class="ok">✓</span> `) +
      `Checked in the client ${when(cc.time)}: ${cc.same} of ${plural(cc.models, "model")} read as retail has them` +
      (cc.differs.length ? `, ${cc.differs.length} drawn differently` : "") +
      (cc.failed.length ? `, <span class="warn">${cc.failed.length} not read</span> (the log names them)` : "") + ".");
  } else if (st.project) {
    if (st.local) notes.push(`<span class="ok">✓</span> Retail ${st.project.build} straight from your local install.`);
    else if (c.local && st.retail_build) notes.push(`<span class="warn">!</span> The kit's project is pinned to retail ${st.project.build}; ` +
      `your install is ${st.retail_build}, so its files come from wago.tools.`);
  }
  for (const p of st.problems) notes.push(`<span class="warn">!</span> Settings: ${p}`);
  if (st.mount_problem) notes.push(`<span class="warn">!</span> ${st.mount_problem}`);
  if (st.mount_stale) notes.push(`<span class="warn">!</span> ${st.mount_stale.join(", ")} changed after your mounts went in ` +
    `(a race package installed again?): its new spell, creature and sound rows are hidden until you Install again.`);
  if (st.mount_icons_gone) notes.push(`<span class="warn">!</span> ${st.mount_icons_gone.join(", ")} was replaced after your ` +
    `mounts went in (another install?): the items that teach them show a red question mark until you Install again.`);
  if (st.mounts && !st.mount_problem) notes.push(`${plural(st.mounts, "mount")}: ` + (direct ?
    "retail's own models, in the same patch." : `converted for any 3.3.5a client, in a patch of their own (patch-M).`) +
    " Each is a spell, its creature with retail's sounds and the item that teaches it (retail's icon) - in the SQL to apply.");
  if (st.foreign) notes.push(`<span class="warn">!</span> Your backport project has ${plural(st.foreign, "look")} made outside the ` +
    `workbench that aren't in your basket - <a href="#" data-go="basket">bring them in or let them go</a> first.`);
  if (st.stats && st.stats.without) notes.push(`<span class="warn">!</span> ${st.stats.without} of ${plural(st.stats.pieces, "piece")} ` +
    `have no stats yet - they'll be level-1 cosmetic copies. <a href="#" data-go="stats">Give them stats</a>`);
  if (!direct && st.equip_plus && !st.equip_plus.wanted) notes.push(`Equip Plus isn't in your client: Install leaves out the extra 3D pieces ` +
    `(skirts, boot shells, buckles, 3D capes); everything else works on any 3.3.5a client.`);
  renderAudit(st.audit || {warnings: [], fails: []}, running);
  $("#stats-state").textContent = st.stats && st.stats.without ? st.stats.without : "";
  $("#stats-state").hidden = !(st.stats && st.stats.without);
  $("#k-data").innerHTML = notes.join("<br>");
  $$("#k-data a[data-go]").forEach(a => a.addEventListener("click", ev => { ev.preventDefault(); show(a.dataset.go); }));

  $("#k-go").disabled = running || !n || st.problems.length > 0 || !!st.foreign;
  $("#k-go").textContent = running && j.name === "go" ? "Installing…" : st.installed ? "Install again" : "Install";
  $("#k-stop").hidden = !running;
  $("#k-undo").disabled = running || !last;
  // retail direct: the installed models read by the client itself (its model check mode)
  $("#k-check").hidden = !direct || !last;
  $("#k-check").disabled = running;
  $("#k-check").textContent = running && j.name === "check" ? "Checking…" : "Check in the client";
  $("#k-build").disabled = running || !st.project || !n;

  // progress: the job's steps, each ticked as this job passes it (a new install starts them all clear)
  const done = s => (j && j.done || []).includes(s);
  if (j && (j.name === "go" || j.name === "build" || j.name.startsWith("rerun"))) {
    const go = j.name === "go";
    const rows = [...(go && (!st.project || j.step === "create") ? [["create", "Create the kit's project"]] : []),
                  ...st.steps.map(x => [x.step, x.words]),
                  ...(go && st.mounts && st.route !== "direct" ? [["mounts", `Make the ${plural(st.mounts, "mount")}`]] : []),
                  ...(go ? [["install", "Put the patch in your client" + (c.server_dbc ? " and the items on your server" : "")]] : [])];
    const cur = rows.findIndex(([s]) => s === j.step);
    $("#k-progress").replaceChildren(el("div", {class: "steps"}, rows.map(([s, words], i) => {
      const ok = done(s);
      const mark = running && i === cur ? ["run", "…"] : !running && j.state !== "ok" && i === cur ? ["bad", "✗"] : ok ? ["ok", "✓"] : ["", "•"];
      const idle = s === "measure" && st.measure && !st.measure.needed && !st.measure.done;
      return el("div", {class: "srow"}, el("span", {class: mark[0]}, mark[1]), el("span", {}, words,
        idle ? el("span", {class: "muted"}, " - not needed for weapons") : null));
    })));
  } else $("#k-progress").replaceChildren();

  // the outcome, and the one thing left to you: the item SQL
  const result = [];
  if (j && !running && j.state !== "ok") {
    result.push(el("div", {class: "warnline"}, j.state === "stopped" ? "Stopped." :
      `It stopped at "${stepWords(j.step) || j.name}". The log below says why; nothing was installed by this run.`));
    if (!K.openedLog) { $("#k-log-panel").open = true; K.openedLog = true; }
  } else K.openedLog = false;
  if (last) {
    result.push(el("div", {class: "kit-note"}, `Last install ${when(last.time)}: ` +
      [...last.client, ...last.added.map(a => a.split(/[\\/]/).pop())].join(", ") +
      (last.server.length ? `; server ${last.server.join(", ")}` : "") + ". Restart the worldserver, then log in" +
      (direct ? " with the x64 client." : ".")));
    for (const p of st.sql) result.push(el("div", {class: "kit-note sql"}, "Yours to do: apply the item SQL to your world database - ",
      el("code", {}, `SOURCE ${slash(p)};`), " ", el("button", {class: "copy", onclick: () => copy(`SOURCE ${slash(p)};`)}, "copy")));
  }
  $("#k-result").replaceChildren(...result);

  $("#k-job").textContent = !j ? "Log" : running ? `Log · ${j.name === "go" ? "install" : j.name}: ${j.step || "starting"} …` :
    `Log · ${j.name === "go" ? "install" : j.name}: ${j.state} (${new Date(j.ended * 1000).toLocaleTimeString()})`;
  $("#kit-state").textContent = running ? "…" : "";
  $("#kit-state").hidden = !running;

  // advanced: the kit's own steps, each redoable (retail direct's run together every time)
  $("#k-steps-title").textContent = direct ? "Retail direct's steps" : "The kit's steps";
  $("#k-steps-note").textContent = direct ? "Install runs these every time (they take a minute or so); Build only stops " +
    "before the install, so you can look at the patch and the SQL first." : "Install runs these for you. Redo one when you " +
    "changed something by hand; Build only stops before the install. The kit draws a preview picture of each piece into " +
    "the project's sheets folder.";
  $("#k-steps").replaceChildren(...st.steps.map(x => {
    const mark = running && j.step === x.step ? ["run", "…"] : x.ok === true ? ["ok", "✓"] : x.ok === false ? ["bad", "✗"] : ["", "•"];
    return el("div", {class: "srow", title: x.at ? `${x.ok ? "passed" : "failed"} ${x.at}` : "not run yet"},
      el("span", {class: mark[0]}, mark[1]),
      el("span", {}, x.step, " ", el("span", {class: "sw"}, x.words)),
      x.step === "select" || direct ? el("span") :
        el("button", {class: "redo", disabled: running, onclick: () => kitRun("rerun", x.step)}, "redo from here"));
  }));
  $("#k-open-sheets").hidden = !st.sheets;
}
async function openSheets() {
  try { await post("/api/kit/open-sheets", {}); } catch (e) { toast(e.message); }
}
async function kitRun(action, step = "") {
  try {
    const r = await fetch("/api/kit/run", {method: "POST", headers: {"Content-Type": "application/json"},
                                           body: JSON.stringify({action, step})});
    const body = await r.json();
    if (!r.ok) return toast(body.error || "failed");
    K.status = body; K.was = kitRunning(); K.openedLog = false; renderKit(); K.follow = true; scheduleKit();
  } catch (e) { toast(e.message); }
}
function wireKit() {
  $("#st-save").addEventListener("click", saveSettings);
  $("#k-build").addEventListener("click", () => kitRun("build"));
  $("#k-stop").addEventListener("click", () => kitRun("stop"));
  $("#k-go").addEventListener("click", () => {
    const c = K.status.settings;
    const pl = K.status.plan || {};
    if (K.status.route === "direct") {
      if (confirm(`Install retail's own items into the x64 client - ${pl.adds ? `adding ${plural(pl.adds, "entry")} from the basket` :
                  "the basket"}${pl.take_out ? `, taking out ${pl.take_out}` : ""}${pl.in_game ? ", keeping the rest of your game" : ""}:\n` +
                  `${c.client_data}\n\nIt writes ${K.status.patch_name} (backing up the one it replaces - Undo puts it back) and ` +
                  "the item SQL for your server, which you apply. It runs no SQL and leaves the server's dbc folder alone. Close WoW first."))
        kitRun("go");
      return;
    }
    if (confirm(`Install into your client - ${pl.adds ? `adding ${plural(pl.adds, "entry")} from the basket` : "the basket"}` +
                `${pl.take_out ? `, taking out ${pl.take_out}` : ""}${pl.in_game ? ", keeping the rest of your game" : ""}:\n${c.client_data}\n` +
                (c.server_dbc ? `\nand add its items to the server's dbc files:\n${c.server_dbc}\n` :
                                "\nThe server's dbc folder isn't set, so the server is left alone.\n") +
                "\nIt builds what changed first (that can take a while), backs up everything it replaces " +
                "(Undo puts it back) and runs no SQL. Close WoW first."))
      kitRun("go");
  });
  $("#k-check").addEventListener("click", () => {
    if (confirm("Check the last install in the x64 client? WoW opens in its check mode (no login), reads every " +
                `model ${K.status.patch_name} holds the way play reads them, and closes by itself - about a second ` +
                "a model. The log lists any it refuses or draws differently. Close WoW first."))
      kitRun("check");
  });
  $("#k-undo").addEventListener("click", () => {
    const l = K.status.last_install;
    if (l && confirm(`Undo the install of ${when(l.time)}? It puts back ${[...l.client, ...l.server].join(", ") || "nothing"} ` +
                     `and removes ${l.added.length} added file(s).`)) kitRun("undo");
  });
  $("#basket-history-btn").addEventListener("click", ev => {
    const h = $("#basket-history");
    h.hidden = !h.hidden;
    ev.currentTarget.setAttribute("aria-expanded", String(!h.hidden));
  });
  $("#basket-clear").addEventListener("click", () => {
    if (S.basket.length && confirm(`Take all ${S.basket.length} entries out of the basket?`))
      removeEntries(S.basket.map(keyOf), "everything");
  });
  $("#k-log").addEventListener("scroll", e => { const p = e.target; K.follow = p.scrollTop + p.clientHeight >= p.scrollHeight - 30; });
  $("#k-log-bottom").addEventListener("click", ev => {
    ev.preventDefault(); $("#k-log-panel").open = true;
    K.follow = true; const p = $("#k-log"); p.scrollTop = p.scrollHeight;
  });
}

// ---------------------------------------------------------------------------- 3D preview
// One viewer for the drawer. An item shows its own models alone - or, when it has none (a cloth
// cloak, armour drawn on the body), itself on a character wearing only it. A set is dressed on a
// character; a set of one kind (weapons, masks, cloaks) shows one piece at a time, ◀ ▶ under it.
const PV = {viewer: null, race: "hu", sex: 0, token: 0, races: [], bodies: new Map(), step: null};
try { const s = JSON.parse(localStorage.getItem("wb-preview") || "{}"); PV.race = s.race || "hu"; PV.sex = s.sex || 0; } catch (e) { /* defaults */ }
const HELD = [13, 14, 15, 17, 21, 22, 23, 25, 26];
const BACK = 16, CAPE = 5;                         // the back slot; ModelType 5: a cloak drawn on the body
function previewViewer() {
  if (!PV.viewer) {
    const canvas = el("canvas", {class: "viewer", title: "Left-drag to turn · right-drag to move · wheel to zoom · double-click to reset"});
    try { PV.viewer = new Viewer(canvas); } catch (e) { PV.error = e.message; return null; }
  }
  return PV.viewer;
}
// the race and sex choice: the races your 3.3.5 client plays
function raceSexPicker(onChange) {
  const races = PV.races.length ? PV.races : [{key: "hu", name: "Human"}];
  if (!races.some(r => r.key === PV.race)) PV.race = races[0].key;
  const race = el("select", {"aria-label": "Race"}, races.map(r => el("option", {value: r.key, selected: r.key === PV.race}, r.name)));
  const sex = el("select", {"aria-label": "Sex"}, el("option", {value: 0, selected: PV.sex === 0}, "Male"),
                 el("option", {value: 1, selected: PV.sex === 1}, "Female"));
  const changed = () => {
    PV.race = race.value; PV.sex = +sex.value;
    try { localStorage.setItem("wb-preview", JSON.stringify({race: PV.race, sex: PV.sex})); } catch (e) { /* private window */ }
    onChange();
  };
  race.addEventListener("change", changed); sex.addEventListener("change", changed);
  return el("span", {class: "pv-pick"}, race, sex);
}
const texUrl = source => fdid => `/tex/${source}/${fdid}.png`;
// A collection model is shared by many items (a whole set's belt, boots, hood...): each shows only the
// parts of the body groups its own slot controls, at 1 + its AttachmentGeosetGroup value for that group.
function collectionShows(slot, row, id) {
  const groups = (S.meta.item_geosets || {})[slot] || [], i = groups.indexOf(Math.floor(id / 100));
  return i >= 0 && id % 100 === 1 + ((row && row.attachment_geosets[i]) || 0);
}
// A model of its own (a helm, shoulders, a buckle) shows its slot's groups at 1 + its AttachmentGeosetGroup
// value, or at 1 + the display's GeosetGroupOverride when that is higher (the Heroic and Mythic tier looks
// whose bigger x02 parts show - as the kit builds them); everything else in it draws.
function attachedShows(slot, row, id) {
  const groups = (S.meta.item_geosets || {})[slot] || [], i = groups.indexOf(Math.floor(id / 100));
  if (id < 100 || i < 0 || !row) return true;
  const agg = row.attachment_geosets[i] || 0;
  return agg < 0 || id % 100 === 1 + Math.max(agg, row.geoset_override || 0);
}
function textureThumb(source) {
  return t => el("a", {href: `/tex/${source}/${t.fdid}.png`, target: "_blank", title: `${t.name} · ${t.fdid}`},
    el("img", {src: `/tex/${source}/${t.fdid}.png`, loading: "lazy", alt: t.name}), el("span", {}, t.name));
}
const plural = (n, word) => n === 1 ? `${n} ${word}` : /[^aeiou]y$/.test(word) ? `${n} ${word.slice(0, -1)}ies` : `${n} ${word}s`;

// The preview box: the canvas; under it one row of controls - race and sex, then the versions or the
// ◀ ▶ arrows (add(...) puts them there) - then what's shown and the body textures. load(fn) shows
// something in it, and the race and sex picker shows it again.
function previewBox(cls = "") {
  const box = el("div", {class: "preview" + (cls ? " " + cls : "")});
  const v = previewViewer();
  if (!v) { box.append(el("div", {class: "muted"}, PV.error || "No WebGL")); return {box, load: () => {}, add: () => false}; }
  const pb = {box, v, info: el("div", {class: "pv-info muted"}, "Loading…"), textures: el("div", {class: "pv-body"}), current: null,
              controls: el("div", {class: "pv-controls"}, raceSexPicker(() => pb.current && pb.current()))};
  pb.load = fn => { pb.current = fn; fn(); };
  pb.add = (...kids) => { pb.controls.append(...kids); return true; };
  box.append(v.canvas, pb.controls, pb.info, pb.textures);
  return pb;
}
// versions as chips: [{label, icon?, title?, on, pick()}]
function versionChips(list) {
  const chips = list.map(x => el("button", {class: "chip" + (x.on ? " on" : ""), title: x.title || "",
    onclick: ev => { chips.forEach(c => c.classList.toggle("on", c === ev.currentTarget)); x.pick(); }}, x.icon || null, x.label));
  return el("div", {class: "chips pv-versions", role: "group", "aria-label": "Versions"}, chips);
}

// One display: its models alone; with none, the piece on a character (a cloak seen from behind).
function loadDisplay(pb, display, slot, from = null) {
  pb.load(async () => {
    const v = pb.v, token = ++PV.token, source = from || S.source;
    pb.info.textContent = "Loading…";
    try {
      const p = await api("/api/preview", {source, display, race: PV.race, sex: PV.sex});
      if (token !== PV.token) return;
      pb.textures.replaceChildren(...p.body.map(textureThumb(source)));
      const cape = slot === BACK && p.row && p.row.model_types[0] === CAPE && p.row.materials[0];
      if (!p.models.length && (cape || p.body.length)) {
        const picker = pb.controls.querySelector(".pv-pick");
        if (picker) picker.hidden = false;
        const got = await dress(v, [{display, slot}], token, source);
        if (!got) return;
        v.fit(cape ? "back" : "front");
        v.draw();
        pb.info.textContent = `On ${/^[aeiou]/i.test(got.who) ? "an" : "a"} ${got.who} · ` +
          (cape ? "a cloak, drawn on the body's cape" : "drawn on the body - its textures below");
        notes(pb.info, got.outfit.problems);
        return;
      }
      v.clear();
      // a held piece shown by itself is the same on every body: no race or sex to pick
      const picker = pb.controls.querySelector(".pv-pick");
      if (picker) picker.hidden = HELD.includes(slot) && p.models.length > 0;
      for (const m of p.models) {
        // shoulders: the left one (position 0) on the wearer's left (+Y), the right one on the right
        const offset = slot === 3 && m.position >= 0 ? [0, m.position === 0 ? 0.21 : -0.21, 0] : [0, 0, 0];
        v.add(m.mesh, {texUrl: texUrl(source), offset,
                       visible: id => (m.type === 1 ? collectionShows : attachedShows)(slot, p.row, id)});
      }
      v.fit(HELD.includes(slot) ? "held" : "front", slot);
      v.canvas.hidden = !p.models.length;
      v.draw();
      const tris = p.models.reduce((n, m) => n + m.mesh.triangles, 0);
      pb.info.textContent = p.models.length ? `${plural(p.models.length, "model")} · ${tris.toLocaleString()} triangles` +
        (p.body.length ? " · plus textures on the body" : "") +
        (p.models.some(m => m.type === 1) ? " · worn on the body: see it on a character in its set" : "") : "No model or texture found.";
      if (p.shown_as) notes(pb.info, [p.made_for ? `Made for ${p.made_for} only - shown as theirs` : `No model for this race - shown as the ${p.shown_as}'s`]);
      notes(pb.info, p.problems);
    } catch (e) { if (token === PV.token) pb.info.textContent = e.message; }
  });
}
function notes(info, lines) { for (const l of lines || []) info.append(el("div", {class: "warnline"}, l)); }

// One item's preview section (an item's panel).
function itemPreview(display, slot) {
  const pb = previewBox();
  if (pb.v) loadDisplay(pb, display, slot);
  return Object.assign(section("Preview", pb.box), {pb});
}

// A set of one kind, one piece at a time: ◀ n / N ▶ under the preview (and the ← → keys).
// pieces: [{display, slot, name}]; rows: each piece's row in the list, marked while shown.
function carouselSection(pieces, rows) {
  const pb = previewBox();
  if (!pb.v) return Object.assign(section("Preview", pb.box), {pb});
  let k = 0;
  const label = el("span", {class: "pv-step-label"});
  const show = () => {
    const p = pieces[k];
    label.textContent = `${k + 1} / ${pieces.length} · ${p.name}`;
    rows.forEach((r, i) => r && r.classList.toggle("on", i === k));
    loadDisplay(pb, p.display, p.slot);
  };
  const go = d => { k = (k + d + pieces.length) % pieces.length; show(); };
  PV.step = pieces.length > 1 ? go : null;
  const nav = el("div", {class: "pv-nav"},
    el("button", {class: "btn ghost step", title: "Previous (←)", disabled: pieces.length < 2, onclick: () => go(-1)}, "◀"),
    label,
    el("button", {class: "btn ghost step", title: "Next (→)", disabled: pieces.length < 2, onclick: () => go(1)}, "▶"));
  if (pieces.length > 1) pb.add(nav);
  show();
  return Object.assign(section("Preview", pb.box), {pb});
}

// -- the character view -------------------------------------------------------------------------
async function bodyOf(race, sex) {
  const key = `${race}:${sex}`;
  if (!PV.bodies.has(key)) PV.bodies.set(key, api("/api/body", {race, sex}));
  try { return await PV.bodies.get(key); } catch (e) { PV.bodies.delete(key); throw e; }
}
function loadImage(url) {
  return new Promise((ok, bad) => { const i = new Image(); i.onload = () => ok(i); i.onerror = bad; i.src = url; });
}
// The geoset each body group shows: the body's own (hair, facial hair, bare hands and feet...), then
// each piece's GeosetGroup values in the order the client dresses (value v shows group*100 + 1 + v),
// then what a helm hides.
function wornGeosets(body, outfit) {
  const a = {};
  for (const [g, v] of Object.entries(body.geosets)) a[+g] = v;
  for (const slot of outfit.dress_order) for (const pc of outfit.pieces.filter(p => p.slot === slot)) {
    (outfit.item_geosets[slot] || []).forEach((g, i) => {
      let v = pc.row.geoset_groups[i] || 0;
      // retail's boots say -1 for the feet (no feet: its newer bodies' boot geosets cover them); BfA's
      // bodies keep their feet for the boot's foot texture, as BfA's own data has those boots (0)
      if (g === FEET && v < 0) v = 0;
      a[g] = 1 + v;
    });
  }
  for (const pc of outfit.pieces) for (const g of pc.hides) a[g] = g === 0 ? -1 : 1;
  // a value the body has no geoset for (retail's newer bodies have more boot and feet shapes than
  // BfA's): the nearest one below it the body has, so the leg doesn't vanish
  const has = new Set(body.mesh.batches.map(b => b.geoset));
  for (const g of Object.keys(a).map(Number)) {
    if (g === 0 || a[g] <= 0 || has.has(g * 100 + a[g])) continue;
    let v = a[g];
    while (v > 1 && !has.has(g * 100 + v)) v--;
    if (has.has(g * 100 + v)) a[g] = v;
  }
  return a;
}
const FEET = 20;                                   // the feet geoset group
function shows(a, id, hair) {
  if (id === 0) return true;
  const g = Math.floor(id / 100), v = id % 100;
  if (g === 0) return hair && a[0] > 0 && id === a[0];
  const want = g in a ? a[g] : 1;
  return want >= 0 && v === want;
}
// The skin as the client composites it: the body's layers, then each piece's section textures.
async function compositeSkin(body, outfit, source) {
  const L = body.layout, c = document.createElement("canvas");
  c.width = L.width; c.height = L.height;
  const draws = body.skin.map(([sec, fdid]) => [sec, `/tex/bfa/${fdid}.png`]);
  for (const slot of outfit.dress_order) for (const pc of outfit.pieces.filter(p => p.slot === slot))
    for (const t of pc.body) draws.push([t.section, `/tex/${source}/${t.fdid}.png`]);
  const imgs = await Promise.all(draws.map(([, u]) => loadImage(u).catch(() => null)));
  const ctx = c.getContext("2d");
  draws.forEach(([sec], i) => {
    const img = imgs[i];
    if (!img) return;
    if (sec < 0) ctx.drawImage(img, 0, 0, L.width, L.height);
    else { const r = L.sections[sec]; if (r) ctx.drawImage(img, r[0], r[1], r[2], r[3]); }
  });
  return c;
}
// The viewer dressed: the race's body, its skin composited, then each piece's geosets and models.
// pieces: [{display, slot, name?}]. Returns what it drew, or null when a newer load took over.
async function dress(v, pieces, token, from = null) {
  const source = from || S.source, race = PV.race, sex = PV.sex;
  const [body, outfit] = await Promise.all([bodyOf(race, sex),
    api("/api/outfit", {source, race, sex, items: pieces.map(p => `${p.display}:${p.slot}`).join(",")})]);
  if (token !== PV.token) return null;
  const skin = await compositeSkin(body, outfit, source);
  if (token !== PV.token) return null;
  const worn = wornGeosets(body, outfit);
  const cape = outfit.pieces.find(p => p.cape);
  v.clear();
  const types = {1: skin};
  if (body.hair) types[6] = `/tex/bfa/${body.hair}.png`;
  if (body.skin_extra) types[8] = `/tex/bfa/${body.skin_extra}.png`;
  if (cape) types[2] = `/tex/${source}/${cape.cape}.png`;
  const bodyPart = v.add(body.mesh, {texUrl: texUrl("bfa"), types, visible: id => shows(worn, id, true)});
  let models = 0;
  for (const slot of outfit.dress_order) for (const pc of outfit.pieces.filter(p => p.slot === slot)) for (const m of pc.models) {
    if (m.type === 1) {
      v.add(m.mesh, {texUrl: texUrl(source), bodyOf: bodyPart, visible: id => collectionShows(slot, pc.row, id)});
    } else if (m.attach >= 0) {
      v.add(m.mesh, {texUrl: texUrl(source), attach: {part: bodyPart, id: m.attach}, visible: id => attachedShows(slot, pc.row, id)});
    }
    models++;
  }
  v.canvas.hidden = false;
  const name = d => (pieces.find(p => p.display === d) || {}).name || `display ${d}`;
  outfit.problems = [...outfit.problems, ...outfit.pieces.filter(p => p.made_for).map(p =>
    `${name(p.display)}: made for ${p.made_for} only - not shown on this race`)];
  return {body, outfit, models, who: `${body.name} ${sex ? "female" : "male"}`};
}
// pieces: [{display, slot, name}] - the set's first piece of each slot
function characterSection(pieces) {
  const pb = previewBox("character");
  if (!pb.v) return Object.assign(section("On a character", pb.box), {pb});
  pb.load(async () => {
    const v = pb.v, token = ++PV.token;
    pb.info.textContent = "Dressing…";
    try {
      const got = await dress(v, pieces, token);
      if (!got) return;
      v.fit("front");
      v.draw();
      pb.info.textContent = `${got.who} · ${plural(got.outfit.pieces.length, "piece")} · ${plural(got.models, "model")}`;
      notes(pb.info, got.outfit.problems);
    } catch (e) { if (token === PV.token) pb.info.textContent = e.message; }
  });
  return Object.assign(section("On a character", pb.box), {pb});
}

// ---------------------------------------------------------------------------- views & wiring
const BROWSE = ["items", "sets", "mounts"];
function show(view) {
  S.view = view;
  $$(".nav[data-view]").forEach(b => b.classList.toggle("on", b.dataset.view === view));
  $$(".view").forEach(v => v.hidden = v.id !== `view-${view}`);
  const open = document.body.classList.contains("drawer-open");
  if (!BROWSE.includes(view) && open) {             // the 3D preview waits while you're elsewhere
    S.reopen = S.open; closeDrawer();
  } else if (BROWSE.includes(view) && !open && S.reopen) {
    const o = S.reopen; S.reopen = null;
    reopen(o);
  }
  if (BROWSE.includes(view)) $(view === "sets" ? "#set-filters" : view === "mounts" ? "#mount-filters" : "#item-filters").prepend($(".search"));
  if (view === "basket") renderBasket();
  if (view === "backport") loadKit();
  if (view === "settings") openSettings();
  if (view === "stats") loadStats();
  $("#q").placeholder = view === "sets" ? "Search sets by name, version or group   ( / )" :
    view === "mounts" ? "Search mounts by name, spell or id   ( / )" : "Search items by name or id   ( / )";
  if (view === "mounts" && !$("#mount-grid").children.length) searchMounts(true);
}
function fill(sel, entries) {
  const s = $(sel);
  for (const [v, label] of entries) s.append(el("option", {value: v}, label));
}
async function init() {
  S.meta = await api("/api/meta");
  const exps = Object.entries(S.meta.expansions).reverse();
  fill("#f-slot", S.meta.slot_groups.map(g => [g, SLOT_LABELS[g] || g]));
  fill("#f-armour", S.meta.armour_types.filter(a => a !== "misc").map(a => [a, a[0].toUpperCase() + a.slice(1)]));
  fill("#f-weapon", Object.entries(S.meta.weapons).sort((a, b) => a[1].localeCompare(b[1])));
  fill("#f-expansion", exps); fill("#s-expansion", exps);
  fill("#f-quality", Object.entries(S.meta.qualities).slice(0, 6).map(([q, v]) => [q, `${v.name} or better`]));
  const classes = Object.entries(S.meta.classes);
  fill("#f-cls", classes); fill("#s-cls", classes);
  fill("#s-armour", ["cloth", "leather", "mail", "plate"].map(a => [a, a[0].toUpperCase() + a.slice(1)]));
  try { S.basket = await api("/api/basket"); } catch (e) { S.basket = []; }
  $("#basket-count").textContent = S.basket.length;

  const search = () => (S.view === "sets" ? searchSets(true) : S.view === "mounts" ? searchMounts(true) : searchItems(true));
  const run = debounce(search, 250);
  $("#q").addEventListener("input", run);
  $("#q").addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); search(); } });
  $$("#mount-filters .seg button").forEach(b => b.addEventListener("click", () => {
    S.mounts.kind = b.dataset.kind;
    $$("#mount-filters .seg button").forEach(x => x.classList.toggle("on", x === b));
    searchMounts(true);
  }));
  $("#m-junk").addEventListener("change", () => searchMounts(true));
  $$("#item-filters select, #item-filters input").forEach(c => c.addEventListener("change", () => searchItems(true)));
  $$("#set-filters select").forEach(c => c.addEventListener("change", () => searchSets(true)));
  $$("#set-filters .seg button").forEach(b => b.addEventListener("click", () => {
    S.sets.kind = b.dataset.kind;
    $$("#set-filters .seg button").forEach(x => x.classList.toggle("on", x === b));
    ["#s-expansion", "#s-cls", "#s-armour"].forEach(s => $(s).disabled = S.sets.kind === "itemset");
    searchSets(true);
  }));
  $$(".nav[data-view]").forEach(b => b.addEventListener("click", () => {
    const was = S.view; show(b.dataset.view);
    if ($("#q").value && was !== b.dataset.view) (b.dataset.view === "sets" ? searchSets(true) : b.dataset.view === "items" ? searchItems(true) :
                                                  b.dataset.view === "mounts" ? searchMounts(true) : null);
  }));
  $("#item-more").addEventListener("click", () => { if (!S.items.loading) { S.items.page++; searchItems(false); } });
  $("#set-more").addEventListener("click", () => { if (!S.sets.loading) { S.sets.page++; searchSets(false); } });
  $("#mount-more").addEventListener("click", () => { if (!S.mounts.loading) { S.mounts.page++; searchMounts(false); } });
  const auto = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && !e.target.hidden) e.target.click(); }),
                                        {root: $("#main"), rootMargin: "400px"});
  auto.observe($("#item-more")); auto.observe($("#set-more")); auto.observe($("#mount-more"));
  $("#drawer-close").addEventListener("click", () => { S.reopen = null; closeDrawer(); });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeDrawer();
    if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && PV.step && document.body.classList.contains("drawer-open") &&
        !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      e.preventDefault(); PV.step(e.key === "ArrowLeft" ? -1 : 1);
    }
    if (e.key === "/" && document.activeElement !== $("#q") && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement.tagName)) {
      e.preventDefault();
      if (!BROWSE.includes(S.view)) show("items");
      $("#q").focus();
    }
  });
  wireKit();
  loadKit();
  pollStatus();
  // the app (app.py) ends with its last page: say this one is open, now and then, and when it closes
  const hello = () => fetch("/api/hello", {method: "POST"}).catch(() => {});
  hello(); setInterval(hello, 30000);
  setInterval(async () => {                               // code changed under a running server: say so
    try { appState(await api("/api/status")); } catch (e) { /* not answering */ }
  }, 30000);
  addEventListener("pageshow", e => { if (e.persisted) hello(); });
  addEventListener("pagehide", () => navigator.sendBeacon("/api/bye"));
}
init();
