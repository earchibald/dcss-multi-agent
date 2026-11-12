import json

import pytest

from ladder.brain import fleet, selfplay
from ladder.brain.corpus import HOLDOUT_SEED
from ladder.brain.policy import Style


def _game(game, depth=3, died=True, **kw):
    return {"type": "end", "game": game, "ended_by": "died" if died else "steps", "max_depth": depth,
            "xl": 5, "turn": 1000, "died": died, **kw}


def _shard(directory, tag, results, style=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"shard-{tag}.json").write_text(json.dumps(
        {"name": directory.name, "model": None, "epsilon": 0.0, "style": style or Style().to_dict(),
         "seconds": 10, "results": results}))


def test_selfplay_request_becomes_one_run_of_seeds():
    out = fleet.jobs({"kind": "selfplay", "games": 5, "seed": 11, "model": "models/brain.json",
                      "style": ["margin=0.1"], "name": "p1"})
    (run,) = out["runs"]
    assert run["name"] == "p1" and run["jobs"] == [11, 12, 13, 14, 15]
    assert run["play"] == {"style": ["margin=0.1"], "model": "models/brain.json", "epsilon": 0.2}


def test_selfplay_may_not_use_evaluation_seeds():
    with pytest.raises(ValueError, match="below"):
        fleet.jobs({"kind": "selfplay", "games": 10, "seed": HOLDOUT_SEED - 5})


def test_unknown_style_fails_before_anything_is_sent():
    with pytest.raises(ValueError, match="no style weight"):
        fleet.jobs({"kind": "selfplay", "style": ["nonsense=1"]})


def test_eval_names_match_ladder_brain_eval_and_skip_seeds_already_played(tmp_path):
    out = tmp_path / "brain"
    done = out / "eval-iter2"
    done.mkdir(parents=True)
    (done / "results.json").write_text(json.dumps(
        {"style": Style().to_dict(), "results": [_game(HOLDOUT_SEED), _game(HOLDOUT_SEED + 1),
                                                 {"game": HOLDOUT_SEED + 2, "ended_by": "hung"}]}))
    runs = fleet.jobs({"kind": "eval", "models": ["baseline", "models/iter2.json"], "games": 4}, out=str(out))["runs"]
    assert [r["name"] for r in runs] == ["eval-baseline", "eval-iter2"]
    assert runs[0]["jobs"] == [HOLDOUT_SEED + k for k in range(4)]
    assert runs[1]["jobs"] == [HOLDOUT_SEED + 2, HOLDOUT_SEED + 3] and runs[1]["already"] == 2
    assert runs[1]["play"]["model"] == "models/iter2.json" and runs[1]["play"]["epsilon"] == 0.0
    fresh = fleet.jobs({"kind": "eval", "models": ["models/iter2.json"], "games": 4, "fresh": True}, out=str(out))
    assert len(fresh["runs"][0]["jobs"]) == 4


def test_eval_name_includes_the_style():
    assert fleet.eval_name("models/iter2.json", ["wiki=1", "margin=0.1"]) == "eval-iter2-margin=0.1-wiki=1"


def test_merge_combines_batches_and_prefers_finished_games(tmp_path):
    run = tmp_path / "p1"
    _shard(run, "m4-1", [_game(1, depth=4), {"type": "end", "game": 2, "ended_by": "hung"}])
    _shard(run, "m1-mini-2", [_game(2, depth=6), _game(3, depth=2)])
    summary = fleet.merge(run)
    assert summary["games"] == 3 and summary["lost"] == 0 and summary["max_depth"] == 6
    assert summary["fleet"] == {"shards": 2, "games_by_host": {"m4": 2, "m1-mini": 2}}
    written = json.loads((run / "results.json").read_text())
    assert [r["game"] for r in written["results"]] == [1, 2, 3]
    # merging again (another batch arrived) keeps what results.json already had
    _shard(run, "m4-3", [_game(4, depth=5)])
    assert fleet.merge(run)["games"] == 4


def test_shard_renames_results_so_batches_dont_overwrite(tmp_path, monkeypatch):
    def fake_run(name, jobs, *, out, **kw):
        d = tmp_path / "brain" / name
        d.mkdir(parents=True, exist_ok=True)
        s = {"name": name, "results": [_game(j) for j in jobs], "style": kw["style"].to_dict(), "seconds": 1}
        (d / "results.json").write_text(json.dumps(s))
        return s

    monkeypatch.setattr(selfplay, "run", fake_run)
    spec = {"name": "p1", "jobs": [1, 2], "workers": 2, "server": "ws://localhost:8180/socket",
            "out": str(tmp_path / "brain"), "tag": "m4-1", "play": {"model": None, "epsilon": 0.2, "style": []}}
    s = fleet.shard(spec)
    assert s["shard"].endswith("shard-m4-1.json")
    assert not (tmp_path / "brain" / "p1" / "results.json").exists()
