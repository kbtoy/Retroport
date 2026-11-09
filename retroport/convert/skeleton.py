"""Skeletons that inherit their parent's sequences.

A Legion+ ``.skel`` can name a parent skeleton (``SKPD``). The game plays every sequence the child
does not define from that parent: retail's upright orc male (``orcmaleupright.skel``) defines 118
and takes the other 256 - HandsClosed among them - from ``orcmale_hd.skel``. wotlkconv's merge
(``Skeleton.merge_parent``) fills only the sections a child leaves empty, so a child with sequences
of its own lost all of its parent's: the converted Mag'har male had no HandsClosed (animation 15)
and never closed his hands on a weapon (the client closes them by playing 15 on key bones 8-12
and 13-17, ``CCharacterComponent::ComponentCloseFingers`` 0x004E7700), nor played most emotes.

``install()`` wraps wotlkconv's merge so it also appends the parent's missing sequences to the
child, with the parent's keyframes on the child's bones. retroport's copy of wotlkconv stays as
its repository has it; the engine (``engine.py``) and the Workbench install this before loading
a model.
"""

from __future__ import annotations

#: Bone flags the client animates a bone under (``CM2Model``'s bone update tests ``0x280``); a bone
#: without them keeps its rest pose whatever its tracks hold.
BONE_ANIMATED_FLAGS = 0x280
SEQUENCE_ALIAS_FLAG = 0x40
EMPTY_SLOT = 0xFFFF
_BONE_TRACKS = ("translation", "rotation", "scale")


_DONOR: list = [None]          # the model whose events the inherited sequences take (event_donor)


def install() -> None:
    """Make wotlkconv's skeleton merge inherit the parent's sequences, and its model merge size
    the model's own tracks to them (idempotent)."""
    from wotlkconv.m2 import downgrade
    from wotlkconv.m2 import skel as wskel
    if getattr(wskel.Skeleton.merge_parent, "_retroport", False):
        return
    original = wskel.Skeleton.merge_parent

    def merge_parent(self, parent) -> None:
        if not (self.sequences and parent.sequences and self.bones and parent.bones) \
                or not inherit_sequences(self, parent):
            original(self, parent)
            return
        # the merged sections index the merged list: the parent's must not replace them
        kept = (self.sequences, self.sequence_lookups, self.anim_file_ids)
        original(self, parent)
        self.sequences, self.sequence_lookups, self.anim_file_ids = kept

    merge_parent._retroport = True
    wskel.Skeleton.merge_parent = merge_parent
    original_model = downgrade.merge_skeleton

    def merge_skeleton(model, skel, result) -> None:
        original_model(model, skel, result)
        inherited = getattr(skel, "retroport_inherited", None)
        if inherited and model.sequences is skel.sequences:
            fill_model_tracks(model, inherited, _DONOR[0])

    downgrade.merge_skeleton = merge_skeleton


class event_donor:
    """``with event_donor(m2_bytes):`` - while converting, a model whose skeleton inherits
    sequences takes those sequences' events (footsteps, swing and hit cues) from this model's,
    matched by event id and bone: the model that owns the parent skeleton (retail's hunched orc
    male for the upright one, whose own events cover only its 118 sequences). ``None`` leaves the
    inherited sequences without events."""

    def __init__(self, data: bytes | None):
        self.model = None
        if data:
            from wotlkconv.m2 import model as M
            body = data[8:8 + int.from_bytes(data[4:8], "little")] if data[:4] == b"MD21" else data
            self.model = M.parse_md20(body, "event donor", chunked=data[:4] == b"MD21")

    def __enter__(self):
        _DONOR[0] = self.model
        return self

    def __exit__(self, *exc) -> None:
        _DONOR[0] = None


def fill_model_tracks(model, inherited: list[tuple[int, int, int]], donor=None) -> None:
    """Give the model's own tracks a sub-array for every inherited sequence. The client clamps a
    value track's sequence index (``M2AnimateTrack``: past the end it plays the first sequence's),
    so those get a copy of the first sequence's keys; but it reads event times by index unchecked
    (``CM2Model::ProcessEventCallbacks`` 0x00830FB0, the event-time lookup before it) - past the
    end of a Mag'har male's 118 that read garbage and crashed on his first inherited attack. Events
    take the donor's for that sequence (``inherited``: (merged index, parent index, parent sequence
    count)), else none."""
    from wotlkconv.m2.types import Track, TrackBase
    total = len(model.sequences)
    events = {id(e.get("enabled")) for e in model.events}
    donors = {}
    if donor is not None:
        for e in donor.events:
            donors[(e.get("identifier"), e.get("bone"))] = e.get("enabled")
    for owner in model.events:
        track = owner.get("enabled")
        dtrack = donors.get((owner.get("identifier"), owner.get("bone")))
        _fill(track, inherited, total, dtrack, copy_first=False)
    for track in model.own_tracks():
        if id(track) not in events and isinstance(track, (Track, TrackBase)):
            _fill(track, inherited, total, None, copy_first=True)


def _fill(track, inherited, total: int, donor_track, copy_first: bool) -> None:
    if track is None or track.global_sequence >= 0 or len(track.timestamps) <= 1:
        return                      # no keys at all, or one global loop: the client never indexes it
    has_values = hasattr(track, "values")
    first = min(i for i, _p, _n in inherited)
    del track.timestamps[first:]
    del track.timestamp_spans[first:]
    if has_values:
        del track.values[first:]
        del track.value_spans[first:]
    track.external = {i for i in track.external if i < first}
    while len(track.timestamps) < first:
        track.timestamps.append([])
        track.timestamp_spans.append((0, 0))
        if has_values:
            track.values.append([])
            track.value_spans.append((0, 0))
    for index, pi, parent_count in sorted(inherited):
        src, at = None, None
        if donor_track is not None and len(donor_track.timestamps) == parent_count and pi < parent_count:
            src, at = donor_track, pi
        elif copy_first and 0 not in track.external:
            src, at = track, 0
        if src is None:
            track.timestamps.append([])
            track.timestamp_spans.append((0, 0))
            if has_values:
                track.values.append([])
                track.value_spans.append((0, 0))
            continue
        track.timestamps.append(list(src.timestamps[at]))
        track.timestamp_spans.append(src.timestamp_spans[at] if at < len(src.timestamp_spans) else (0, 0))
        if has_values:
            track.values.append(list(src.values[at]) if at < len(src.values) else [])
            track.value_spans.append(src.value_spans[at] if at < len(src.value_spans) else (0, 0))
        if at in src.external:
            track.external.add(index)
    while len(track.timestamps) < total:
        track.timestamps.append([])
        track.timestamp_spans.append((0, 0))
        if has_values:
            track.values.append([])
            track.value_spans.append((0, 0))


def _key(seq: dict) -> tuple[int, int]:
    return seq.get("id", 0), seq.get("variation_index", 0)


def _pad(track, count: int) -> None:
    """One (empty) sub-array per sequence up to ``count``: the client gives an empty one the
    track's default value (``M2AnimateTrack``: no keys, no change)."""
    for spans in (track.timestamp_spans, track.value_spans):
        spans.extend([(0, 0)] * (count - len(spans)))
    track.timestamps.extend([] for _ in range(count - len(track.timestamps)))
    track.values.extend([] for _ in range(count - len(track.values)))


def _has_keys(track) -> bool:
    return any(track.timestamps) or bool(track.external)


def inherit_sequences(child, parent) -> int:
    """Append to wotlkconv skeleton ``child`` the sequences of ``parent`` it does not define,
    with the parent's keyframes for them on the child's bones. Returns how many were added.

    Bones are matched by name hash, else by position when both rigs have as many bones; a child
    bone with no counterpart stays at rest in the inherited sequences, and one that gains keys
    gains the parent bone's animated flags. Each inherited sequence keeps its own ``.anim`` (the
    parent's AFID entry); aliases and variation chains point into the merged list; the sequence
    lookup is rebuilt for it. Tracks on a global loop are left alone, and so is everything but
    the bones: a model's own tracks (colours, texture animation) with fewer sub-arrays than
    sequences play their first sequence's (``CM2Model::FindKey``)."""
    from wotlkconv.m2.types import Track
    have = {_key(s) for s in child.sequences}
    take = [i for i, s in enumerate(parent.sequences) if _key(s) not in have]
    if not take:
        return 0
    first = len(child.sequences)
    merged = {_key(s): i for i, s in enumerate(child.sequences)}
    for k, pi in enumerate(take):
        merged[_key(parent.sequences[pi])] = first + k

    def where(index: int) -> int:
        if 0 <= index < len(parent.sequences):
            return merged.get(_key(parent.sequences[index]), index)
        return index

    # an alias plays its target's keyframes and carries the same spans; one the parent aliases to a
    # sequence the child defines (retail's 1824 to the upright's own 64) takes the child's, or its
    # parent spans - into the parent's .anim - would not fit the child's file, and the converter
    # drops that whole file's bone keyframes (64 and 65 stood still)
    from_child: dict[int, int] = {}
    for k, pi in enumerate(take):
        seq = dict(parent.sequences[pi])
        if seq.get("flags", 0) & SEQUENCE_ALIAS_FLAG:
            seq["alias_next"] = where(seq.get("alias_next", 0))
            if seq["alias_next"] < first:
                from_child[k] = seq["alias_next"]
        child.sequences.append(seq)
    relink_variations(child.sequences, {_key(parent.sequences[pi])[0] for pi in take})

    crcs = [b.get("bone_name_crc", 0) for b in parent.bones]
    by_crc = {c: j for j, c in enumerate(crcs)} if len(set(crcs)) == len(crcs) else {}
    same_shape = len(child.bones) == len(parent.bones)
    total = len(child.sequences)
    for i, bone in enumerate(child.bones):
        j = by_crc.get(bone.get("bone_name_crc", 0)) if by_crc else None
        if j is None and same_shape:
            j = i
        source = parent.bones[j] if j is not None else None
        gained = False
        for name in _BONE_TRACKS:
            track = bone.get(name)
            if not isinstance(track, Track) or track.global_sequence >= 0:
                continue
            ptrack = source.get(name) if source is not None else None
            if not isinstance(ptrack, Track) or ptrack.global_sequence >= 0:
                ptrack = None
            if ptrack is not None and not _has_keys(track) and _has_keys(ptrack):
                track.interpolation = ptrack.interpolation
            track.trim_to(first)
            _pad(track, first)
            for k, pi in enumerate(take):
                if k in from_child:
                    t = from_child[k]
                    track.timestamps.append(list(track.timestamps[t]))
                    track.values.append(list(track.values[t]))
                    track.timestamp_spans.append(track.timestamp_spans[t])
                    track.value_spans.append(track.value_spans[t])
                    if t in track.external:
                        track.external.add(first + k)
                    continue
                if ptrack is None or pi >= len(ptrack.timestamps):
                    _pad(track, first + k + 1)
                    continue
                track.timestamps.append(list(ptrack.timestamps[pi]))
                track.values.append(list(ptrack.values[pi]) if pi < len(ptrack.values) else [])
                track.timestamp_spans.append(ptrack.timestamp_spans[pi] if pi < len(ptrack.timestamp_spans)
                                             else (0, 0))
                track.value_spans.append(ptrack.value_spans[pi] if pi < len(ptrack.value_spans) else (0, 0))
                if pi in ptrack.external:
                    track.external.add(first + k)
                gained = gained or bool(ptrack.timestamps[pi]) or pi in ptrack.external
            _pad(track, total)
        if gained:
            bone["flags"] = bone.get("flags", 0) | (source.get("flags", 0) & BONE_ANIMATED_FLAGS)

    own = {(r.anim_id, r.sub_anim_id) for r in child.anim_file_ids}
    taken = {_key(parent.sequences[pi]) for pi in take}
    child.anim_file_ids = list(child.anim_file_ids) + [
        r for r in parent.anim_file_ids if (r.anim_id, r.sub_anim_id) in taken and (r.anim_id, r.sub_anim_id) not in own]
    hint = len(child.sequence_lookups) or len(parent.sequence_lookups)
    if hint:
        child.sequence_lookups = build_sequence_lookup(child.sequences, hint)
    # for the model merge (fill_model_tracks): which merged sequence came from which parent one
    child.retroport_inherited = getattr(child, "retroport_inherited", []) + [
        (first + k, pi, len(parent.sequences)) for k, pi in enumerate(take)]
    return len(take)


def relink_variations(sequences: list[dict], ids: set[int]) -> None:
    """Chain each of ``ids``' variations in ``variation_index`` order (-1 ends a chain)."""
    for anim_id in ids:
        chain = sorted((i for i, s in enumerate(sequences) if s.get("id") == anim_id),
                       key=lambda i: (sequences[i].get("variation_index", 0), i))
        for a, b in zip(chain, chain[1:] + [-1]):
            sequences[a]["variation_next"] = b


def lookup_sequence(table: list[int], sequences: list[dict], anim_id: int) -> int | None:
    """The client's search (``CM2Model::HasSequence``, 0x00825E00): slot ``id % n``, then
    ``(slot + step * step) % n`` for step 1, 2, ... until the id or an empty slot."""
    n = len(table)
    if not n:
        return next((i for i, s in enumerate(sequences) if s.get("id") == anim_id), None)
    slot = anim_id % n
    step = 1
    while table[slot] != EMPTY_SLOT and sequences[table[slot]].get("id") != anim_id:
        if step > 2 * n:
            return None
        slot = (slot + step * step) % n
        step += 1
    return None if table[slot] == EMPTY_SLOT else table[slot]


def build_sequence_lookup(sequences: list[dict], size_hint: int = 0) -> list[int]:
    """A lookup the client finds every id through (``lookup_sequence``): each id's first
    sequence in the first empty slot on its probe chain; the table grows until all fit."""
    first: dict[int, int] = {}
    for i, seq in enumerate(sequences):
        first.setdefault(seq.get("id", 0), i)
    n = max(size_hint, 2 * len(first) + 1, 1)
    while True:
        table = [EMPTY_SLOT] * n
        for anim_id, index in first.items():
            slot = anim_id % n
            step = 1
            while table[slot] != EMPTY_SLOT and step <= 2 * n:
                slot = (slot + step * step) % n
                step += 1
            if table[slot] != EMPTY_SLOT:
                break
            table[slot] = index
        else:
            return table
        n += 1
