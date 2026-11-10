"""Turning a recorded human game (playproxy's play<n>.jsonl) into step-log rows."""

import json
import os

from helpers import map_message

from ladder.brain import corpus
from ladder.brain.features import N_COMPONENTS
from ladder.brain.humanplay import convert, convert_all, key_tokens, step_of
from ladder.state import MF_MONS_HOSTILE


def game(msg: dict) -> dict:
    return {"t": 0, "from": "game", "msg": msg}


def key(text: str) -> dict:
    return {"t": 0, "from": "player", "msg": {"msg": "input", "text": text}}


def code(n: int) -> dict:
    return {"t": 0, "from": "player", "msg": {"msg": "key", "keycode": n}}


def mode(n: int) -> dict:
    return game({"msg": "input_mode", "mode": n})


def start(rows: list[str], hp: int = 20, hp_max: int = 20, turn: int = 10, depth: int = 3, **player) -> list[dict]:
    msg, (px, py) = map_message(rows, clear=True)
    return [{"t": 0, "from": "proxy", "msg": {"msg": "session", "user": "laddertest", "started": "x"}},
            game({"msg": "game_started"}), game(msg),
            game({"msg": "player", "hp": hp, "hp_max": hp_max, "turn": turn, "xl": 1, "place": "Dungeon",
                  "depth": depth, "pos": {"x": px, "y": py}, "status": [], **player}),
            mode(1)]


def after(turn: int | None = None, *extra: dict, **player) -> list[dict]:
    """The game's answer to a key: busy, what changed, waiting again."""
    update = {"msg": "player", **({"turn": turn} if turn is not None else {}), **player}
    return [mode(0), *extra, game(update), mode(1)]


def monster(pos: tuple[int, int], mid: int, name: str = "jackal") -> dict:
    return game({"msg": "map", "cells": [{"x": pos[0], "y": pos[1], "mf": MF_MONS_HOSTILE, "t": {"bg": 1},
                                          "mon": {"id": mid, "name": name, "threat": 1, "att": 0, "typedata": {}}}]})


def say(*texts: str) -> dict:
    return game({"msg": "msgs", "messages": [{"text": t, "turn": 0, "channel": 0} for t in texts]})


def run(tmp_path, lines: list[dict], name: str = "play1.jsonl"):
    rec = tmp_path / "runs" / "20260101-000000" / name
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text("".join(json.dumps(line) + "\n" for line in lines))
    summary = convert(rec, tmp_path / "out")
    out = [json.loads(line) for line in open(summary["out"])]
    return summary, [r for r in out if r.get("type") != "end"], out[-1]


def test_keycodes_from_webtiles():
    assert key_tokens({"msg": "input", "text": "o"}) == ["o"]
    assert key_tokens({"msg": "key", "keycode": 9}) == ["\t"]
    assert key_tokens({"msg": "key", "keycode": 24}) == ["^x"]          # ctrl-X, as in the recordings
    assert key_tokens({"msg": "key", "keycode": -254}) == ["k"]         # arrow up
    assert key_tokens({"msg": "key", "keycode": -245}) == ["n"]         # PgDn
    assert key_tokens({"msg": "key", "keycode": -243}) == ["K"]         # shift-up: run
    assert key_tokens({"msg": "key", "keycode": -223}) == ["^n"]        # ctrl-PgDn: attack in place
    assert key_tokens({"msg": "key", "keycode": -1007}) == ["7"]        # numpad 7
    assert step_of("k") == (0, -1) and step_of("K") == (0, -1) and step_of("^k") == (0, -1)
    assert step_of("7") == (-1, -1) and step_of("5") is None and step_of("^x") is None and step_of("o") is None


def test_explore_and_rest_become_rows_and_the_game_ends(tmp_path):
    lines = start(["@...."], hp=10)
    lines += [key("o"), *after(40, pos={"x": 4, "y": 0})]
    lines += [key("5"), *after(90, hp=20)]
    summary, rows, end = run(tmp_path, lines)
    assert [r["action"] for r in rows] == ["explore", "rest"]
    assert all(r["source"] == "human" and r["game"] == 1 for r in rows)
    assert rows[0]["obs"]["turn"] == 10 and rows[1]["obs"]["turn"] == 40
    assert rows[1]["obs"]["last_action"] == "explore" and rows[1]["obs"]["level_steps"] == 1
    assert "explore" in rows[0]["avail"] and rows[0]["baseline"] in rows[0]["avail"]
    assert end == {**end, "type": "end", "game": 1, "died": False, "ended_by": "left", "turn": 90, "hp": 20,
                   "depth": 3, "max_depth": 3}
    assert summary["by_action"] == {"explore": 1, "rest": 1} and summary["keys"] == 2


def test_fight_one_row_per_blow(tmp_path):
    lines = start(["@...."]) + [monster((1, 0), 7)]
    lines += [key("l"), *after(11, hp=18)]               # step into the jackal: an attack
    lines += [code(9), *after(12)]                        # Tab
    lines += [code(9), *after(13)]
    summary, rows, _ = run(tmp_path, lines)
    assert [r["action"] for r in rows] == ["fight"] * 3
    assert rows[0]["obs"]["mons"][0]["name"] == "jackal" and rows[0]["obs"]["n_hostiles"] == 1
    assert rows[1]["obs"]["hp_delta"] < 0


def test_stepping_toward_a_distant_hostile_is_fight(tmp_path):
    lines = start(["@...."]) + [monster((4, 0), 7)]
    lines += [key("l"), *after(11, pos={"x": 1, "y": 0})]
    _, rows, _ = run(tmp_path, lines)
    assert [r["action"] for r in rows] == ["fight"]


def test_unmapped_keys_and_idle_commands_are_skipped(tmp_path):
    lines = start(["@...."])
    lines += [key("l"), *after(11, pos={"x": 1, "y": 0})]                       # walking by hand
    lines += [key("i"), mode(0), game({"msg": "menu", "tag": "inventory", "items": []}),
              code(27), game({"msg": "close_menu"}), mode(1)]                    # a menu, cancelled
    lines += [key("o"), mode(0), say("Done exploring."), mode(1)]                # no time passed
    lines += [key("s"), *after(12)]                                              # waiting at full HP
    summary, rows, _ = run(tmp_path, lines)
    assert rows == []
    assert summary["skipped"] == {"manual_move": 1, "unmapped": 2, "no_turn": 1, "wait_unhurt": 1}
    assert summary["keys"] == 5


def test_done_exploring_marks_the_level(tmp_path):
    lines = start(["@...."], hp=10)
    lines += [key("o"), mode(0), say("Done exploring."), mode(1)]
    lines += [key("5"), *after(30, hp=20)]
    _, rows, _ = run(tmp_path, lines)
    assert rows[0]["action"] == "rest" and rows[0]["obs"]["level_explored"]
    assert "explore" not in rows[0]["avail"]


def test_quaff_and_read_by_the_stack_used(tmp_path):
    # Letters repeat across item classes (0.32+): potion a and scroll a are different items.
    inv = {"0": {"base_type": 7, "quantity": 2, "letter": ord("a"), "name": "2 potions of curing"},
           "1": {"base_type": 7, "quantity": 1, "letter": ord("b"), "name": "bubbling potion"},
           "2": {"base_type": 5, "quantity": 1, "letter": ord("a"), "name": "scroll labelled FOO"},
           "3": {"base_type": 7, "quantity": 1, "letter": ord("c"), "name": "potion of might"}}
    lines = start(["@...."], hp=5, inv=inv)
    lines += [key("q"), mode(0), key("a"), *after(11, inv={"0": {"quantity": 1, "name": "potion of curing"}})]
    lines += [key("q"), mode(0), key("\r"), *after(12, inv={"1": {"quantity": 0}})]       # Enter on the hovered one
    lines += [key("r"), mode(0), key("a"), *after(13, inv={"2": {"quantity": 0}})]
    lines += [key("q"), mode(0), key("c"), *after(14, inv={"3": {"quantity": 0}})]       # known, not healing
    lines += [key("q"), mode(0), code(27), mode(1)]                                       # changed their mind
    summary, rows, _ = run(tmp_path, lines)
    assert [r["action"] for r in rows] == ["quaff_heal", "quaff_unknown", "read_unknown"]
    assert summary["skipped"] == {"item_other": 2, "item_cancelled": 2}


def test_wait_and_flee_up_with_hostiles(tmp_path):
    lines = start(["<..@.", "....."]) + [monster((4, 1), 7)]
    lines += [key("h"), *after(11, pos={"x": 2, "y": 0})]     # away from the jackal, a step nearer the stairs
    lines += [monster((4, 1), 7), game({"msg": "map", "cells": [{"x": 4, "y": 1, "mon": None},
                                                                  {"x": 4, "y": 0, "mon": {"id": 7}}]})]
    lines += [key("s"), *after(12)]                            # it is two away: waiting is a choice
    lines += [key("h"), key("h"), *after(14, pos={"x": 0, "y": 0})]
    lines += [key("<"), *after(15, game(map_message(["@.."], clear=True)[0]), depth=2)]
    summary, rows, end = run(tmp_path, lines)
    assert [r["action"] for r in rows] == ["flee_up", "wait", "flee_up", "flee_up"]
    assert all(r["action"] in r["avail"] for r in rows)
    assert summary["skipped"] == {"while_busy": 1}             # the second h, typed ahead
    assert end["depth"] == 2 and end["max_depth"] == 3


def test_descend_by_key_and_by_travel(tmp_path):
    lines = start([".>..."], depth=1, pos={"x": 1, "y": 0})
    lines += [key(">"), *after(11, game(map_message(["@>.."], clear=True)[0]), depth=2, pos={"x": 0, "y": 0})]
    lines += [key("G"), mode(7), key(">"), *after(20, game(map_message(["@.."], clear=True)[0]), depth=3)]
    lines += [key(">"), mode(0), say("You can't go down here!"), mode(1)]
    summary, rows, end = run(tmp_path, lines)
    assert [r["action"] for r in rows] == ["descend", "descend"]
    assert rows[1]["obs"]["level_steps"] == 0 and rows[1]["obs"]["depth"] == 2
    assert summary["skipped"] == {"no_turn": 1}
    assert end["max_depth"] == 3


def test_corpus_reads_and_labels_a_death(tmp_path):
    lines = start(["@...."], hp=6) + [monster((1, 0), 7, "orc")]
    lines += [code(9), *after(11, hp=3)]
    lines += [code(9), mode(0), say("The orc hits you!", "You die..."), game({"msg": "player", "hp": -1}), mode(5),
              code(27), key("\r"), game({"msg": "game_ended", "reason": "dead"})]
    summary, rows, end = run(tmp_path, lines)
    assert end["died"] and end["ended_by"] == "died"
    # the killing blow is a row though no new turn count came with it; the death screen's keys are not
    assert [r["action"] for r in rows] == ["fight", "fight"]
    assert summary["skipped"] == {"while_busy": 2}
    [g] = corpus.read_games([tmp_path / "out"])
    assert len(g["steps"]) == 2 and g["end"]["died"]
    q = corpus.label(g)
    assert q.shape == (2, N_COMPONENTS) and (q[:, 0] == 1.0).all()             # died soon
    meta = corpus.build([tmp_path / "out"], tmp_path / "corpus.npz")
    assert meta["by_source"] == {"human": 2} and meta["deaths"] == 1


def test_convert_all_skips_spectator_records_and_fresh_outputs(tmp_path):
    run_dir = tmp_path / "runs" / "20260101-000000"
    run_dir.mkdir(parents=True)
    lines = start(["@...."], hp=10) + [key("5"), *after(30, hp=20)]
    (run_dir / "play1.jsonl").write_text("".join(json.dumps(line) + "\n" for line in lines))
    (run_dir / "player1.protocol.jsonl").write_text("")
    first = convert_all(tmp_path / "runs", tmp_path / "out")
    assert [s["rows"] for s in first] == [1]
    assert (tmp_path / "out" / "20260101-000000-play1" / "steps.jsonl").exists()
    assert convert_all(tmp_path / "runs", tmp_path / "out") == []
    os.utime(run_dir / "play1.jsonl", (2e9, 2e9))                     # the recording changed since
    assert len(convert_all(tmp_path / "runs", tmp_path / "out")) == 1
