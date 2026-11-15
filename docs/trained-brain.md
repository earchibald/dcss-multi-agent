# The trained brain

A small neural network, trained on this machine from the ladder's own games, that chooses Reflex's
next action. It is not a language model and makes no API calls: it reads numbers about the moment and
runs in numpy in well under a millisecond. It is the same idea as the trained brain in
`~/Code/s1-battle`, moved to a game that can't be forked.

## Where it stands

**2026-11-14, evening:** the rule `v5-seen` seemed to have found (read teleportation when spent after a rage,
monsters in view) is in the rules of thumb as an opt-in switch, `--style teleport=1`, and does not beat them:
+0.10 on the tuning blocks, −0.01 [−0.16, +0.13] on two fresh ones (pre-registered). It stays off. Still
nothing beats the rules of thumb (section "The teleport rule on its own", below).

**2026-11-14, later:** still no model beats the rules of thumb. Averaging 5 training seeds (H1) steadies the
estimate but keeps the bias all seeds share, and plays like an average seed (−0.32 on block A). 2,069
forks that compare exploring on with going down from the same state (H2) show the two are worth the same
on average and that no model can tell the moments apart; retraining on them made the estimate *more*
pro-descend. The retrained ensemble `v5-forks3` was level on block A and was pre-registered: on two fresh
blocks it is +0.05 [−0.28, +0.38] against the rules of thumb. Two measurement bugs were found and fixed on
the way: 1–7% of every evaluation's games resumed an older game's save, and fork regret's "moments" mixed in
other states (section "Ensembles, explore-or-descend forks", below).

**2026-11-14:** `iter2` is still the champion. On 200 evaluation dungeons it averages 5.51 (500000–500199)
and 5.48 (530000–530199). The version 5 inputs (below) did not beat it. On 400 dungeons it is level with the
rules of thumb (−0.14 [−0.44, +0.16]). All six retrained models (3 training seeds each of the version 5 and
version 4 inputs) are behind it on block A, and the seed alone moves a model by up to 0.8 depths. `v5-seen`
at `margin=1.0` beats it on a fresh block (+0.41 [+0.00, +0.84]), but only by being the rules of thumb
(follow-up, below).

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
to see the spread in games, and add forks (the rows that compare actions) before adding inputs. *Done below.*

#### Follow-up: noise, margins, training seeds and a fresh block (2026-11-14)

All games with HEAD's code (which now plays version 4 models), no random choices, 7 at once (ladderbrain7
is left out), runs in `runs/brain/v5/games/`. Paired by dungeon over games both finished, 95% bootstrap.
**Block A (500000–500199) is now a tuning block**: margins and seeds were chosen on it. Only block C
(540000–540199, never played before) counts as evidence.

**The noise floor is small.** Games are nearly repeatable: the same model replayed gives the same game on
97% of dungeons, and the old code gives the same games as HEAD's.

| champion `iter2`, block A | finished (hung) | mean depth | died | turns | vs `A-brain-head` | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `A-brain-head` (HEAD's code) | 199 (1) | 5.51 | 192 | 1843 | | | |
| `A-brain-head2` (the same again) | 200 (0) | 5.50 | 193 | 1830 | +0.02 | [−0.03, +0.06] | 3 / 194 / 2 (194 of 200 games identical) |
| `eval-brain` (the previous commit's code) | 199 (1) | 5.51 | 193 | 1817 | +0.00 | [−0.09, +0.08] | 5 / 191 / 3 (190 identical) |

A game that does diverge diverges a lot (one went from D:2 to D:7), so the noise is a few games, not a
small shift in each. Any paired difference wider than about ±0.1 is the models, not the replay.

**Margins (block A).** A larger margin removes the loss, but only by switching the model off.

| model | margin | finished (hung) | mean depth | died | mean XL | turns | leaves the rules | `descend` share | vs champion at 0.25 | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| champion `iter2` | 0.25 | 199 (1) | 5.51 | 192 | 5.64 | 1843 | 15.6% | 29.9% | | | |
| champion `iter2` | 0.6 | 197 (3) | 5.57 | 181 | 5.77 | 2167 | 1.3% | 29.7% | +0.03 | [−0.33, +0.38] | 69 / 65 / 62 |
| `v5-seen` | 0.25 | 199 (1) | 4.84 | 188 | 4.70 | 1294 | 34.2% | 38.0% | −0.66 | [−1.10, −0.22] | 59 / 43 / 96 |
| `v5-seen` | 0.4 | 196 (4) | 5.14 | 183 | 5.29 | 1919 | 17.7% | 35.3% | −0.36 | [−0.76, +0.04] | 61 / 46 / 88 |
| `v5-seen` | 0.6 | 198 (2) | 5.58 | 179 | 5.74 | 2211 | 2.3% | 32.8% | +0.07 | [−0.37, +0.49] | 73 / 52 / 72 |
| `v5-seen` | 1.0 | 197 (3) | 5.68 | 178 | 5.87 | 2276 | 0.4% | 30.9% | +0.14 | [−0.27, +0.55] | 71 / 61 / 64 |
| rules of thumb (`baseline`) | | 197 (3) | 5.54 | 180 | 5.72 | 2178 | 0 | 30.8% | +0.03 | [−0.38, +0.43] | 69 / 67 / 61 |

Both at 0.6, `v5-seen` − champion is +0.03 [−0.37, +0.42]. At 0.6 and above every model is the rules of
thumb with a few changes, and **the champion at its default margin is itself only level with the rules of
thumb on 200 dungeons** (−0.03 [−0.43, +0.38]).

**Training seeds (block A, margin 0.25).** Training is deterministic: a retrain of `s12` seed 1 gave the
same weights byte for byte, so the gate's seeds 1 and 2 are the "2 more seeds" (`models/v5-s12-s1.json`,
`v5-s12-s2`, `v5-v4control-s1`, `v5-v4control-s2`, each with its parity file).

| recipe | seed | mean depth | died | mean XL | turns | leaves the rules | commonest change | vs champion | 95% interval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `s12` (version 5) | 0 (`v5-seen`) | 4.84 | 188 | 4.70 | 1294 | 34.2% | explore → descend | −0.66 | [−1.10, −0.22] |
| `s12` | 1 | 4.66 | 194 | 4.40 | 926 | 25.5% | read_unknown → descend | −0.83 | [−1.21, −0.45] |
| `s12` | 2 | 5.14 | 195 | 5.08 | 1640 | 36.5% | read_unknown → descend | −0.35 | [−0.71, +0.02] |
| control (version 4 inputs) | 0 (`v5-v4control`) | 5.26 | 180 | 5.40 | 2019 | 20.3% | fight → descend | −0.23 | [−0.64, +0.18] |
| control | 1 | 5.22 | 192 | 4.68 | 935 | 21.1% | explore → descend | −0.25 | [−0.69, +0.17] |
| control | 2 | 4.50 | 193 | 4.08 | 1228 | 59.0% | read_unknown → descend | −1.01 | [−1.39, −0.64] |

Mean over seeds: `s12` −0.61 (range 0.48), control −0.50 (range 0.78). **The seed matters more than the
inputs**: the spread between seeds of one recipe is wider than the gap between recipes, every one of the six
models is behind the champion, and each dives in its own way. What they share is the corpus (today's
rows, 21% from earlier models), not the version 5 inputs.

**The fresh block C (540000–540199).** The setting picked on block A before block C was played: `v5-seen` at
`margin=1.0` (0.6 as a second).

| block C | finished (hung) | mean depth | died | mean XL | turns | leaves the rules | vs champion | 95% interval | deeper / same / shallower | vs rules of thumb | 95% interval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| champion `iter2` | 194 (6) | 5.12 | 186 | 5.25 | 1638 | 16.1% | | | | −0.26 | [−0.70, +0.17] |
| `v5-seen`, `margin=1.0` | 194 (6) | 5.52 | 176 | 5.78 | 2113 | 0.4% | **+0.41** | [+0.00, +0.84] | 79 / 51 / 58 | +0.19 | [−0.04, +0.41] |
| `v5-seen`, `margin=0.6` | 193 (7) | 5.27 | 183 | 5.56 | 2022 | 4.3% | +0.20 | [−0.25, +0.66] | 66 / 53 / 68 | −0.14 | [−0.53, +0.25] |
| rules of thumb | 195 (5) | 5.36 | 176 | 5.66 | 2086 | 0 | +0.26 | [−0.17, +0.70] | 71 / 52 / 66 | | |

- On the fresh block `v5-seen` at `margin=1.0` comes out ahead of the champion, with the interval's lower
  end at zero. It does that by **being the rules of thumb**: it leaves them at 0.4% of choices (`wield` →
  `descend` at full HP, and `fight` → `read_teleport`), and the rules of thumb alone are +0.26 against the
  champion here. Against the rules of thumb it is +0.19 [−0.04, +0.41] (26 / 156 / 11), and +0.12 on block
  A; pooled over A and C it is +0.15 [−0.02, +0.32]. That is a lead to follow, not a result.
- The champion is behind the rules of thumb on block C and level on block A: −0.14 [−0.44, +0.16] pooled.
  **No model has yet been shown better than the rules of thumb on 400 dungeons.** Its 2026-11-09 lead
  (5.85 against 5.58) was on 60.

**Where `v5-seen`'s games end (block A, 198 dungeons both finished; block B says the same).**

| | champion | `v5-seen` |
| --- | --- | --- |
| mean depth, deaths | 5.52, 192 | 4.86, 187 |
| died on D:1–3 (block B) | 33 (46) | 62 (69) |
| at death: depth, XL, median turn | 5.55, 5.73, 1700 | 4.95, 4.81, 1145 |
| reached D:4: games, XL, turn | 156, 3.87, 1277 | 126, 3.39, 1003 |
| reached D:6: games, XL, turn | 98, 5.93, 1912 | 78, 5.40, 1444 |
| last 10 choices before death | fight 53%, descend 22%, flee_up 8% | fight 66%, descend 12%, flee_up 3% |
| most often in view at death | wight 12, gnoll 9, ogre 9 | gnoll 20, yak 8, wight 7 |
| both died: `v5-seen` died shallower / same floor / deeper | | 88 / 38 / 57 |

It reaches each floor about a quarter sooner and half a level lower, dies earlier, shallower and lower
(gnolls on D:2–4 more than anything), and flees up less. At its 10,208 explore → descend overrides (in 578
of 748 floor visits) its `depth_end` says descend is worth **+0.32** more than exploring, while
`died_soon` is +0.02 *against* descending (worse for descend at 97% of them). So the dive comes from
`depth_end`, not from the sharper death prediction. The champion, scoring the same moments, puts the gap at
+0.05 and would have overridden 2% of them. Once it has started for the stairs it keeps going (89% of the
next choices), so most of those 10,208 are one decision repeated.

The gap is a shift that depends on the seed. Scored on the champion's own games (8,995 moments where the
rules said explore and the stairs were known), each model's preference for descend over explore:

| model | `depth_end` gap | `died_soon` gap | value gap | above 0.25 | above 0.4 | above 0.6 |
| --- | --- | --- | --- | --- | --- | --- |
| champion `iter2` | +0.08 | +0.01 | +0.07 | 8% | 1% | 0% |
| `s12` seeds 0 / 1 / 2 | +0.28 / +0.16 / +0.04 | +0.02 / +0.00 / +0.01 | +0.26 / +0.16 / +0.03 | 49% / 21% / 3% | 8% / 4% / 0% | 1% / 0% / 0% |
| control seeds 0 / 1 / 2 | +0.13 / +0.28 / +0.10 | +0.04 / −0.01 / −0.00 | +0.10 / +0.29 / +0.10 | 15% / 60% / 10% | 3% / 15% / 1% | 0% / 2% / 0% |

`v5-seen`'s average preference sits right at the 0.25 margin, so half the time it crosses it. That
explains both the dive and why 0.6 stops it. This number does not predict a model's score, though:
`s12` seed 2 and control seed 2 hardly prefer descend here and still lose, by overriding `read_unknown`
over and over in their own games. A model that skips a scroll keeps the scroll, so the rules suggest it again
at the next choice, and the same override is counted many times. The dive is a closed loop: each seed has a
different bias of about ±0.15 depths, about the size of the margin, and play then amplifies it.
**Verified**: the numbers above, and that the recomputed values match the logged ones. **Inferred**: that
the seed-dependent offset is how `depth_end` handles actions the data seldom compares (descend vs explore
from the same state), and that the loop through the model's own states amplifies it.

Throughput: about 28 s per game, 6 at once (240 games in 11 minutes); a fork costs about 18 s of one
worker, since it replays the game to the fork and then plays on. Training takes under a minute. A model
is 108 KB (39k weights, float16) and matches torch to 5 decimal places.

#### Ensembles, explore-or-descend forks, and two bugs in the measurements (2026-11-14)

Two hypotheses about the dive, cheapest first. H1: averaging training seeds removes the per-seed bias. H2:
`depth_end` is biased because the rows seldom compare explore and descend from the same state, so forks
that do will fix it. Scripts in the job's `brain-v5c/` scratch directory; runs under `runs/brain/v5/`.

**Two bugs, both now fixed, that touched every number above.**

- *Stale saves.* A game that ends without a death (mostly the 1,500-choice limit at "You can't go down
  here!") was not always quit: Ctrl-Q's prompt was hidden by a late "ready" signal, so `quit_game` returned
  early. The account's next seeded start then **resumed the old game**, recorded under the new seed. 1–7% of
  the games of every run in `runs/brain/v5/games/` started mid-game (the rules of thumb 11–13 of 200).
  `quit_game` now catches up first, and `selfplay` checks the turn at the start, quits a resumed game and
  starts again (`StaleSave`). From here on paired numbers leave such dungeons out on both sides ("clean");
  it moves earlier pairs by up to 0.2 depths.
- *Fork regret's moments were not one moment.* A fork's rows after its forked step kept the group of the
  recorded game's step with the same number, a different state. They are now in no group
  (`corpus.build`). Clean, random choice loses 1.10 at the 238 old held-out moments, not 1.46, and **no
  model is clearly better than random there** (below). The fork-regret columns earlier in this file are
  the contaminated ones.

| block | pair (clean) | before | clean |
| --- | --- | --- | --- |
| A | champion − rules of thumb | −0.03 [−0.43, +0.38] | +0.15 [−0.26, +0.57] |
| C | champion − rules of thumb | −0.26 [−0.70, +0.17] | −0.40 [−0.87, +0.06] |
| A | `v5-seen` `margin=1.0` − rules | +0.12 [−0.14, +0.37] | +0.15 [−0.07, +0.37] |
| C | `v5-seen` `margin=1.0` − rules | +0.19 [−0.04, +0.41] | **+0.27 [+0.08, +0.47]** |

**H1: an ensemble.** `net.Ensemble` averages several models' outputs behind the same `forward()` and
`counts` (an action counts as seen as often as the least-trained member saw it); `net.load_model` takes a
model, a manifest (`models/v5-ens5.json`: the `s12` recipe at seeds 0–4) or files joined by commas, so
`--model` and `--brain` take any of them. Seeds 3 and 4 were already trained by the gate
(`models/v5-s12-s3.json`, `-s4`); seeds 5–9 were trained for a second, disjoint ensemble.

Offline, on the champion's 8,995 block-A moments where the rules said explore and the stairs were known:

| model | value gap (descend − explore) | above 0.25 | above 0.4 |
| --- | --- | --- | --- |
| champion `iter2` | +0.07 | 8% | 1% |
| `s12` seeds 0–9, one at a time | +0.16 mean, sd 0.10 (+0.03 to +0.30) | 3–75% | 0–13% |
| ensemble of seeds 0–4 (`v5-ens5`) | +0.17 | 18% | 2% |
| ensemble of seeds 5–9 | +0.15 | 11% | 0% |

- Averaging does what it can: two disjoint 5-seed ensembles differ by 0.02 where single seeds spread by
  0.10, and fewer moments cross the margin. It **can't remove the part all seeds share**: the ensemble's
  gap is the seeds' mean, +0.16, twice the champion's.
- Fork regret (clean groups, 679 held-out moments): `v5-ens5` 1.28, its members 1.20–1.32, seeds 5–9
  averaged 1.25, all ten 1.23, champion 1.29, random 1.34. Ensemble − mean member: inside ±0.1.

| block A (clean) | finished (hung) | mean depth | died | died on D:1–3 | XL | turns | leaves the rules | `descend` share | vs rules of thumb | vs champion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules of thumb | 197 (3) | 5.45 | 180 | 35 | 5.72 | 2178 | 0 | 30.8% | | −0.15 [−0.57, +0.26] |
| champion `iter2` | 199 (1) | 5.52 | 192 | 31 | 5.64 | 1843 | 15.6% | 29.9% | +0.15 [−0.26, +0.57] | |
| `s12` seed 0 / 1 / 2 | | 4.82 / 4.67 / 5.14 | | 62 / 62 / 41 | | 1294 / 926 / 1640 | 34% / 26% / 37% | | −0.58 / −0.82 / −0.28 | −0.70 / −0.81 / −0.36 |
| `v5-ens5` | 200 (0) | 5.08 | 196 | 58 | 4.82 | 1249 | 28.4% | 31.8% | −0.32 [−0.80, +0.15] | −0.43 [−0.89, +0.03] |

**H1 fails in games**: the ensemble plays like an average seed (−0.32 against the rules of thumb, −0.43
against the champion), dies on D:1–3 as often as the worst seeds, and its commonest changes are still
skipping a potion or a scroll for the stairs (`quaff_unknown` → `descend` 6,857 times, `read_unknown` → 3,784).

**H2: forks that compare explore with descend.** `ladder brain forks --kind stairs` picks moments with
nothing in view where both are possible and the rules chose one (at most one per visit to a level), and
forks each **both ways**, played on by the rules of thumb. A `descend` is one step toward the stairs, after
which the rules would explore again, so these forks commit (`BrainTiers(commit=True)`): on that level the
forked action replaces the other wherever the rules would choose it. Only rules-said-explore moments
exist: once a level is explored, `explore` is not possible. Moments come from rounds 1–4's self-play
(training seeds only); round 0's games diverge on replay with today's code (24 of 32 in a pilot).

| forks | |
| --- | --- |
| planned (2,400 moments + a 60-moment pilot) | 4,920 |
| played / lost (hung, errors, stale) / left the recorded game | 4,768 / 152 / 486 |
| moments with both branches in the corpus | **2,069** (403 held out by dungeon) |
| wall time, 7 workers | 4 h 4 min (3.0 s per fork; about 21 s of one worker) |
| corpus | 2,233,423 rows (was 810,581): 6,547 forked rows, 79,263 committed steps, the rest the forks' play to the end |

What happened each way (the corpus's own labels, default style, 95% bootstrap):

| moments | true value gap, descend − explore | `depth_end` gap | `died_soon` gap | descend better / same / worse |
| --- | --- | --- | --- | --- |
| training (1,666) | +0.00 [−0.13, +0.14] | +0.01 | +0.01 | 550 / 537 / 579 |
| held out (403) | +0.02 [−0.27, +0.30] | +0.03 | +0.02 | 145 / 113 / 145 |

**Going down now is worth the same as exploring on, on average**, and the outcome of one pair is mostly
noise (a standard deviation of about 2.6 depths). Retrained with them, the `s12` recipe at 3 seeds:
`v5-forks` (the default rebuild) and `v5-pairs` (the version 5 corpus plus only the 4,376 forked rows,
without the forks' play to the end). Offline:

| model | gap on block-A moments | above 0.25 | held-out pairs: predicted gap | corr(pred, true) | picks the better branch | fork regret (all 679 / old 238 / stairs 441) |
| --- | --- | --- | --- | --- | --- | --- |
| random choice | | | | | | 1.34 / 1.10 / 1.47 |
| champion `iter2` | +0.07 | 8% | +0.04 | −0.03 | 47% | 1.29 / 1.24 / 1.32 |
| `v5-ens5` | +0.17 | 18% | +0.14 | −0.05 | 49% | 1.28 / 1.23 / 1.30 |
| `v5-forks` seeds 0 / 1 / 2 | +0.11 / +0.39 / +0.38 | 5 / 93 / 91% | +0.08 / +0.38 / +0.39 | ±0.01 | 49–50% | 1.28 / 1.23 / 1.27 (all) |
| `v5-forks3` (ensemble) | **+0.29** | 74% | +0.28 | −0.01 | 50% | 1.27 / 1.27 / 1.27 |
| `v5-pairs` seeds 0 / 1 / 2 | +0.22 / +0.39 / +0.41 | 33 / 91 / 98% | +0.20 (seed 0) | | | 1.25 / 1.14 / 1.18 (all) |
| `v5-pairs3` (ensemble) | +0.34 | 91% | +0.33 | −0.03 | 50% | 1.18 / 1.04 / 1.26 |
| pairs only, fork rows weighted 200 (×3 seeds) | −0.26 / +0.15 / +0.37 | | −0.30 / +0.11 / +0.39 | | 49–50% | |

- **The forks did not fix the estimate; they moved it the wrong way.** At the very states of the training
  pairs (true gap −0.05) `v5-pairs3` predicts +0.33. All models under-predict `depth_end` there (true 3.33
  either way, predicted 2.5–2.9), and the new rows lift the descend output more than explore's, which its
  128k ordinary rows hold down. Weighting the pairs 10× more scatters the seeds (−0.26 to +0.37) instead.
- **No model can tell which moments favour the stairs**: correlation with the true gap is −0.06 to +0.05
  and every model picks the better branch half the time. On the old held-out moments only `v5-pairs3`
  (1.04) is a little better than random (1.10); `v5-pairs3` − `v5-ens5` over all 679 is −0.10
  [−0.17, −0.03], mostly from two seeds.

| block A (clean) | finished (hung) | mean depth | died | died on D:1–3 | XL | turns | leaves the rules | `descend` share | explore → descend | vs rules of thumb | vs champion |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `v5-forks3` | 199 (1) | 5.59 | 193 | 41 | 5.06 | 919 | 22.6% | 24.9% | 4,987 | +0.17 [−0.31, +0.66] | +0.04 [−0.39, +0.45] |

In games `v5-forks3` dives harder than anything so far (the same depth in 42% of the rules' turns, a level
lower) and still comes out level with the rules of thumb and the champion on block A. With the offline
table saying its estimate is the most biased of all, read that as a block-A draw (the interval is ±0.5),
not as the forks working. It is the only H1/H2 configuration at least level on block A, so it is the one
confirmed below.

**Pre-registered (written before any game on block D):** configuration `models/v5-forks3.json` at the
default style (`margin=0.25`), no random choices, against the rules of thumb (`baseline`), paired by dungeon
over games both finished and neither resumed a stale save, 95% bootstrap. Block D = 550000–550199. Block E
= 560000–560199 is played only if D's difference is above zero, and the claim "beats the rules of thumb"
needs the pooled D+E interval above zero.

| fresh blocks (clean) | finished (hung) | mean depth | died | died on D:1–3 | XL | turns | leaves the rules | `descend` share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D rules of thumb | 197 (3) | 5.27 | 184 | 52 | 5.51 | 1992 | 0 | 30.3% |
| D `v5-forks3` | 198 (2) | 5.32 | 192 | 41 | 4.77 | 865 | 28.5% | 29.3% |
| E rules of thumb | 197 (3) | 5.46 | 186 | 39 | 5.76 | 2068 | 0 | 24.6% |
| E `v5-forks3` | 200 (0) | 5.52 | 197 | 44 | 4.84 | 903 | 25.6% | 25.8% |

| `v5-forks3` − rules of thumb | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| D | 195 | +0.05 | [−0.43, +0.51] | 78 / 49 / 68 |
| E | 197 | +0.05 | [−0.43, +0.53] | 75 / 53 / 69 |
| **D + E (the pre-registered test)** | 392 | **+0.05** | **[−0.28, +0.38]** | 153 / 102 / 137 |
| A + D + E | 577 | +0.09 | [−0.19, +0.37] | 228 / 142 / 207 |

**Not confirmed: `v5-forks3` is level with the rules of thumb, not better.** It reaches the same depth in
less than half the turns at a level lower, so it plays a different game to the same place. No game on D or
E resumed a stale save (the fix holds live; before it, 1–7% of games did).

**The one lead with an interval above zero is not the model's estimate but one rule it found.** `v5-seen`
at `margin=1.0`, pooled over A and C (clean): +0.21 [+0.06, +0.35] (356 dungeons, 40 / 301 / 15; A is the
block its margin was tuned on). Its gain is almost all one override, `fight` → `read_teleport` (126 times on
A and C), in the games where it happens: +0.55 per game on A (20 games), +1.09 on C (22); `wield` →
`descend` is neutral (−0.36, +0.36). At those moments the character is at full HP (median), 3 hostiles in
view, D:7 (median), and in 64 of 126 just out of a rage (`-Berserk` with `Slow`). That is a rule of thumb
the rules lack: *exhausted after a rage, with monsters in view, read teleportation*.

- **Verified**: every number in these tables; that the fork pairs share their state (identical inputs at
  99.8% of pairs); the stale saves (protocol logs show the next game resuming the old one's turn) and that
  none happen with the fix; that the ensemble's outputs are the mean of its members' (tests).
- **Inferred**: why the forks raise the descend estimate (explore's output held down by its many ordinary
  rows, all models under-predicting `depth_end` at those states); that `v5-forks3`'s level result is luck
  of the blocks rather than the forks (offline it is the most biased model); that the teleport rule is the
  cause of `v5-seen`'s lead (an attribution by game, not a test).

#### The teleport rule on its own (2026-11-14, evening)

**Not confirmed: the rule is level with the rules of thumb, not better.** "Spent after a rage, monsters in
view: read teleportation" (`--style teleport=1`) was +0.10 [−0.05, +0.24] on the tuning blocks A and C and
**−0.01 [−0.16, +0.13]** on the fresh blocks F and G (395 dungeons), the pre-registered test. A second rule
(also read it when outnumbered by something dangerous) took the tuning gain away and was not carried forward.
The switch stays off. The model's teleport lead was either luck of blocks A and C or depends on *which*
spent moments it picked, which a plain rule doesn't capture.

**What the model did (blocks A and C, `v5-seen` at `margin=1.0`).** 126 overrides to `read_teleport` in 81
games (108 from `fight`, 12 from `berserk`, the rest from `descend`, `quaff_heal`, `flee_up`). Grouped by the
statuses at the moment:

| at the override | A | C | HP (median, at full) | hostiles in view (median) | one of threat 2+ in view | games' depth vs rules |
| --- | --- | --- | --- | --- | --- | --- |
| spent after a rage (`-Berserk` and `Slow`) | 47 in 30 games | 32 in 28 | 100%, 57% | 3–4 | 90% | +0.76 (A, 25 games), +1.57 (C, 23) |
| `-Berserk`, no longer slowed | 4 | 4 | 100%, 88% | 3–4 | 100% | |
| not after a rage | 17 in 16 games | 22 in 17 | 100%, 85% | 3 | 95% | +1.67 (A, 12), +1.76 (C, 17) |

The model is choosy. A scroll could be read while spent at 602 moments on A and 505 on C (in 140 and 114
separate spells of exhaustion, in only about 45 games each, since few games ever identify the scroll), and it
read one at 8% of them: where it read, 4.1 hostiles were in view on average against 1.6–1.8 where it didn't,
and 84–96% had one of threat 2 or more against 55%. The not-after-a-rage overrides are mostly at full HP with
nothing within two squares and a threat-3 monster in view about half the time. No single clean condition
separates its picks from the rest; the two below are the plainest ones that cover most of them.

**The rules, as coded** (`policy.teleport_rule`, used by `policy.baseline`; switch `Style.teleport`, off by
default, `--style teleport=1`):

- `teleport=1`, *spent*: `-Berserk` and `Slow` both showing, a hostile in view, a known scroll of
  teleportation that can be read: read it. First in the fight order (after curing serious poison), before
  the healing potion.
- `teleport=2`, also *crowded*: 3 or more hostiles in view, one of them threat 2 or 3: read it, after the
  rage and the healing potion (so a rage still comes first wherever the rules would rage).
- Neither while `Tele` shows: a second scroll would cancel the teleport already coming.

**Tuning on blocks A and C** (rules of thumb replayed with HEAD's code, `A-rules-h` and `C-rules-h`; no stale
saves on either side; paired by dungeon, 95% bootstrap). Replay is exact here: every game in which the rule
never fired is the same game, so the whole difference comes from the ~45 games per block that read a scroll.

| arm | block | finished (hung) | mean depth | died | died on D:1–3 | scrolls read | games with a read | vs rules | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules of thumb | A | 197 (3) | 5.46 | 179 | 35 | 9 (fallbacks) | 5 | | | |
| `teleport=1` | A | 195 (5) | 5.53 | 177 | 34 | 80 | 47 | +0.09 | [−0.13, +0.33] | 19 / 163 / 13 |
| `teleport=2` | A | 196 (4) | 5.44 | 178 | 34 | 86 (29 crowded) | 48 | +0.03 | [−0.19, +0.24] | 19 / 161 / 15 |
| rules of thumb | C | 194 (6) | 5.36 | 173 | 44 | 0 | 0 | | | |
| `teleport=1` | C | 193 (7) | 5.44 | 172 | 41 | 63 | 42 | +0.10 | [−0.05, +0.26] | 14 / 170 / 9 |
| `teleport=2` | C | 192 (8) | 5.33 | 169 | 40 | 68 (26 crowded) | 46 | +0.00 | [−0.17, +0.17] | 14 / 162 / 16 |
| **`teleport=1`, A + C** | | | | | | | | **+0.10** | [−0.05, +0.24] | 33 / 333 / 22 |
| `teleport=2`, A + C | | | | | | | | +0.01 | [−0.13, +0.15] | 33 / 323 / 31 |

For scale, against the same replayed rules `v5-seen` at `margin=1.0` is +0.17 (A) and +0.26 (C), and
`teleport=1` − `v5-seen` is −0.10 (A) and −0.16 (C): the spent rule recovers about half of the model's lead.
Adding the crowded rule takes the gain away again.

**Pre-registered (written before any game on block F or G):** configuration: the rules of thumb with
`--style teleport=1`, no model, no random choices, against the plain rules of thumb (no model, default
style), both played with this working tree's code, 200 games per block from seeds 570000 (block F,
570000–570199) and 580000 (block G, 580000–580199), 8 workers. Both blocks are played whatever F shows.
Paired by dungeon over games both finished and neither resumed a stale save; 95% bootstrap over dungeons
(10,000 resamples, `arms.py`). **Pass: the pooled F + G interval's lower end is above zero.** Analysed once.

| fresh blocks | finished (hung) | mean depth | died | died on D:1–3 | XL | turns | scrolls read | games with a read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| F rules of thumb | 197 (3) | 5.62 | 186 | 36 | 5.89 | 2131 | 4 (fallbacks) | 3 |
| F `teleport=1` | 197 (3) | 5.63 | 187 | 35 | 5.96 | 2147 | 96 | 53 |
| G rules of thumb | 198 (2) | 5.49 | 181 | 37 | 5.77 | 2121 | 5 (fallbacks) | 1 |
| G `teleport=1` | 198 (2) | 5.45 | 180 | 40 | 5.72 | 2131 | 87 | 51 |

| `teleport=1` − rules of thumb | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| F | 197 | +0.02 | [−0.21, +0.23] | 21 / 159 / 17 |
| G | 198 | −0.04 | [−0.24, +0.14] | 19 / 161 / 18 |
| **F + G (the pre-registered test)** | 395 | **−0.01** | **[−0.16, +0.13]** | 40 / 320 / 35 |
| ... F + G, games where it read a scroll | 104 | +0.07 | [−0.43, +0.58] | 40 / 31 / 33 |
| A + C + F + G (descriptive; A and C were tuning) | 783 | +0.04 | [−0.06, +0.14] | 73 / 653 / 57 |

- **Fails the pass rule**: the pooled interval's lower end is −0.16. Neither fresh block shows the tuning
  blocks' +0.1. No stale save on any side of any of the eight runs.
- The rule fires in about a quarter of games (those that have identified the scroll and rage), roughly 1.8
  scrolls per such game; in the other games play is the same game exactly (2 of 291 on G diverged anyway,
  replay noise). Within the games it changes, it wins about as often as it loses (40 / 31 / 33), and dying
  on D:1–3 doesn't move.
- **Verified**: the counts and tables above; that the switch off leaves play as it was (the replayed rules
  give the same game as the earlier runs on 367 of 368 clean dungeons of A and C) and that the unit tests
  hold the old behaviour. **Inferred**: that the model's +0.21 on A and C came from choosing its moments
  (where it read, 4 hostiles in view, one dangerous) or from block luck; the plain rule reads at the first
  chance in every spell of exhaustion (80 scrolls on A against the model's 47 while spent), and recovers half
  the tuning lead and none of it fresh.
- Blocks F (570000–) and G (580000–) are now spent. Runs: `runs/brain/v5/games/{A,C}-rules-h`,
  `{A,C}-tele{1,2}`, `{F,G}-rules`, `{F,G}-tele1`; scripts in the job's `brain-v5d/` scratch directory.

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

`--style teleport=1` adds one rule (`policy.teleport_rule`): read a known scroll of teleportation when spent
after a rage (`-Berserk` and `Slow`) with monsters in view, not while a teleport is already coming.
`teleport=2` also reads it with 3 or more hostiles in view, one dangerous, where the rules wouldn't rage.
Both are off by default: neither beat the plain rules ("The teleport rule on its own", above).

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
uv run ladder brain forks runs/brain/iter4 --kind stairs --points 500   # explore vs descend, both ways, committed
uv run ladder brain human                     # convert new recordings of your own games
uv run ladder brain corpus                    # runs/**/steps.jsonl -> runs/brain/corpus.npz
uv run ladder brain train --model-out models/candidate.json
uv run ladder brain eval baseline models/brain.json models/candidate.json --games 60
uv run ladder brain selfplay --model models/v5-ens5.json ...   # an ensemble: a manifest, or a.json,b.json,c.json
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
| `src/ladder/brain/net.py` | model file format, numpy forward pass, parity check, `Ensemble` and `load_model` |
| `src/ladder/brain/gear.py` | ranks weapons and armour, and says which piece in the pack is better than the one in use |
| `src/ladder/brain/policy.py` | `available`, `baseline`, `baseline_wiki`, `teleport_rule`, `Style`, and `BrainTiers`, which sits in Reflex where `StubTiers` did |
| `docs/wiki-strategy.md` | the DCSS wiki's strategy guides, sorted by what the brain would need to use each piece of advice |
| `src/ladder/brain/steplog.py` | `steps.jsonl` writer shared by self-play, `spike` and the cockpit |
| `src/ladder/brain/selfplay.py` | parallel games, one process each, with a watchdog for hung reads |
| `src/ladder/brain/forks.py` | picks the moments to fork and writes the replay scripts (`kind="stairs"`: explore vs descend) |
| `src/ladder/brain/humanplay.py` | a person's recorded game to a step log |
| `src/ladder/brain/corpus.py` | step logs to labelled training rows |
| `src/ladder/brain/train.py` | PyTorch training and export |
| `src/ladder/brain/cli.py` | `ladder brain ...`, including the iterate loop |
| `models/brain.json`, `models/brain.ledger.json` | the champion (none yet) and the record of every `iterate` round |
| `models/iter<n>.json` | each round's candidate, with its parity vectors |
| `models/v5-*.json` | version 5 experiments, each with its parity file; `v5-ens5`, `v5-forks3`, `v5-pairs3` are ensemble manifests |
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
   *Follow-up: the training seed moves a model by up to 0.8 depths in games, more than the inputs do.
   Before comparing inputs again, train an ensemble (average 3–5 seeds' predictions) or promote on the mean
   of several seeds, and gate on forks that compare descend with explore from the same state.*
   *Done (2026-11-14, later): neither helped (the "Ensembles, explore-or-descend forks" section). The
   estimate of one action against another is the weak part, and more rows of either kind haven't fixed it.
   Next, cheapest first: (a) put the rule `v5-seen` found into the rules of thumb (read teleportation
   when exhausted after a rage with monsters in view) and test that rule alone against today's rules on a
   fresh block; (b) use the network only where it is confident and the pairs agree (as `margin=1.0` did),
   and mine its confident overrides for rules; (c) if the network is to choose more often, predict the
   difference between two actions directly from paired forks instead of each action's outcome on its own.*
   *(a) done: level on fresh blocks (−0.01 [−0.16, +0.13]); the switch `teleport=1` stays off. (b) is next;
   mined rules need a fresh-block test each, and blocks F and G are spent.*
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
