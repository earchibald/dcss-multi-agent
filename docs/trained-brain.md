# The trained brain

A small neural network, trained on this machine from the ladder's own games, that chooses Reflex's
next action. It is not a language model and makes no API calls: it reads numbers about the moment and
runs in numpy in well under a millisecond. It is the same idea as the trained brain in
`~/Code/s1-battle`, moved to a game that can't be forked.

## Where it stands

**2026-11-14:** `iter2` is still the champion. On 200 evaluation dungeons it averages 5.51 (500000–500199)
and 5.48 (530000–530199). The version 5 inputs (below) did not beat it.

Measured 2026-11-09 on this Mac, Minotaur Berserker, 60 fixed evaluation dungeons (seeds 500000–500059)
that training never sees. "Depth" is the deepest floor reached. The last column compares model and
baseline dungeon by dungeon.

| | games | mean depth | median | best | mean XL | game turns | vs baseline: deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Rules of thumb, first version (no equipment) | 56 | 4.36 | 4 | 10 | 4.66 | 1664 | |
| **Rules of thumb now** (`baseline`: wields and wears what it finds) | 60 | **5.55** | 6 | 12 | 5.67 | 1960 | |
| `iter1`, discounted reward (how round 1 first came out) | 60 | 4.00 | 4 | 10 | 3.80 | 943 | 9 / 15 / 36 |
| `iter1`, retrained to predict depth gained by the end of the game | 60 | 5.48 | 6 | 15 | 5.15 | 1140 | 22 / 13 / 25 |
| the same, `margin=0.6` | 60 | 5.25 | 5 | 12 | 5.32 | 1725 | 16 / 24 / 20 |
| the same, `margin=1.0 died_soon=-3` | 60 | 5.28 | 5 | 12 | 5.48 | 1964 | 8 / 39 / 13 |
| **`iter2`** (round 2: + 178 games and 425 forks played to the end) — the champion | 60 | **5.85** | 6 | 12 | 5.73 | 1754 | 19 / 26 / 15 |
| `iter3` (round 3: + 177 games and 767 forks), against `iter2` on the same dungeons | 58 | 5.59 | 5 | 11 | 5.09 | 1319 | 19 / 10 / 28 vs `iter2` |
| `iter4` (round 4: + 171 games, 199 forks and 1,153 rows of your own play), against `iter2` | 59 | 5.86 | 6 | 11 | 5.86 | 1796 | 20 / 17 / 21 vs `iter2` |
| the same, with the nudge toward what you did (`human=0.2`) | 60 | 3.27 | 3 | 8 | 4.13 | 1867 | |

**The gain so far has come from what the bot can do, not from the model.** Equipment took the rules of
thumb from 4.36 to 5.55, and fixing the hangs means all 60 games now finish (4 to 8 used to be lost).
**Round 2's model is the first to come out ahead** (5.85 against 5.58 for the baseline replayed alongside
it) and is the champion: `models/brain.json`, which `--brain` now plays. Read that as "level or slightly
better", not as proof: one standard error on a mean depth is about 0.3, and the baseline replayed four
times gave 5.55, 5.48, 5.42 and 5.58. The three `iter1` rows are level with it.

What the model rows say:

- With time-discounted rewards the model dives, however the reward is shaped. Paying for a depth only
  after 200 turns survived there did not help (4.00): a discount prefers the same depth sooner, and that
  alone is a preference for the stairs over exploring first.
- Predicting **depth gained by the end of the game, undiscounted** (`depth_end`, the number the
  evaluation counts) brought the same network on the same data level with the baseline. On held-out
  forked moments it picks the best action tried 63% of the time (35% before; 126 moments).
- It still replaces "explore" and "wear" with "descend" more than half the time, and reaches the same
  depth in 40% fewer turns at a lower level. That trade is neutral here; it would be wrong for a character
  meant to survive past D:12. Holding it closer to the baseline (the last two rows) removes the trade
  without finding anything better.

Round 2 ran overnight and the server stopped answering part-way (most likely the laptop slept): 141 of
566 forks and 28 of 60 evaluation games were lost, and the loop promoted on the 32 that finished. The row
above is a clean re-run the next morning. The loop now refuses to promote unless 90% of the evaluation
games finished. Keep the machine awake for long runs (`caffeinate -i uv run ladder brain iterate ...`).

Rounds 3 and 4 (2026-11-10) did not move it. `iter2` stays the champion, replayed at 5.86.

- **Round 3** (`iter3`) came out behind, 5.59, and dived again: the same floors in a quarter fewer turns,
  at a lower level.
- **Round 4** (`iter4`) is level, 5.86 against 5.86. The loop was stopped during its forks (199 of 735)
  and the round finished by hand. Its one fewer death is a game stuck on D:2, so it was not promoted.
- **More of the same data has stopped helping.** The corpus grew from 505k to 801k rows over the two
  rounds and the validation numbers did not change (outcome loss 0.75, `depth_end` R² 0.21 to 0.23). On
  held-out forked moments `iter4` barely beats choosing at random (regret 1.40 against 1.46; `iter2` had
  0.98 against 1.16 on a smaller set). That points at what the model sees and can do (Next, 2 and 3),
  not at volume.
- **Your games are in the corpus**: 1,153 rows from 17 recordings. One is a manual game that reached
  D:10 in 6,139 turns, deeper than 9 in 10 of the bot's games; 11 are short take-overs of Reflex's games
  (1 to 19 rows each, nearly all `fight`, `rest` and `flee_up`). They are 0.14% of the rows, so they
  can't have moved `iter4` as outcome labels.
- **The nudge toward what you did makes it worse** (`--style human=0.2`: 3.27). The converter keeps only
  commands that are one of the brain's actions: in the D:10 game 909 of 2,081 commands became rows, and
  835 steps walked by hand were dropped, with them most of the walking to stairs. What is left is 63%
  `fight` and 1% `descend`, so the prior learned from it holds the bot on each floor. It stays off
  (`human` is 0 by default) until walking by hand is mapped to something.
- A take-over that ends without a death is labelled as if the game stopped there. The character went on
  in the next run and usually died within a thousand turns; the recordings are not yet joined up.
- Games that hang are back: 9 of 180 self-play games in round 4, and 1 or 2 of 60 in each evaluation
  with no random choices.

The first three candidates (before equipment, 3.75 to 4.30 against the old 4.36) are in `models/v2/`.

### Version 5: richer inputs (2026-11-14)

`FEATURE_VERSION` 5 adds the monster table and what the game state shows beyond names ("What it sees"
below). Measured offline first, then in games.

**Offline.** One corpus (810,581 rows, the same rows and the same validation split by dungeon for every
variant: 167,251 validation rows, 240 held-out forked moments), sliced by columns, each variant trained at 5
seeds with the usual settings. Mean ± standard deviation over the seeds; fork regret is the default style's
value lost against the best action tried at a forked moment (random choice loses 1.46).

| inputs | q_loss | R² died_soon | R² depth_end | danger AUC | fork regret |
| --- | --- | --- | --- | --- | --- |
| `v4`: version 4's | 0.7565 ± 0.0036 | 0.309 ± 0.006 | 0.212 ± 0.009 | 0.800 ± 0.002 | 1.34 ± 0.08 |
| `s1`: + the monster table | 0.7545 ± 0.0045 | 0.309 ± 0.005 | 0.211 ± 0.010 | 0.802 ± 0.002 | 1.39 ± 0.08 |
| `s12`: + the table and sight (version 5) | **0.7503 ± 0.0021** | **0.319 ± 0.005** | 0.215 ± 0.006 | 0.800 ± 0.003 | 1.28 ± 0.07 |
| control: `s12` with the new columns shuffled across rows | 0.7540 ± 0.0012 | 0.307 ± 0.003 | 0.218 ± 0.004 | 0.800 ± 0.002 | 1.34 ± 0.08 |
| `s12` without the name hash | 0.7503 ± 0.0032 | 0.323 ± 0.010 | 0.211 ± 0.008 | 0.798 ± 0.003 | 1.26 ± 0.08 |

Paired over the 240 held-out forked moments (seeds averaged), fork regret against `v4`: `s1` +0.04
[−0.03, +0.12], `s12` −0.06 [−0.13, +0.02], control −0.00 [−0.09, +0.08], no hash −0.08 [−0.18, +0.02]
(95% bootstrap over moments).

- **The monster table alone (stage 1) does nothing measurable.** Every difference from `v4` is inside the
  seed-to-seed spread. The name hash and the threat level already carried most of it.
- **The table plus sight (stage 1+2) is a small, real gain on two numbers**: outcome loss −0.006 (about 2
  standard deviations, and 0.004 better than the shuffled control, which itself drifts 0.002) and R² of
  dying soon +0.010 (about 2 sd; the control is −0.002). It does **not** move what the policy uses to
  choose: R² of `depth_end`, danger AUC and fork regret are all within the spread, and the fork interval
  includes zero. So it passes the offline gate narrowly, on predicting death, not on choosing.
- Dropping the name hash makes no difference either way, so it stays (it keeps version 4's columns a clean
  prefix).
- The training numbers stop improving after 3–6 epochs whatever the inputs; the network memorises games
  from there.

**In games it is worse, and that is real.** `models/v5-seen.json` (the `s12` inputs, trained the usual way
at seed 0, chosen before any game) against the champion `iter2`, both with no random choices, 8 at once, on
two blocks of 200 evaluation dungeons. The champion was played with this branch's previous commit, since
version 5 refuses it. Block A is the usual 500000–500199; block B, 530000–530199, had never been played by
anything. Differences are paired by dungeon over the games both finished, with a 95% bootstrap interval.

| | block | finished (hung) | mean depth | died | mean XL | game turns | `descend` share of choices |
| --- | --- | --- | --- | --- | --- | --- | --- |
| champion `iter2` | A | 199 (1) | 5.51 | 193 | 5.65 | 1817 | 28.9% |
| `v5-seen` | A | 199 (1) | 4.84 | 188 | 4.70 | 1294 | 38.0% |
| control: version 4 inputs, retrained on the same rows (`v5-v4control`) | A | 199 (1) | 5.26 | 180 | 5.40 | 2019 | 38.8% |
| champion `iter2` | B | 194 (6) | 5.48 | 183 | 5.32 | 1743 | 31.7% |
| `v5-seen` | B | 195 (5) | 4.69 | 187 | 4.54 | 1239 | 37.3% |

| paired | block | dungeons | depth difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- |
| `v5-seen` − champion | A | 198 | **−0.66** | [−1.10, −0.22] | 59 / 44 / 95 |
| `v5-seen` − champion | B (fresh) | 190 | **−0.82** | [−1.35, −0.30] | 63 / 38 / 89 |
| control − champion | A | 198 | −0.23 | [−0.65, +0.19] | 75 / 44 / 79 |
| `v5-seen` − control | A | 198 | −0.42 | [−0.89, +0.05] | 70 / 41 / 87 |

- Under the promotion rule (higher mean depth, at least 90% of games finished) `v5-seen` is not promoted,
  and the fresh block says the loss is not a fluke of block A. `iter2` stays the champion.
- It **dives again**: the same kind of floor in 30% fewer turns, a level lower, more `descend`. The
  control, which sees only version 4's inputs of the same rows, does not (2,019 turns) and is level with
  the champion within the interval. So retraining on today's corpus costs little or nothing, and most of
  the loss comes with the new inputs, though `v5-seen` against the control alone is only borderline.
- Read with the offline table: the new inputs predict *dying soon* better and *depth gained* no better,
  and the policy acts on `depth_end − died_soon`. A sharper `died_soon` on a few moments can't explain
  diving, so the likelier cause is that the extra inputs let the network fit the self-play policy's own
  habits more closely (the corpus is 73% rules of thumb and 21% earlier models, which already dived), and
  the 0.25 margin then lets it act on that more often. Measured on block A: `v5-seen` leaves the rules of
  thumb at **34%** of its choices, the champion at 16% and the control at 20%, and its commonest change is
  explore → descend (10,244 times; the champion's is drinking an unknown potion → descend). The cause is
  inferred, not verified, and with one training seed per model the spread of play between seeds is
  unmeasured.
- About 1 in 200 games hangs without random choices on block A and 1 in 35 on block B, for every model.

What would test it next, cheapest first: play `v5-seen` at `margin=0.6` or `1.0` (the earlier way to hold a
diving model near the baseline), train 2–3 more seeds of `s12` and of the control and play them on block A
to see the spread in games, and add forks (the rows that compare actions) before adding inputs.

Throughput: about 28 s per game, 6 at once (240 games in 11 minutes); a fork costs about 18 s of one
worker, since it replays the game to the fork and then plays on. Training takes under a minute. A model
is 108 KB (39k weights, float16) and matches torch to 5 decimal places.

## What carried over from s1-battle, and what couldn't

| s1-battle | here |
| --- | --- |
| A set encoder: one shared sub-network per opponent, pooled, so order doesn't matter | The same, per monster in view (up to 8, nearest first) |
| The network predicts several outcomes per option, not one score | Six outcomes per action (below) |
| A *style* weighs the outcomes at decision time, so behaviour changes without retraining | `policy.Style`, set with `--style key=value` |
| float16 weights in a JSON file, forward pass re-implemented without the training framework, parity-checked | `models/*.json` (~100 KB), numpy forward pass in `net.py`, `check_parity` on every training run |
| Expert iteration: the current model plays, the next one learns from those games too | `ladder brain iterate` |
| Labels from **counterfactual rollouts**: fork the simulator once per option and play each out | DCSS can't be cloned mid-game, but a seeded game **replays identically**, so `forks.py` replays a recorded game to a choice and takes another action there. About 1 replay in 15 drifts from the recording (the fork is then detected and dropped). A fork costs a replay of everything before it, seconds where s1 paid microseconds |

That last row is the big difference. Most rows here only know what happened after the action that was
actually taken, in that one game; forks are the few places where several actions' outcomes are known
from the same state. So:

- Forks are spent where a choice matters most: 70% on the last 40 choices before a death, the rest
  anywhere there was more than one thing to do. A fork row counts 20 times in the loss.
- Self-play makes a share of its choices at random (`--epsilon`, 0.2 by default). Those are the rows that
  tell the network what the *other* actions lead to.
- The network is not trusted far from its data. It only overrides the rules of thumb when it predicts an
  action to be better by a margin (`Style.margin`), and only for actions it saw at least `Style.min_count`
  times in training.
- Games are seeded, and a seed replays identically for the same choices. Evaluation plays the same seeds
  with each model, so two models are compared on the same dungeons.

## What it decides

Reflex still runs the game (keys, prompts, detectors, logs). The brain replaces `StubTiers.next_action`:
at every step it picks one of these, from those possible right now (`policy.available`):

| action | what Reflex does |
| --- | --- |
| `explore` | autoexplore (`o`) |
| `fight` | autofight (`Tab`), or one step along our own path when autofight can't reach |
| `rest` | rest (`5`) |
| `descend` | one step toward the nearest known `>`, or `>` when standing on it |
| `flee_up` | one step toward the nearest known `<`, or `<` when standing on it (not from D:1) |
| `quaff_heal` | drink a known potion of curing or heal wounds: curing when seriously poisoned or at full HP, heal wounds otherwise, the other when only one is held (`policy.heal_potion`) |
| `quaff_unknown` | drink an unidentified potion |
| `read_unknown` | read an unidentified scroll |
| `read_teleport` | read a known scroll of teleportation |
| `wait` | pass one turn (`s`) |
| `berserk` | Trog's Berserk (`a`, `a`) |
| `wield` | wield the best mace or flail in the pack, if it beats the one in hand (`w`, letter) |
| `wear` | put on the piece of armour that improves the character most (`W`, letter) |

The brain decides *when* to change equipment (never with something hostile in view); `gear.py` decides
*what*, by a fixed ranking: base damage and speed for the mace family, armour class for body armour, any
piece for an empty cloak, glove, boot, head or shield slot. The rc's autopickup function collects one of
each kind it ranks. Artefacts and other weapon types are left alone.

Decision cards (stairs, altars, uniques, the stat prompt) still go through `Hooks.decide` and Authority
as before. Where the stub raised an escalation (HP at half with monsters in view, an action that makes
no progress) the brain picks another action instead, so a game runs until the character dies.

The **rules of thumb** (`policy.baseline`) are what plays when there is no model, and what the model is
measured against: berserk when hurt or facing something tough, drink a healing potion at half HP, fight,
change to better equipment, rest below 80%, read and drink unknowns when safe, explore, then go down.
Before all of these, seriously poisoned (the poison will take over 65% of current HP, the game's own
"seriously poisoned") with curing in the pack: drink it.

`berserk` is never available while the poison already in the character would kill it once a rage
ended (`policy.poison_lethal_after_rage`). A rage multiplies current HP by 3/2 at its start and by 2/3
at its end (`calc_hp(true)` in `player::go_berserk` and `player_end_berserk`); the poison still to
come is not scaled. So in a rage the poison is lethal at its end once `poison_survival <= hp/3`, and
before one the HP comes back whole, so it is lethal afterwards exactly when it is lethal now
(`poison_survival` 0). What the rage adds is that nothing can be drunk until it is over. These are
rules in `available`, so a model can't choose otherwise; `FEATURE_VERSION` did not change for them.

`--style wiki=1` plays a variant that follows the DCSS wiki's strategy guides (`policy.baseline_wiki`):
rest to full, drink before the rage, go up nearby stairs when hurt, teleport and try unknowns as last
resorts. On the 60 evaluation dungeons it came out about one standard error *behind* (5.20 against 5.58
alone, 5.53 against 5.86 under `iter2`), so it is off by default. `docs/wiki-strategy.md` has the rules,
the measurement and the rest of what the guides say.

## What it sees

`features.observe` writes the moment as a JSON dict (this is what the step log keeps); `features.encode`
turns it into numbers:

- **About the character**: HP and MP fractions, level and progress, AC/EV/SH, stats, depth, 18 status
  flags, Trog and piety, healing potions / unknown potions / unknown scrolls / teleports carried.
- **About the place**: on stairs or not, walking distance to known up and down stairs, open neighbours
  (corridor or open floor), level explored, choices and turns spent on this level.
- **About the fight**: how many hostiles, how many adjacent, nearest, worst and total threat, a unique.
- **Recent history**: HP change since the last choice, the last action, which actions are possible
  (so "a better weapon is in the pack" is seen as "`wield` is possible").
- **Per monster** (a set): distance, direction, adjacent, unique, webtiles' threat level (0–3), and its name
  hashed into 24 buckets.

Those are version 4's inputs (81 numbers, 33 per monster). `FEATURE_VERSION` 5 keeps them as the front of
each vector and adds two groups (`features.SELF_GROUPS`, `MON_GROUPS`):

- **From the monster table** ("table", 15 per monster, 7 totals). `src/ladder/brain/monsters-0.34.json` is a
  53 KB copy of `docs/data/monsters-0.34.json` shipped inside the package, so every worker has it
  (`monsters.lookup` handles "the", zombies, spectral, vault names; 99.99% of the corpus's sightings are
  found). Per monster: found or not, hit dice, average HP against our max HP, its attacks' maximum damage
  times its speed against our current HP, fast, slow, eight kinds of threat (hits from range, poison,
  disables, blinks, summons, drains or corrodes, smites, reach), experience. Totals: summed HP and damage,
  the worst damage, the highest HD, how many are fast, ranged, not in the table. Computed from the names
  alone, so every step ever logged re-encodes.
- **From the game state** ("seen", 12 per monster, 11 in the character vector), read by `features.sight`:
  each monster's damage level and the HP that leaves (its `avghp` from webtiles times the middle of the
  damage band), asleep / unaware / fleeing / paralysed, poisoned, in a net or web, and status icons
  (summoned, buffed, debuffed); the score `gear.py` gives the weapon in hand; and the map around the
  character: walkable squares within 2, a corridor (walls on both sides), the shortest, mean and longest of
  eight rays to a wall (up to 7), unknown squares within 3. `observe` logs these from now on. Older steps
  get them from `ladder brain reobserve`, which replays each game's protocol log (below). A step that has
  none has `seen_missing` set: zeros never stand for "not known".

The name hash stays. It is part of version 4's prefix, which keeps the comparison below clean, and removing
it made no measurable difference either way (the version 5 table under "Where it stands").

Still not seen: what is worn (only the AC it adds up to), skills, spells, and the map as a picture.

## What it predicts

For each action, seven numbers about what follows (`corpus.label` computes them from the rest of the game):

| component | meaning |
| --- | --- |
| `died_soon` | died within 30 game turns |
| `hp_lost` | deepest HP drop within 30 turns, as a fraction of max HP |
| `xp_soon` | experience levels gained within 100 turns |
| `depth_go` | new depths reached later **and survived for 200 turns**, each discounted by exp(−turns / 1500) |
| `xp_go` | experience gained later, discounted the same way |
| `died_go` | exp(−turns until death / 400); 0 if the game didn't end in death |
| `depth_end` | how many depths deeper than now the game ever got, undiscounted |

A depth used to count on arrival, and the first models learned that the stairs pay whoever dies at the
bottom of them. Now a descent the character doesn't outlive by 200 turns earns nothing.

plus `danger` (the chance of losing a quarter of max HP within 30 turns) and a `prior` (which action the
recorded player took here). The default style is

    value = depth_end − died_soon

and an action replaces the rules of thumb's choice only when its value is 0.25 better. The other
components are predicted so they can be tried without retraining.

`--style depth_go=1 died_go=-2 margin=0.1` and so on change it for a run. `human=1` adds the prior's log-probability,
which only means something once the corpus has a good number of a person's games in it.

## The corpus: every session adds to it

A step log is `steps.jsonl`: one line per choice (observation, what was possible, what the rules of thumb
would do, what was done, who chose), and one end line per game. They come from three places:

1. **Self-play** (`ladder brain selfplay`, and the self-play and evaluation games inside `iterate`), under
   `runs/brain/<name>/g<seed>/`. Each game also keeps its full webtiles protocol, gzipped, so features can
   be rebuilt from scratch later.
2. **The cockpit and `spike` with `--brain`**: the brain plays as `ladderbot` in front of you, and its
   steps land in that run's directory.
3. **Your own games**: the cockpit's recording proxy writes `play<n>.jsonl` (the game's messages and your
   keys). `humanplay.py` replays one through `GameState`, maps your keys to the brain's actions (`o` is
   explore, Tab or walking into a monster is fight, `5` is rest, `q`/`r` by which stack shrank, and so on)
   and writes a step log with `"source": "human"`. `iterate` and `corpus` convert new recordings on
   their own.

`ladder brain corpus` reads every `steps.jsonl` under `runs/`, labels each step from what happened later
in its game, and writes `runs/brain/corpus.npz`. One game in five is held out for validation, chosen by a
hash of where it came from, so validation is always on unseen games.

## The loop

```bash
uv sync --group train                         # torch, for training only
uv run ladder brain iterate --rounds 3        # each round: 60 self-play games, 100 forked moments, retrain, 30 evaluation games
```

One round:

1. **Self-play** with the champion (`models/brain.json`; the rules of thumb if there is none yet), with
   20% random choices, on fresh seeds.
1b. **Forks**: replay 100 moments of those games (`--fork-points`) and try up to three other actions at each.
2. **Corpus**: rebuild from everything under `runs/`, including earlier rounds and your own games.
   Games on evaluation dungeons are left out.
3. **Train** a candidate, `models/iter<n>.json`, and check numpy against torch.
4. **Evaluate** candidate and champion on the same fixed seeds (500000 and up, never used for self-play),
   with no random choices. A model's evaluation is kept and reused.
5. **Promote** the candidate to `models/brain.json` if its mean depth is higher (fewer deaths breaks a tie).
   `models/brain.ledger.json` records every round.

The parts on their own:

```bash
uv run ladder brain selfplay --games 40 --seed 100 --epsilon 0.2 [--model models/brain.json]
uv run ladder brain forks runs/brain/iter0 --points 300   # replay games to a choice, try the other actions
uv run ladder brain human                     # convert new recordings of your own games
uv run ladder brain corpus                    # runs/**/steps.jsonl -> runs/brain/corpus.npz
uv run ladder brain train --model-out models/candidate.json
uv run ladder brain eval baseline models/brain.json models/candidate.json --games 60
uv run ladder spike --brain --games 3         # watch it play as ladderbot (also: ladder cockpit --brain)
```

Self-play uses its own accounts, `ladderbrain1` to `ladderbrain<workers>`, so it never touches
`ladderbot`'s save. Six at once play a game every three seconds or so on an M-series Mac.

## Changing the contract

`FEATURE_VERSION`, the action list and the component list are written into every corpus and model.
`TrainedNet` refuses a model made for another contract. After adding a feature or an action: bump
`FEATURE_VERSION`, run `ladder brain corpus` (old step logs are re-encoded from their observation dicts,
so no game is lost; a new field is simply missing from old observations) and train again.

A version 4 model still loads: version 5 keeps version 4's numbers at the front of each vector, and
`TrainedNet` gives such a model only that front part. So the champion `iter2` keeps playing under version
5's code. (The comparison below was played before this was added, with the champion run from the code it
was trained with.) Models older than version 4 are refused.

Fields that need the game state, not only the observation dict, can be rebuilt for old steps:

```bash
uv run ladder brain reobserve --sidecars runs/brain/obsx      # protocol logs -> steps.x.jsonl per step log
uv run ladder brain corpus --sidecars runs/brain/obsx         # folds them in
```

`reobserve` replays every `game<seed>.protocol.jsonl.gz` through `GameState` and lines each logged step up
with its moment in the log (the `_ladder` key notes, or `input_mode` messages in round 0's logs), checking
that turn, HP, depth and every monster's position agree and that `observe` there reproduces the logged
fields. Over the whole corpus (1,495,092 steps, replayed fork steps included, 3 minutes on 6 cores):
**99.92% of the steps that have a protocol log are placed** (99.66% exactly), 96.66% of all steps; 48,816
have no protocol log (round 0's lost ones, some forks, your games). Of the 810,581 training rows, 786,235
have sight fields and 24,346 (3.0%) are marked missing. Evaluation dungeons and qw runs are never read.

## Files

| | |
| --- | --- |
| `src/ladder/brain/features.py` | actions, components, `observe` (state to dict) and `encode` (dict to numbers) |
| `src/ladder/brain/monsters.py`, `monsters-0.34.json` | the shipped monster table and the name lookup |
| `src/ladder/brain/reobserve.py` | rebuilds `sight` fields for old step logs from their protocol logs |
| `src/ladder/brain/net.py` | model file format, numpy forward pass, parity check |
| `src/ladder/brain/gear.py` | ranks weapons and armour, and says which piece in the pack is better than the one in use |
| `src/ladder/brain/policy.py` | `available`, `baseline`, `baseline_wiki`, `Style`, and `BrainTiers`, which sits in Reflex where `StubTiers` did |
| `docs/wiki-strategy.md` | the DCSS wiki's strategy guides, sorted by what the brain would need to use each piece of advice |
| `src/ladder/brain/steplog.py` | `steps.jsonl` writer shared by self-play, `spike` and the cockpit |
| `src/ladder/brain/selfplay.py` | parallel games, one process each, with a watchdog for hung reads |
| `src/ladder/brain/forks.py` | picks the moments to fork and writes the replay scripts |
| `src/ladder/brain/humanplay.py` | a person's recorded game to a step log |
| `src/ladder/brain/corpus.py` | step logs to labelled training rows |
| `src/ladder/brain/train.py` | PyTorch training and export |
| `src/ladder/brain/cli.py` | `ladder brain ...`, including the iterate loop |
| `models/brain.json`, `models/brain.ledger.json` | the champion (none yet) and the record of every `iterate` round |
| `models/iter<n>.json` | each round's candidate, with its parity vectors |
| `models/v2/` | the first three candidates, from before the equipment actions; today's code refuses to load them |

## What it found on the way

Running whole games unattended turned up things the stub's short games never reached. All are fixed in
this branch:

- DCSS's autofight refuses to attack below 50% HP ("You are too injured to fight recklessly!"), so the bot
  stood still and died. The rc now sets `autofight_stop = 0`.
- `q`/`r` plus a letter went through `act()` as one burst; the menu passing by was taken for a prompt and
  left Reflex one reply behind the game. Item use now waits for the menu, then sends the letter.
- A scroll that asks for a target (blinking) or an item waited forever. It is cancelled, with "yes" to
  "really abort and waste the scroll?".
- After a scroll of poison the only move left was into the gas, and "Really walk into that cloud?" was
  answered no, forever. An action that uses no game time twice in a row is now set aside for 50 turns.
- A monster behind glass or across water made explore and "go to the stairs" take turns undoing each other.
- A berserk character can't enter a shop, and Reflex waited for the shop menu that never opened.
- A killed game's save reopens the prompt it hung on, and a seeded start waits for a seed menu that
  doesn't come while a save exists.
- A level-up in the same turn as a potion put the stat prompt where a scroll's prompt was expected, and it
  takes neither Esc nor Y.
- Webtiles corrupts accounts registered at the same instant: `ladderbrain7` and `ladderbrain9` have a
  two-character password hash on the server and can't log in. Self-play now registers one at a time and
  leaves a slot out if its account won't open. (To get those two back: delete their rows from
  `/data/webserver/passwd.db3` in the container, or `docker compose down -v`.)

Found once equipment made games longer (the second commit):

- **The cause of most "hung" games.** Explore sometimes ends with two "ready for a command" signals.
  `act()` returned on the first, and the second was then read as the reply to the *next* key. Usually that
  only meant seeing a result one step late. When the next key opened a menu (`q`, `r`, `a`, `W`), the menu
  arrived unseen, the item's letter was never sent, and the read (dcss-api has none with a timeout) never
  came back. `Connection.catch_up()` now reads everything already sent before a menu key, by asking the
  server an unrelated question and reading up to its answer.
- Explore walks into a shop it has found and opens it; nothing could read that menu either. The brain now
  presses a macro key (`ladder_fence_shops` in the rc) that excludes shops in view from travel, and never
  visits them, since it has no action that buys.
- "Keep equipping yourself?" (a monster appeared part-way through putting armour on) is a yes/no menu
  that ignores Esc.
- dcss-api's `quit_game` answers "yes", but DCSS asks an established character to type "quit". A game that
  ended without a death could never be cleared from its account, and every later game given to that
  account hung at the start. One account had been stuck that way since the first round.
  `Connection.quit_game()` now reads the prompt.
- Corrosion shows as a minus on the weapon in hand only, so the spare looked better, was wielded, and
  then showed the minus itself: a swap every turn.
- A killed game's recording was missing its last lines (file buffering), which hid all of the above. The
  recording is now written line by line, and includes the keys sent (`{"msg": "_ladder", ...}` lines).

With these, 108 games in a row at the rules of thumb finished with none lost. With 20% random choices
about 1 in 80 still hangs; those have not been looked at. Two rarer dead ends remain, both ending the game
early rather than hanging it: a level whose stairs can't be reached, and "You can't go down here!" on a
staircase.

## Next

In the order I would take them:

1. **Forks played to the end, on the model's own games, in volume.** This is the part of s1's method
   still missing at scale: s1 learned from 300,000 forked moments, this from 982, and most of those were
   cut off 1,500 turns after the fork, which the new `depth_end` label can't use properly. Forks now play
   to the end by default. An overnight run (`iterate --rounds 8 --fork-points 400`) is about 6,000.
   *After rounds 3 and 4: 2,550 forks are in the corpus and the last 970 changed nothing. Do 2 and 3
   first, then come back to volume.*
2. **More to do in a fight.** Deaths are still mostly at D:5–8 to packs and uniques. Trog's Hand and
   Brothers in Arms, throwing what it picks up, stepping back into a corridor, and going upstairs earlier
   are each an action in `features.ACTIONS`, a line in `available`, and keys in `perform`.
   *The wiki's guides rank these (`docs/wiki-strategy.md`, section 2): back into a corridor first,
   then walk to the stairs up before the fight, then Trog's Hand and Brothers in Arms, which only work
   before a rage.*
3. **More to see.** A local map patch, monster HP, what is wielded and worn, skills. The model can't
   tell a character who is ready for the next floor from one who isn't, except by level and AC.
   *From the wiki (`docs/wiki-strategy.md`, section 3): a flag per monster for what kind of threat it
   is (hits from range, one-hit killer, fast, paralyses, blinks), since each wants a different answer
   and 24 name buckets can't tell them apart; and weapon skill, so `gear.py` stops taking a great mace
   it swings too slowly.*
   *Done in part as version 5 (2026-11-14): the monster table, monster HP and behaviour, the weapon,
   map summaries. It predicts death a little better and plays worse (0.7 to 0.8 depths, on two blocks of
   200 dungeons), because it dives. Not done: worn armour (only the brain's own belief exists), skills (not
   sent), the map patch. Inputs are not the bottleneck while the labels can't tell actions apart.*
4. **Promote on more than 60 dungeons.** Differences under 0.3 depths can't be seen with 60; the same
   baseline replayed varies by 0.1. 200 evaluation dungeons would take about 15 minutes per model.
5. **The remaining dead ends**: games that hang (1 in 20 with random choices in round 4, 1 in 40
   without), unreachable stairs,
   "You can't go down here!".
6. **Answer the prompts.** Identify and acquirement scrolls are cancelled and wasted today.
   Designed, with using known scrolls and potions, in `docs/brain-consumables.md`.
7. **Answer the decision cards.** Stairs, uniques and altars are the same kind of choice; the brain could
   be the recommendation Authority shows, and the player's answers would be labels.
8. **Learn from more people.** Your recordings are in the loop: 1,153 rows from 17 files, one of them a
   game to D:10. Three things would make them count: map walking by hand (toward the stairs is `descend`,
   toward unseen floor is `explore`) so the prior stops under-counting both; join a take-over to the run
   that continued the same character, so its rows know how the game ended; and turn Reflex's own turns in
   a shared game into rows from the spectator protocol. Other servers' games are public as ttyrecs and spectator streams, which have states but not keys.
9. **Other characters.** Everything so far is a Minotaur Berserker. Species and background would need to be
   inputs, and the action list would need spells; `gear.py` ranks only maces and flails.
