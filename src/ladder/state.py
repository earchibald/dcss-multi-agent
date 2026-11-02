"""Game state assembled from webtiles messages.

Webtiles sends partial updates: `player` messages carry only changed fields,
and `map` messages carry only changed cells (with run-length x coordinates).
GameState folds them into a current picture and produces compact snapshots
for interrupt detection and logging.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# map feature codes ("mf") from the webtiles protocol
MF_UNSEEN, MF_FLOOR, MF_WALL, MF_MAP_FLOOR, MF_MAP_WALL, MF_DOOR, MF_ITEM = 0, 1, 2, 3, 4, 5, 6
MF_MONS_FRIENDLY, MF_MONS_PEACEFUL, MF_MONS_NEUTRAL, MF_MONS_HOSTILE, MF_MONS_NO_EXP = 7, 8, 9, 10, 11
MF_STAIR_UP, MF_STAIR_DOWN, MF_STAIR_BRANCH, MF_FEATURE = 12, 13, 14, 15
MF_WATER, MF_LAVA, MF_TRAP, MF_DEEP_WATER = 16, 17, 18, 22
MF_PORTAL, MF_EXCL_ROOT, MF_EXCL, MF_UNEXPLORED = 23, 24, 25, 26

SHOP_GLYPH = "\u2229"               # ∩, the "arch" glyph: shops and portals
NOT_WALKABLE = {MF_UNSEEN, MF_WALL, MF_MAP_WALL, MF_LAVA, MF_DEEP_WATER, MF_UNEXPLORED}
FEATURE_KINDS = {
    MF_STAIR_UP: "upstairs",
    MF_STAIR_DOWN: "downstairs",
    MF_STAIR_BRANCH: "branch_stairs",
    MF_FEATURE: "feature",       # altars, fountains, shops…
    MF_PORTAL: "portal",
    MF_TRAP: "trap",
}

# tile background flags (webtiles enums.js): cell is remembered, not currently in view
BG_UNSEEN, BG_MM_UNSEEN = 0x40000, 0x20000

ATT_HOSTILE = 0
# monster threat levels as webtiles reports them
THREAT_NAMES = {0: "trivial", 1: "easy", 2: "tough", 3: "nasty"}

PLACE_ABBREV = {
    "Dungeon": "D", "Temple": "Temple", "Lair": "Lair", "Orcish Mines": "Orc",
    "Swamp": "Swamp", "Shoals": "Shoals", "Snake Pit": "Snake", "Spider Nest": "Spider",
    "Elven Halls": "Elf", "Vaults": "Vaults", "Crypt": "Crypt", "Depths": "Depths",
}

_TAG = re.compile(r"</?[a-z]+>")


def strip_tags(text: str) -> str:
    return _TAG.sub("", text)


@dataclass
class Monster:
    id: int
    name: str
    pos: tuple[int, int]
    threat: int
    attitude: int
    no_exp: bool

    @property
    def hostile(self) -> bool:
        return self.attitude == ATT_HOSTILE and not self.no_exp

    @property
    def unique(self) -> bool:
        # Named uniques (Natasha, Sigmund, Grinder…) are the only capitalized monster names
        return self.name[:1].isupper()


def in_view(cell: dict) -> bool:
    bg = (cell.get("t") or {}).get("bg")
    return bg is None or not (bg & (BG_UNSEEN | BG_MM_UNSEEN))


@dataclass
class GameState:
    player: dict = field(default_factory=dict)
    cells: dict[tuple[int, int], dict] = field(default_factory=dict)
    monster_info: dict[int, dict] = field(default_factory=dict)
    messages: list[dict] = field(default_factory=list)   # {"turn", "channel", "text"}
    level_seq: int = 0          # bumps on every map clear (new level, or a scenario rebuild)
    dead: bool = False
    in_game: bool = False

    # --- folding messages ----------------------------------------------

    def apply(self, msg: dict) -> None:
        kind = msg.get("msg")
        if kind == "player":
            self.player.update({k: v for k, v in msg.items() if k != "msg"})
        elif kind == "map":
            self._apply_map(msg)
        elif kind == "msgs":
            for m in msg.get("messages", []):
                text = strip_tags(m.get("text", ""))
                self.messages.append({"turn": m.get("turn"), "channel": m.get("channel"), "text": text})
                if "You die..." in text:
                    self.dead = True
        elif kind == "game_started":
            self.in_game = True
        elif kind == "go_lobby":
            self.in_game = False

    def _apply_map(self, msg: dict) -> None:
        if msg.get("clear"):
            self.cells.clear()
            self.level_seq += 1
        x = y = 0
        for cell in msg.get("cells", []):
            x = cell.get("x", x)
            y = cell.get("y", y)
            cur = self.cells.setdefault((x, y), {})
            for key, value in cell.items():
                if key in ("x", "y"):
                    continue
                if key == "mon":
                    if value is None:
                        cur.pop("mon", None)
                        continue
                    mid = value.get("id")
                    if mid is None:
                        # an update without an id refers to whatever already stands here
                        mid = cur.get("mon")
                        if mid is None:
                            continue
                    known = self.monster_info.setdefault(mid, {})
                    known.update({k: v for k, v in value.items() if k != "id"})
                    if "name" not in known:
                        # Webtiles sends a bare id for a monster of the same kind as the most
                        # recently described one; copy that one's info (dcss-api monster docs).
                        donors = [k for k, v in self.monster_info.items() if k != mid and v.get("name")]
                        if donors:
                            known.update(self.monster_info[max(donors)])
                    cur["mon"] = mid
                elif key == "t":
                    cur.setdefault("t", {}).update(value)
                else:
                    cur[key] = value
            x += 1

    # --- reading -------------------------------------------------------

    @property
    def pos(self) -> tuple[int, int]:
        p = self.player.get("pos") or {}
        return (p.get("x", 0), p.get("y", 0))

    @property
    def hp(self) -> int:
        return self.player.get("hp", 0)

    @property
    def hp_max(self) -> int:
        return self.player.get("hp_max", 0) or 1

    @property
    def turn(self) -> int:
        return self.player.get("turn", 0)

    @property
    def place(self) -> str:
        place = self.player.get("place", "")
        depth = self.player.get("depth", 0)
        abbrev = PLACE_ABBREV.get(place, place)
        return f"{abbrev}:{depth}" if depth else abbrev

    @property
    def statuses(self) -> list[str]:
        out = []
        for s in self.player.get("status", []) or []:
            label = s.get("light") or s.get("text")
            if label:
                out.append(label)
        return out

    @property
    def caught(self) -> bool:
        """Held in a web or net: moving only struggles, and autofight won't attack."""
        return "Held" in self.statuses

    def monsters(self) -> list[Monster]:
        """Monsters currently in view. Webtiles keeps remembered monsters on unseen cells."""
        out = []
        for pos, cell in self.cells.items():
            mid = cell.get("mon")
            if mid is None or not in_view(cell):
                continue
            info = self.monster_info.get(mid, {})
            out.append(Monster(
                id=mid,
                name=info.get("name", "?"),
                pos=pos,
                threat=info.get("threat", 0),
                attitude=info.get("att", ATT_HOSTILE),
                no_exp=bool((info.get("typedata") or {}).get("no_exp")) or cell.get("mf") == MF_MONS_NO_EXP,
            ))
        return out

    def hostiles(self) -> list[Monster]:
        return [m for m in self.monsters() if m.hostile]

    def features(self) -> dict[tuple[int, int], str]:
        return {pos: FEATURE_KINDS[c["mf"]] for pos, c in self.cells.items() if c.get("mf") in FEATURE_KINDS}

    def shops(self) -> set[tuple[int, int]]:
        """Shop entrances. Portals share the arch glyph but not the minimap feature flag."""
        return {pos for pos, c in self.cells.items() if c.get("mf") == MF_FEATURE and c.get("g") == SHOP_GLYPH}

    def items(self) -> set[tuple[int, int]]:
        return {pos for pos, c in self.cells.items() if c.get("mf") == MF_ITEM}

    def distance(self, pos: tuple[int, int]) -> int:
        px, py = self.pos
        return max(abs(pos[0] - px), abs(pos[1] - py))

    def snapshot(self) -> dict:
        """Compact, JSON-ready view of the situation: what a log line (and later Jev) sees."""
        hostiles = sorted(self.hostiles(), key=lambda m: self.distance(m.pos))
        return {
            "turn": self.turn,
            "place": self.place,
            "level_seq": self.level_seq,
            "pos": list(self.pos),
            "hp": self.hp,
            "hp_max": self.player.get("hp_max", 0),
            "mp": self.player.get("mp", 0),
            "xl": self.player.get("xl", 0),
            "species": self.player.get("species"),
            "god": self.player.get("god") or None,
            "status": self.statuses,
            "hostiles": [
                {"name": m.name, "dist": self.distance(m.pos), "threat": THREAT_NAMES.get(m.threat, m.threat),
                 **({"unique": True} if m.unique else {})}
                for m in hostiles
            ],
            "items_known": len(self.items()),
        }

    def recent_messages(self, n: int = 5) -> list[str]:
        return [m["text"] for m in self.messages[-n:]]
