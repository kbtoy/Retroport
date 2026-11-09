"""A skeleton plays the sequences it lacks from its SKPD parent (convert/skeleton.py)."""

from wotlkconv.m2.model import AnimFileRef
from wotlkconv.m2.skel import Skeleton
from wotlkconv.m2.types import Track

from retroport.convert import skeleton as S

STAND, WALK, HANDS_CLOSED, EMOTE = 0, 4, 15, 60


def _seq(anim_id, var=0, flags=0x20, alias=0, nxt=-1):
    return {"id": anim_id, "variation_index": var, "flags": flags, "alias_next": alias, "variation_next": nxt,
            "duration": 100}


def _track(per_seq, interpolation=1):
    """per_seq: one list of keys per sequence (a key is a timestamp; the value is the same number)."""
    return Track(kind="quat16", interpolation=interpolation, timestamps=[list(k) for k in per_seq],
                 values=[list(k) for k in per_seq], timestamp_spans=[(len(k), 0) for k in per_seq],
                 value_spans=[(len(k), 0) for k in per_seq])


def _bone(crc, per_seq, flags=0x200, interpolation=1):
    return {"bone_name_crc": crc, "flags": flags, "parent_bone": -1,
            "translation": _track([[] for _ in per_seq]), "rotation": _track(per_seq, interpolation),
            "scale": _track([[] for _ in per_seq])}


def _pair():
    """An upright child (Stand, Walk of its own) and its hunched parent (Stand, Walk, HandsClosed,
    an emote kept in an .anim). Bone 0x11 is a finger: still in the child's own sequences."""
    child = Skeleton(sequences=[_seq(STAND), _seq(WALK)], sequence_lookups=[0xFFFF] * 7,
                     bones=[_bone(0x10, [[1], [2]]), _bone(0x11, [[], []], flags=0, interpolation=0)],
                     anim_file_ids=[AnimFileRef(WALK, 0, 500)])
    parent = Skeleton(sequences=[_seq(STAND), _seq(WALK), _seq(HANDS_CLOSED), _seq(EMOTE, flags=0)],
                      sequence_lookups=[0xFFFF] * 9,
                      bones=[_bone(0x11, [[9], [9], [7, 8], []]), _bone(0x10, [[3], [4], [5], []])],
                      anim_file_ids=[AnimFileRef(WALK, 0, 600), AnimFileRef(EMOTE, 0, 601)])
    parent.bones[0]["rotation"].external.add(3)
    return child, parent


def test_the_childs_missing_sequences_come_from_its_parent():
    child, parent = _pair()
    assert S.inherit_sequences(child, parent) == 2
    assert [(s["id"], s["variation_index"]) for s in child.sequences] == [(STAND, 0), (WALK, 0), (HANDS_CLOSED, 0),
                                                                         (EMOTE, 0)]
    # bones matched by name hash, not position: the finger (0x11) is the parent's bone 0
    finger = child.bones[1]["rotation"]
    assert finger.timestamps == [[], [], [7, 8], []] and 3 in finger.external
    assert finger.interpolation == 1                                     # it had no keys: the parent's
    assert child.bones[1]["flags"] & S.BONE_ANIMATED_FLAGS               # and is animated now
    # the child's own sequences keep the child's keys
    assert child.bones[0]["rotation"].timestamps == [[1], [2], [5], []]
    # each inherited sequence keeps its .anim; the child's own Walk keeps the child's
    assert {(r.anim_id, r.file_id) for r in child.anim_file_ids} == {(WALK, 500), (EMOTE, 601)}
    assert all(len(b[n].timestamps) == 4 for b in child.bones for n in ("translation", "rotation", "scale"))


def test_the_lookup_finds_every_id_the_way_the_client_searches():
    child, parent = _pair()
    S.inherit_sequences(child, parent)
    for i, s in enumerate(child.sequences):
        assert S.lookup_sequence(child.sequence_lookups, child.sequences, s["id"]) == i
    assert S.lookup_sequence(child.sequence_lookups, child.sequences, 99) is None
    table = S.build_sequence_lookup([_seq(i) for i in range(0, 600, 7)], 5)
    assert all(S.lookup_sequence(table, [_seq(i) for i in range(0, 600, 7)], i) == k
               for k, i in enumerate(range(0, 600, 7)))


def test_aliases_and_variations_point_into_the_merged_list():
    child = Skeleton(sequences=[_seq(STAND)], bones=[_bone(1, [[1]])])
    parent = Skeleton(sequences=[_seq(STAND), _seq(EMOTE), _seq(EMOTE, var=1), _seq(70, flags=0x40, alias=1)],
                      bones=[_bone(1, [[1], [2], [3], []])])
    S.inherit_sequences(child, parent)
    ids = [(s["id"], s["variation_index"]) for s in child.sequences]
    assert ids == [(STAND, 0), (EMOTE, 0), (EMOTE, 1), (70, 0)]
    assert child.sequences[3]["alias_next"] == 1
    assert child.sequences[1]["variation_next"] == 2 and child.sequences[2]["variation_next"] == -1


def test_an_inherited_alias_of_the_childs_own_sequence_carries_the_childs_keyframes():
    # retail's 1824 aliases 64; the upright skeleton defines 64 itself, in its own .anim
    child = Skeleton(sequences=[_seq(STAND), _seq(64, flags=0)], bones=[_bone(1, [[1], []])])
    child.bones[0]["rotation"].timestamp_spans[1] = (3, 40)
    child.bones[0]["rotation"].external.add(1)
    parent = Skeleton(sequences=[_seq(STAND), _seq(64, flags=0), _seq(1824, flags=0x40, alias=1)],
                      bones=[_bone(1, [[1], [], []])])
    parent.bones[0]["rotation"].timestamp_spans[1:] = [(5, 900), (5, 900)]
    parent.bones[0]["rotation"].external |= {1, 2}
    S.inherit_sequences(child, parent)
    rot = child.bones[0]["rotation"]
    assert child.sequences[2]["alias_next"] == 1
    assert rot.timestamp_spans[2] == (3, 40) and 2 in rot.external      # the child's, not the parent's


def test_the_models_own_tracks_cover_every_inherited_sequence():
    """The client reads event times by sequence index unchecked (ProcessEventCallbacks): a model's
    events sized to the child's own sequences crashed the game on the first inherited attack."""
    from wotlkconv.m2.model import M2Model
    from wotlkconv.m2.types import TrackBase
    child, parent = _pair()
    S.inherit_sequences(child, parent)                         # 2 own + HandsClosed + emote
    swing = TrackBase(timestamps=[[5], [6]], timestamp_spans=[(1, 0), (1, 0)])
    colour = _track([[1], [2]])
    model = M2Model(sequences=child.sequences, events=[{"identifier": b"$CSS", "bone": 3, "enabled": swing}],
                    colors=[{"alpha": colour}])
    donor = M2Model(events=[{"identifier": b"$CSS", "bone": 3,
                             "enabled": TrackBase(timestamps=[[], [], [40], []],
                                                  timestamp_spans=[(0, 0), (0, 0), (1, 0), (0, 0)])}])
    S.fill_model_tracks(model, child.retroport_inherited, donor)
    assert swing.timestamps == [[5], [6], [40], []]           # the donor's cue for HandsClosed
    assert colour.timestamps == [[1], [2], [1], [1]]          # the first sequence's, as the client plays it
    S.fill_model_tracks(model, child.retroport_inherited)      # no donor: no events, but no gap either
    assert swing.timestamps == [[5], [6], [], []]


def test_install_wraps_the_engines_merge():
    S.install()
    S.install()                                                         # idempotent
    child, parent = _pair()
    child.anim_file_ids = []                                            # none of its own
    child.merge_parent(parent)
    assert len(child.sequences) == 4
    # the parent's own AFID (its Walk) must not replace the merged list
    assert {(r.anim_id, r.file_id) for r in child.anim_file_ids} == {(EMOTE, 601)}
    assert len(child.sequence_lookups) >= 7
    # a child that defines no sequences takes the parent's whole, as before
    empty, parent = Skeleton(bones=[_bone(1, [])]), _pair()[1]
    empty.merge_parent(parent)
    assert empty.sequences is parent.sequences
