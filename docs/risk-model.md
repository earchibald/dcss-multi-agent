# Death-risk model

A first model of one number: the chance that the character dies within the next N game turns, given
one logged moment. It was built offline on existing logs. qw can now compute it at every decision
(see [In qw](#in-qw-the-lua-export)), and an opt-in stance reads a scroll of teleportation on it
([A stance](#a-stance-teleport-on-the-alarm); not yet measured in whole games). Code in `tools/risk/`, data and
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

## A stance: teleport on the alarm

Fork replays of deaths in `zk-train-400` forced qw's `teleport` at the first decision of the final
alarm episode (p ≥ 0.0365), where a scroll could be read. Against reroll controls, survival 200 turns
past the original death rose by +0.23 ± 0.04 (94 moments; +0.24 ± 0.07 on validation seeds) and at
1,000 turns by +0.16 ± 0.05. On 31 false alarms the teleport cost nothing in survival. Live, a rule
cannot know which episode is the last one, and scrolls are few, so the rule was chosen by replaying
the logged games first.

**Episodes and scrolls.** All 400 games of `zk-train-400` (training seeds 100000–100399), with the
`N50-zk` probability from their `QWS` lines. "fit" are the 331 games on seeds the trees were trained
on (probabilities in sample); "val" are the 69 on validation seeds (out of sample). An episode starts
at an alarmed decision with no alarmed decision in the 20 turns before it.

| Threshold | Episodes a game, fit / val | Per 1,000 turns, val | Scroll readable at the start, val | Death within 50 turns, fit / val | Deaths with an episode start, scroll readable, 10–200 turns before, fit / val |
| --- | --- | --- | --- | --- | --- |
| 0.0365 | 15.3 / 18.3 | 1.40 | 59% | 5.2% / 5.1% | 65% / 59% |
| 0.06 | 9.8 / 11.4 | 0.87 | 59% | 8.6% / 8.7% | 59% / 52% |
| 0.10 | 6.3 / 7.3 | 0.56 | 55% | 14.0% / 13.6% | 55% / 41% |
| 0.15 | 4.4 / 5.3 | 0.41 | 52% | 20.6% / 18.4% | 50% / 34% |
| 0.25 | 2.7 / 3.3 | 0.25 | 45% | 33.3% / 28.8% | 41% / 18% |

Without the 20-turn merge the counts nearly double (29 episodes a game at 0.0365, fit); a 50-turn
merge takes off about 9% more. A game finds 4.6 scrolls of teleportation (0.35 per 1,000 turns; 74% of
games ever hold one), qw reads 1.8 itself, and a game ends holding 2.9 on average. Of the 388 deaths,
67% have a decision in their final episode where a scroll could be read, and in 36% qw read one
itself during it.

**Rules, replayed.** The logged game is kept and the rule's reads are taken off the scroll count; a
read of qw's own within 30 decisions after a firing counts as replaced by it, and one that finds no
scroll left counts as starved. The rule fires at any decision where p is over its threshold, a
scroll can be read (`can_teleport`, not already teleporting) and 20 turns have passed since it last
fired. fit / val:

| Rule | Firings a game | Death within 50 turns of a firing | Extra scrolls read a game | qw reads starved a game | Deaths with a firing 10–200 turns before | Deaths with a firing in the final episode |
| --- | --- | --- | --- | --- | --- | --- |
| p ≥ 0.0365 | 3.68 / 4.16 | 5% / 7% | 3.28 / 3.51 | 1.23 / 1.20 | 19% / 28% | 12% / 9% |
| p ≥ 0.06 | 3.44 / 3.65 | 10% / 11% | 2.79 / 2.83 | 0.89 / 0.94 | 31% / 29% | 23% / 26% |
| **`t10`**: p ≥ 0.10 | 2.90 / 2.84 | 19% / 17% | 2.06 / 2.00 | 0.49 / 0.70 | 39% / 32% | 40% / 35% |
| **`t15`**: p ≥ 0.15 | 2.29 / 2.33 | 29% / 21% | 1.46 / 1.54 | 0.31 / 0.46 | 42% / 32% | 48% / 35% |
| **`tier`**: 0.25 / 0.15 / 0.10 with 1 / 2 / 3+ scrolls | 2.65 / 2.62 | 27% / 20% | 1.74 / 1.75 | 0.26 / 0.48 | 43% / 29% | 52% / 44% |
| p ≥ 0.25 | 1.62 / 1.58 | 43% / 28% | 0.94 / 0.99 | 0.15 / 0.23 | 40% / 19% | 53% / 32% |
| p ≥ 0.15, keep one scroll | 1.83 / 1.88 | 30% / 22% | 1.08 / 1.16 | 0.14 / 0.22 | 35% / 28% | 39% / 29% |

- At the alarm's own threshold the rule reads three or four scrolls a game on false alarms, leaves qw
  without one for two of every three of its own reads, and has a scroll in only 9–12% of final
  episodes. Higher thresholds keep the scrolls for the end.
- The lead shrinks as the threshold rises. The first firing in the final episode comes a median of
  23 / 18 turns before the death for `t10` (fit / val), 20 / 11 for `t15`, 19.5 / 8 for `tier` and
  15 / 7.5 for p ≥ 0.25; the final episode itself starts 21 / 14 turns before. A scroll takes 3–5 turns to act, so a late
  firing is worth little; the forks say nothing about firings later in the episode.
- Cheap extra conditions did nothing: requiring hostiles in view, or danger in view and not standing
  on an upstair, changed coverage by 1–3 points (at p ≥ 0.10 enemies are nearly always in view).
  Firing only at an episode's first decision, or once per episode, was no better than any decision
  with a cooldown. Cooldowns of 20, 50 and 100 turns differ little. Keeping one scroll in reserve
  halves the starved reads and loses 6–9 points of final episodes.
- The candidates were chosen on the fit games: `t15` (the middle of the threshold range), `tier`
  (most final episodes covered for its spend) and `t10` (the most lead). On the validation games
  (68 deaths, a small sample) `tier` covers the most final episodes (44% against 35% and 35%) and
  `t10` keeps the most lead.
- The replay is first order. After a real teleport the game changes, and the starved count assumes
  qw's later reads would have happened anyway.

**In qw.** The stance is a separate section at the end of `tools/qw/policy_risk_alarm.lua`, off
unless `LADDER_RISK_STANCE` is set. With it off, the policy's output is byte-identical to the
alarm-only policy exported before it (checked offline on four logged games: every `QWRISK` line and
every returned spec). With `LADDER_RISK_STANCE = "teleport"`, `ladder_choose` returns
`{ force = "teleport", n = 1 }`, the spec fork runs use, so ladder.lua runs its `teleport` primitive,
qw's own `can_teleport() and teleport()`: if qw cannot read, nothing is read and qw's cascade decides.
The settings are `LADDER_RISK_STANCE_THRESHOLD` (a number, or `{ 1 scroll, 2, 3+ }`; default the alarm
threshold), `LADDER_RISK_STANCE_COOLDOWN` (game turns, default 20, at least 1, counted from every
firing, so a read that fails cannot repeat at every decision) and `LADDER_RISK_STANCE_RESERVE`
(default 0). A fixed override for the decision comes first. Each firing logs
`QWSTANCE decision turn p action acted` once the primitive has run.

```sh
uv run --group risk python tools/risk/export_lua.py export runs/risk/N50-zk --stance all
    # -> policy_risk_alarm.lua and policy_risk_stance_<name>.lua for each of export_lua.STANCES
caffeinate -i uv run python tools/qw/run.py --seeds 100500-100699 --no-build --lib-dir /data/qw/lib-zk \
    --lua runs/qw/combo1-lua/MiBe_mace.lua --time-limit 3600 --workers 9 --state-log \
    --policy runs/risk/N50-zk/policy_risk_stance_t15.lua --name stance-live-t15
uv run python tools/qw/compare.py pace-base stance-live-t15
```

**Smoke test** (6 games, training seeds 100430–100435, two per variant: `runs/qw/stance-smoke-tier`,
`-t15`, `-t10`). 39 firings, all 39 acted: each logged `force:teleport` as the plan, the scroll
count fell by one at the next decision and `teleporting` was set. No firing without a scroll, the
shortest gap between firings was 27 turns, and there were no `QWSTANCEERR`, `QWRISKERR`, nudges,
stalls or qw errors. In game, the re-exported policy's probabilities still match LightGBM's
(10,072 of 10,080 identical on the `tier` run, the rest within 4e-18). Several firings came at full
HP early on (D:2 at 26/26 and at 31/31): the false alarms the replay counted. One deep game
(100431, Vaults:1, XL 18) fired 15 times and qw never read a teleport scroll itself. These games
only check the mechanics. They are not a measure of the rule.

`tests/test_risk.py` checks with qw stubbed: no action with the stance off, the read through qw's
primitive, the cooldown, no firing without a readable scroll or while teleporting, a fixed override
first, a read qw refuses (logged with acted 0, no repeat in the same turn), the thresholds by scrolls
held and the reserve, and that each exported variant switches the stance on.

### More stance options

`t10`'s 194 deaths on seeds 100500–100699 had three patterns the rule did not touch: 131 with the
alarm on and no scroll left (or none ever), 48 that teleported and died anyway (13 of them held a
scroll that the 20-turn cooldown kept unread after landing in danger again) and 11 that held a scroll
and did not read it (8 were berserk, and berserk stops reading). Three options in the template's
stance section answer them. Each is off unless its global is set, so `t15`, `tier`, `t10`, `t07` and
`t05` are unchanged: their headers are the same, and replaying logged games through the old and the
re-exported policies gives identical `QWRISK`, `QWSTANCE` lines and specs.

- **After landing** (`LADDER_RISK_STANCE_AFTER_LANDING = g`). While a teleport is pending the rule
  never reads, as before. Once the state's `teleporting` has gone from on to off after the last
  firing, the cooldown stops applying: the rule may read again `g` turns after the landing (`0`:
  at once) if p is still over its threshold. Logged as `teleport_landed`.
- **Read before berserk** (`LADDER_RISK_STANCE_BERSERK = true` or a probability). ladder.lua runs a
  forced primitive before qw's cascade, so berserk never pre-empts a firing; qw goes berserk at
  decisions where the rule does not fire. In `t10`, of 1,720 berserks with a readable scroll, 20
  came at p ≥ 0.10 (during the cooldown) and 278 at p ≥ 0.05; in six of the eight deaths the
  berserk came at p 0.04–0.09, under the rule's threshold. So the option does two things: a firing also vetoes qw's `berserk`
  plan (`{ force = "teleport", veto = { "berserk" } }`; the veto applies only if the read fails),
  and at a decision where the rule does not fire but p ≥ the option's threshold, a scroll can be
  read and qw wants to berserk (`can_berserk` and qw's own `want_to_berserk()`, asked before the
  cascade), it reads instead (`teleport_not_berserk`, once a turn, cooldown ignored). Already
  berserk with a scroll held, nothing can be read: `berserk_blocked` is logged once a berserk.
- **Fallback with no scroll** (`LADDER_RISK_STANCE_FALLBACK = { names }`, tried in order, at p ≥ the
  stance threshold with one scroll and no teleport pending). `"stairs"`: on an upstair qw can flee
  by, ladder.lua's `stairs_up` primitive (`stairs_up`); otherwise, with one at most
  `LADDER_RISK_STANCE_STAIRS_DIST` (10) squares away by qw's flee distance, one step of ladder.lua's
  `flee` primitive (`flee_to_stairs`); at most `LADDER_RISK_STANCE_STAIRS_MAX` (5) climbs a level,
  and after `LADDER_RISK_STANCE_STAIRS_STUCK` (3) steps running that bring the stair no nearer, no
  more steps until it is nearer or 10 turns have passed (the first smoke test had a 15-step walk
  that stayed 3 squares away while HP fell from 82 to 27).
  `"unknown_scroll"`: qw's own `read_unided_scroll()` (its identify-by-use plan, which qw otherwise
  runs only when safe), when an unidentified scroll is held and one can be read (`unknown_scroll`).
  A fallback fires at most three times a game turn, and not again in a turn where a firing did not
  act. Both use only what qw and ladder.lua already have; no new movement.

| Variant | Settings |
| --- | --- |
| `t10a` | `t10`, after landing with no grace |
| `t10ab` | `t10a`, read before berserk at p ≥ 0.05 |
| `t10abs` | `t10ab`, fallback `stairs` |
| `t10abu` | `t10ab`, fallback `unknown_scroll` |

`want_to_berserk()` runs before the cascade only at decisions where everything else for the option
holds; it is qw's own function, but its threat assessment can compute hit chances, which can draw from
the game's random numbers, so such a decision can play out differently even when the option then
does nothing.

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
