"""Extract a monster table from DCSS 0.34's own source: the data the knowledge bots' monster lookup uses.

    uv run python tools/knowledge/monsters.py                      # read from the running container
    uv run python tools/knowledge/monsters.py --src ~/src/crawl/crawl-ref/source

Reads (read-only, with `docker exec ... cat`):
- mon-data.h          stats, attacks, resists, flags, spellbook (generated from dat/mons/*.yaml)
- mon-spell.h         what each spellbook casts, and how often
- spl-data.h          spell display names
- mon-pick-data.h     where each monster spawns at random: branch, depth range, weight
- dat/des/builder/uniques.des   where each unique is placed

Writes docs/data/monsters-0.34.json. Not covered: bands (an orc priest comes with orcs), vault-placed
monsters, equipment (mon-gear.cc), and what holiness adds (undead and demons resist more than listed).
Numbers are the definition's: HP is the average (each monster rolls within about a third of it),
attack damage is the maximum before the monster's weapon.
"""

from __future__ import annotations

import argparse
import json
import operator
import re
import subprocess
import sys
from pathlib import Path

CONTAINER = "dcss-multi-agent-dcss-1"
CRAWL = "/crawl"
OUT = Path(__file__).resolve().parents[2] / "docs" / "data" / "monsters-0.34.json"
TAG_MAJOR_VERSION = 34
COMPARE = {"==": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge,
           "<": operator.lt, "<=": operator.le}

# monsterentry's fields in order (mon-util.h, struct monsterentry)
FIELDS = ["mc", "glyph", "colour", "name", "flags", "resists", "exp", "exp_is_mult", "genus", "species",
          "holiness", "will", "attacks", "hd", "hp_10x", "ac", "ev", "spellbook", "corpse", "shout",
          "intel", "habitat", "speed", "energy", "uses", "size", "shape", "god", "tile", "corpse_tile"]
ENERGY = ["move", "swim", "attack", "missile", "spell"]     # mon_energy_usage, 10 = normal, lower = faster
FLAGS_KEPT = {"M_UNIQUE", "M_FIGHTER", "M_ARCHER", "M_SEE_INVIS", "M_INVIS", "M_FLIES", "M_FAST_REGEN",
              "M_SPEAKS", "M_BATTY", "M_STATIONARY", "M_PHASE_SHIFT", "M_SPINY", "M_PREFER_RANGED",
              "M_WEB_SENSE", "M_CANT_SPAWN", "M_NO_EXP_GAIN", "M_MAINTAIN_RANGE"}
# Attack flavours a Minotaur Berserker of Trog has to answer differently (docs/knowledge-bots.md).
# Effects as melee-attack.cc applies them to the player in 0.34.
DANGER_FLAVOURS = {
    "AF_POISON": ("poison",), "AF_POISON_STRONG": ("poison",), "AF_REACH_STING": ("poison", "reach"),
    "AF_POISON_PARALYSE": ("poison", "slows", "paralyses"),      # hornet, jorogumo
    "AF_MINIPARA": ("poison", "paralyses"), "AF_DRAIN_SPEED": ("slows",), "AF_CONFUSE": ("confuses",),
    "AF_RAGE": ("forces berserk",), "AF_SLEEP": ("sleep",), "AF_ENSNARE": ("ensnares",),
    "AF_DRAIN": ("drains",), "AF_WEAKNESS": ("weakens",), "AF_CORRODE": ("corrodes",), "AF_ACID": ("corrodes",),
    "AF_ANTIMAGIC": ("antimagic",), "AF_STEAL": ("steals",), "AF_BARBS": ("barbs",), "AF_DRAG": ("drags",),
    "AF_REACH": ("reach",), "AF_REACH_TONGUE": ("reach", "corrodes"), "AF_REACH_CLEAVE_UGLY": ("reach",),
    "AF_TRAMPLE": ("trample",), "AF_SWOOP": ("swoop",), "AF_BLINK": ("blinks",), "AF_BLINK_WITH": ("blinks",),
    "AF_DISTORT": ("distorts",), "AF_RIFT": ("distorts",), "AF_CHAOTIC": ("chaos",), "AF_VAMPIRIC": ("vampiric",),
    "AF_SPIDER": ("summons",), "AF_DOOM": ("doom",), "AF_VULN": ("strips willpower",), "AF_DROWN": ("drowns",),
}
# Effects that live in code, not in mon-data.h
CODE_TAGS = {"MONS_TORPOR_SNAIL": ("slows",)}      # an aura that keeps you slowed while near it (mon-aura.cc)
# Words in a spellbook's spell names, and the tag each gives
SPELL_TAGS = (("slow", "slows"), ("concentrate venom", "slows"), ("paraly", "paralyses"), ("confus", "confuses"),
              ("blink", "blinks"), ("haste", "hastes"), ("summon", "summons"), ("call", "summons"),
              ("poison", "poison"), ("venom", "poison"), ("virulence", "poison"), ("smit", "smites"),
              ("petrif", "petrifies"), ("teleport", "teleports"), ("mesmeris", "mesmerises"),
              ("siren song", "mesmerises"), ("dimension anchor", "anchors"), ("ensnare", "ensnares"),
              ("banish", "banishes"), ("sleep", "sleep"))


def read(path: str, src: Path | None) -> str:
    if src:
        return (src / path).read_text(errors="replace")
    return subprocess.run(["docker", "exec", CONTAINER, "cat", f"{CRAWL}/{path}"], check=True,
                          capture_output=True, text=True, errors="replace").stdout


def preprocess(text: str) -> str:
    """Drop comments, #define blocks, and #if TAG_MAJOR_VERSION branches that don't hold for 0.34."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    out, keep, in_define = [], [True], False
    for line in text.split("\n"):
        s = line.strip()
        if in_define:
            in_define = s.endswith("\\")
            continue
        if s.startswith("#define"):
            in_define = s.endswith("\\")
            continue
        if s.startswith("#if"):
            m = re.match(r"#if\s+TAG_MAJOR_VERSION\s*(==|!=|>=|<=|>|<)\s*(\d+)", s)
            cond = COMPARE[m.group(1)](TAG_MAJOR_VERSION, int(m.group(2))) if m else True
            keep.append(keep[-1] and cond)
            continue
        if s.startswith("#else"):
            keep[-1] = not keep[-1] and keep[-2]
            continue
        if s.startswith("#endif"):
            keep.pop()
            continue
        if s.startswith("#"):
            continue
        if keep[-1]:
            out.append(line)
    return "\n".join(out)


def unquoted(text: str, start: int = 0):
    """(index, char) for each character outside C string and char literals (a glyph can be '{')."""
    quote, escaped = None, False
    for i in range(start, len(text)):
        ch = text[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        yield i, ch


def split_top(body: str) -> list[str]:
    """Split on commas that are not inside braces, parentheses or quotes."""
    parts, depth, last = [], 0, 0
    for i, ch in unquoted(body):
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(body[last:i].strip())
            last = i + 1
    if body[last:].strip():
        parts.append(body[last:].strip())
    return parts


def braced(text: str, start: int) -> tuple[str, int]:
    """The text inside the brace at `start`, and the index after its closing brace."""
    depth = 0
    for i, ch in unquoted(text, start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
    raise ValueError("unbalanced braces")


def next_brace(text: str, start: int) -> int:
    return next((i for i, ch in unquoted(text, start) if ch == "{"), -1)


def array_body(text: str, marker: str) -> str:
    start = next_brace(text, text.index(marker))
    return braced(text, start)[0]


def enum_name(token: str, prefix: str) -> str:
    return token.strip().removeprefix(prefix).lower().replace("_", " ")


def parse_resists(expr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for term in (t.strip() for t in expr.split("|")):
        if m := re.fullmatch(r"mrd\((MR_\w+),\s*(-?\d+)\)", term):
            out[enum_name(m.group(1), "MR_RES_")] = int(m.group(2))
        elif term.startswith("MR_RES_"):
            out[enum_name(term, "MR_RES_")] = 1
        elif term.startswith("MR_VUL_"):
            out[enum_name(term, "MR_VUL_")] = -1
    return out


def parse_attacks(expr: str) -> list[dict]:
    return [{"type": enum_name(m.group(1), "AT_"), "flavour": enum_name(m.group(2), "AF_"),
             "damage": int(m.group(3)), "_af": m.group(2)}
            for m in re.finditer(r"\{\s*(AT_\w+)\s*,\s*(AF_\w+)\s*,\s*(\d+)\s*\}", expr)]


def parse_energy(expr: str) -> dict[str, int]:
    expr = expr.strip()
    if expr == "DEFAULT_ENERGY":
        return dict.fromkeys(ENERGY, 10)
    if m := re.fullmatch(r"mon_energy_usage::(attack|missile|swim)_cost\((\d+)(?:,\s*(\d+))?\)", expr):
        e = dict.fromkeys(ENERGY, 10)
        e[m.group(1)] = int(m.group(2))
        if m.group(3):
            e["swim"] = int(m.group(3))
        return e
    nums = [int(x) for x in re.findall(r"-?\d+", expr)]
    return dict(zip(ENERGY, nums + [10] * (len(ENERGY) - len(nums))))


def parse_monsters(text: str) -> list[dict]:
    body = array_body(preprocess(text), "mondata[]")
    mons, i = [], 0
    while (start := next_brace(body, i)) >= 0:
        inner, i = braced(body, start)
        f = dict(zip(FIELDS, split_top(inner)))
        if len(f) < len(FIELDS) - 1:
            continue
        flags = [t.strip() for t in f["flags"].split("|")]
        hd = int(f["hd"])
        will: int | str = "invuln" if f["will"].strip() == "WILL_INVULN" else int(f["will"])
        if isinstance(will, int) and will < 0:
            will = -will * hd              # negative means per HD
        energy = parse_energy(f["energy"])
        mons.append({
            "name": f["name"].strip().strip('"'),
            "enum": f["mc"].strip(),
            "glyph": f["glyph"].strip().strip("'"),
            "colour": f["colour"].strip().lower(),
            "hd": hd,
            "hp": round(int(f["hp_10x"]) / 10, 1),
            "ac": int(f["ac"]),
            "ev": int(f["ev"]),
            "will": will,
            "speed": int(f["speed"]),
            "energy": {k: v for k, v in energy.items() if v != 10},
            "attacks": parse_attacks(f["attacks"]),
            "resists": parse_resists(f["resists"]),
            "flags": sorted(enum_name(x, "M_") for x in flags if x in FLAGS_KEPT),
            "holiness": [enum_name(x, "MH_") for x in f["holiness"].split("|")],
            "intel": enum_name(f["intel"], "I_"),
            "habitat": enum_name(f["habitat"], "HT_"),
            "size": enum_name(f["size"], "SIZE_"),
            "uses": enum_name(f["uses"], "MONUSE_"),
            "god": enum_name(f["god"], "GOD_"),
            "exp": int(f["exp"]),
            "spellbook": f["spellbook"].strip(),
        })
    return mons


def parse_spell_names(text: str) -> dict[str, str]:
    return dict(re.findall(r"\b(SPELL_\w+),\s*\"([^\"]+)\"", text))


def parse_spellbooks(text: str, names: dict[str, str]) -> dict[str, list[dict]]:
    body = array_body(preprocess(text), "mspell_list[]")
    books, i = {}, 0
    while (start := next_brace(body, i)) >= 0:
        inner, i = braced(body, start)
        m = re.match(r"\s*(MST_\w+)\s*,", inner)
        if not m:
            continue
        books[m.group(1)] = [
            {"spell": names.get(s.group(1), enum_name(s.group(1), "SPELL_")), "freq": int(s.group(2)),
             "kind": sorted(enum_name(x, "MON_SPELL_") for x in s.group(3).split("|") if x.strip())}
            for s in re.finditer(r"\{\s*(SPELL_\w+)\s*,\s*(\d+)\s*,\s*([^}]*)\}", inner)]
    return books


def parse_population(text: str) -> dict[str, list[dict]]:
    """monster enum -> [{branch, from, to, weight, shape}] for random generation."""
    clean = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    out: dict[str, list[dict]] = {}
    branch = None
    for line in clean.split("\n"):
        if m := re.match(r"\s*\{\s*//\s*([A-Z][A-Za-z' ]+)", line):
            branch = m.group(1).strip()
            continue
        if line.lstrip().startswith("#define"):
            branch = None                  # the shared Depths list, named where it is used
        m = re.match(r"\s*\{\s*(-?\d+),\s*(-?\d+),\s*(\d+),\s*(\w+),\s*(MONS_\w+)\s*\}", line)
        if m and branch and not branch.startswith("Extended generic zombie"):
            out.setdefault(m.group(5), []).append({"branch": branch, "from": int(m.group(1)), "to": int(m.group(2)),
                                                   "weight": int(m.group(3)), "shape": m.group(4).lower()})
    return out


def parse_uniques(text: str) -> dict[str, list[str]]:
    """unique name -> its DEPTH lines from uniques.des."""
    out: dict[str, list[str]] = {}
    depth: list[str] = []
    for line in text.split("\n"):
        if line.startswith("NAME:"):
            depth = []
        elif line.startswith("DEPTH:"):
            depth.append(line.split(":", 1)[1].strip())
        elif m := re.match(r":\s*place_unique\(_G,\s*\"(.+?)(?: band)?\"\)", line):
            out.setdefault(m.group(1), []).extend(depth)
        elif (m := re.match(r"MONS:\s*(.+)", line)) and depth:
            out.setdefault(m.group(1).strip(), []).extend(depth)
    return out


def tags(m: dict, book: list[dict]) -> list[str]:
    """Plain danger tags, derived only from the numbers above (no judgement about the monster)."""
    t = set()
    if m["speed"] > 10:
        t.add("fast")
    if m["speed"] < 10:
        t.add("slow mover")
    if m["energy"].get("attack", 10) < 10:
        t.add("quick attacks")
    if m["energy"].get("attack", 10) > 10:
        t.add("slow attacks")
    for a in m["attacks"]:
        t.update(DANGER_FLAVOURS.get(a["_af"], ()))
    t.update(CODE_TAGS.get(m["enum"], ()))
    spells = " ".join(s["spell"].lower() for s in book)
    t.update(tag for word, tag in SPELL_TAGS if word in spells)
    if "unique" in m["flags"]:
        t.add("unique")
    if m["resists"].get("poison", 0) > 0 or set(m["holiness"]) & {"undead", "nonliving", "demonic"}:
        t.add("rPois")
    return sorted(t)


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--src", type=Path, help="a crawl-ref/source checkout instead of the container")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()

    mons = parse_monsters(read("mon-data.h", args.src))
    books = parse_spellbooks(read("mon-spell.h", args.src), parse_spell_names(read("spl-data.h", args.src)))
    pop = parse_population(read("mon-pick-data.h", args.src))
    uniq = parse_uniques(read("dat/des/builder/uniques.des", args.src))
    rows = []
    for m in mons:
        if m["name"].startswith("removed "):
            continue
        book = books.get(m["spellbook"], [])
        row = {k: v for k, v in m.items() if k != "spellbook"}
        row["tags"] = tags(m, book)
        for a in row["attacks"]:
            a.pop("_af")
        row["spells"] = book
        row["spawns"] = pop.get(m["enum"], [])
        if m["name"] in uniq:
            row["placed"] = uniq[m["name"]]
        rows.append(row)
    rows.sort(key=lambda r: r["name"].lower())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"version": "0.34.0",
            "source": "crawl-ref/source: mon-data.h, mon-spell.h, spl-data.h, mon-pick-data.h, "
                      "dat/des/builder/uniques.des",
            "generator": "tools/knowledge/monsters.py",
            "notes": "hp is the average; attack damage is the maximum before weapons; speed 10 = normal; "
                     "energy lists only non-default costs (lower = faster); spawns are random generation only "
                     "(no bands or vaults); a 'from' below 1 widens the weighting, it does not place a monster "
                     "above the branch's first floor; tags are derived from these numbers, not judged."}
    # one monster per line: greppable, and a new crawl version diffs monster by monster
    lines = ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    args.out.write_text(f'{{"meta": {json.dumps(meta)},\n"monsters": [\n{lines}\n]}}\n')
    print(f"{len(rows)} monsters, {len(books)} spellbooks -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
