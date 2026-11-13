"""Human Minotaur Berserkers on the public servers, measured the way tools/qw measures the bot.

    # 1. the 0.34 logfiles (one full fetch each; see docs/human-mibe-reference.md for URLs)
    uv run python -I tools/humangames/mibe.py report --logfile CDI=PATH --logfile CBR2=PATH \\
        --bots seedData.ts --bot-run runs/qw/zk-train-400 --out runs/humangames/report.json
    # 2. which morgues to fetch: every MiBe win and a random sample of the rest
    uv run python -I tools/humangames/mibe.py pick-morgues --logfile CDI=PATH ... --bots seedData.ts \\
        --sample 100 --out runs/humangames/morgues.json
    # 3. fetch them, one at a time, slowly, never twice
    uv run python -I tools/humangames/mibe.py fetch --list runs/humangames/morgues.json --dir DIR
    # 4. exact deepest floor and pacing from the morgues, beside the bot's own morgues
    uv run python -I tools/humangames/mibe.py morgues --list runs/humangames/morgues.json --dir DIR \\
        --bot-run runs/qw/zk-train-400 --logfile CDI=PATH ... --bots seedData.ts \\
        --out runs/humangames/morgue-report.json
    # 5. the side-by-side tables, as markdown
    uv run python -I tools/humangames/mibe.py tables --report runs/humangames/report.json

Logfile lines and morgues are data from other people's games: names stay in runs/ (git-ignored) and
only aggregates are printed. Nothing downloaded is executed.

"Deepest floor" for the bot (tools/qw/run.py) is the deepest Dungeon level visited: the morgue's
"Branches:" overview `Dungeon (n/15)` or qw's own place log. A logfile line only says where the game
ended, so `logfile_deepest_d` gives a lower bound from the end place (the branch's shallowest possible
entrance from the Dungeon, from 0.34's branch-data.h and the portal .des files). The same rule is
applied to the bot's own logfile lines, and the morgues give the exact value for a sample.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

# --- logfile lines ---------------------------------------------------------------------------

_SPLIT = re.compile(r"(?<!:):(?!:)")


def parse_xlog(line: str) -> dict[str, str]:
    """One logfile or milestone line: key=value fields joined by ':', a literal ':' written '::'."""
    out: dict[str, str] = {}
    for part in _SPLIT.split(line.rstrip("\r\n")):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v.replace("::", ":")
    return out


def morgue_stamp(end: str) -> str:
    """Logfile `end` (YYYYMMDDHHMMSS, month 0-based, then S or D) to the morgue name's YYYYMMDD-HHMMSS."""
    y, mo, rest = end[:4], int(end[4:6]) + 1, end[6:14]
    return f"{y}{mo:02d}{rest[:2]}-{rest[2:8]}"


# Shallowest Dungeon level a character must have reached to be in each branch (0.34.0's
# branch-data.h for the branches; dat/des/portals/*.des for the portals' entry depths).
D_FLOOR_BY_BRANCH = {
    "Temple": 4, "Orc": 9, "Elf": 9, "Lair": 8, "Swamp": 8, "Shoals": 8, "Snake": 8, "Spider": 8,
    "Slime": 8, "Vaults": 13, "Crypt": 13, "Tomb": 13, "Forest": 13, "Blade": 13, "Depths": 15,
    "Zot": 15, "Hell": 15, "Dis": 15, "Geh": 15, "Coc": 15, "Tar": 15, "Pan": 15, "Zig": 15,
    "Sewer": 3, "Ossuary": 4, "Bailey": 7, "IceCv": 8, "Volcano": 8, "Gauntlet": 8, "WizLab": 9,
    "Desolation": 9,
}
LAIR_BRANCHES = {"Lair", "Swamp", "Shoals", "Snake", "Spider", "Slime"}
RUNE_BRANCHES = {"Swamp", "Shoals", "Snake", "Spider", "Slime"}
LATE = {"Vaults", "Crypt", "Tomb", "Forest", "Blade", "Depths", "Zot", "Hell", "Dis", "Geh", "Coc",
        "Tar", "Pan", "Zig"}
NOT_DEATHS = {"winning", "quitting", "leaving", "exploremode", "wizmode", "unfinished"}


def place_parts(place: str) -> tuple[str, int]:
    if ":" in place:
        br, d = place.split(":", 1)
        return br, int(d) if d.isdigit() else 1
    return place, 1


def logfile_deepest_d(g: dict) -> int:
    """Lower bound on the deepest Dungeon level from a logfile line alone (see module doc)."""
    br, lvl = place_parts(g.get("place", "D:1"))
    absdepth = int(g.get("absdepth") or 0)
    if br == "D":
        d = lvl
    elif br == "Necropolis":
        # A necropolis has the absdepth of the floor it was entered from: D:n is n; any other
        # branch is 11 or more, and those are entered from D:8 at least.
        d = absdepth if 0 < absdepth <= 10 else 8
    else:
        d = D_FLOOR_BY_BRANCH.get(br, 1)  # Abyss, Labyrinth, Bazaar, Trove: unknown, so 1
    if g.get("ktyp") == "winning":
        d = 15
    if int(g.get("urune") or g.get("nrune") or 0) > 0:
        d = max(d, 8)
    return d


def logfile_reached_lair(g: dict) -> bool:
    """Lower bound on 'entered the Lair': ended in it or a branch below it, holds a rune, or won."""
    br, _ = place_parts(g.get("place", "D:1"))
    return (br in LAIR_BRANCHES or int(g.get("urune") or g.get("nrune") or 0) > 0
            or g.get("ktyp") == "winning")


def end_zone(g: dict) -> str:
    br, lvl = place_parts(g.get("place", "D:1"))
    if br == "D":
        return "D:1-4" if lvl <= 4 else "D:5-10" if lvl <= 10 else "D:11-15"
    if br == "Lair":
        return "Lair"
    if br in ("Orc", "Elf"):
        return "Orc, Elf"
    if br in RUNE_BRANCHES:
        return "Lair rune branches"
    if br in LATE:
        return "Vaults, Crypt, Depths, Zot and later"
    if br == "Abyss":
        return "Abyss"
    return "portals, Temple"


ZONES = ["D:1-4", "D:5-10", "D:11-15", "Lair", "Orc, Elf", "Lair rune branches",
         "Vaults, Crypt, Depths, Zot and later", "Abyss", "portals, Temple"]


def killer_label(g: dict) -> str:
    k = (g.get("killer") or "").strip()
    if not k:
        return f"({g.get('ktyp') or '?'})"
    if k.endswith("'s ghost") or k.endswith("' ghost"):
        return "a player ghost"
    if k.endswith("'s illusion") or k.endswith("' illusion"):
        return "a player illusion"
    return k


def game_row(g: dict, server: str) -> dict:
    """The measures used here, from one logfile line (human or bot)."""
    return {
        "server": server, "name": g.get("name", ""), "start": g.get("start", ""),
        "end": g.get("end", ""), "v": g.get("v", ""), "god": g.get("god", ""),
        "xl": int(g.get("xl") or 0), "turn": int(g.get("turn") or 0), "dur": int(g.get("dur") or 0),
        "place": g.get("place", ""), "ktyp": g.get("ktyp", ""), "killer": killer_label(g),
        "runes": int(g.get("urune") or g.get("nrune") or 0),
        "deepest_d_lb": logfile_deepest_d(g), "reached_lair_lb": logfile_reached_lair(g),
        "zone": end_zone(g), "won": g.get("ktyp") == "winning",
    }


def read_bots(path: Path | None) -> set[str]:
    """Bot account names: a plain list (one per line) or dcss-stats' seedData.ts `bots: [...]`."""
    if path is None:
        return set()
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"bots:\s*\[(.*?)\]", text, re.S)
    if m:
        return {(a or b).lower() for a, b in re.findall(r"'([^']+)'|\"([^\"]+)\"", m.group(1))}
    return {ln.strip().lower() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}


def load_logfiles(specs: list[str], bots: set[str], combo: str = "MiBe",
                  version: str = "0.34") -> tuple[list[dict], dict]:
    """MiBe rows from SERVER=PATH logfiles, and per-player facts from every game in them."""
    rows: list[dict] = []
    wins_by_player: Counter = Counter()
    info: dict = {"files": {}, "bot_games_dropped": 0, "other_version": 0}
    for spec in specs:
        server, path = spec.split("=", 1)
        n = 0
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                g = parse_xlog(line)
                if not g.get("name"):
                    continue
                n += 1
                if not g.get("v", "").startswith(version):
                    info["other_version"] += 1
                    continue
                name = g["name"].lower()
                if g.get("ktyp") == "winning" and name not in bots:
                    wins_by_player[name] += 1
                if g.get("char") != combo:
                    continue
                if name in bots:
                    info["bot_games_dropped"] += 1
                    continue
                rows.append(game_row(g, server))
        info["files"][server] = {"path": str(path), "games": n}
    for r in rows:
        r["player_wins_any"] = wins_by_player[r["name"].lower()]
    info["players_with_a_win_any_combo"] = len(wins_by_player)
    return rows, info


# --- bands and measures ---------------------------------------------------------------------


def played(r: dict, min_turn: int = 1000) -> bool:
    """Band (b): the game lasted min_turn turns and did not end by quitting or leaving."""
    return r["turn"] >= min_turn and r["ktyp"] not in ("quitting", "leaving")


def first_n_per_player(rows: list[dict], n: int) -> list[dict]:
    by: dict[str, list[dict]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: (r["start"], r["server"])):
        if len(by[r["name"].lower()]) < n:
            by[r["name"].lower()].append(r)
    return [r for rs in by.values() for r in rs]


TURN_BUCKETS = [(0, 1000), (1000, 3000), (3000, 10000), (10000, 30000), (30000, 100000),
                (100000, 10**9)]


def _q(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]


def summarize(rows: list[dict], deepest_key: str = "deepest_d_lb", top: int = 12) -> dict:
    """Every measure of the comparison for one band of games."""
    n = len(rows)
    if not n:
        return {"games": 0}
    deaths = [r for r in rows if r["ktyp"] not in NOT_DEATHS]
    xl = [r["xl"] for r in rows]
    xl_dead = [r["xl"] for r in deaths]
    deep = [r[deepest_key] for r in rows if r.get(deepest_key) is not None]
    turns_dead = [r["turn"] for r in deaths]
    sd = statistics.stdev(deep) if len(deep) > 1 else 0.0
    return {
        "games": n,
        "players": len({r["name"].lower() for r in rows}),
        "wins": sum(r["won"] for r in rows),
        "win_rate": round(sum(r["won"] for r in rows) / n, 4),
        "quits": sum(r["ktyp"] in ("quitting", "leaving") for r in rows),
        "deaths": len(deaths),
        "deepest_d_mean": round(statistics.mean(deep), 2) if deep else None,
        "deepest_d_se": round(sd / len(deep) ** 0.5, 2) if deep else None,
        "deepest_d_median": statistics.median(deep) if deep else None,
        "deepest_d_hist": dict(sorted(Counter(deep).items())),
        "share_deepest_ge": {k: round(sum(d >= k for d in deep) / len(deep), 3)
                             for k in (5, 8, 10, 12, 15)} if deep else {},
        "xl_mean": round(statistics.mean(xl), 2), "xl_median": statistics.median(xl),
        "xl_dead_mean": round(statistics.mean(xl_dead), 2) if xl_dead else None,
        "xl_dead_median": statistics.median(xl_dead) if xl_dead else None,
        "reached_lair_lb": sum(r["reached_lair_lb"] for r in rows),
        "reached_lair_lb_share": round(sum(r["reached_lair_lb"] for r in rows) / n, 3),
        "runes_total": sum(r["runes"] for r in rows),
        "games_with_runes": sum(r["runes"] > 0 for r in rows),
        "games_with_3_runes": sum(r["runes"] >= 3 for r in rows),
        "death_turn_quartiles": [_q(turns_dead, p) for p in (0.25, 0.5, 0.75)] if deaths else None,
        "death_turn_buckets": {f"{a}-{b if b < 10**9 else ''}": sum(a <= t < b for t in turns_dead)
                               for a, b in TURN_BUCKETS},
        "death_zones": {z: sum(r["zone"] == z for r in deaths) for z in ZONES},
        "ktyp": dict(Counter(r["ktyp"] for r in rows).most_common()),
        "top_killers": dict(Counter(r["killer"] for r in deaths).most_common(top)),
        "killers_all": dict(Counter(r["killer"] for r in deaths).most_common()),
        "god": dict(Counter(r["god"] or "(none)" for r in rows).most_common(6)),
    }


def bands(rows: list[dict], first_n: int = 3) -> dict[str, list[dict]]:
    b = [r for r in rows if played(r)]
    return {
        "a_all": rows,
        "b_played": b,
        "c_winners_played": [r for r in b if r["player_wins_any"] > 0],
        "c_never_won_played": [r for r in b if r["player_wins_any"] == 0],
        f"d_first{first_n}_per_player": first_n_per_player(rows, first_n),
        f"d_first{first_n}_per_player_played": first_n_per_player(b, first_n),
        "d_first1_per_player_played": first_n_per_player(b, 1),
    }


# --- the bot's games, through the same rules -------------------------------------------------


def load_bot_run(run: Path) -> list[dict]:
    """The bot's games: its own logfile line through game_row, plus the exact deepest D from results."""
    res = json.loads((run / "results.json").read_text())
    out = []
    for g in res["games"]:
        lf = run / "games" / g["tag"] / "logfile.txt"
        if lf.exists():
            row = game_row(parse_xlog(lf.read_text(encoding="utf-8").splitlines()[0]), "bot")
        else:  # unfinished (timeout): no logfile line; keep it as the run's summary does
            row = {"server": "bot", "name": "bot", "start": str(g["seed"]), "end": "", "v": "",
                   "god": g.get("god") or "", "xl": g.get("xl") or 0, "turn": g.get("turns") or 0,
                   "dur": 0, "place": g.get("place") or "", "ktyp": "unfinished",
                   "killer": "(unfinished)", "runes": 0, "won": False, "zone": "",
                   "deepest_d_lb": None, "reached_lair_lb": False}
            row["zone"] = end_zone({"place": row["place"] or "D:1"})
        row["name"] = "bot"
        row["seed"] = g["seed"]
        row["deepest_d"] = g.get("deepest_d")
        row["reached_lair"] = bool(g.get("reached_lair"))
        row["player_wins_any"] = 0
        out.append(row)
    return out


# --- morgues ---------------------------------------------------------------------------------

MORGUE_BASE = {"CDI": "https://crawl.dcss.io/crawl/morgue", "CBR2": "https://cbro.berotato.org/morgue"}
_SAFE = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")


def morgue_url(server: str, name: str, end: str) -> str | None:
    if server not in MORGUE_BASE or not _SAFE.match(name):
        return None
    return f"{MORGUE_BASE[server]}/{name}/morgue-{name}-{morgue_stamp(end)}.txt"


_BRANCH_RE = re.compile(r"([A-Z][A-Za-z' ]+?) \((\d+)/(\d+)\)")
_NOTE_RE = re.compile(r"^\s*(\d+) \| ([^|]*?)\s*\| (.*)$")
_XL_RE = re.compile(r"Reached XP level (\d+)")


def morgue_branches(text: str) -> dict[str, int]:
    """Deepest level per branch from the 'Branches:' overview, as tools/qw/run.py reads it."""
    m = re.search(r"\nBranches:\n(.*?)\n\n", text, re.S)
    out: dict[str, int] = {}
    if m:
        for name, deepest, _ in _BRANCH_RE.findall(m.group(1)):
            if int(deepest) > 0:
                out[name.strip()] = int(deepest)
    return out


def morgue_notes(text: str) -> list[tuple[int, str, str]]:
    """The Notes table: (turn, place, note)."""
    i = text.find("\nNotes\n")
    if i < 0:
        return []
    out = []
    for line in text[i:].splitlines()[3:]:
        m = _NOTE_RE.match(line)
        if m:
            out.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip()))
        elif out and not line.strip():
            break
    return out


PACE_EVENTS = ["D:5", "D:8", "Lair", "Orc", "first rune", "Vaults", "third rune", "Depths", "Zot"]


def pacing(notes: list[tuple[int, str, str]]) -> dict[str, dict]:
    """Turn and XL at the first note on D:5, D:8, in each branch, and at the first and third rune."""
    xl, out, runes = 1, {}, 0
    for turn, place, note in notes:
        m = _XL_RE.search(note)
        if m:
            xl = max(xl, int(m.group(1)))
        br, lvl = place_parts(place)
        keys = []
        if br == "D" and lvl >= 5:
            keys.append("D:5")
        if br == "D" and lvl >= 8:
            keys.append("D:8")
        if br in ("Lair", "Orc", "Vaults", "Depths", "Zot"):
            keys.append(br)
        if re.search(r"\bGot an? .*rune of Zot", note):
            runes += 1
            if runes == 1:
                keys.append("first rune")
            if runes == 3:
                keys.append("third rune")
        for k in keys:
            if k not in out:
                out[k] = {"turn": turn, "xl": xl}
    return out


def morgue_row(text: str, end_place: str = "") -> dict:
    """Deepest D as tools/qw/run.py takes it: the overview, or any Dungeon level seen in the notes
    or died on, whichever is deeper (the overview lags after a fall down a shaft)."""
    br = morgue_branches(text)
    notes = morgue_notes(text)
    ds = [lvl for b, lvl in (place_parts(p) for _, p, _ in notes) if b == "D"]
    if br.get("Dungeon") is not None:
        ds.append(br["Dungeon"])
    b, lvl = place_parts(end_place) if end_place else ("", 0)
    if b == "D":
        ds.append(lvl)
    lair = "Lair" in br or any(place_parts(p)[0] == "Lair" for _, p, _ in notes)
    return {"deepest_d": max(ds) if ds else None, "reached_lair": lair, "pace": pacing(notes)}


def _mean_se(vals: list[float]) -> list | None:
    if not vals:
        return None
    se = statistics.stdev(vals) / len(vals) ** 0.5 if len(vals) > 1 else 0.0
    return [round(statistics.mean(vals), 2), round(se, 2), len(vals)]


def pace_table(rows: list[dict]) -> dict[str, dict]:
    out = {}
    for ev in PACE_EVENTS:
        hits = [r["pace"][ev] for r in rows if ev in r.get("pace", {})]
        if hits:
            out[ev] = {"games": len(hits),
                       "turn_median": statistics.median(h["turn"] for h in hits),
                       "turn_q25_q75": [_q([h["turn"] for h in hits], 0.25),
                                        _q([h["turn"] for h in hits], 0.75)],
                       "xl_median": statistics.median(h["xl"] for h in hits),
                       "xl_q25_q75": [_q([h["xl"] for h in hits], 0.25),
                                      _q([h["xl"] for h in hits], 0.75)]}
    return out


def stratified(rows: list[dict], sample: list[dict]) -> dict:
    """Exact deepest D and 'entered the Lair' for a band of logfile rows, estimated from a morgue sample.

    Each non-winning row gets its logfile-rule value plus the sample's mean (exact - rule) for games
    that ended in the same zone, and the sample's Lair share for that zone (the whole sample's where a
    zone has no sampled game). A win is 15 and entered the Lair.
    """
    diff: dict[str, list[int]] = defaultdict(list)
    lair: dict[str, list[bool]] = defaultdict(list)
    for s in sample:
        diff[s["zone"]].append(s["deepest_d"] - s["deepest_d_lb"])
        lair[s["zone"]].append(s["reached_lair"])
    all_d = [x for v in diff.values() for x in v]
    all_l = [x for v in lair.values() for x in v]
    deep, lr = [], []
    for r in rows:
        if r["won"]:
            deep.append(15.0)
            lr.append(1.0)
        else:
            deep.append(r["deepest_d_lb"] + statistics.mean(diff.get(r["zone"]) or all_d))
            lr.append(statistics.mean(lair.get(r["zone"]) or all_l))
    n = len(rows)
    lair_n = sum(lr)
    return {"games": n, "deepest_d_est": round(statistics.mean(deep), 2) if n else None,
            "reached_lair_est": round(lair_n / n, 3) if n else None,
            "runes_per_lair_game": round(sum(r["runes"] > 0 for r in rows) / lair_n, 3) if lair_n else None,
            "three_runes_per_lair_game": round(sum(r["runes"] >= 3 for r in rows) / lair_n, 3) if lair_n else None,
            "wins_per_lair_game": round(sum(r["won"] for r in rows) / lair_n, 3) if lair_n else None}


def after_lair(rows: list[dict]) -> dict:
    """How games that entered the Lair ended: rows need exact 'reached_lair'."""
    rl = [r for r in rows if r["reached_lair"]]
    return {"entered_lair": len(rl),
            "died_in_lair": sum(r["zone"] == "Lair" for r in rl),
            "died_in_rune_branches": sum(r["zone"] == "Lair rune branches" for r in rl),
            "with_a_rune": sum(r["runes"] > 0 for r in rl),
            "with_3_runes": sum(r["runes"] >= 3 for r in rl),
            "won": sum(r["won"] for r in rl)}


def fetch(urls: list[dict], dest: Path, delay: float, agent: str) -> dict:
    """Fetch each URL once to dest/<file>, one at a time, `delay` seconds apart; skip what exists."""
    dest.mkdir(parents=True, exist_ok=True)
    got = skipped = failed = 0
    nbytes = 0
    for u in urls:
        path = dest / u["file"]
        if path.exists() or (dest / (u["file"] + ".missing")).exists():
            skipped += 1
            continue
        req = urllib.request.Request(u["url"], headers={"User-Agent": agent})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read(2_000_000)
            path.write_bytes(data)
            nbytes += len(data)
            got += 1
        except Exception as e:  # 404s and timeouts: remember, do not retry
            (dest / (u["file"] + ".missing")).write_text(repr(e)[:200])
            failed += 1
        time.sleep(delay)
    return {"fetched": got, "skipped": skipped, "failed": failed, "bytes": nbytes}


# --- CLI -------------------------------------------------------------------------------------


def _write(path: str | None, obj) -> None:
    text = json.dumps(obj, indent=1)
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text + "\n")
    else:
        print(text)


def cmd_report(a) -> None:
    rows, info = load_logfiles(a.logfile, read_bots(a.bots))
    out: dict = {"info": info, "human": {k: summarize(v) for k, v in bands(rows).items()}}
    per_player = Counter(r["name"].lower() for r in rows)
    top10 = sum(c for _, c in per_player.most_common(10))
    info["games_per_player"] = {"players": len(per_player), "median": statistics.median(per_player.values()),
                                "max": max(per_player.values()), "top10_share": round(top10 / len(rows), 3)}
    info["versions"] = dict(Counter(r["v"] for r in rows).most_common())
    if a.bot_run:
        bot = load_bot_run(Path(a.bot_run))
        out["bot"] = {"a_all": summarize(bot), "b_played": summarize([r for r in bot if played(r)]),
                      "a_all_exact": summarize(bot, "deepest_d")}
        out["bot"]["a_all_exact"]["reached_lair_exact"] = sum(r["reached_lair"] for r in bot)
        out["bot_rule_check"] = {
            "games": len(bot),
            "exact_mean": round(statistics.mean(r["deepest_d"] for r in bot if r["deepest_d"]), 2),
            "rule_mean": round(statistics.mean(r["deepest_d_lb"] for r in bot
                                               if r["deepest_d_lb"] is not None), 2),
            "rule_equal_exact": sum(r["deepest_d_lb"] == r["deepest_d"] for r in bot),
            "exact_minus_rule": _mean_se([r["deepest_d"] - r["deepest_d_lb"] for r in bot
                                          if r["deepest_d_lb"] is not None and r["deepest_d"]]),
            "exact_minus_rule_by_zone": {
                z: _mean_se([r["deepest_d"] - r["deepest_d_lb"] for r in bot
                             if r["zone"] == z and r["deepest_d_lb"] is not None and r["deepest_d"]])
                for z in ZONES if any(r["zone"] == z for r in bot)},
            "reached_lair_exact": sum(r["reached_lair"] for r in bot),
            "reached_lair_rule": sum(r["reached_lair_lb"] for r in bot),
        }
    _write(a.out, out)


def cmd_pick(a) -> None:
    rows, _ = load_logfiles(a.logfile, read_bots(a.bots))
    rows = [r for r in rows if r["server"] in MORGUE_BASE]
    wins = [r for r in rows if r["won"]]
    rng = random.Random(a.seed)
    sample = []
    for server in sorted({r["server"] for r in rows}):
        pool = [r for r in rows if r["server"] == server and played(r) and not r["won"]]
        sample += rng.sample(pool, min(a.sample, len(pool)))
    picks = []
    for kind, rs in (("win", wins), ("sample", sample)):
        for r in rs:
            url = morgue_url(r["server"], r["name"], r["end"])
            if url:
                picks.append({"kind": kind, "server": r["server"], "url": url,
                              "file": f"{r['server']}-{url.rsplit('/', 1)[1]}", "row": r})
    # alternate servers so each sees one request per two delays
    by = defaultdict(list)
    for p in picks:
        by[p["server"]].append(p)
    order = [p for grp in zip(*by.values()) for p in grp]
    order += [p for ps in by.values() for p in ps[min(len(v) for v in by.values()):]]
    _write(a.out, order)
    print(f"{len(order)} morgues: {len(wins)} wins, {len(sample)} sampled", file=sys.stderr)


def cmd_fetch(a) -> None:
    picks = json.loads(Path(a.list).read_text())
    print(json.dumps(fetch(picks, Path(a.dir), a.delay, a.agent)))


def cmd_morgues(a) -> None:
    picks = json.loads(Path(a.list).read_text())
    rows = []
    for p in picks:
        path = Path(a.dir) / p["file"]
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "\nNotes\n" not in text:
            continue
        m = morgue_row(text, p["row"]["place"])
        rows.append({**p["row"], **m, "kind": p["kind"]})
    out: dict = {"morgues_read": len(rows)}
    for kind in ("win", "sample"):
        rs = [r for r in rows if r["kind"] == kind]
        exact = [r for r in rs if r["deepest_d"] is not None]
        out[kind] = {
            "games": len(rs),
            "with_deepest_d": len(exact),
            "deepest_d_exact": _mean_se([r["deepest_d"] for r in exact]),
            "deepest_d_exact_mean": round(statistics.mean(r["deepest_d"] for r in exact), 2) if exact else None,
            "deepest_d_rule_mean": round(statistics.mean(r["deepest_d_lb"] for r in exact), 2) if exact else None,
            "rule_equal_exact": sum(r["deepest_d"] == r["deepest_d_lb"] for r in exact),
            "exact_minus_rule": _mean_se([r["deepest_d"] - r["deepest_d_lb"] for r in exact]),
            "exact_minus_rule_by_zone": {
                z: _mean_se([r["deepest_d"] - r["deepest_d_lb"] for r in exact if r["zone"] == z])
                for z in ZONES if any(r["zone"] == z for r in exact)},
            "reached_lair_by_deepest_rule": {
                f"rule {lo}-{hi}": [sum(r["reached_lair"] for r in exact if lo <= r["deepest_d_lb"] <= hi),
                                    sum(lo <= r["deepest_d_lb"] <= hi for r in exact)]
                for lo, hi in ((1, 7), (8, 11), (12, 15))},
            "reached_lair_exact": sum(r["reached_lair"] for r in exact),
            "reached_lair_rule": sum(r["reached_lair_lb"] for r in exact),
            "pace": pace_table(rs),
            "pace_reached_lair": pace_table([r for r in rs if "Lair" in r["pace"]]),
            "after_lair": after_lair(rs),
        }
    if a.logfile:
        sample = [r for r in rows if r["kind"] == "sample" and r["deepest_d"] is not None]
        hum, _ = load_logfiles(a.logfile, read_bots(a.bots))
        out["bands_estimated"] = {k: stratified(v, sample) for k, v in bands(hum).items()}
    if a.bot_run:
        bot_rows = load_bot_run(Path(a.bot_run))
        out["bot_after_lair"] = after_lair(bot_rows)
        out["bot_b_after_lair"] = after_lair([r for r in bot_rows if played(r)])
        out["bot_exact"] = {
            "a_all": _mean_se([r["deepest_d"] for r in bot_rows if r["deepest_d"]]),
            "b_played": _mean_se([r["deepest_d"] for r in bot_rows if r["deepest_d"] and played(r)]),
            "reached_lair_a": sum(r["reached_lair"] for r in bot_rows),
            "reached_lair_b": sum(r["reached_lair"] for r in bot_rows if played(r))}
        bot, same = [], 0
        for g in json.loads((Path(a.bot_run) / "results.json").read_text())["games"]:
            mp = Path(a.bot_run) / "games" / g["tag"] / "morgue.txt"
            if mp.exists():
                bot.append(morgue_row(mp.read_text(encoding="utf-8", errors="replace"), g.get("place") or ""))
                same += bot[-1]["deepest_d"] == g.get("deepest_d")
        out["bot"] = {"games": len(bot), "morgue_deepest_d_equals_results": same,
                      "pace": pace_table(bot),
                      "pace_reached_lair": pace_table([r for r in bot if "Lair" in r["pace"]]),
                      "pace_3_runes": pace_table([r for r in bot if "third rune" in r["pace"]])}
    _write(a.out, out)


TABLE_COLUMNS = [("bot", "a_all", "Bot, all"), ("bot", "b_played", "Bot, (b)"),
                 ("human", "a_all", "(a) all"), ("human", "b_played", "(b) played"),
                 ("human", "c_winners_played", "(c) winners"),
                 ("human", "c_never_won_played", "(c) never won"),
                 ("human", "d_first3_per_player_played", "(d) first 3"),
                 ("human", "d_first1_per_player_played", "(d) first 1")]


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def tables(report: dict) -> str:
    """The side-by-side tables of docs/human-mibe-reference.md, as markdown."""
    cols = [(report[who][band], label) for who, band, label in TABLE_COLUMNS if band in report.get(who, {})]
    out = ["| | " + " | ".join(lab for _, lab in cols) + " |",
           "|---|" + "---|" * len(cols)]

    def row(name, f):
        out.append(f"| {name} | " + " | ".join(f(s) for s, _ in cols) + " |")

    row("Games", lambda s: f"{s['games']:,}")
    row("Players", lambda s: f"{s['players']:,}")
    row("Wins", lambda s: f"{s['wins']} ({_pct(s['win_rate'])})")
    row("Quit or left", lambda s: str(s["quits"]))
    row("Deepest D, logfile rule, mean (SE)", lambda s: f"{s['deepest_d_mean']:.2f} ({s['deepest_d_se']:.2f})")
    for k in ("5", "8", "10", "15"):
        row(f"Deepest D ≥ {k} (rule)", lambda s, k=k: _pct(s["share_deepest_ge"][k]))
    row("XL at end, mean / median", lambda s: f"{s['xl_mean']:.2f} / {s['xl_median']:g}")
    row("XL at death, mean / median", lambda s: f"{s['xl_dead_mean']:.2f} / {s['xl_dead_median']:g}")
    row("Ended in the Lair or below, or with a rune (rule)", lambda s: _pct(s["reached_lair_lb_share"]))
    row("Runes, total (per game)", lambda s: f"{s['runes_total']} ({s['runes_total'] / s['games']:.3f})")
    row("Games with a rune / with 3+", lambda s: f"{s['games_with_runes']} / {s['games_with_3_runes']}")
    row("Death turn, quartiles", lambda s: " / ".join(f"{t:,}" for t in s["death_turn_quartiles"]))
    out.append("")
    out.append("Where deaths happen, share of deaths (wins, quits and unfinished games left out):")
    out.append("")
    out.append("| End place | " + " | ".join(lab for _, lab in cols) + " |")
    out.append("|---|" + "---|" * len(cols))
    for z in ZONES:
        row(z, lambda s, z=z: _pct(s["death_zones"][z] / s["deaths"]))
    out.append("")
    out.append("Death turn, share of deaths:")
    out.append("")
    out.append("| Turns | " + " | ".join(lab for _, lab in cols) + " |")
    out.append("|---|" + "---|" * len(cols))
    for k in cols[0][0]["death_turn_buckets"]:
        row(k.replace("-", "–") if not k.endswith("-") else k[:-1] + "+",
            lambda s, k=k: _pct(s["death_turn_buckets"][k] / s["deaths"]))
    # killers: the union of the bot's and the human (b) band's top lists
    bot, hum = report["bot"]["a_all"], report["human"]["b_played"]
    names = list(dict.fromkeys(list(hum["top_killers"]) + list(bot["top_killers"])))
    out.append("")
    out.append("Killers, share of deaths (top 12 of the bot and of human band (b)):")
    out.append("")
    out.append("| Killer | Bot, all | (a) all | (b) played | (c) winners |")
    out.append("|---|---|---|---|---|")
    full = {k: report["human"][k].get("killers_all", {}) for k in ("a_all", "b_played", "c_winners_played")}
    bot_all = bot.get("killers_all", bot["top_killers"])
    for k in names:
        vals = [bot_all.get(k, 0) / bot["deaths"]] + [
            full[b].get(k, 0) / report["human"][b]["deaths"] for b in full]
        out.append(f"| {k} | " + " | ".join(_pct(v) for v in vals) + " |")
    return "\n".join(out) + "\n"


def cmd_tables(a) -> None:
    print(tables(json.loads(Path(a.report).read_text())))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("report", "pick-morgues"):
        p = sub.add_parser(name)
        p.add_argument("--logfile", action="append", required=True, help="SERVER=PATH (CDI, CBR2, ...)")
        p.add_argument("--bots", type=Path, help="bot account names (list, or dcss-stats seedData.ts)")
        p.add_argument("--out")
        if name == "report":
            p.add_argument("--bot-run", help="a tools/qw run directory, e.g. runs/qw/zk-train-400")
        else:
            p.add_argument("--sample", type=int, default=100, help="non-winning games per server")
            p.add_argument("--seed", type=int, default=1)
    p = sub.add_parser("fetch")
    p.add_argument("--list", required=True)
    p.add_argument("--dir", required=True)
    p.add_argument("--delay", type=float, default=1.5)
    p.add_argument("--agent", default="xlog-reader/0.1")
    p = sub.add_parser("morgues")
    p.add_argument("--list", required=True)
    p.add_argument("--dir", required=True)
    p.add_argument("--bot-run")
    p.add_argument("--logfile", action="append", help="SERVER=PATH: also estimate every band from the sample")
    p.add_argument("--bots", type=Path)
    p.add_argument("--out")
    p = sub.add_parser("tables")
    p.add_argument("--report", required=True, help="the report command's JSON")
    a = ap.parse_args(argv)
    {"report": cmd_report, "pick-morgues": cmd_pick, "fetch": cmd_fetch, "morgues": cmd_morgues,
     "tables": cmd_tables}[a.cmd](a)


if __name__ == "__main__":
    main()
