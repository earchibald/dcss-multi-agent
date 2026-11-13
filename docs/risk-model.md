# Death-risk model

A first model of one number: the chance that the character dies within the next N game turns, given
one logged moment. It is offline work on existing logs and is not wired into play. Code in
`tools/risk/`, data and models in `runs/risk/` (ignored by git). Measured 2026-11-12.

**In short:** at N = 50 turns, gradient-boosted trees reach AUROC 0.86 on the brain's held-out games and
0.91 on qw's, against 0.68 and 0.79 for HP fraction alone. The probabilities are close to calibrated below
about 35% and too high above 50%. The small neural net is level with the trees. With the alarm set to go
off on 5% of moments that are not followed by a death, the warning comes a median of 13–15 turns before
the death (6–10 turns for HP alone). That is enough to drink, retreat or not go berserk, and not enough to
plan a descent. The deep slice is thin: 51 qw games, 46 deaths, 14 of them in a rune branch.

## Data

One row per logged moment: a brain choice (`steps.jsonl`, the observation dict) or a qw decision (its
`QWS` state line, before it acts). Only qw runs with `--state-log` can be used: `train-base-r1`,
`qw-base-200` and the fork runs `forks-r1`, `forks-r1c`, `forks-r2` and `choke1`–`3`. A fork keeps only its
rows from the fork onwards. qw fork rows are thinned to one in three. The brain's 17 human recordings are
left out (no seed, and most are take-overs). So are forks whose replay diverged and 446 brain evaluation
games that exactly repeat another one on the same seed.

| Source | Split | Games | Deaths | Rows | Died within 50 | Died within 200 |
| --- | --- | --- | --- | --- | --- | --- |
| brain | train, games | 1,126 | 1,079 | 409,784 | 7.7% | 18.5% |
| brain | train, forks | 2,190 | 1,871 | 399,333 | 11.5% | 22.9% |
| brain | test (seeds 500000+) | 1,028 | 961 | 436,919 | 6.7% | 15.4% |
| qw | train, games | 300 | 286 | 744,064 | 1.2% | 2.4% |
| qw | train, forks | 7,779 | 3,642 | 916,075 | 3.2% | 6.0% |
| qw | test (`qw-base-200`) | 200 | 189 | 538,756 | 1.1% | 2.2% |

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
  `qw-base-200`). It was predicted and scored once, after all choices were made.
- Validation is one training seed in six, by hash, original games only (241 games). It was used for
  early stopping, the hyperparameters and including the forks: with the same tree settings, forks raised
  validation AUROC from 0.878 to 0.888.
- Training uses the other training seeds plus their forks (2.07M rows at N = 50). One model covers both
  sources.
- **Baseline**: logistic regression on HP fraction, fitted per source.
- **Trees**: LightGBM, 31 leaves, at least 1,000 rows per leaf, learning rate 0.05, early stopped (406
  rounds at N = 50).
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

- **The deep slice is thin, and is the old qw.** The only held-out qw games with state logs are
  `qw-base-200`: build 8698adc with qw's settings before the berserk fixes. 51 games reach XL 12 and 46
  die there, but only 14 of those deaths are in a rune branch. The later `fix1`/`zk` runs on held-out
  seeds have no state logs. Re-running the 200 held-out seeds on the current build with `--state-log`
  is the cheapest way to measure the deep slice properly.
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
