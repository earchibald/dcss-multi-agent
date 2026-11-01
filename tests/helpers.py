"""Build GameStates from small ASCII maps for detector and travel tests."""

from ladder.state import (BG_UNSEEN, MF_FEATURE, MF_FLOOR, MF_ITEM, MF_MONS_HOSTILE, MF_STAIR_DOWN,
                          MF_STAIR_UP, MF_TRAP, MF_UNEXPLORED, MF_WALL, GameState)

GLYPH_MF = {
    ".": MF_FLOOR, "#": MF_WALL, "?": MF_UNEXPLORED, ">": MF_STAIR_DOWN, "<": MF_STAIR_UP,
    "^": MF_TRAP, "_": MF_FEATURE, "$": MF_ITEM, "@": MF_FLOOR,
}


def map_message(rows: list[str], clear: bool = False) -> tuple[dict, tuple[int, int]]:
    """A webtiles `map` message for an ASCII map, using run-length x like the server does."""
    cells, player = [], (0, 0)
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == " ":
                continue
            cell = {"mf": GLYPH_MF[ch], "g": ch, "t": {"bg": 1}}
            if x == 0 or row[x - 1] == " ":
                cell.update(x=x, y=y)
            cells.append(cell)
            if ch == "@":
                player = (x, y)
    return {"msg": "map", "clear": clear, "cells": cells}, player


def make_state(rows: list[str], hp: int = 20, hp_max: int = 20, turn: int = 10, **player) -> GameState:
    state = GameState()
    msg, (px, py) = map_message(rows, clear=True)
    state.apply(msg)
    state.apply({"msg": "player", "hp": hp, "hp_max": hp_max, "turn": turn, "xl": 1, "place": "Dungeon",
                 "depth": 1, "pos": {"x": px, "y": py}, "status": [], **player})
    return state


def add_monster(state: GameState, pos, mid: int, name: str, threat: int = 1, att: int = 0,
                visible: bool = True) -> None:
    cell = {"x": pos[0], "y": pos[1], "mf": MF_MONS_HOSTILE,
            "mon": {"id": mid, "name": name, "threat": threat, "att": att, "typedata": {}},
            "t": {"bg": 1 if visible else 1 | BG_UNSEEN}}
    state.apply({"msg": "map", "cells": [cell]})


def say(state: GameState, *texts: str, turn: int | None = None) -> None:
    state.apply({"msg": "msgs", "messages": [{"text": t, "turn": turn or state.turn, "channel": 0} for t in texts]})


def player(state: GameState, **fields) -> None:
    state.apply({"msg": "player", **fields})
