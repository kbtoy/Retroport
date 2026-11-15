"use strict";
// My collections: your own sets, put together piece by piece as you browse. Any piece opened on its own (an
// item, a set's piece) has "Add to Custom Collection": the version shown goes into the collection being built,
// in its slot (one piece a slot; a one-handed weapon to the main hand, else the off hand; a two-hander empties
// the off hand). The My collections view shows the collection dressed on the character beside its slots: a
// click on a piece opens it (and "Back to <collection>" returns), x takes it out, and "Add to basket" puts the
// whole collection in the basket as one entry - each piece an item, Stats treating it as a set. A piece opened
// from here can take colours of its own (its Colours section keeps them with the piece): each piece of a
// collection in its own colourway, its own paint and its effects' colours.
// Kept by the workbench (/api/collections): {collections: [{key, name, pieces}], current}.

const CL = {doc: {collections: [], current: ""}, loaded: false};
// the collection's slots: [key, label, the inventory types that go there], in paper-doll order
const COL_SLOTS = [
  ["head", "Head", [1]], ["shoulder", "Shoulders", [3]], ["back", "Back", [16]], ["chest", "Chest", [5, 20]],
  ["shirt", "Shirt", [4]], ["tabard", "Tabard", [19]], ["wrist", "Wrists", [9]],
  ["hands", "Hands", [10]], ["waist", "Waist", [6]], ["legs", "Legs", [7]], ["feet", "Feet", [8]],
  ["main", "Main hand", [13, 17, 21]], ["off", "Off hand", [13, 14, 22, 23]], ["ranged", "Ranged", [15, 25, 26]],
];
const COL_LEFT = ["head", "shoulder", "back", "chest", "shirt", "tabard", "wrist"];
const COL_RIGHT = ["hands", "waist", "legs", "feet"];
const COL_HANDS = ["main", "off", "ranged"];
const TWO_HAND = 17;
const slotLabel = k => (COL_SLOTS.find(s => s[0] === k) || [k, k])[1];

async function loadCollections() {
  try { CL.doc = await api("/api/collections"); } catch (e) { CL.doc = {collections: [], current: ""}; }
  CL.loaded = true;
  collectionCount();
}
function saveCollections() {
  collectionCount();
  const body = JSON.stringify(CL.doc);
  CL.saving = (CL.saving || Promise.resolve()).then(() =>
    fetch("/api/collections", {method: "POST", headers: {"Content-Type": "application/json"}, body})
      .catch(() => toast("Could not save your collections")));
  return CL.saving;
}
function collectionCount() {
  const c = currentCollection(false), b = $("#collection-count");
  if (b) b.textContent = c ? c.pieces.length : 0;
}
// the collection being built (a new "My collection" when there's none and `make`)
function currentCollection(make = true) {
  let c = CL.doc.collections.find(x => x.key === CL.doc.current) || CL.doc.collections[0] || null;
  if (!c && make) {
    c = {key: `c${Date.now().toString(36)}`, name: "My collection", pieces: []};
    CL.doc.collections.push(c);
  }
  if (c) CL.doc.current = c.key;
  return c;
}
// where a piece of inventory type `inv` goes in `c`: a one-hander to the main hand, else the off hand
function slotFor(c, inv) {
  if (inv === 13) {
    const main = c.pieces.find(p => p.slot === "main");
    return !main || main.inv === TWO_HAND ? "main" : !c.pieces.some(p => p.slot === "off") ? "off" : "main";
  }
  const s = COL_SLOTS.find(([, , invs]) => invs.includes(inv));
  return s ? s[0] : null;
}
const samePiece = (a, b) => a && b && a.source === b.source && a.item === b.item && a.display === b.display;
function pieceIn(c, piece) { return c ? c.pieces.find(p => samePiece(p, piece)) : null; }

// piece: {source, item, display, label, name, icon, quality, inv}
function addPiece(piece) {
  const c = currentCollection();
  const had = pieceIn(c, piece);
  if (had) {                                       // already there: the button takes it out
    c.pieces = c.pieces.filter(p => p !== had);
    saveCollections();
    toast(`Took ${piece.name} out of ${c.name}`, "Undo", () => { c.pieces.push(had); saveCollections(); refreshCollectionView(); });
    refreshCollectionView();
    return;
  }
  const slot = slotFor(c, piece.inv);
  if (!slot) { toast(`${piece.name} has no look to wear in a collection`); return; }
  const before = c.pieces.slice();
  const replaced = c.pieces.find(p => p.slot === slot);
  // a two-hander empties the off hand, and an off-hand piece takes the two-hander out, as the game does
  c.pieces = c.pieces.filter(p => p.slot !== slot && !(piece.inv === TWO_HAND && p.slot === "off") &&
                                  !(slot === "off" && p.slot === "main" && p.inv === TWO_HAND));
  c.pieces.push({...piece, slot});
  saveCollections();
  if (replaced) toast(`${piece.name} replaced ${replaced.name} in ${c.name}`, "Undo", () => { c.pieces = before; saveCollections(); refreshCollectionView(); });
  else toast(`Added ${piece.name} to ${c.name}`, "View", () => show("collection"));
  refreshCollectionView();
}
// the button an opened piece gets (openItem): what it does says which collection
function collectionButton(piece) {
  const c = currentCollection(false), on = pieceIn(c, piece);
  return el("button", {class: "btn" + (on ? " ghost" : ""), title: c ? `The collection being built: ${c.name}` : "Starts a collection",
    onclick: () => { addPiece(piece); if (S.open) reopen(S.open); }},
    on ? `In ${c.name} ✓ (take out)` : "Add to Custom Collection");
}

// -- the My collections view ------------------------------------------------------------------
function collectionEntry(c) {
  const first = c.pieces[0] || {};
  return {kind: "collection", source: "mine", id: c.key, name: c.name, icon: first.icon || 0, quality: first.quality,
          sub: plural(c.pieces.length, "piece"),
          pieces: c.pieces.map(p => ({source: p.source, item: p.item, display: p.display, label: p.label || "",
                                      inv: p.inv, slot: p.slot, ...(p.colour ? {colour: p.colour} : {})}))};
}
const colKey = c => `collection:mine:${c.key}`;
function refreshCollectionView() {
  if (S.view === "collection") renderCollectionView();
  collectionCount();
}
function renderCollectionView() {
  const root = $("#collection-body");
  if (!root) return;
  const c = currentCollection(false);
  const pick = el("select", {"aria-label": "Collection"}, CL.doc.collections.map(x =>
    el("option", {value: x.key, selected: c && x.key === c.key}, `${x.name} (${x.pieces.length})`)));
  pick.addEventListener("change", () => { CL.doc.current = pick.value; saveCollections(); renderCollectionView(); openCollection(); });
  const tools = el("div", {class: "cl-tools"},
    CL.doc.collections.length ? pick : el("span", {class: "muted"}, "No collection yet"),
    el("button", {class: "btn ghost", onclick: () => {
      const name = prompt("Name of the new collection", "My collection");
      if (!name) return;
      const n = {key: `c${Date.now().toString(36)}`, name: name.trim().slice(0, 60) || "My collection", pieces: []};
      CL.doc.collections.push(n); CL.doc.current = n.key; saveCollections(); renderCollectionView(); openCollection();
    }}, "New"),
    c ? el("button", {class: "btn ghost", onclick: () => {
      const name = prompt("Rename the collection", c.name);
      if (!name) return;
      c.name = name.trim().slice(0, 60) || c.name; saveCollections(); renderCollectionView(); openCollection();
    }}, "Rename") : null,
    c ? el("button", {class: "btn ghost", onclick: () => {
      const i = CL.doc.collections.indexOf(c);
      CL.doc.collections.splice(i, 1); CL.doc.current = (CL.doc.collections[0] || {}).key || "";
      saveCollections(); renderCollectionView(); closeDrawer(); if (CL.doc.collections.length) openCollection();
      toast(`Deleted ${c.name}`, "Undo", () => { CL.doc.collections.splice(i, 0, c); CL.doc.current = c.key; saveCollections(); renderCollectionView(); openCollection(); });
    }}, "Delete") : null);
  if (!c) {
    root.replaceChildren(tools, el("p", {class: "muted cl-empty"},
      "Open any item (or a set's piece) and press Add to Custom Collection: the version you're looking at goes in its slot here."));
    return;
  }
  const slotCard = key => {
    const p = c.pieces.find(x => x.slot === key);
    if (!p) return el("div", {class: "cl-slot empty"}, el("span", {class: "cl-label"}, slotLabel(key)), el("span", {class: "muted"}, "empty"));
    return el("div", {class: "cl-slot", title: `Open ${p.name}`, onclick: () => openCollectionPiece(c, p)},
      icon(p.icon, p.quality, "sm", p.source),
      el("div", {class: "cl-name"}, el("span", {class: "cl-label"}, slotLabel(key)),
         el("span", {style: `color:${qcolor(p.quality)}`}, p.name),
         p.label ? el("span", {class: "muted"}, p.label) : null,
         p.colour ? el("span", {class: "cl-way", title: "In its own colours"}, p.colour.name || "Custom colours") : null),
      el("button", {class: "x", title: `Take ${p.name} out`, onclick: ev => {
        ev.stopPropagation();
        c.pieces = c.pieces.filter(x => x !== p); saveCollections(); refreshCollectionView(); openCollection();
        toast(`Took ${p.name} out`, "Undo", () => { c.pieces.push(p); saveCollections(); refreshCollectionView(); openCollection(); });
      }}, "×"));
  };
  const k = colKey(c), inB = inBasket(k);
  const stale = inB && JSON.stringify(S.basket.find(e => keyOf(e) === k).pieces) !== JSON.stringify(collectionEntry(c).pieces);
  root.replaceChildren(tools,
    el("div", {class: "cl-doll"},
      el("div", {class: "cl-col"}, COL_LEFT.map(slotCard)),
      el("div", {class: "cl-col"}, COL_RIGHT.map(slotCard), el("div", {class: "cl-gap"}), COL_HANDS.map(slotCard))),
    el("div", {class: "actions"},
      el("button", {class: "btn", disabled: !c.pieces.length, onclick: () => {
        if (inB) S.basket = S.basket.filter(e => keyOf(e) !== k);
        if (!inB || stale) { S.basket.push(collectionEntry(c)); toast(stale ? `Updated ${c.name} in the basket` : `Added ${c.name} to the basket`); }
        else toast(`Removed ${c.name} from the basket`);
        saveBasket(); renderCollectionView();
      }}, !inB ? "Add to basket" : stale ? "Update in basket" : "Remove from basket"),
      el("button", {class: "btn ghost", onclick: openCollection}, "Show on the character"),
      el("span", {class: "muted"}, `${plural(c.pieces.length, "piece")} of ${COL_SLOTS.length} slots`)));
}
// the collection dressed, in the drawer
async function openCollection() {
  const c = currentCollection(false);
  if (!c) return;
  await ensureRaces();
  S.open = {kind: "collection", id: c.key};
  PV.step = null;
  // held as the game holds them: a one-hander in the off hand in the left hand (an off-hand weapon's type), a
  // ranged weapon only with empty hands (else it is on the back, sheathed)
  const armed = c.pieces.some(p => p.slot === "main" || p.slot === "off");
  const pieces = COL_SLOTS.flatMap(([key]) => c.pieces.filter(p => p.slot === key))
    .filter(p => p.slot !== "ranged" || !armed)
    .map(p => ({display: p.display, slot: p.slot === "off" && p.inv === 13 ? 22 : p.inv, name: p.name, source: p.source,
                ...(p.colour ? {colour: p.colour} : {})}));
  const body = [el("div", {class: "d-head"}, el("div", {},
    el("h2", {}, c.name), el("div", {class: "d-sub"}, `Your collection · ${plural(c.pieces.length, "piece")}`)))];
  if (pieces.length) {
    // pieces from one source dress together; another source's are left to their own views
    const src = pieces[0].source, here = pieces.filter(p => p.source === src);
    const ch = characterSection(here, src);
    body.push(ch);
    if (here.length < pieces.length) body.push(el("div", {class: "warnline"}, `${pieces.length - here.length} piece(s) from another source aren't on the character`));
  } else body.push(el("p", {class: "muted"}, "Nothing in it yet."));
  showDrawer(body);
}
function openCollectionPiece(c, p) {
  useSource(p.source);
  openItem(p.item, {name: c.name, open: () => { show("collection"); openCollection(); }, piece: {c, p}}, p.display);
}
// a piece's own colourway, kept with it in its collection (the item's Colours section, opened from the collection)
function pieceStore(c, p) {
  return {name: c.name, get: () => p.colour || null,
          put: way => { if (way) p.colour = way; else delete p.colour; saveCollections(); refreshCollectionView(); }};
}
window.CollectionsUI = {loadCollections, addPiece, collectionButton, renderCollectionView, openCollection, collectionEntry, pieceStore};
