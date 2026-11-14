"""FEATURE_VERSION 5: the monster table, the sight fields, reobserve's alignment, and the contract."""

import gzip
import json
from pathlib import Path

import numpy as np
import pytest
from helpers import add_monster, make_state, map_message

from ladder.brain import corpus, monsters, reobserve
from ladder.brain.features import (FEATURE_VERSION, MAX_MONS, MON_DIM, MON_GROUPS, SEEN_MON, SELF_DIM, SELF_GROUPS,
                                   TABLE_MON, V4_MON, V4_SELF, encode, fg_bits, merge_sight, observe, sight)
from ladder.brain.net import ModelMismatch, TrainedNet, contract
from ladder.state import MF_MONS_HOSTILE, GameState

ROOT = Path(__file__).resolve().parents[1]
SEEN0 = SELF_GROUPS["seen"][0]               # first "seen" column of the character vector: seen_missing


def obs(**over):
    base = {
        "turn": 100, "place": "Dungeon", "depth": 3, "hp": 20, "hp_max": 40, "mp": 0, "mp_max": 0,
        "xl": 3, "progress": 10, "ac": 2, "ev": 8, "sh": 0, "str": 12, "int": 8, "dex": 10,
        "poison_survival": 20, "status": [], "mons": [], "n_hostiles": 0,
        "inv": {"heal": 0, "unknown_potions": 0, "unknown_scrolls": 0, "teleport": 0},
        "on_down": False, "on_up": False, "dist_down": -1, "dist_up": -1, "open_neighbors": 4,
        "level_explored": False, "level_steps": 5, "level_turns": 50, "hp_delta": 0.0, "last_action": None,
    }
    base.update(over)
    return base


def mon(name="orc", dx=1, dy=0, threat=1, unique=False, **extra):
    return {"name": name, "dx": dx, "dy": dy, "threat": threat, "unique": unique, **extra}


# --- the monster table ---------------------------------------------------------------------------------

def test_shipped_table_is_current_with_the_source_data():
    """Fails when docs/data/monsters-0.34.json changed without `python -m ladder.brain.monsters`."""
    shipped = json.loads(monsters.TABLE.read_text())
    assert shipped["monsters"] == monsters.compact(ROOT / "docs/data/monsters-0.34.json")["monsters"]


def test_lookup_known_names_and_fallbacks():
    orc = monsters.lookup("orc")
    assert orc["hd"] == 1 and orc["speed"] == 10 and orc["hp"] > 0
    assert monsters.lookup("Orc") == orc                         # case
    assert monsters.lookup("the orc") == orc                     # article
    assert monsters.lookup("orc zombie") == orc                  # derived undead: the base monster's numbers
    assert monsters.lookup("spectral orc") == orc
    assert monsters.lookup("orcs") == orc                        # a plural
    assert monsters.lookup("Grum the Hunter") is not None        # a vault name ending in a known one
    assert monsters.lookup("dancing +0 dagger") == monsters.lookup("dancing weapon")
    assert monsters.lookup("no such thing anywhere") is None
    assert monsters.lookup("") is None


def test_lookup_kinds():
    assert "poison" in monsters.lookup("adder")["kinds"]
    assert "ranged" in monsters.lookup("orc wizard")["kinds"]
    assert "ranged" in monsters.lookup("centaur")["kinds"]       # an archer
    assert monsters.lookup("jackal")["speed"] > 10
    assert set(k for v in monsters.table().values() for k in v["kinds"]) <= set(monsters.KINDS)


# --- encode: the layout --------------------------------------------------------------------------------

def test_groups_tile_the_vectors():
    assert SELF_GROUPS["v4"] == (0, V4_SELF) and SELF_GROUPS["seen"][1] == SELF_DIM
    assert SELF_GROUPS["v4"][1] == SELF_GROUPS["table"][0] and SELF_GROUPS["table"][1] == SELF_GROUPS["seen"][0]
    assert MON_GROUPS["v4"] == (0, V4_MON) and MON_GROUPS["seen"][1] == MON_DIM
    assert MON_GROUPS["table"] == (V4_MON, V4_MON + TABLE_MON)
    assert MON_GROUPS["seen"][1] - MON_GROUPS["seen"][0] == SEEN_MON


def test_version_4_inputs_are_unchanged_by_the_new_fields():
    """The first V4_SELF / V4_MON columns are version 4's, whatever else the observation carries."""
    plain = obs(mons=[mon("orc"), mon("adder", 2, 1)], n_hostiles=2)
    rich = merge_sight(plain, {"mons": [{"fg": True, "mdam": 4, "beh": 1, "pois": 1, "caught": True,
                                         "st": ["hasted"], "avghp": 9}] * 2,
                               "wpn": 8.0, "wpn_held": True, "obsx": 1,
                               "map": {"open2": 10, "unseen3": 3, "corridor": True, "rays": [1] * 8}})
    s1, m1, k1 = encode(plain, ["fight"])
    s2, m2, k2 = encode(rich, ["fight"])
    assert np.array_equal(s1[:V4_SELF], s2[:V4_SELF]) and np.array_equal(m1[:, :V4_MON], m2[:, :V4_MON])
    assert np.array_equal(s1[SELF_GROUPS["table"][0]:SEEN0], s2[SELF_GROUPS["table"][0]:SEEN0])
    assert not np.array_equal(s1[SEEN0:], s2[SEEN0:])
    assert np.array_equal(k1, k2)


# --- encode: the table's numbers -----------------------------------------------------------------------

def test_table_columns_per_monster_and_totals():
    o = obs(hp=10, hp_max=40, mons=[mon("orc warrior"), mon("jackal", 2, 0), mon("zzz unknown", 3, 0)], n_hostiles=3)
    s, m, _ = encode(o, ["fight"])
    t0 = MON_GROUPS["table"][0]
    warrior, jackal, unknown = m[0, t0:t0 + TABLE_MON], m[1, t0:t0 + TABLE_MON], m[2, t0:t0 + TABLE_MON]
    w = monsters.lookup("orc warrior")
    assert warrior[0] == 1 and unknown[0] == 0 and not unknown.any()
    assert warrior[1] == pytest.approx(w["hd"] / 30)
    assert warrior[2] == pytest.approx(min(w["hp"] / 40, 4) / 4)                    # HP against our max HP
    assert warrior[3] == pytest.approx(min(w["dmg"] * w["speed"] / 10 / 10, 2) / 2)  # damage a turn against our HP
    assert jackal[4] == 1 and warrior[4] == 0                                        # fast
    ranged = 6 + monsters.KINDS.index("ranged")
    assert m[0, t0 + ranged] == 0
    tot = s[SELF_GROUPS["table"][0]:SEEN0]
    assert tot[4] == pytest.approx(1 / 8)                                            # one fast monster
    assert tot[6] == pytest.approx(1 / 8)                                            # one not in the table
    assert tot[3] == pytest.approx(w["hd"] / 30)                                     # the highest HD


def test_table_columns_are_zero_without_monsters():
    s, m, mask = encode(obs(), ["explore"])
    assert not s[SELF_GROUPS["table"][0]:SEEN0].any() and not m.any() and not mask.any()


# --- encode: sight -------------------------------------------------------------------------------------

def test_a_step_without_sight_fields_is_marked_missing_not_just_zero():
    s, m, _ = encode(obs(mons=[mon("orc")], n_hostiles=1), ["fight"])
    assert s[SEEN0] == 1.0 and not s[SEEN0 + 1:].any()
    assert not m[0, MON_GROUPS["seen"][0]:].any()


def test_sight_columns_from_the_fields():
    x = {"fg": True, "mdam": 4, "beh": 2, "pois": 1, "caught": False, "st": ["summoned", "slowed"], "avghp": 20}
    o = merge_sight(obs(hp_max=40, mons=[mon("orc")], n_hostiles=1),
                    {"mons": [x], "wpn": 10.0, "wpn_held": True, "obsx": 1,
                     "map": {"open2": 12, "unseen3": 6, "corridor": True, "rays": [0, 1, 2, 3, 4, 5, 6, 7]}})
    s, m, _ = encode(o, ["fight"])
    seen = m[0, MON_GROUPS["seen"][0]:]
    assert seen[0] == 1 and seen[1] == pytest.approx(0.3)                    # severely damaged: ~30% left
    assert seen[2] == pytest.approx(20 * 0.3 / 40 / 4)                       # its HP left against our max HP
    assert seen[3:7].tolist() == [0, 1, 0, 0]                                # unaware
    assert seen[7:].tolist() == [1, 0, 1, 0, 1]                              # poisoned, not caught, summoned, debuffed
    me = s[SEEN0:]
    assert me[0] == 0 and me[1] == pytest.approx(0.5) and me[2] == 0         # weapon 10 of 20, a ranked one
    assert me[3] == pytest.approx(0.5) and me[4] == 1                        # open2 12 of 24, corridor
    assert me[5:8].tolist() == pytest.approx([0, 3.5 / 7, 1])                # rays: min, mean, max
    assert me[10] == pytest.approx(1 / 8)                                    # one monster not aware of us


def test_fg_bits_reads_ints_and_word_pairs():
    assert fg_bits({}) is None and fg_bits({"t": {}}) is None
    assert fg_bits({"t": {"fg": 0x00100005}}) == 0x00100005
    assert fg_bits({"t": {"fg": [0x40000000, 0x01]}}) == 0x40000000 | (1 << 32)


def state_with_monster(fg, icons=(), avghp=None):
    state = make_state(["#####", "#@..#", "#...#", "#####"], hp=30, hp_max=40)
    add_monster(state, (3, 1), 7, "orc")
    t = {"bg": 1, "fg": fg}
    if icons:
        t["icons"] = list(icons)
    state.apply({"msg": "map", "cells": [{"x": 3, "y": 1, "mon": {"id": 7, "typedata": {"avghp": avghp}}, "t": t}]})
    return state


def test_sight_reads_damage_behaviour_poison_net_and_icons():
    # almost dead (MDAM_ADEAD: low bits 30-31 and the high word's bit 0), fleeing, more poison, in a net
    fg = [0x40000000 | 0x80000000 | 0x00300000 | 0x00800000, 0x01 | 0x10000000]
    state = state_with_monster(fg, icons=(10204, 10192, 99999), avghp=11)
    x = sight(state, state.hostiles())
    assert x["mons"] == [{"fg": True, "mdam": 7, "beh": 3, "pois": 2, "caught": True,
                          "st": ["hasted", "summoned"], "avghp": 11}]
    assert x["obsx"] == 1


def test_sight_map_rays_corridor_and_unseen():
    state = make_state(["#######", "#.....#", "#######"])
    state.apply({"msg": "player", "pos": {"x": 1, "y": 1}})
    x = sight(state, [])
    n, ne, e, se, s, sw, w, nw = x["map"]["rays"]
    assert e == 4 and w == 0 and n == 0 and s == 0                 # four floor squares east, walls round
    assert x["map"]["corridor"] is True                            # walls north and south
    assert x["map"]["open2"] == 2
    assert x["map"]["unseen3"] > 0                                 # rows outside the map are unknown


def test_sight_weapon_score():
    state = make_state(["@."])
    state.apply({"msg": "player", "weapon_index": 0,
                 "inv": {"0": {"name": "a +2 flail", "base_type": 0, "quantity": 1, "letter": 97, "plus": 2}}})
    x = sight(state, [])
    assert x["wpn"] == pytest.approx(12.0) and x["wpn_held"] is True
    state.apply({"msg": "player", "inv": {"0": {"name": "a +0 war axe", "plus": 0}}})
    x = sight(state, [])
    assert x["wpn"] is None and x["wpn_held"] is True              # a weapon the brain doesn't rank
    s, _, _ = encode(observe(state, [], {}), ["explore"])
    assert s[SEEN0 + 2] == 1.0


def test_observe_logs_sight_fields_and_stays_json():
    state = state_with_monster([0x00100000 | 0x80000000, 0])
    o = observe(state, state.hostiles(), {})
    assert o["obsx"] == 1 and "map" in o and "wpn_held" in o
    assert o["mons"][0]["mdam"] == 2 and o["mons"][0]["beh"] == 1      # moderately damaged, asleep
    json.dumps(o)
    s, _, _ = encode(o, ["fight"])
    assert s[SEEN0] == 0.0


# --- reobserve: lining logged steps up with the protocol -----------------------------------------------

V4_KEYS = {"turn", "place", "depth", "hp", "hp_max", "mp", "mp_max", "xl", "progress", "ac", "ev", "sh", "str",
           "int", "dex", "poison_survival", "god", "piety", "status", "mons", "n_hostiles", "inv", "on_down",
           "on_up", "dist_down", "dist_up", "open_neighbors", "level_explored", "level_steps", "level_turns",
           "hp_delta", "last_action"}


def as_v4(o: dict) -> dict:
    """An observation as version 4 logged it: no sight fields."""
    out = {k: v for k, v in o.items() if k in V4_KEYS}
    out["mons"] = [{k: m[k] for k in reobserve.V4_MON_KEYS} for m in o["mons"]]
    return out


def synthetic_game(directory: Path, seed: int, notes: bool = True) -> tuple[list[dict], list[dict]]:
    """A protocol log and a version-4 step log for a three-choice game; returns (steps, true sight dicts)."""
    rows = ["#######", "#@....#", "#.....#", "#######"]
    msgs, (px, py) = [], (0, 0)
    m, (px, py) = map_message(rows, clear=True)
    msgs.append(m)
    msgs.append({"msg": "player", "hp": 30, "hp_max": 40, "turn": 10, "xl": 1, "place": "Dungeon", "depth": 1,
                 "pos": {"x": px, "y": py}, "status": []})
    script = [
        # (messages before the choice, monster hp shown) -- each choice is followed by a note
        [{"msg": "map", "cells": [{"x": 4, "y": 1, "mf": MF_MONS_HOSTILE, "t": {"bg": 1, "fg": [0x00200000, 0]},
                                   "mon": {"id": 3, "name": "gnoll", "threat": 1, "att": 0,
                                           "typedata": {"avghp": 13}}}]}],
        [{"msg": "player", "turn": 12, "hp": 26},
         {"msg": "map", "cells": [{"x": 4, "y": 1, "mf": 1, "mon": None, "t": {"bg": 1}},
                                  {"x": 3, "y": 1, "mf": MF_MONS_HOSTILE, "t": {"bg": 1, "fg": [0xC0000000, 0]},
                                   "mon": {"id": 3}}]}],
        [{"msg": "player", "turn": 14, "hp": 24}],
    ]
    state = GameState()
    for x in msgs:
        state.apply(x)
    steps, truth, lines = [], [], list(msgs)
    for i, part in enumerate(script):
        for x in part:
            state.apply(x)
            lines.append(x)
        lines.append({"msg": "input_mode", "mode": 1})
        o = observe(state, state.hostiles(), {"last_action": "fight" if i else None})
        truth.append(sight(state, sorted(state.hostiles(), key=lambda mm: state.distance(mm.pos))))
        steps.append({"game": seed, "step": i + 1, "obs": as_v4(o), "avail": ["fight"], "baseline": "fight",
                      "action": "fight", "source": "baseline"})
        if notes:
            lines.append({"msg": "_ladder", "keys": ["key_tab"]})
    directory.mkdir(parents=True, exist_ok=True)
    with gzip.open(directory / f"game{seed}.protocol.jsonl.gz", "wt") as fh:
        fh.write("".join(json.dumps(x) + "\n" for x in lines))
    end = {"type": "end", "game": seed, "died": False, "turn": 14, "max_depth": 1}
    (directory / "steps.jsonl").write_text("".join(json.dumps(x) + "\n" for x in steps + [end]))
    return steps, truth


@pytest.mark.parametrize("notes", [True, False])
def test_reobserve_aligns_every_step_and_rebuilds_its_sight(tmp_path, notes):
    steps, truth = synthetic_game(tmp_path / "g101" / "t", 101, notes=notes)
    lines = reobserve.sidecar_for(tmp_path / "g101" / "t" / "steps.jsonl")
    assert [x["step"] for x in lines] == [1, 2, 3]
    assert all(x["ok"] and x["exact"] for x in lines)
    assert [x["x"] for x in lines] == truth
    assert lines[0]["x"]["mons"][0]["beh"] == 2 and lines[1]["x"]["mons"][0]["mdam"] == 3


def test_a_step_the_replay_never_reaches_is_missing(tmp_path):
    d = tmp_path / "g102" / "t"
    steps, _ = synthetic_game(d, 102)
    steps[1]["obs"]["hp"] = 99                                 # no moment in the log has this
    (d / "steps.jsonl").write_text("".join(json.dumps(s) + "\n" for s in steps))
    lines = reobserve.sidecar_for(d / "steps.jsonl")
    assert [x["ok"] for x in lines] == [True, False, False]   # alignment is in order: what follows is lost too


def test_reobserve_without_a_protocol_log_marks_steps_missing(tmp_path):
    d = tmp_path / "g103" / "t"
    synthetic_game(d, 103)
    (d / "game103.protocol.jsonl.gz").unlink()
    assert [x["ok"] for x in reobserve.sidecar_for(d / "steps.jsonl")] == [False] * 3


def test_reobserve_never_reads_evaluation_dungeons(tmp_path):
    d = tmp_path / "g600000" / "t"
    synthetic_game(d, corpus.HOLDOUT_SEED + 100_000)
    assert reobserve.sidecar_for(d / "steps.jsonl") == []
    assert corpus.step_files(tmp_path) == []                   # nor walks into their directories


def test_step_files_skips_qw_runs_and_holdout_dirs(tmp_path):
    for rel in ("iter0/g5/t", "qw-s3/g5/t", "eval-x/g500001/t", "forks0/g7-3-rest/t", "forks0/g500002-3-rest/t"):
        (tmp_path / rel).mkdir(parents=True)
        (tmp_path / rel / "steps.jsonl").write_text("")
    got = sorted(str(f.parent.relative_to(tmp_path)) for f in corpus.step_files(tmp_path))
    assert got == ["forks0/g7-3-rest/t", "iter0/g5/t"]


def test_corpus_folds_sidecars_in_and_counts_what_is_missing(tmp_path):
    root, side = tmp_path / "runs", tmp_path / "side"
    synthetic_game(root / "brain" / "it" / "g104" / "t", 104)
    synthetic_game(root / "brain" / "it" / "g105" / "t", 105)
    src = root / "brain" / "it" / "g104" / "t" / "steps.jsonl"
    reobserve._job((str(src), str(side / "brain" / "it" / "g104" / "t" / reobserve.SIDECAR)))
    meta = corpus.build([root], tmp_path / "c.npz", sidecars=side)
    assert meta["sight"] == {"live": 0, "sidecar": 3, "missing": 3}
    data = np.load(tmp_path / "c.npz")
    assert sorted(data["self"][:, SEEN0].tolist()) == [0, 0, 0, 1, 1, 1]
    cov = reobserve.coverage([root], side)
    assert cov["total"]["steps"] == 3 and cov["total"]["ok"] == 3


def test_corpus_counts_live_sight_fields(tmp_path):
    d = tmp_path / "g106" / "t"
    steps, truth = synthetic_game(d, 106)
    live = [{**s, "obs": merge_sight(s["obs"], x)} for s, x in zip(steps, truth)]
    (d / "steps.jsonl").write_text("".join(json.dumps(s) + "\n" for s in live))
    assert corpus.build([tmp_path], tmp_path / "c.npz")["sight"] == {"live": 3, "sidecar": 0, "missing": 0}


# --- the contract --------------------------------------------------------------------------------------

def test_contract_carries_the_version_5_dims():
    c = contract()
    assert FEATURE_VERSION == 5
    assert (c["feature_version"], c["self_dim"], c["mon_dim"], c["max_mons"]) == (5, SELF_DIM, MON_DIM, MAX_MONS)
    assert SELF_DIM > V4_SELF and MON_DIM > V4_MON


def test_a_version_4_model_still_loads_and_reads_the_front_of_each_vector():
    """Version 4's numbers are the front of version 5's vectors, so the champion keeps playing."""
    rng = np.random.default_rng(0)
    H = 8
    shapes = {"self1": (H, V4_SELF), "mon1": (H, V4_MON + H), "mon2": (H, H), "trunk": (H, 3 * H),
              "head1": (H, H), "head2": (len(contract()["actions"]) * len(contract()["components"]), H),
              "danger": (1, H), "prior": (len(contract()["actions"]), H)}

    def b64(a):
        import base64
        return base64.b64encode(a.astype(np.float32).tobytes()).decode()
    layers = {k: {"shape": list(sh), "w": b64(rng.normal(size=sh)), "b": b64(rng.normal(size=sh[0]))}
              for k, sh in shapes.items()}
    v4 = {"format": "dcss-trained-brain", **contract(), "feature_version": 4, "self_dim": V4_SELF,
          "mon_dim": V4_MON, "dtype": "f32", "layers": layers,
          "norm": {"self_mean": [0.0] * V4_SELF, "self_std": [1.0] * V4_SELF,
                   "mon_mean": [0.0] * V4_MON, "mon_std": [1.0] * V4_MON}}
    net = TrainedNet(v4, "old")
    s, m = rng.normal(size=SELF_DIM).astype(np.float32), rng.normal(size=(MAX_MONS, MON_DIM)).astype(np.float32)
    mask = np.array([1, 1] + [0] * (MAX_MONS - 2), dtype=np.float32)
    q5, d5, p5 = net.forward(s, m, mask)
    q4, d4, p4 = net.forward(s[:V4_SELF], m[:, :V4_MON], mask)
    assert np.array_equal(q5, q4) and d5 == d4 and np.array_equal(p5, p4)
    with pytest.raises(ModelMismatch, match="feature_version"):
        TrainedNet({**v4, "feature_version": 3}, "old")
    with pytest.raises(ModelMismatch):
        TrainedNet({**v4, "self_dim": V4_SELF + 1}, "old")


def test_train_on_a_column_subset_only_when_not_strict(tmp_path):
    """The offline comparison trains on version 4's columns of a version 5 corpus."""
    pytest.importorskip("torch")
    from test_brain import synthetic_corpus

    from ladder.brain.train import train
    root = synthetic_corpus(tmp_path, games=8, length=12)
    full = tmp_path / "c.npz"
    corpus.build([root], full)
    data = dict(np.load(full))
    data["self"], data["mons"] = data["self"][:, :V4_SELF], data["mons"][:, :, :V4_MON]
    sub = tmp_path / "v4.npz"
    np.savez(sub, **data)
    meta = json.loads(Path(f"{full}.meta.json").read_text())
    Path(f"{sub}.meta.json").write_text(json.dumps({**meta, "self_dim": V4_SELF, "mon_dim": V4_MON}))
    with pytest.raises(ValueError, match="rebuild"):
        train(sub, tmp_path / "m.json", epochs=1, hidden=8, log=lambda *_: None)
    train(sub, tmp_path / "m.json", epochs=1, hidden=8, log=lambda *_: None, strict=False, save_val=tmp_path / "v.npz")
    model = json.loads((tmp_path / "m.json").read_text())
    assert (model["self_dim"], model["mon_dim"]) == (V4_SELF, V4_MON)
    assert TrainedNet(model).self_dim == V4_SELF               # plays as a version 4 model
    v = np.load(tmp_path / "v.npz")
    assert v["pred"].shape == (int(data["val"].sum()), len(contract()["components"]))


def test_the_champion_on_disk_still_loads_and_matches_its_parity_file():
    champion = ROOT / "models" / "brain.json"
    if not champion.exists():
        pytest.skip("no champion")
    from ladder.brain.net import check_parity
    assert TrainedNet.load(champion).self_dim in (V4_SELF, SELF_DIM)
    iter2 = ROOT / "models" / "iter2.json"                     # the champion's own training output
    if iter2.exists() and iter2.with_suffix(".parity.json").exists():
        assert check_parity(iter2) < 2e-3


# --- ensembles ------------------------------------------------------------------------------------------

def random_model(seed: int, self_dim: int = SELF_DIM, mon_dim: int = MON_DIM, counts: dict | None = None) -> dict:
    import base64
    rng = np.random.default_rng(seed)
    H, A, K = 8, len(contract()["actions"]), len(contract()["components"])
    shapes = {"self1": (H, self_dim), "mon1": (H, mon_dim + H), "mon2": (H, H), "trunk": (H, 3 * H),
              "head1": (H, H), "head2": (A * K, H), "danger": (1, H), "prior": (A, H)}
    b64 = lambda a: base64.b64encode(a.astype(np.float32).tobytes()).decode()  # noqa: E731
    return {"format": "dcss-trained-brain", **contract(), "self_dim": self_dim, "mon_dim": mon_dim,
            "feature_version": FEATURE_VERSION if self_dim == SELF_DIM else 4, "dtype": "f32",
            "action_counts": counts or {a: 100 for a in contract()["actions"]},
            "layers": {k: {"shape": list(sh), "w": b64(rng.normal(size=sh)), "b": b64(rng.normal(size=sh[0]))}
                       for k, sh in shapes.items()},
            "norm": {"self_mean": [0.0] * self_dim, "self_std": [1.0] * self_dim,
                     "mon_mean": [0.0] * mon_dim, "mon_std": [1.0] * mon_dim}}


def test_an_ensemble_averages_its_members_and_loads_from_a_manifest_or_a_list(tmp_path):
    from ladder.brain.net import ENSEMBLE_FORMAT, Ensemble, load_model
    few = {a: 100 for a in contract()["actions"]} | {"wear": 10}
    (tmp_path / "models").mkdir()
    paths = []
    for i, model in enumerate([random_model(1), random_model(2, counts=few), random_model(3, V4_SELF, V4_MON)]):
        paths.append(tmp_path / "models" / f"m{i}.json")
        paths[-1].write_text(json.dumps(model))
    nets = [TrainedNet.load(p) for p in paths]
    rng = np.random.default_rng(0)
    s, m = rng.normal(size=SELF_DIM).astype(np.float32), rng.normal(size=(MAX_MONS, MON_DIM)).astype(np.float32)
    mask = np.array([1] + [0] * (MAX_MONS - 1), dtype=np.float32)
    outs = [n.forward(s, m, mask) for n in nets]

    manifest = tmp_path / "ens.json"                          # member paths are relative to the manifest
    manifest.write_text(json.dumps({"format": ENSEMBLE_FORMAT, "members": [f"models/m{i}.json" for i in range(3)]}))
    for ens in (load_model(manifest), load_model(",".join(map(str, paths)))):
        assert isinstance(ens, Ensemble) and len(ens.members) == 3
        q, danger, prior = ens.forward(s, m, mask)
        assert q.shape == outs[0][0].shape and np.allclose(q, np.mean([o[0] for o in outs], 0))
        assert danger == pytest.approx(np.mean([o[1] for o in outs]))
        assert np.allclose(prior, np.mean([o[2] for o in outs], 0))
        assert ens.counts["wear"] == 10 and ens.counts["fight"] == 100      # the least any member saw
    assert load_model(manifest).name == "ens"
    assert isinstance(load_model(paths[0]), TrainedNet)
    assert len(load_model(f"{manifest},{paths[0]}").members) == 4          # a manifest in a list: its members
    with pytest.raises(ValueError):
        Ensemble([])


def test_brain_tiers_plays_with_an_ensemble(tmp_path):
    import random

    from test_brain import stairs_state

    from ladder.brain.net import load_model
    from ladder.brain.policy import BrainTiers
    for i in range(2):
        (tmp_path / f"m{i}.json").write_text(json.dumps(random_model(i)))
    tiers = BrainTiers(load_model(f"{tmp_path / 'm0.json'},{tmp_path / 'm1.json'}"), rng=random.Random(0))
    assert tiers.next_action(stairs_state()) in ("explore", "travel")
    assert tiers.last["source"] == "net" and set(tiers.last["values"]) == set(tiers.last["avail"])
    assert tiers.describe()["model"] == "m0+m1"
