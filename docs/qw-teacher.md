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
| Baseline, rerun 2026-11-12 (1800 s limit) | 500000–500199 | 7.13 | 8.73 | 30% |
| + searched settings (see below) | 500000–500199 | 8.70 (+1.56 ± 0.39) | 10.37 (+1.64 ± 0.40) | 45% |
| Baseline, fixed build (3600 s limit) | 500000–500199 | 7.13 | 8.72 | 30% |
| + searched settings, fixed build | 500000–500199 | 8.79 (+1.65 ± 0.38) | 10.66 (+1.94 ± 0.40) | 46% |

- qw as shipped never goes berserk: `can_berserk()` has an operator-precedence bug. Fixing that
  one line is worth about 2.5 dungeon levels for this character.
- No game in 200 was won. A handful took a rune (0.02 per game).
- The round-1 policy row is contaminated: 31 of its 200 games ended on a qw Lua error
  (`plan_flight_move_towards_enemy`, since patched) and 4 timed out. It has not been rerun.
- "Deepest D" understates qw's better games, which turn into the Lair around D:8–11.

## Settings search

Searched by whole games (2026-11-11 and 12): each variant is a few lines of Lua run after
`qw.lua` (`tools/qw/variants.py`), scored against the baseline on the same seeds.

- Stage 1: 25 single changes on seeds 100000–100149 (600 s limit).
- Stage 2: the leaders and their combinations on fresh seeds 100150–100449 (1800 s limit).
- Stage 3: four survivors, once, on the held-out seeds against a baseline in the same run.

Stage 3, 200 held-out seeds, difference from the baseline ± SE:

| Settings | XL | Deepest D | Reached Lair | XL 12+ |
|---|---|---|---|---|
| Baseline | 8.73 | 7.13 | 30% | 25% |
| `zerk_hp70` | 9.86 (+1.12 ± 0.37) | 8.14 (+1.01 ± 0.37) | 43% | 38% |
| `zerk_hp70+zerk_early` | 10.10 (+1.36 ± 0.38) | 8.45 (+1.31 ± 0.37) | 46% | 41% |
| `zerk_hp70+bia7` | 10.21 (+1.48 ± 0.37) | 8.45 (+1.31 ± 0.36) | 46% | 40% |
| `zerk_hp70+zerk_early+bia7` | 10.37 (+1.64 ± 0.40) | 8.70 (+1.56 ± 0.39) | 45% | 43% |

- `zerk_hp70`: berserk under 70% HP with an enemy adjacent, not 50%. `zerk_early`: high-threat
  cutoff 7, not 10. `bia7`: Brothers in Arms at threat 7 (qw's own test rarely fires).
- The triple led stage 2 as well (XL +1.50 ± 0.30, depth +1.18 ± 0.29 on 300 seeds). The four
  rows above are not separable from each other; all are clear of the baseline.
- Everything that worked is "rage sooner". Skill weights, heal thresholds, rest and flee
  thresholds, extreme-threat cutoffs and Trog's Hand were within noise. Worse than the
  baseline: lighter armour (`dodgy`), early Orc, more defensive skills (`defence_hi`, which
  looked fine on 150 seeds and lost 0.6 XL on 300).
- Still no wins in 200 games. The unfinished games were almost all the best ones: stalled in
  Vaults at XL 17–20 (7 of the triple's 9) or cut at the limit in Spider, Shoals or Snake.
  Both are qw bugs, traced and patched on 2026-11-12: see "Unfinished games" below.

```sh
uv run python tools/qw/search.py run --stage NAME --seeds A-B --time-limit 1800 --variants a,b,a+b [--fleet]
uv run python tools/qw/search.py table --stage NAME
```

`--fleet` plays on the other Macs through `ladder-fleet qw`. Apple-silicon hosts replay
identically to this machine; the Intel NUCs do not, so they stay out.

## Unfinished games

Every stall, hang and error loop of stages 2 and 3 came from four causes. All are patched
(`tools/qw/patches.py`, `tools/qw/ladder.lua`); the seven games below, replayed on the
fixed build all finish.

- **Bound in place (the Vaults stall).** qw does not know the -Move status, which an ironbound
  beastmaster's bolas gives in Vaults and electricity gives in water. Each step answered "You
  cannot move." without spending a turn, every move plan "failed despite returning true", and
  the game span on one turn. 36 of the 41 stalls, 33 of them in Vaults. Now `unable_to_move()`
  and `move_to()` know the status, and the plan of last resort waits.
- **Flee search (the Spider, Shoals and Snake "slowness").** Not slowness: one decision that
  never returned. `distance_map_search_from()` tests an undefined global, `cache`, where it
  means `cache_result`, so its memo never hits and the search for a flee route is exponential
  in the route's length. One word.
- **`compare_table_keys`.** Two wand-attack results with no properties scored raised "attempt
  to compare two nil values" on every decision. A missing property now counts as 0.
- **Every plan declines.** 5 stalls in D:10–15: on arrival in a cloud, mid-teleport, no plan
  acted and no turn passed. Not traced further. `ladder.lua` now waits a turn after 50 such
  decisions (`QWNUDGE`) and qw's own stuck plans take over; the D:10 game went on to the Lair.

The seven unfinished games of the triple, replayed on the fixed build:

| Seed | Before | After |
|---|---|---|
| 500020 | hung in Snake:2, XL 16 | died in Abyss:4, XL 22, 2 runes |
| 500024 | stalled in Vaults:4, XL 19 | died in Vaults:4, XL 20, 1 rune |
| 500042 | stalled in Vaults:3, XL 19 | died in Zot:1, XL 23, 3 runes |
| 500085 | stalled in Vaults:1, XL 17 | died in Vaults:2, XL 18, 1 rune |
| 500094 | stalled in Vaults:4, XL 20 | died in Depths:1, XL 21, 2 runes |
| 500130 | stalled in Vaults:2, XL 18 | died in Depths:2, XL 21, 2 runes |
| 500151 | stalled in Vaults:1, XL 17 | died in Snake:2, XL 16 |

All 200 held-out seeds on the fixed build, 3600 s limit (stage `fix1`):

| Settings | Finished | With a rune | Best game |
|---|---|---|---|
| Baseline | 200 of 200 | 2 | Depths:4, XL 22, 2 runes |
| `zerk_hp70+zerk_early+bia7` | 198 of 200 | 16 (eight with 1, seven with 2, one with 3) | Zot:1, XL 23, 3 runes |

No wins. Before the fixes the triple left 9 of 200 unfinished and 6 finished games with a rune. The two
still unfinished, both at the hour limit:

- 500139: D:12 at XL 18, no error and no nudge, so one decision that never returned. Not traced.
- 500143: Lair:5 at XL 13, "Cannot currently process new keys (there is pending input)" 9
  times, 9 nudges. Not traced.

A game that hangs inside one decision shows as `timeout` with crawl at 100% CPU. To find the
plan, pass `--lua` a file that wraps `ladder_record_plan` and prints each plan's name: the
hang is in the plan after the last one printed.

## Deep deaths, quit games and five more fixes

The 400 held-out games on the `fix1` build were read for how the deep games end.

Of the tuned settings' 200 games, 55 end at XL 15 or more. They die in Spider 13, Snake 10,
D 7, Vaults 5, Orc 5, Depths 5, Shoals 4, Swamp 2, and one each in the Abyss, Zot, Desolation
and the Lair. The wall is the first rune branch at XL 15–18 (29 deaths), not Vaults or Depths.
Of those 29: 28 carried potions of curing, 25 scrolls of teleportation, 20 were on berserk
cooldown, 19 slowed, 18 lethally poisoned, 6 lacked poison resistance, none had haste.

What happens: qw goes berserk with poison in it or in a poison cloud, the poison turns lethal
mid-rage, the potion is refused ("You are too berserk!") and qw dies as the rage ends. Separately,
qw only cured poison that would take 60 HP or more, so under 60 HP a lethal dose never
qualified.

17 of the 400 games ended with qw quitting: it gets stuck, idles until Zot's clock drains it,
and quits. The commonest cause is a walk that steps between two or three squares for ever:
the route that avoids exclusions and the plain route disagree about the next step.

Five fixes (stage `zk`, build `runs/qw/build-zk`, deployed to `/data/qw/lib-zk`; `/data/qw/lib`
is still the `fix1` build):

- Lethal poison is cured wherever it is noticed, not only at 60 HP of damage with an enemy in view.
- Poison that will take half the current HP is cured before going berserk.
- The two poison plans no longer try to drink while berserk.
- A walk to a destination will not step back onto its last 16 squares (two patches).

The 17 quit games replayed with the walk fix: 13 play on to an ordinary death, 3 still quit
(500053, 500065, 500165) and 500146 runs out the 30 minutes.

All five fixes against the `fix1` build, tuned settings, training seeds 100000–100149, the same
seeds in both (113 of 150 games are identical):

| | `fix1` build | With the five fixes |
|---|---|---|
| Died of poison | 13 | 8 |
| Quit | 7 | 4 |
| Games with a qw panic | 15 | 6 |
| Mean XL | 10.40 | 10.55 (+0.15 ± 0.36) |
| Deepest D level, mean | 8.52 | 8.65 |
| Reached XL 15 | 38 | 38 |
| Reached the Lair | 73 | 75 |
| Runes | 17 | 14 |

The bugs are gone and the average does not move: a character that was dying of poison mostly
dies of something else in the same place. Six of the eight poison deaths left are poison landing
during the rage, which no cure order fixes. Not yet measured on the held-out seeds.

Quit games still open on the fixed build: a plan that flips between "PLANNING ORC" and
"PLANNING D" (100103, 100147), a stall at an exclusion through another plan (100011), "Sorry,
I don't know how to get there" on D:3 (500053), and two unclassified (100047, 500065). Panics
still open: `unwield_weapon`, `stairdance_up`, `upgrade_equipment` and `brothers_in_arms`
"failed despite returning true".

## Poison and the rage: when the lethal dose arrives (stage `zr`)

The 0.34.0 source (in the container at `/crawl`) shows that a rage does not make poison you
already have any worse:

- `go_berserk` (`player-act.cc` 697–700) and `player_end_berserk` (`player.cc` 9184–9205) both
  call `calc_hp(true)`, which rescales current HP by new max / old max and keeps the fraction in
  `hit_points_regeneration` (`player.cc` 2798–2817). The rage's +50% and its end's 2/3 cancel, so
  poison present before a rage is lethal after it exactly when it is lethal now
  (`poison_survival() <= 0`). Poison that lands during a rage costs only 2/3 as much once the rage is
  over. In a rage, poison is lethal at the end once `poison_survival <= hp - hp * base / mhp`
  (about `hp / 3`).
- What the rage changes is that nothing can be drunk (`item-name.cc` 3233), read (3068) or
  invoked (`ability.cc` 1816; Trog's Hand has no `berserk_ok` flag) until it ends. Attacks reset
  `berserk_penalty` (`fight.cc` 600); each non-attack action in a row takes 1, 2, 3… more turns off
  the rage (`main.cc` 2851–2876). The rage expires in `_decrement_durations`, and that turn's
  poison tick comes after it (`player-reacts.cc` 1355, 1370), against the rescaled HP. A single
  tick cannot kill a character the rage left alive, so qw always gets one action after the rage.

The 34 zk games on training seeds 100000–100149 that ended poisoned, replayed with the state log
(33 replayed identically). The onset is the first decision at which the poison would be lethal once
any rage is over:

| Lethal onset | Games | Of them XL 11+ | Detail |
|---|---|---|---|
| During a rage, no poison before it | 5 | 4 | all of the poison landed in the rage |
| During a rage, some poison before it | 9 | 2 | zk's half-HP cure rule held in 2 (no potion); in 6 of the other 7, curing was in the pack |
| After a rage (slowed, on cooldown) | 6 | 3 | 4 of the 6 read teleportation with curing in the pack; 2 were lethal on the first action after the rage |
| Outside a rage | 2 | 1 | 100088: read teleportation with 5 curing, 7 turns after a clean rage |
| Before the rage | 1 | 0 | XL 1, no potion |
| Never lethal from poison | 11 | | killed outright; the morgue says "lethally poisoned" only because HP is ≤ 0 |

There is no fix during the rage that the game allows. After it, there is: zk's lethal-poison cure
is seventh in the emergency cascade, behind `stairdance_up` and `teleport`, and a teleport scroll
read with lethal poison means 3–5 more turns of poison with no cure. Stage `zr`
(`runs/qw/build-zr`, `/data/qw/lib-zr`, `build.py --stage zr`) adds one plan at the head of the
emergency cascade: lethal poison and a potion of curing mean drink. There is no new berserk rule.
On zk's half-HP rule: since the rage is neutral to poison you already have, the rule only decides
whether to spend an unraged turn so that potions are not needed mid-rage. 6 of the rage deaths
started below it with curing in the pack. A lower threshold would be another rule of thumb and
has not been tried.

zk against zr, tuned settings, training seeds 100000–100149, 3600 s limit:

| | `zk` (`zk1-fix`) | `zr` (`zr1-fix`) |
|---|---|---|
| Unfinished | 0 | 0 |
| Died of poison | 8 (6 in a rage, 2 after one) | 6 (6 in a rage) |
| Died with the end of a rage in the last messages | 44 (3 lethally poisoned) | 43 (0) |
| Quit | 4 | 6 |
| Mean XL | 10.55 ± 0.42 | 10.73 ± 0.45 (paired +0.18 ± 0.10) |
| Deepest D level, mean | 8.65 ± 0.38 | 8.69 ± 0.39 (paired +0.04 ± 0.08) |
| Reached XL 15 | 38 | 39 |
| Runes | 14 | 24 |

- The new plan acted 29 times in 17 games. In 11 of them it did what zk's cure would have done
  one plan later, and the game is identical. 2 had already diverged by noise (below). In 4 it
  replaced a teleport: 100022 (Shoals:2 XL 17
  became Vaults:5 XL 24, 2 runes), 100023 (XL 16 became 18, 1 rune), and 100082 and 100118, which
  died where they did before (re-poisoned, or the HP was already gone).
- The other 12 changed games diverge before any lethal poison, at crawl-side splits (a different
  artefact on the floor, a different level). That is replay noise and not the patch. It includes
  both of zk's after-rage poison deaths (100006, 100088) and most of the runes. The part that can
  be attributed is +9 XL and +3 runes over 150 games (+0.06 XL a game). That is real but small,
  and inside the noise of a 150-game comparison.

## Other builds

qw plays any species and background through `--combo`, with the gods in its list (Trog,
Okawaru, Makhleb among them). It does not play casters. A probe on the `fix1` build, training
seeds 100000–100049, the tuned settings unless noted:

| Build | Mean XL | Reached the Lair | Reached XL 15 | Runes |
|---|---|---|---|---|
| Minotaur Berserker, mace (ours) | 10.86 | 26 | 14 | 7 |
| Minotaur Berserker, hand axe | 10.74 | 24 | 14 | 10 |
| Minotaur Fighter of Okawaru, war axe, qw's own settings | 9.92 | 22 | 10 | 3 |
| Troll Berserker, claws | 9.76 | 21 | 3 | 0 |
| Minotaur Berserker, mace, qw's own settings | 8.78 | 15 | 9 | 1 |
| Demonspawn Berserker, hand axe | 8.24 | 14 | 6 | 0 |
| Gargoyle Berserker, hand axe | 7.68 | 11 | 5 | 2 |
| Oni Berserker, mace | 6.98 | 6 | 1 | 0 |

No build beats the Minotaur. The Fighter's 20 of 50 games that end before an Okawaru altar is
found count against it, and its settings are untuned: it is the one worth a settings search.
Every build played all 50 games without a port bug of its own. The same seed and settings
played three times gave 48 or 49 identical games of 50.

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
| `tools/qw/patches.py` | 38 patches to qw for 0.34 and Lua 5.4, each with its reason; 14 fix qw's own bugs |
| `tools/qw/build.py` | Builds `qw.lua` and the rc into `runs/qw/build`; `--deploy` copies to `/data/qw/lib` in the container |
| `tools/qw/ladder.lua` | Our Lua: shims, error recovery, the state and action logs, the override hook, forceable primitives |
| `tools/qw/ladder.rc` | MiBe with a mace, Trog, the 3-rune goal, auto-start |
| `tools/qw/run.py` | Plays seeds or a jobs file of forks in parallel; writes `runs/qw/<name>/results.json`. `--combo GrBe.handaxe`, or a `-- combo: GrBe.handaxe` line in the `--lua` file, picks the character |
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
uv run python tools/qw/build.py --stage zr --out runs/qw/build-zr --deploy --lib-dir /data/qw/lib-zr
caffeinate -i uv run python tools/qw/run.py --seeds 100000-100149 --no-build --lib-dir /data/qw/lib-zr --lua runs/qw/combo1-lua/MiBe_mace.lua --time-limit 3600 --workers 9 --name zr1-fix
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

1. Stop tuning the Minotaur Berserker's settings. `zerk_hp70+zerk_early+bia7` is the baseline;
   the settings left to find are worth less than the noise.
2. Deploy the `zk` build as `/data/qw/lib` and re-measure both settings on the held-out 200,
   once, as a bug-fix re-measure. The fixes came from reading held-out deaths, so the result
   flatters them.
3. The rune-branch wall is berserk itself: poison and slowness land during and after the rage.
   Most lethal poison lands during the rage (14 of 23 games above), where the game allows no
   potion. Things to try, on training seeds: no berserk in a poison cloud or without poison
   resistance in Spider, Snake and Swamp, with poisoners in view; choose the rune branches by
   resistances held. Measure `zr` on more seeds before deploying it.
4. Search the Minotaur Fighter of Okawaru's settings (heroism, finesse, when to flee): a second
   teacher that does not depend on rage.
5. For the imitation step, record games from the Minotaur Berserker (both weapons) and the
   Fighter. Troll, Demonspawn, Gargoyle and Oni add weaker play, not variety worth learning.
6. Trace the open quit causes and panics above, the two unfinished games (500139, 500143) and
   the every-plan-declines stall.
7. Rerun the round-1 policy on the fixed build; give forks a longer horizon and a progress
   measure beyond XL.
8. Imitate qw from its state log with our own network, as the starting point for a learned
   player that is not tied to qw's plan order.
