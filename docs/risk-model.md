# Death-risk model

A first model of one number: the chance that the character dies within the next N game turns, given
one logged moment. It was built offline on existing logs. qw can now compute it at every decision
(see [In qw](#in-qw-the-lua-export)), but nothing acts on it yet. Code in `tools/risk/`, data and
models in `runs/risk/` (ignored by git). Measured 2026-11-12.

**In short:** at N = 50 turns, gradient-boosted trees reach AUROC 0.86 on the brain's held-out games and
0.91 on qw's, against 0.68 and 0.79 for HP fraction alone. The probabilities are close to calibrated below
about 35% and too high above 50%. The small neural net is level with the trees. With the alarm set to go
off on 5% of moments that are not followed by a death, the warning comes a median of 13–15 turns before
the death (6–10 turns for HP alone). That is enough to drink, retreat or not go berserk, and not enough to
plan a descent. The deep slice is thin: 51 qw games, 46 deaths, 14 of them in a rune branch.

## Data

One row per logged moment: a brain choice (`steps.jsonl`, the observation dict) or a qw decision (its
`QWS` state line, before it acts). Only qw runs with `--state-log` can be used (`dataset.QW_BASE_RUNS`
and `QW_FORK_RUNS`):

- `train-base-r1`: training seeds 100000–100299, the old build (8698adc with qw's own settings).
- `zk-train-400`: training seeds 100000–100399, the `zk` build with the tuned MiBe settings
  (`runs/qw/combo1-lua/MiBe_mace.lua`).
- `qw-base-200` and `zk-heldout-200`: the held-out seeds 500000–500199, on the old build and on `zk`
  with the tuned settings.
- The fork runs `forks-r1`, `forks-r1c`, `forks-r2` and `choke1`–`3`, on training seeds.

A fork keeps only its rows from the fork onwards. qw fork rows are thinned to one in three. The brain's 17
human recordings are left out (no seed, and most are take-overs). So are forks whose replay diverged and
446 brain evaluation games that exactly repeat another one on the same seed.

| Source | Split | Games | Deaths | Rows | Died within 50 | Died within 200 |
| --- | --- | --- | --- | --- | --- | --- |
| brain | train, games | 1,126 | 1,079 | 409,784 | 7.7% | 18.5% |
| brain | train, forks | 2,190 | 1,871 | 399,333 | 11.5% | 22.9% |
| brain | test (seeds 500000+) | 1,028 | 961 | 436,919 | 6.7% | 15.4% |
| qw | train, games (`train-base-r1`) | 300 | 286 | 744,064 | 1.2% | 2.4% |
| qw | train, games (`zk-train-400`) | 400 | 388 | 1,299,457 | 1.0% | 1.9% |
| qw | train, forks | 7,779 | 3,642 | 916,075 | 3.2% | 6.0% |
| qw | test (`qw-base-200`) | 200 | 189 | 538,756 | 1.1% | 2.2% |
| qw | test (`zk-heldout-200`) | 200 | 196 | 649,115 | 1.0% | 2.1% |

**The held-out seeds stay out of training.** `dataset.py` builds rows for every run, held-out seeds
included, and defines the rule (`HOLDOUT_SEED = 500000`). `train.splits` applies it: training and
validation take only seeds below 500000, and it asserts that no held-out seed reaches either.
`zk-heldout-200` (seeds 500000–500199) is therefore test only, like `qw-base-200`.

**Labels and censoring.** In a game that ended in a death, every row is labelled: 1 if the death came
within N turns, 0 otherwise. Every other ending is censored at its last turn: qw quitting, timeout, stall,
Lua error loop, a fork stopped at its horizon, the brain's `end_game` and `left`, and a log with no end
line. In a censored game a row at least N turns before the end is a known 0, and a later row is dropped,
never counted as a death. This drops 0.1–2% of rows in original games and 1–7% in forks.
`tests/test_risk.py` covers it.

**N = 50 is the main horizon.** The logs describe the fight in progress: HP, poison, the monsters in view.
At 50 turns that is the information that decides the outcome, and it is the scale at which berserk,
retreat and potions are chosen. At 200 turns, most deaths come from fights that haven't started yet, and
every model drops to AUROC 0.78–0.84. Both horizons are reported below.

**Features** (113, the same schema for both sources, NaN where a source lacks a field, listed in
`dataset.FEATURES`):

- HP, max HP, poison: the HP left once the poison runs out, and HP after a rage ends (×2/3, poison not
  scaled).
- Level, AC, EV, SH, Str, Dex, an approximate absolute depth and branch group.
- 14 status flags, healing potions and teleport scrolls, unknown potions and scrolls.
- Turns on this level, standing on an upstair, open neighbours, number of hostiles.
- The nearest 5 monsters, looked up in `docs/data/monsters-0.34.json`:
  - XP, HD, HP and damage per turn (attack damage × speed), summed and maximum.
  - Damage within 2 squares over current HP; monster HP over current HP.
  - Adjacent count, nearest distance, count faster than the player (also counting the player's own
    slow, haste and rage).
  - A count for each danger tag (poison, slows, paralyses, blinks, smites, …).
- Past rows of the same game: HP change since the last row, minimum HP over 20 turns, HP drop over 10
  turns, turns since full HP, and rows in the last 20 turns.
- qw only: its threat numbers, `scary_enemy`, `immediate_danger`, safe or cloudy position, flee distance,
  Fighting skill, and the enemies' sleeping, ranged and hasted flags.
- Brain only: webtiles threat levels, distance to known stairs, level explored.

Every monster name in the logs is found in the table except megabat, microbat and three shapeshifter
names.

## Method

- Splits are by dungeon seed. Test is seeds 500000+ (1,028 brain evaluation games, all 200 of
  `qw-base-200`, and for the retrained models all 200 of `zk-heldout-200`). It was predicted and scored
  once, after all choices were made.
- Validation is one training seed in six, by hash (`crc32(str(seed)) % 6 == 0`), original games only
  (241 games; 310 once `zk-train-400` was added). It was used for early stopping, the hyperparameters
  and including the forks: with the same tree settings, forks raised validation AUROC from 0.878 to 0.888.
- Training uses the other training seeds plus their forks (2.07M rows at N = 50; 3.17M with
  `zk-train-400`). One model covers both sources.
- **Baseline**: logistic regression on HP fraction, fitted per source.
- **Trees**: LightGBM, 31 leaves, at least 1,000 rows per leaf, learning rate 0.05, early stopped (406
  rounds at N = 50; 315 for the retrained `N50-zk`, 159 for `N200-zk`).
- **MLP**: 113 → 256 → 128 → 1, dropout 0.2, AdamW. Inputs are signed-log scaled and standardised, NaN
  set to 0.

```sh
uv run --group risk python tools/risk/dataset.py build          # 30 s, 14 processes
uv run --group train --group risk python tools/risk/train.py --horizon 50 [--final]
uv run --group train --group risk python tools/risk/train.py --horizon 50 --models mlp [--final]
uv run --group risk python tools/risk/report.py scores|early|bootstrap|importance --dir runs/risk/N50 --split test
uv run --group risk python tools/risk/report.py leakage --horizon 50
```

LightGBM is in a new dependency group `risk` (`lightgbm>=4.5`). LightGBM and torch each load their own
OpenMP and abort in one process on macOS, so the MLP trains in a second invocation.

## Retrained with the `zk` runs (`N50-zk`, `N200-zk`)

The same settings, retrained after `zk-train-400` and `zk-heldout-200` joined the data
(`runs/risk/N50-zk`, `runs/risk/N200-zk`; the first models are `runs/risk/N50` and `N200`). Early
stopping on validation: N = 50 reaches AUROC 0.916 (all sources; qw rows 0.900, AP 0.308) at 315
rounds, N = 200 reaches 0.864 at 159 rounds. On the held-out runs, qw rows, AUROC / average precision:

| Held-out run | Horizon | Retrained | First model | HP fraction |
| --- | --- | --- | --- | --- |
| `zk-heldout-200` | 50 | **0.889** / **0.252** | 0.887 / 0.227 | 0.800 / 0.149 |
| `zk-heldout-200` | 200 | **0.775** / **0.187** | 0.773 / 0.164 | 0.659 / 0.107 |
| `qw-base-200` | 50 | **0.916** / **0.318** | 0.910 / 0.295 | 0.786 / 0.185 |
| `qw-base-200` | 200 | **0.839** / **0.230** | 0.837 / 0.203 | 0.679 / 0.135 |
| `zk-heldout-200`, deep | 50 | **0.902** / **0.263** | 0.899 / 0.236 | 0.844 / 0.174 |
| `qw-base-200`, deep | 50 | **0.951** / **0.311** | 0.937 / 0.269 | 0.870 / 0.205 |

The first model was scored on the current rows with its own trees. The retrain gains little in AUROC
and 2–4 points of average precision. The `zk` games are harder to read than the old build's: HP alone
does better on them (0.800 against 0.786) and the trees do worse (0.889 against 0.916). The held-out
deep slice is now larger: 97 `zk-heldout-200` games reach it and 94 die there, 36 of those deaths in a
rune branch. On qw validation rows, the alarm threshold at 5% false alarms is 0.0365 (recall 65%,
median final-episode lead 19 turns).

The tables below are the first models (`N50`, `N200`), before the `zk` runs were added.

## Results, held-out seeds

N = 50. The deep slice is moments at XL 12+ or in a rune branch (Spider, Snake, Shoals, Swamp, Vaults,
Slime). No brain game gets there.

| Slice | Model | Games / deaths | Rows (died ≤ 50) | AUROC | Avg. precision | Brier | ECE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| brain | HP fraction | 1,027 / 961 | 434,392 (6.7%) | 0.681 | 0.235 | 0.0570 | 0.021 |
| brain | trees | | | **0.863** | **0.439** | **0.0481** | 0.007 |
| brain | MLP | | | 0.856 | 0.420 | 0.0492 | 0.005 |
| qw | HP fraction | 200 / 189 | 538,316 (1.1%) | 0.786 | 0.185 | 0.0098 | 0.008 |
| qw | trees | | | **0.910** | 0.295 | 0.0089 | 0.002 |
| qw | MLP | | | 0.906 | 0.292 | 0.0089 | 0.001 |
| qw deep | HP fraction | 51 / 46 | 184,171 (0.9%) | 0.870 | 0.205 | 0.0083 | 0.011 |
| qw deep | trees | | | 0.937 | 0.269 | 0.0078 | 0.003 |
| qw deep | MLP | | | **0.943** | **0.309** | **0.0075** | 0.002 |

90% intervals from resampling whole games. Trees: brain 0.854–0.871, qw 0.889–0.927, qw deep
0.911–0.954. Trees minus HP fraction: brain +0.17 to +0.19, qw +0.11 to +0.14, qw deep +0.05 to +0.10.
Trees and MLP are not separable.

N = 200, AUROC (avg. precision):

| Slice | HP fraction | Trees | MLP |
| --- | --- | --- | --- |
| brain | 0.590 (0.246) | 0.782 (0.421) | 0.780 (0.423) |
| qw | 0.679 (0.135) | 0.837 (0.203) | 0.828 (0.206) |
| qw deep | 0.741 (0.166) | 0.861 (0.196) | 0.869 (0.259) |

**Calibration (N = 50).**

- Below a predicted 35%, both models are within about 3 points of what happened. Examples: brain trees
  predicted 0.141, observed 0.143; qw trees 0.141, observed 0.132; nearly all rows are under 5% and land
  on it.
- Above 50% both overpredict: trees predicted 0.85, observed 0.74 (brain) and 0.75 (qw). The likely
  cause is the forks, which oversample fatal fights.
- The HP baseline overpredicts throughout on test (brain 0.134 → 0.102).
- At N = 200 the trees overpredict by a third in the 5–35% range for qw.

**What carries the trees** (share of gain, N = 50):

| Feature | Share |
| --- | --- |
| Monster HP in view / own HP | 0.16 |
| Webtiles threat, summed | 0.08 |
| qw `threat_avail` / its high-threat level | 0.08 |
| HP left after poison | 0.07 |
| Brain: distance to known downstairs | 0.05 |
| Turns on this level | 0.05 |
| qw Fighting skill | 0.04 |
| AC | 0.03 |
| HP after the rage ends | 0.03 |
| Absolute depth | 0.03 |

At N = 200, qw's `threat_avail` alone has 0.27.

**Ablations** (validation, AUROC of the trees for brain / qw / qw deep):

| Features | brain | qw | qw deep |
| --- | --- | --- | --- |
| All | 0.855 | 0.876 | 0.913 |
| Without the monster table | 0.847 | 0.861 | 0.898 |
| Without qw's own fields | 0.854 | 0.861 | 0.883 |
| Without the monster table, qw's fields and the brain's own (threat, stairs) | 0.809 | 0.844 | 0.873 |
| HP fraction alone | 0.651 | 0.756 | 0.820 |

Most of the gain over HP comes from the character itself: poison, depth, AC, level, statuses and time on
the level. The monster table adds about 0.01–0.015. qw's own threat number is worth 0.03 in the deep
slice, and a player of ours would have to compute something like it.

## How early it sees a death coming (N = 50, held-out)

The alarm threshold is set per source on validation so that 5% (or 1%) of moments **not** followed by a
death within 50 turns would alarm. It is then applied unchanged to the test games. The lead is the start
of the final alarm episode: alarmed moments no more than 10 turns apart that reach the death.

| Source, model | False alarms on test | Recall (rows) | Lead, median (p25–p75) | Deaths with an alarm 10–200 / 20–200 turns before |
| --- | --- | --- | --- | --- |
| brain, trees, 5% | 5.9% | 52% | 13 (7–20) turns | 754 / 538 of 961 |
| brain, HP, 5% | 5.9% | 32% | 6 (3–11) | 491 / 354 |
| qw, trees, 5% | 3.4% | 59% | 15 (9–24) | 162 / 116 of 189 |
| qw, HP, 5% | 3.1% | 45% | 9.5 (5–18) | 112 / 67 |
| brain, trees, 1% | 1.5% | 29% | 7 (3–12) | 449 / 230 |
| qw, trees, 1% | 0.8% | 37% | 9 (6–16) | 103 / 55 |

The MLP gives the same numbers within a turn. Deaths with an alarm 50 to 200 turns before them: 39% for
brain and 35% for qw at 5% false alarms. Some of those are chance alarms, since 5% of safe moments
alarm too. The warning that can be trusted is the final episode: about a dozen turns.

## In qw: the Lua export

`N50-zk` runs inside qw as a policy that takes no action: at every decision it computes the
probability from the state qw decided from, writes it to the state log and sets `ladder_risk.alarm_on`
(p ≥ 0.0365, qw's 5% false-alarm threshold on validation) for a later stance rule.

```sh
uv run --group risk python tools/risk/export_lua.py export runs/risk/N50-zk     # -> policy_risk_alarm.lua
uv run python tools/qw/run.py --seeds 100400-100407 --no-build --lib-dir /data/qw/lib-zk \
    --lua runs/qw/combo1-lua/MiBe_mace.lua --state-log --policy runs/risk/N50-zk/policy_risk_alarm.lua --name NAME
uv run --group risk python tools/risk/export_lua.py parity runs/qw/NAME --model runs/risk/N50-zk
```

- **The whole model, not a smaller one.** `export_lua.py` writes each of the 315 trees as a Lua
  function of nested ifs. Splits on features that are constant for qw (`is_qw`, the brain's own fields,
  and the paralysis, weakness and drain statuses, which qw does not log) are decided at export. That
  leaves 8,210 of 9,450 splits. The policy is about 1 MB of rc text and 3 MB of Lua heap. A decision
  costs about 13,000 Lua VM instructions (7,000 of them the trees; at most 14,200), 0.05 ms, measured on
  3,000 logged decisions with a stock Lua 5.5 on the Mac. Crawl's Lua throttle (a sleep every 50,000 instructions, the script killed after
  15) is off outside `DGAMELAUNCH` builds, which ours is not; even with it on, a decision stays under
  one unit. A smaller booster would save nothing that matters, so none was trained.
- **The features come from one definition.** `tools/qw/policy_risk_alarm.lua` mirrors `dataset.qw_row`.
  The tables it reads (monster book, branch depths, feature order, tags) are written from `dataset.py`
  at export, so they cannot drift. To reproduce the offline number exactly, it takes these steps:
  - It reads each state value as the `QWS` line logs it: floats to 4 significant digits, flags as 0/1,
    NaN and `err` as missing. The trees were trained on logged values, not on live ones.
  - It rounds every feature to float32, as the dataset stores rows.
  - It computes the derived values from those float32 values where Python does: the history and
    monster HP over own HP.
  - It sums monster values the way Python 3.12's `sum()` does (Neumaier compensation).
  - It sorts the monsters stably by distance.
  - It keeps the history (HP trend, rows in the last 20 turns, turns since full HP) itself, from the
    game's earlier decisions, like `dataset.History`.

  Every feature can be computed live; none had to be dropped. `mhp_log` uses `log(1 + mhp)` where
  Python uses `log1p`; `1 + mhp` is exact for an integer `mhp`, and the two agreed after float32
  rounding on every row checked.
- **Verified in game.** These are 8 games on fresh training seeds 100400–100407 (`runs/qw/risk-alarm-100400`),
  with the feature row also logged. Over 17,445 decisions, 17,420 probabilities are identical to what
  LightGBM computes in Python from the same `QWS` lines. The other 25 differ by at most 7e-18, the last
  bit of `exp()` in two C libraries. Every feature matched. The alarm bit agreed on all 17,445 decisions
  (1,237 alarms).
- **Behaviour unchanged.** The same 8 seeds without the policy (`runs/qw/risk-base-100400`, also with
  the state log) ended identically: same place, XL, turn, killer and score. Every `QWACT` and `QWS` line
  was identical. Total wall time was 478 s with the policy and 481 s without.
- `tests/test_risk.py` checks:
  - Lua features on live-style states (booleans, full-precision floats, odd monster names) against
    `qw_row` on the logged values.
  - The Lua trees against LightGBM on rows with NaNs.
  - Pruning.
  - That the policy only returns the rc's fixed overrides and has no line that would end the rc's
    Lua block.
  - With the local model and logs present, the real model on a real game.

  The tests need `lua` (5.4+) on `PATH`.

Log lines: `QWRISK decision turn p raw alarm`, `QWRISKF decision features…` with
`LADDER_RISK_FEATURES = true`, and `QWRISKERR` if the computation fails (qw carries on). The
probability is "risk under qw as it plays now": once a stance rule acts on the alarm, the future the
label measured changes (see Limits).

## Leakage checks

- **Structure.** No row is after its game's end or at 0 HP. Each row is the state before the action
  (`QWS`, not `QWACT`; the brain's `obs`). No message text or end-of-game field is a feature. No
  held-out seed appears in training or validation (asserted in `train.splits`).
- **No single feature gives the answer.** The best single feature on validation has AUROC 0.76 (qw: HP
  left after poison, monster HP over own HP, HP fraction).
- **The clock is left out.** The game turn alone gives 0.62 (brain, whose games are short) and 0.52
  (qw). Adding it to the trees changes validation AUROC by +0.001 (brain) and −0.005 (qw).
- **Past only.** The history features use earlier rows only. For a fork they include its replayed
  prefix, which is the same game.
- **Choices made before the test.** Every choice (horizon, hyperparameters, including forks, MLP
  settings) was made on validation. Test predictions were made once. Retraining reproduces the
  validation scores exactly.

## Limits

- **The deep slice was thin, and was the old qw.** In `qw-base-200` (build 8698adc with qw's settings
  before the berserk fixes) 51 games reach XL 12 and 46 die there, only 14 of them in a rune branch.
  `zk-heldout-200` reruns the 200 held-out seeds on the `zk` build with state logs: 97 games reach the
  deep slice, 94 die there, 36 in a rune branch (see the retrained results above).
- **The brain never goes deep.** It dies on D:3–8 and never reaches XL 12, so nothing here shows that
  brain-style features work deeper.
- **What the logs lack.** Monster HP and wounds, the map beyond distances to stairs, clouds (qw has
  only "standing in one"), what monsters are casting, rage turns left, and which potion is curing and
  which is heal wounds for the brain.
  - qw lists only the 5 nearest enemies; the brain lists 8, cut to 5 here.
  - Rows are moments of decision, not turns: dense in fights, sparse while exploring. Rates are per
    moment.
- **Policy dependence.** Risk is "risk under the bot that was playing". Brain test games are
  deterministic evaluation runs of several models; training games use 20% random choices. Gating a
  different action changes the future the label measured.
- **Overconfident at the top.** Recalibrate (isotonic, on validation) before using the probability above
  0.5 as a number rather than a ranking.
