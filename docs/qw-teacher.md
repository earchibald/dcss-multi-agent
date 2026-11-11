# qw as teacher and baseline

[qw](https://github.com/crawl/qw) is the DCSS devteam's rule-based Lua bot, the first bot to win
the game unassisted. It runs here on our 0.34.0 container, headless, at about 345 game turns a
second, on any seed. This page records what was measured with it (2026-11-10 and 11) and how to
rerun it. The tools are in `tools/qw/`; qw's own source is not in the repo (`runs/qw/src` is a
clone, ignored by git).

## Results

Minotaur Berserker of Trog with a mace, the character our trained brain plays.

| Player | Seeds | Mean deepest D | Mean XL | Reached Lair |
|---|---|---|---|---|
| Our rules of thumb | 500000–500059 | 5.58 | n/a | 0 |
| Our model `iter2` | 500000–500059 | 5.86 | n/a | 0 |
| qw as shipped | 500000–500059 | 5.53 | 6.85 | 9 of 60 |
| qw, patched | 500000–500059 | 8.00 | 9.63 | 26 of 60 |
| qw, patched (the baseline) | 500000–500199 | 7.08 (SE 0.29) | 8.71 | 30% |
| + Trog's Hand at every fight's start | 500000–500199 | 7.29 (+0.20 ± 0.31) | 8.88 (+0.17 ± 0.32) | 35% |
| + learned policy, round 1 | 500000–500199 | 6.70 | 8.05 | 23% |

- qw as shipped never goes berserk: `can_berserk()` has an operator-precedence bug. Fixing that
  one line is worth about 2.5 dungeon levels for this character.
- No game in 200 was won. A handful took a rune (0.02 per game).
- The round-1 policy row is contaminated: 31 of its 200 games ended on a qw Lua error
  (`plan_flight_move_towards_enemy`, since patched) and 4 timed out. It has not been rerun.
- "Deepest D" understates qw's better games, which turn into the Lair around D:8–11.

## Where qw dies

From 300 training games (seeds 100000–100299), 7,506 serious fights, 286 of them fatal:

- 133 of 300 games end by D:5. Gnolls kill 33, Sigmund 16.
- 51% of deaths come in fights that peak at 6 or more enemies, 74% at 4 or more. Fights with one
  or two enemies are fatal about 1.3% of the time.
- 93% of fatal fights start at full HP.
- qw's threat number tracks risk: 0.3% fatal under a fifth of its "high" cutoff, 24–39% above
  twice the cutoff.

## Forks: does a different choice in the fight help?

A fork replays a game to one decision, forces or vetoes something there, and plays 2,500 turns
on. Gain is alive-at-the-horizon plus 0.1 × XL, against two control forks that leave qw's choice
alone and only re-roll the dice.

**The controls matter.** Re-rolling the dice alone saves 45% of the fights qw died in. Measured
against the base game instead, every option looked like a large gain, opposites included.

Round 1, existing options, at a fight's start and at 70% and 40% HP (2,897 forks, 635 moments):

| Option | Fatal fights, at start | Survived fights, at start |
|---|---|---|
| Trog's Hand | +0.16 ± 0.09 | +0.05 ± 0.05 |
| Berserk now | +0.05 ± 0.07 | −0.03 ± 0.03 |
| Flee | +0.07 ± 0.08 | +0.02 ± 0.05 |
| Teleport | +0.03 ± 0.12 | −0.01 ± 0.08 |
| Hold the rage for 8 decisions | −0.15 ± 0.08 | −0.08 ± 0.04 |
| Refuse melee for 3 decisions | −0.28 ± 0.07 | −0.04 ± 0.04 |
| Tactical step | −0.12 ± 0.13 | −0.24 ± 0.09 |

Round 2, new actions, at the first moment three or more enemies are closing (1,389 forks, 598
moments):

| Option | Fatal fights | Survived fights |
|---|---|---|
| Fight on the upstairs | +0.14 ± 0.06 | −0.02 ± 0.03 |
| Hold a choke point | +0.07 ± 0.07 | −0.01 ± 0.04 |
| Trog's Hand | +0.08 ± 0.06 | +0.03 ± 0.03 |

Survived fights outnumber fatal ones about ten to one, so used everywhere these are worth about
nothing, and no logged quantity at that moment (threat, level, enemy count, distance to stairs,
open ground) separates the fights where they help. The linear policy fitted on each round gains
+0.01 to +0.04 per moment on held-out games.

**Reading:** among actions available once a fight has started, qw's choice is already about
right for this character, and the dice decide the rest. What is left is upstream of the fight:
how strong the character is when it meets the pack (skills, armour, when it descends, when it
enters the Lair), and which fights it takes at all.

## What is built

| File | What it does |
|---|---|
| `tools/qw/patches.py` | 28 patches to qw for 0.34 and Lua 5.4, each with its reason; 4 fix qw's own bugs |
| `tools/qw/build.py` | Builds `qw.lua` and the rc into `runs/qw/build`; `--deploy` copies to `/data/qw/lib` in the container |
| `tools/qw/ladder.lua` | Our Lua: shims, error recovery, the state and action logs, the override hook, forceable primitives |
| `tools/qw/ladder.rc` | MiBe with a mace, Trog, the 3-rune goal, auto-start |
| `tools/qw/run.py` | Plays seeds or a jobs file of forks in parallel; writes `runs/qw/<name>/results.json` |
| `tools/qw/log.py` | Reads a game's log, one dict per decision (state, plan chosen, override) |
| `tools/qw/forks.py` | Picks moments and writes the fork jobs, controls included |
| `tools/qw/learn.py` | Scores forks against controls, fits one row of weights per option, writes a Lua policy |
| `tools/qw/compare.py` | Compares runs on the same seeds |
| `tools/qw/policy_hand.lua`, `policy_example.lua` | Hand-written policies |
| `models/qw-policy-r1.lua` | The round-1 learned policy (worse than qw: see above) |

Forceable primitives: `berserk`, `trogs_hand`, `brothers_in_arms`, `teleport`, `heal_wounds`,
`flee`, `stairs_up`, `rest`, `attack`, `retreat_step`, `throw`, `choke`, `stairs_fight`, and the
controls `reroll` and `reroll2`. A veto names any plan in qw's cascade.

```sh
uv run python tools/qw/build.py --deploy
caffeinate -i uv run python tools/qw/run.py --seeds 500000-500199 --state-log --name NAME
uv run python tools/qw/forks.py runs/qw/BASE --out runs/qw/JOBS.json --kinds crowd --max-turn 9000
caffeinate -i uv run python tools/qw/run.py --jobs runs/qw/JOBS.json --state-log --name FORKS --no-build
uv run python tools/qw/learn.py --forks runs/qw/FORKS --jobs runs/qw/JOBS.json --out models/POLICY.lua
caffeinate -i uv run python tools/qw/run.py --seeds 500000-500199 --action-log --policy models/POLICY.lua --name NAME --no-build
uv run python tools/qw/compare.py qw-base-200 NAME
```

## Things to know

- Games replay identically from a seed, with our fix for Lua 5.4's per-process `pairs()` order.
  A minority of seeds still split inside crawl (level generation or item rolls). The runner
  checks every fork's prefix against its base (`prefix_match`) and the learner drops mismatches
  (48 of 7,739 forks so far).
- Logging must not call crawl functions that roll the game's dice (hit-chance descriptions,
  `you.status()` in a cloud). `ladder.lua` works around both; `acc_exact` and `status_exact` in
  the state mark the approximations.
- Don't train on seeds 500000 and up. Training games so far use 100000–100299.
- Everything in the container lives under `/data/qw/`. Nothing touches webtiles or its accounts.
- The same seed has not been checked to give the same dungeon here as in the webtiles harness.

## Next

1. Search qw's settings by whole games instead of moments: skill weights, when to descend and
   enter the Lair, the heal and Brothers in Arms thresholds, armour choice. Each variant is 200
   to 600 games (about half an hour per 200) against the baseline.
2. Rerun the round-1 policy now that the Lua error is patched, and rerun the baseline on the
   same build.
3. Give forks a longer horizon and a progress measure beyond XL, to see choices whose payoff
   comes later (piety spent on Trog's Hand, for one).
4. Imitate qw from its state log with our own network, as the starting point for a learned
   player that is not tied to qw's plan order.
