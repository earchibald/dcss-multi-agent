"""Human MiBe reference from public logfiles and morgues (tools/humangames/mibe.py)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "humangames"))

import mibe  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "humangames"


def _bots(tmp_path):
    p = tmp_path / "seedData.ts"
    p.write_text("export const x = {\n  bots: [\n    'autorobin',\n    'qw',\n  ],\n  servers: []}\n")
    return p


def test_parse_xlog_keeps_literal_colons():
    g = mibe.parse_xlog("v=0.34.1:place=Lair::2:tmsg=a:: b:ktyp=mon\n")
    assert g == {"v": "0.34.1", "place": "Lair:2", "tmsg": "a: b", "ktyp": "mon"}


def test_morgue_stamp_makes_the_month_one_based():
    assert mibe.morgue_stamp("20261012212600S") == "20261112-212600"
    assert mibe.morgue_stamp("20260011235959D") == "20260111-235959"


def test_logfile_deepest_d_is_a_lower_bound_by_end_place():
    d = mibe.logfile_deepest_d
    assert d({"place": "D:7", "absdepth": "7"}) == 7
    assert d({"place": "Lair:3", "absdepth": "12"}) == 8
    assert d({"place": "Vaults:1"}) == 13
    assert d({"place": "Zot:5"}) == 15
    assert d({"place": "Necropolis", "absdepth": "6"}) == 6     # entered from D:6
    assert d({"place": "Necropolis", "absdepth": "12"}) == 8    # from a branch
    assert d({"place": "Abyss:2"}) == 1                         # unknown
    assert d({"place": "D:1", "ktyp": "winning"}) == 15
    assert d({"place": "D:3", "urune": "1", "ktyp": "leaving"}) == 8


def test_morgue_url_rejects_unsafe_names():
    assert mibe.morgue_url("CDI", "abc_1", "20260101000000S") == \
        "https://crawl.dcss.io/crawl/morgue/abc_1/morgue-abc_1-20260201-000000.txt"
    assert mibe.morgue_url("CDI", "../x", "20260101000000S") is None
    assert mibe.morgue_url("CAO", "abc", "20260101000000S") is None


def test_load_logfiles_drops_bots_other_versions_and_counts_any_combo_wins(tmp_path):
    bots = mibe.read_bots(_bots(tmp_path))
    assert bots == {"autorobin", "qw"}
    rows, info = mibe.load_logfiles([f"CDI={FIX / 'logfile'}"], bots)
    assert len(rows) == 6                       # 9 lines: OpSh, the qw bot and 0.33 left out
    assert info["bot_games_dropped"] == 1 and info["other_version"] == 1
    wins = {r["name"]: r["player_wins_any"] for r in rows}
    assert wins == {"alice": 1, "bob": 0, "carol": 1}   # carol's win is OpSh
    ghost = next(r for r in rows if r["name"] == "bob" and r["xl"] == 13)
    assert ghost["killer"] == "a player ghost" and ghost["zone"] == "Lair"
    assert ghost["reached_lair_lb"] and ghost["deepest_d_lb"] == 8


def test_bands_and_summary(tmp_path):
    rows, _ = mibe.load_logfiles([f"CDI={FIX / 'logfile'}"], mibe.read_bots(_bots(tmp_path)))
    b = mibe.bands(rows)
    assert len(b["a_all"]) == 6
    assert len(b["b_played"]) == 5                 # the 40-turn quit is out
    assert {r["name"] for r in b["c_never_won_played"]} == {"bob"}
    assert len(b["d_first1_per_player_played"]) == 3
    s = mibe.summarize(b["a_all"])
    assert s["games"] == 6 and s["players"] == 3 and s["wins"] == 1 and s["quits"] == 1
    assert s["deaths"] == 4
    assert s["deepest_d_mean"] == round((3 + 15 + 8 + 1 + 9 + 8) / 6, 2)
    assert s["death_zones"]["D:1-4"] == 1 and s["death_zones"]["Lair rune branches"] == 1
    assert s["runes_total"] == 4 and s["games_with_runes"] == 2
    assert s["reached_lair_lb"] == 3


def test_morgue_overview_notes_and_pacing():
    text = (FIX / "morgue.txt").read_text()
    assert mibe.morgue_branches(text)["Dungeon"] == 12
    notes = mibe.morgue_notes(text)
    assert notes[0] == (0, "D:1", "Reached XP level 1. HP: 19/19 MP: 0/0")
    assert len(notes) == 10
    row = mibe.morgue_row(text)
    assert row["deepest_d"] == 12 and row["reached_lair"]
    p = row["pace"]
    assert p["D:5"] == {"turn": 4100, "xl": 6}
    assert p["Lair"] == {"turn": 9500, "xl": 11}
    assert p["Orc"]["turn"] == 12000
    assert p["first rune"] == {"turn": 14500, "xl": 14}
    assert "third rune" not in p
    # the overview lags after a shaft: the place of death counts too, as in tools/qw/run.py
    assert mibe.morgue_row(text, "D:13")["deepest_d"] == 13
    assert mibe.morgue_row(text, "Lair:2")["deepest_d"] == 12


def test_stratified_estimate_corrects_the_rule_by_zone():
    sample = [{"zone": "Lair", "deepest_d": 11, "deepest_d_lb": 8, "reached_lair": True},
              {"zone": "Lair", "deepest_d": 9, "deepest_d_lb": 8, "reached_lair": True},
              {"zone": "D:1-4", "deepest_d": 3, "deepest_d_lb": 3, "reached_lair": False}]
    rows = [{"zone": "Lair", "deepest_d_lb": 8, "won": False, "runes": 0},
            {"zone": "D:1-4", "deepest_d_lb": 2, "won": False, "runes": 0},
            {"zone": "Abyss", "deepest_d_lb": 1, "won": False, "runes": 0},   # unsampled: whole-sample mean
            {"zone": "D:1-4", "deepest_d_lb": 15, "won": True, "runes": 3}]
    s = mibe.stratified(rows, sample)
    assert s["deepest_d_est"] == round((10 + 2 + (1 + 4 / 3) + 15) / 4, 2)
    assert s["reached_lair_est"] == round((1 + 0 + 2 / 3 + 1) / 4, 3)
    assert s["wins_per_lair_game"] == round(1 / (1 + 2 / 3 + 1), 3)


def test_bot_run_goes_through_the_same_rules(tmp_path):
    run = tmp_path / "run"
    (run / "games" / "1").mkdir(parents=True)
    (run / "games" / "1" / "logfile.txt").write_text(
        "v=0.34.0:name=x:char=MiBe:xl=12:place=Lair::4:absdepth=13:turn=9000:ktyp=mon:killer=a yak\n")
    (run / "results.json").write_text(json.dumps({"games": [
        {"tag": "1", "seed": 1, "deepest_d": 10, "reached_lair": True},
        {"tag": "2", "seed": 2, "status": "timeout", "xl": 18, "place": "Vaults:2", "turns": 50000},
    ]}))
    bot = mibe.load_bot_run(run)
    assert bot[0]["deepest_d_lb"] == 8 and bot[0]["deepest_d"] == 10 and bot[0]["killer"] == "a yak"
    assert bot[1]["ktyp"] == "unfinished" and bot[1]["deepest_d_lb"] is None
    s = mibe.summarize(bot)
    assert s["games"] == 2 and s["deepest_d_mean"] == 8
