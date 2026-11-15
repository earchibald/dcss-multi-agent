# The trained brain

A small neural network, trained on this machine from the ladder's own games, that chooses Reflex's
next action. It is not a language model and makes no API calls: it reads numbers about the moment and
runs in numpy in well under a millisecond. It is the same idea as the trained brain in
`~/Code/s1-battle`, moved to a game that can't be forked.

## Where it stands

**2026-11-15, morning: a model beats the rules of thumb in a pre-registered test for the first time.** `v6-clean3`
(the `s12` recipe at 3 training seeds, trained only on 2,600 games played with today's code and rules) at
`--style margin=0.6` is **+0.14 [+0.06, +0.23]** deeper than the rules alone on 600 fresh dungeons (seeds
660000–660599; section "New default rules, and a model retrained on clean games", below). It leaves the rules at 0.1%
of choices, almost all to read teleportation when spent after a rage, hurt and facing dangerous monsters; at the
default margin the same model dives and loses (−0.28 on A + C). `recover=1 retreat=2` is now the default rules of
thumb. The champion `iter2` at its default margin is −0.30 [−0.65, +0.04] against the new rules on A + C, so the
cockpit's `--brain` should not play it at that margin. `models/brain.json` is unchanged.

**2026-11-15, night: `recover=1 retreat=2` passes a pre-registered replication on 1,000 fresh dungeons, +0.45
[+0.24, +0.65]** against HEAD defaults (seeds 650000–650999; section "The wrong dungeon fixed, and a larger
replication", below). Mean depth 5.97 against 5.53; dying just after taking the stairs spent falls from 24% of games
to 10%. The defaults are not changed yet (the orchestrator decides; what would change is listed there). The
wrong-dungeon bug is fixed at its root: `quit_game` returned before the game had taken the word "quit", so the
throwaway game was saved instead of ended. It now waits for the game to end, and a guard (`not_on_seed`) refuses to
play any game whose opening isn't a new game on its seed. 0 of 2,042 games since were off their seed.

**2026-11-15, later: going up the stairs when a rage runs out mid-fight, with the stairs close (`--style
retreat=2`), together with `recover=1`, does not pass a pre-registered fresh-block test: +0.30 [−0.03, +0.64]**
against HEAD defaults on blocks J and K (section "Fights around a rage", below). On the tuning blocks it was
+0.33 [+0.02, +0.66], and `retreat=2` alone added +0.08 on top of `recover=1`. Deadly rages are the ones begun
against more HP than the character has; going up helps only within about 8 steps of the stairs. All new switches
stay off; `recover=1` as a default is still unsettled. About 1 game in 100 was found played on a random dungeon
(a resumed throwaway save) and is now left out of every pairing.

**2026-11-15: a bug fix and `recover=1` together pass a pre-registered fresh-block test, +0.43 [+0.12, +0.75]**
against today's rules on blocks H and I (section "The reply a key behind, and the rage that ends exploring",
below). The staircase loop came from cancelling a scroll's prompt with Esc and Y typed together: the Y ran
later as a command, and from then on the bot read every reply a key late (12–19% of all keys, in two games
of three). Fixed and on by default (+0.36 [+0.16, +0.57] alone on the tuning blocks; no loop left, hangs 9 →
1). Waiting out a rage instead of trying to explore (`--style calm=1`, off by default) works as meant and is
level on depth. `recover=1` stays off by default until the orchestrator decides; it is what passed, with the fix.

**2026-11-14, night: a diagnosis of where the rules of thumb lose games** (section "Where the rules of thumb
lose games", below). A rage stops autoexplore, so the rules leave most levels from D:4 on mid-way, raging or
exhausted (64% of all level exits), arrive under qw's level and unable to rage, and a quarter of all games
end within 50 turns of such an arrival. Resting the rage out before the stairs (`--style recover=1`, off by
default) is +0.29 [−0.01, +0.59] on the tuning blocks A and C, untested on a fresh block. The larger loss is
in the fights themselves: at the same XL and depth the rules die on a level about twice as often as qw,
mostly after a rage runs out with monsters left. 6% of games stop alive, stuck on a staircase.

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

#### Where the rules of thumb lose games (2026-11-14, night)

A diagnosis from games already played, not another knob. Source: the 786 finished plain-rules games on the
spent blocks A, C, F and G (`{A,C}-rules-h`, `{F,G}-rules`; none resumed a stale save), with each death's
DCSS morgue file (copied from the server: exact killer, statuses, what was really in the pack) matched to
its game by seed and turn count (all 719 deaths matched). qw's five base runs (988 finished games, other
dungeons) are the reference for a stronger bot with the same character. Scripts in the job's `brain-v5e/`.

**Summary.**

- **One mechanism explains most of the early exits from a level, and a quarter of the deaths.** DCSS
  refuses to autoexplore during a rage ("Calm down first, please."). Two refusals and the brain sets
  `explore` aside for 50 turns (`BLOCK_TURNS`), so the rules head for the stairs and go down, mid-level,
  raging or exhausted. **64% of all level exits happen that way, and 90% from D:4 on**; only 28% of exits
  follow a level explored to the end. So the bot skips most of every level from D:4, spends a quarter of
  qw's turns per level (about 250 against 950), arrives a level or two under qw, and arrives slowed and
  unable to rage: **25% of all games end with a death within 50 turns (median 8) of such an arrival**.
- **Fixing that helps less than it removes.** A switch that rests a rage out before taking the stairs
  (`--style recover=1`, below) cuts arrivals raging or spent from 57% to 9% and is **+0.29 [−0.01, +0.59]**
  on the tuning blocks A and C (383 dungeons): the best lead so far, not yet tested on a fresh block. Also
  resting before exploring on (`recover=2`) brings XL on arrival to within half a level of qw's and is level
  (−0.01 [−0.32, +0.30]). Either way most of the removed deaths reappear later, in fights.
- **The rules lose fights that qw survives at the same level and depth.** Arriving on D:3–9 with XL one
  above the depth, the rules die on that level 17% of the time (24% with `recover=2`), qw 9%. qw's chance of
  dying on a level stays at 6–10% from D:4 to D:10; the rules' rises from 15% to 50%. What kills it is
  mostly a rage that runs out with the fight still on: in the plain rules that happened 1,031 times, and
  30% died within 50 turns (67% with four or more hostiles left, 54% under half HP).
- **Not deaths: 6% of games stop at the 1,500-choice limit on one level**, 41 of 49 on D:1–3, all but a
  few pressing `>` on a staircase that the game answers with "You can't go down here!" one step later (a
  reply one key behind, the dead end listed in Next, 5). Another 2% stop with nothing possible.

**Death and ending causes.** One cause per game, the first that applies in this order. "The last fight"
is the run of choices on the death level since nothing was last in view. "Spent" is DCSS's exhaustion
after a rage: `-Berserk` (no second rage yet) and usually `Slow` (every action takes twice as long). The
bound in the last column is a back-of-envelope ceiling, not a measurement: a game that ended at depth d is
given what the rules' own games reach once past d, E[max depth | max depth > d], as if every such ending
were avoided and the character then did as well as the average survivor; summed and divided by all 786.

| cause | games | share | D:1–3 | D:4–6 | D:7+ | mean depth | arrived below qw's median XL | known teleport scroll held | bound if avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| took the stairs raging or spent, died within 50 turns of arriving | 196 | 24.9% | 23 | 103 | 70 | 5.93 | 161 | 55 | +0.65 |
| walked into the last fight already spent (same level) | 119 | 15.1% | 27 | 53 | 39 | 5.61 | 82 | 36 | +0.42 |
| raged in the last fight, the rage ran out before the fight did | 226 | 28.8% | 43 | 85 | 98 | 6.05 | 173 | 71 | +0.77 |
| died still raging (the rage was not enough) | 88 | 11.2% | 32 | 30 | 26 | 4.95 | 59 | 22 | +0.33 |
| killed in melee, never raged (no reason under the rules) | 44 | 5.6% | 12 | 18 | 14 | 5.59 | 31 | 10 | +0.16 |
| poisoned to death (none of the above) | 23 | 2.9% | 8 | 7 | 8 | 5.00 | 15 | 9 | +0.09 |
| killed from range or by a spell (none of the above) | 13 | 1.7% | 2 | 7 | 4 | 6.54 | 10 | 4 | +0.04 |
| autofight refused (confused, out of reach) and it stood or fled | 10 | 1.3% | 5 | 3 | 2 | 4.50 | 6 | 0 | +0.04 |
| *not a death*: 1,500 choices on one level (stuck on a staircase) | 49 | 6.2% | 41 | 7 | 1 | 2.24 | | | +0.25 |
| *not a death*: nothing the brain can do | 18 | 2.3% | 8 | 7 | 3 | 4.11 | | | +0.08 |

Read alongside it (deaths only, not exclusive): spent at death 78%; 59% had four or more hostiles in view at
once; 30% died holding a scroll of teleportation (29% knew it), 44% some escape scroll (teleportation,
blinking, fear, fog); 5% a healing potion; 9% died of poison in all; 17% were killed from range or by a
spell in all. Commonest killers: gnoll 58, orc wizard 52, wight 34, killer bee 31, orc 26, Sigmund 23, ogre
22. qw's: gnoll 79, Sigmund 51, orc priest 36, orc wizard 31, electric eel 25 (the same early killers; qw's
later deaths are in Lair and other branches, where the rules never go).

**Pacing against qw.** XL on first arrival at each depth (mean), and the share of games arriving that die
on that level. qw arrives later and stronger, and its per-level death rate barely rises with depth.

| depth | rules: arriving | XL | turn (median) | died there | qw: arriving | XL | turn (median) | died there |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D:2 | 750 | 1.9 | 607 | 9% | 966 | 2.1 | 895 | 10% |
| D:3 | 666 | 3.1 | 1049 | 12% | 860 | 3.6 | 1750 | 10% |
| D:4 | 570 | 4.2 | 1475 | 15% | 776 | 4.9 | 2617 | 8% |
| D:5 | 473 | 5.3 | 1826 | 23% | 705 | 6.4 | 3595 | 8% |
| D:6 | 376 | 6.1 | 2097 | 30% | 648 | 7.6 | 4616 | 6% |
| D:7 | 258 | 6.9 | 2394 | 37% | 606 | 8.5 | 5644 | 9% |
| D:8 | 163 | 7.5 | 2747 | 39% | 556 | 9.1 | 6651 | 10% |
| D:9 | 99 | 8.1 | 3075 | 48% | 446 | 10.2 | 7740 | 8% |
| D:10 | 48 | 8.6 | 3364 | 50% | 364 | 11.3 | 9202 | 6% |

| XL on arrival against the depth (D:3–9 pooled) | rules: arrivals | died on that level | rules `recover=2` (A only) | qw: arrivals | died on that level |
| --- | --- | --- | --- | --- | --- |
| two or more below | 84 | 36% | 3, 67% | 19 | 21% |
| one below | 545 | 32% | 30, 33% | 108 | 19% |
| equal | 1249 | 22% | 195, 18% | 819 | 12% |
| one above | 614 | 17% | 289, 24% | 2081 | 9% |
| two or more above | 113 | 9% | 125, 16% | 1570 | 5% |

Share of deaths by depth: rules 21% on D:1–3, 43% on D:4–6, 29% on D:7–9, 7% deeper; qw 21%, 17%, 15%, 8%,
and 39% in branches. So both: **the rules dive (by accident, through the explore block) and arrive under
qw's level, and at the same level they still die about twice as often.** Removing the dive (below) shows the
second is what holds the depth down.

How each level is left (3,520 exits): explore set aside, character spent 36%, raging 27%, fresh 4%; level
explored 31%; fell through a trapdoor 1%. From D:4 down to D:10, 83–91% of exits are with explore set aside.
With `recover=2` on block A, 79% of exits follow a level explored to the end.

**What each cause is worth.** The bounds in the cause table are ceilings. For the top causes there is
also a measurement:

- *Took the stairs, or walked into a fight, spent* (40% of games, ceiling +1.07 together). Measured
  directly by a switch that removes it (`recover`, next paragraph), played on A and C: whole games, paired
  by dungeon. `recover=1` removes five arrivals in six that were raging or spent (deaths of the first kind
  94 → 24 on A + C) and gains +0.29 [−0.01, +0.59], a quarter of the ceiling: the rest of those deaths
  happen a level or so later, mostly when a rage runs out mid-fight (110 → 140). The saved character is not
  an average survivor; it is still the bot that loses fights.
- *The rage ran out before the fight did* (29%, ceiling +0.77). No fork measures it: the rules choose
  `fight` again on the next choice after any single different action, so a one-action fork changes
  nothing, and the existing forks (`ladder brain forks`) refuse evaluation seeds. The nearest measurement
  is the teleport switch above: reading teleportation at exactly that moment (spent, monsters in view) was
  −0.01 [−0.16, +0.13] on F and G. Of the 1,031 times a rage ran out with something still in view, 30% died
  within 50 turns: 19% with one hostile left, 33% with two or three, 67% with four or more; 54% under half
  HP. The stairs up were known in 192 of the 219 deaths of this kind, within 10 steps in 89.
- *Stuck on a staircase* (6%, ceiling +0.25; +0.29 to +0.38 per block). Not a death, so the ceiling is
  close to the value: these characters were alive, mostly on D:1–3, and stopped. A fix to the reply that
  comes one key late would recover most of it. With `recover=2` the game spends more choices per level and
  it happens more (13 → 18 on A).

**The switch, `--style recover=1|2` (off by default).** `policy.recovering` is true while `Berserk`,
`-Berserk` or `Slow` shows. With nothing in view and `recovering`, the rules rest (`5`; at full HP DCSS
"starts waiting", so the turns pass) before taking the stairs (`recover=1`), and also before exploring on
(`recover=2`). `available(..., recover=True)` lets `rest` be chosen at full HP then, and a rest that left
HP where it was doesn't rule it out (it was for the time, not the HP). A rest that passes no time at all is
set aside like any other action. Resting while still raging also ends the rage sooner (DCSS shortens a
rage with nothing to hit). In the smoke games a spell of exhaustion took two rests, about 25–30 turns.

Tuning on A and C only (whole games against the plain rules replayed with today's code; paired by dungeon,
none stale, 95% bootstrap). Here play diverges from the first rage, so every game differs and the
interval is wide.

| arm | block | finished (hung) | mean depth | died | died on D:1–3 | XL | turns | arrivals raging or spent | vs rules | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules of thumb | A | 197 (3) | 5.46 | 179 | 35 | 5.62 | 2046 | 55% | | | |
| `recover=2` | A | 195 (5) | 5.51 | 169 | 25 | 6.62 | 3639 | 11% | +0.04 | [−0.43, +0.50] | 69 / 56 / 69 |
| rules of thumb | C | 194 (6) | 5.36 | 173 | 44 | 5.66 | 2023 | 59% | | | |
| `recover=2` | C | 196 (4) | 5.39 | 172 | 44 | 6.35 | 3541 | 11% | −0.06 | [−0.48, +0.36] | 65 / 59 / 67 |
| `recover=2`, A + C | | | | | | | | | −0.01 | [−0.32, +0.30] | 134 / 115 / 136 |
| `recover=1` | A | 195 (5) | 5.85 | 171 | 23 | 6.56 | 3227 | 8% | +0.39 | [−0.02, +0.81] | 80 / 58 / 56 |
| `recover=1` | C | 194 (6) | 5.54 | 174 | 44 | 6.13 | 3023 | 9% | +0.18 | [−0.24, +0.60] | 70 / 55 / 64 |
| **`recover=1`, A + C** | | | | | | | | | **+0.29** | **[−0.01, +0.59]** | 150 / 113 / 120 |
| `recover=1` − `recover=2`, A + C | | | | | | | | | +0.24 | [−0.08, +0.56] | 145 / 129 / 111 |

- **`recover=1` is the better level**, and the only arm since the champion with a tuning-block interval
  that nearly clears zero. It rests in 177–179 of ~195 games per block (5,000–5,500 rests), so it touches
  almost every game; it plays 50% more turns and ends about 0.5–0.9 XL higher.
- Resting before exploring too (`recover=2`) adds nothing: it explores whole levels (79% of exits follow
  a level explored to the end, against 52% with `recover=1` and 31% plain), gains XP, and meets more fights
  per level. Arriving fresh is what pays, not exploring more.
- Causes on A + C (cause table's order; plain → `recover=1` → `recover=2`): took the stairs spent 94 → 24 →
  33; walked into the last fight spent 59 → 66 → 70; rage ran out 110 → 140 → 129; died raging 42 → 47 → 56;
  melee without a rage 20 → 41 → 28; stuck on a staircase 29 → 32 → 35. Deaths on D:1–3 on A: 35 → 23 → 25.
- Not confirmed: A and C are where it was tuned (two levels tried). The pre-registration for a fresh block
  is the orchestrator's to write; `recover=1` against the plain rules is the configuration it would test.

**Proposed rule changes, ranked by what the evidence supports** (none tested on a fresh block):

1. **Rest out a rage before taking the stairs: `--style recover=1`** (cause: took the stairs raging or
   spent; 25% of games; ceiling +0.65). Implemented, off by default; +0.29 [−0.01, +0.59] on A + C
   (tuning); touches about 90% of games. The candidate for a fresh-block test.
2. **Fix the staircase dead end** (cause: stuck on a staircase; 6% of games, 41 of 49 on D:1–3; ceiling
   +0.25, and close to it since these characters are alive). When `>` on a staircase is answered "You
   can't go down here!", the replies are a key behind: catch up (`Connection.catch_up()`, as before menus)
   before the next key. A bug fix rather than a rule; it changes nothing else, so it should show most of
   its +0.25 wherever it is tested, and adds to rule 1.
3. **Retreat when a rage runs out mid-fight** (cause: rage ran out; 29% of games, 36% under `recover=1`;
   ceiling +0.77, +1.10 under `recover=1`). Spent, with two or more hostiles in view and the stairs up
   known: walk to them and go up (committed, as the stairs forks commit, since the rules would otherwise
   turn and fight after one step), then rest out the exhaustion upstairs (`recover`). It targets the moments
   that kill: 441 of the 1,031 rage endings had two or more hostiles left, and 40% of those died within 50
   turns. The stairs up were within 10 steps in 89 of 219 such deaths. Caution: the teleport switch acted
   at the same moments and gained nothing, and adjacent monsters follow up the stairs, so the gain may be
   well under the ceiling.

Not proposed, for want of evidence: raging later (the rules rage at the first threat-2 monster within two
squares; 59% of deaths had four or more hostiles at once), and drinking before the rage (the wiki variant
did that and came out behind).

- **Verified**: every count and table in this section; the morgue matched to every death (seed, turn count,
  time); that `explore` is set aside after "Calm down first, please." and that the rules then go down
  (protocol logs, step logs); that `recover` rests pass 10–30 turns at full HP and end the exhaustion
  (smoke games); that the switch off leaves play unchanged (unit tests; the code path is not entered).
- **Inferred**: that the "one key behind" reply causes the staircase loop (the protocol shows `>`
  followed by a step and "You can't go down here!" one key later, but the cause in `act()` was not traced);
  the ceilings, which assume the saved character does as well as the average survivor, and the `recover`
  arms show it doesn't; that qw's lower death rate comes from its fighting (retreat, escapes, choosing
  ground) rather than from its dungeons: qw played other seeds, so its numbers are a reference, not a pair.
- Runs: `runs/brain/v5/games/{A,C}-recover{1,2}`; the 8-game smoke test in `runs/brain/v5e/`. Scripts
  (`gather.py`, `flags.py`, `causes.py`, `pace.py`, `pace_xl.py`, `departures.py`, `rage_end.py`, `arms.py`)
  and the copied morgues in the job's `brain-v5e/` scratch directory.

#### The reply a key behind, and the rage that ends exploring (2026-11-15)

**Summary.**

- **The staircase loop was a symptom of a bigger bug: after cancelling a scroll's prompt, the bot played one
  reply behind the game, in two games out of three.** To cancel a scroll that asks for a target or an item
  (blinking, identify, enchant, brand, acquirement) the brain sent Esc and Y together. The Y was typed ahead:
  the "really abort?" question that Esc brings up doesn't take it (and acquirement asks nothing), so DCSS kept
  it and ran it later as a command ("Unknown command."). That is one reply more than the bot read, and from
  then on every key's answer was the previous key's, until the next menu key happened to catch up. On A and C
  that was 17–19% of all keys sent, in 261 of 400 games. On a staircase it never ends: the bot sees itself
  on the stairs only once it has stepped off them, presses `>` one square away ("You can't go down here!"),
  steps back, and so on until the 1,500-choice limit. All 24 staircase loops on A and C began that way.
- **Fixed, on by default**: `conn.cancel_prompt` sends Esc, then Y only once the question is up; `act()`
  stops at a bare yes/no question instead of waiting for ever; and `Reflex._answer_prompts` catches up after
  answering any prompt (a rarer source: an Enter sent for a `--more--` that a popup had swallowed, after a
  shaft). On A and C the loop is gone (24 → 0), no key is sent a reply behind, hung games fall from 9 to 1,
  and the 130 games that never cancelled a prompt replay the same (129; the other differs by one turn of
  explore, replay noise). **The fix alone is +0.36 [+0.16, +0.57]** against the rules as they were.
- **The explore block is fixed at its source by a switch, `--style calm=1` (off by default)**: wait out a
  rage instead of trying to explore, and don't count "Calm down first, please." as the level being done.
  It works as meant (levels left after exploring to the end: 31% → 86%) and is level on depth (+0.16
  [−0.17, +0.49] against the fix alone), as resting before exploring (`recover=2`) was before.
- **The best tuning arm is the fix with `recover=1`** (rest out a rage before the stairs): +0.24 [−0.06,
  +0.54] over the fix alone, +0.61 [+0.28, +0.95] over the rules as they were. Pre-registered below for
  fresh blocks H and I.

**What happened, in the protocol** (run `A-rules-h`, seed 500033, D:1; the bot's keys and what it read):
Esc and Y go out together; the question comes up and stays open; Reflex answers it with Esc ("Okay, then.");
the next key, `o`, reads "Unknown command." (the Y); the next `o` reads the first one's explore, and so on.
By turn 629 the bot reads "There is a stone staircase leading down here" for the step it took a key earlier
and presses `>` while the game has already moved it one square west; it reads that move as the answer to `>`,
walks back east, and the 940 turns to the limit are that cycle. In every one of the 24 loops on A and C the
last thing before it is a typed-ahead cancel followed by "Unknown command.".

| plain rules, before the fix | games | cancelled a scroll prompt | "Unknown command." | keys sent a reply behind | stuck on a staircase | hung |
| --- | --- | --- | --- | --- | --- | --- |
| A (`A-rules-h`) | 200 | 138 | 135 | 17% (spells: median 7 keys, mean 66, longest 1,467) | 11 | 3 |
| C (`C-rules-h`) | 200 | 123 | 119 | 19% (median 4, mean 62, longest 1,466) | 13 | 6 |
| A with the fix (`A-fix`) | 200 | 141 | 8 (after a shaft; caught up at once) | 0 | 0 | 0 |
| C with the fix (`C-fix`) | 200 | 128 | 6 (the same) | 0 | 0 | 1 |

**The fix, as coded** (`src/ladder/conn.py`, `src/ladder/brain/policy.py`, `src/ladder/brain/selfplay.py`,
`src/ladder/reflex.py`; tests in `test_conn.py`, `test_brain.py`, `test_reflex.py`):

- `conn.cancel_prompt(conn)`: `act("key_esc", through_menu=True)`; if that left a menu or a yes/no open,
  `act("Y", through_menu=True)`. Used by `BrainTiers.perform` for `ITEM_PROMPTS` and by `selfplay._clear_save`.
  A test plays a fake game that keeps typed-ahead keys from the question: with the old pair of keys the next
  move's reply is "Unknown command." and the move's own comes a key late; with `cancel_prompt` each reply is
  its own key's.
- `Connection.act`: a reply whose last input mode is 8 (yes/no) with no menu open returns `blocking="yesno"`
  (before, it read on, waiting for a reply that only comes after an answer). Replies with a menu are as before.
- `Reflex._answer_prompts`: after a prompt is answered, `catch_up()` (read everything already sent, as
  before menu keys); a prompt found there is answered too. No key is sent, so a game with nothing left
  unread plays the same.

**Where the fix's gain comes from** (A + C, paired by dungeon against `{A,C}-rules-h`, both finished): the 24
dungeons that were stuck on a staircase, +3.75 each (63% of the gain); the 237 others that cancelled a prompt,
+0.19 each (32%: a bot that sees the game as it is); the 130 that never did, one game of replay noise (+6).

**The switch, `--style calm=1` (off by default)** (`policy.raging`, `available(..., calm=True)`, `baseline(...,
calm=True)`, `BrainTiers.observe`). While `Berserk` shows and nothing is in view: `explore` is not offered (DCSS
would refuse it) and `rest` is, even at full HP, so the rules rest the rage off and then explore on. A refusal
with "Calm down first, please." no longer counts toward setting `explore` aside for `BLOCK_TURNS`. The
exhaustion after a rage doesn't stop autoexplore, so `calm` explores on through it; with `recover=1` too, the
exhaustion is also rested off before the stairs. It changes most games (it touches every rage with nothing left
in view), so it is a switch, not a default.

**Tuning on blocks A and C** (whole games; paired by dungeon over games both finished, none stale on any
side; 95% bootstrap over dungeons, 10,000 resamples). "Before the fix" is `{A,C}-rules-h`, played earlier
with code whose default play is commit 9aab0f0's; every other row is this working tree's.

| arm | block | finished (hung) | mean depth | XL | turns | died | died on D:1–3 / 4–6 / 7+ | stuck at the limit | arrivals raging or spent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules, before the fix | A | 197 (3) | 5.46 | 5.62 | 2046 | 179 | 35 / 83 / 61 | 13 | 55% |
| `recover=1`, before the fix | A | 195 (5) | 5.85 | 6.56 | 3227 | 171 | 23 / 79 / 69 | 16 | 8% |
| the fix | A | 200 (0) | 5.88 | 5.96 | 2173 | 193 | 33 / 89 / 71 | 3 | 54% |
| the fix + `calm=1` | A | 200 (0) | 5.97 | 7.01 | 3920 | 190 | 28 / 94 / 68 | 3 | 9% |
| the fix + `recover=1` | A | 200 (0) | 6.21 | 6.80 | 3226 | 190 | 26 / 84 / 80 | 3 | 9% |
| the fix + `calm=1 recover=1` | A | 200 (0) | 5.92 | 6.93 | 3812 | 189 | 27 / 98 / 64 | 3 | 7% |
| the fix + `recover=2` | A | 200 (0) | 5.91 | 6.91 | 3718 | 190 | 26 / 97 / 67 | 3 | 10% |
| rules, before the fix | C | 194 (6) | 5.36 | 5.66 | 2023 | 173 | 44 / 63 / 66 | 16 | 59% |
| `recover=1`, before the fix | C | 194 (6) | 5.54 | 6.13 | 3023 | 174 | 44 / 57 / 73 | 16 | 9% |
| the fix | C | 199 (1) | 5.73 | 5.91 | 2072 | 193 | 40 / 79 / 74 | 1 | 60% |
| the fix + `calm=1` | C | 200 (0) | 5.93 | 6.89 | 3870 | 193 | 45 / 67 / 81 | 1 | 8% |
| the fix + `recover=1` | C | 199 (1) | 5.86 | 6.38 | 3042 | 191 | 44 / 60 / 87 | 2 | 8% |
| the fix + `calm=1 recover=1` | C | 200 (0) | 5.93 | 6.84 | 3857 | 193 | 45 / 64 / 84 | 1 | 7% |
| the fix + `recover=2` | C | 200 (0) | 5.87 | 6.78 | 3686 | 193 | 43 / 71 / 79 | 1 | 10% |

| A + C, paired | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| **the fix − rules before it** | 391 | **+0.36** | **[+0.16, +0.57]** | 76 / 269 / 46 |
| ... A alone, C alone | 197, 194 | +0.41, +0.32 | [+0.11, +0.72], [+0.06, +0.59] | |
| the fix + `calm=1` − the fix | 399 | +0.16 | [−0.17, +0.49] | 148 / 111 / 140 |
| **the fix + `recover=1` − the fix** | 398 | **+0.24** | [−0.06, +0.54] | 165 / 113 / 120 |
| the fix + `calm=1 recover=1` − the fix | 399 | +0.13 | [−0.20, +0.47] | 147 / 113 / 139 |
| the fix + `recover=2` − the fix | 399 | +0.09 | [−0.24, +0.42] | 146 / 113 / 140 |
| the fix + `calm=1` − rules before it | 391 | +0.53 | [+0.18, +0.89] | 169 / 94 / 128 |
| **the fix + `recover=1` − rules before it** | 390 | **+0.61** | **[+0.28, +0.95]** | 182 / 90 / 118 |
| the fix + `calm=1 recover=1` − rules before it | 391 | +0.50 | [+0.15, +0.85] | 168 / 97 / 126 |
| the fix + `recover=2` − rules before it | 391 | +0.47 | [+0.12, +0.82] | 168 / 92 / 131 |

How levels are left on A (all exits; departures.py): the fix alone, 31% after exploring to the end and 62%
with explore set aside while raging or spent; `calm=1`, 86% explored to the end and 5% set aside while raging
or spent; `recover=1`, 53% explored to the end, 38% set aside but rested before the stairs. So `calm` does what
it is for and, like `recover=2` before it, exploring whole levels does not deepen the game: more XL (+1.0) and
nearly twice the turns, the same depth. What pays is arriving rested (`recover=1`), not exploring more.

**Death and ending causes, A + C** (the cause table's rules, above; finished games, none stale, deaths with a
matched morgue: 3 of the fix's and 1 of the chosen arm's morgues were not found and those games are left out).

| cause | rules before the fix | the fix | the fix + `recover=1` |
| --- | --- | --- | --- |
| games (mean depth) | 391 (5.41) | 396 (5.81) | 398 (6.04) |
| took the stairs raging or spent, died within 50 turns | 94 (24%) | 100 (25%) | 27 (7%) |
| walked into the last fight already spent | 59 (15%) | 61 (15%) | 76 (19%) |
| raged in the last fight, the rage ran out first | 110 (28%) | 124 (31%) | 151 (38%) |
| died still raging | 42 (11%) | 51 (13%) | 58 (15%) |
| killed in melee, never raged | 20 (5%) | 18 (5%) | 37 (9%) |
| poisoned; from range or a spell; autofight refused | 14; 9; 4 | 13; 10; 6 | 13; 13; 5 |
| *not a death*: 1,500 choices on one level | 29 (25 on D:1–3; staircases) | 4 (other dead ends) | 5 (other dead ends) |
| *not a death*: nothing the brain can do | 10 | 9 | 13 |

The fix turns the 25 stuck games into games that go on and mostly die later, of the same causes. `recover=1`
removes three deaths in four of the first kind (100 → 27) and, as before, most of them come back a level or
so deeper as a rage that runs out mid-fight (124 → 151): the fights are still what the rules lose.

**Pre-registered (written before any game on block H or I).** Configuration: this working tree's code (the
cancel fix, the yes/no stop and the catch-up after prompts, all on by default) with `--style recover=1`, no
model, no random choices. Baseline: the plain rules of thumb (no model, default style) played with commit
9aab0f0's code, exported with `git archive` to the job's `brain-v5f/old/src` and put first on `PYTHONPATH`, that
is today's bot without any of the new fixes, so the test measures the whole package against what we have. 200
games per block from seeds 590000 (block H, 590000–590199) and 620000 (block I, 620000–620199), 9 workers asked
(7 accounts log in), one run after another. Both blocks are played whatever H shows. Paired by dungeon over
games both finished and neither resumed a stale save; 95% bootstrap over dungeons (10,000 resamples,
`brain-v5f/arms.py`). **Pass: the pooled H + I interval's lower end is above zero.** Analysed once.

**Result: passes.** The package (the fix, with `recover=1`) is **+0.43 [+0.12, +0.75]** against today's rules on
the fresh blocks H and I (396 dungeons), the first pre-registered test since the champion to clear zero.

| fresh blocks | finished (hung) | mean depth | XL | turns | died | died on D:1–3 / 4–6 / 7+ | stuck at the limit (on a staircase) | arrivals raging or spent | keys sent a reply behind |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| H, rules at 9aab0f0 | 198 (2) | 5.60 | 5.83 | 2152 | 182 | 41 / 65 / 76 | 12 (8) | 54% | 15% |
| H, the fix + `recover=1` | 200 (0) | 5.92 | 6.56 | 3226 | 194 | 40 / 70 / 84 | 2 (0) | 8% | 0 |
| I, rules at 9aab0f0 | 198 (2) | 5.28 | 5.64 | 2017 | 186 | 47 / 74 / 65 | 10 (5) | 59% | 12% |
| I, the fix + `recover=1` | 200 (0) | 5.81 | 6.42 | 3221 | 189 | 45 / 65 / 79 | 3 (0) | 7% | 0 |

| the fix + `recover=1` − rules at 9aab0f0 | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| H | 198 | +0.32 | [−0.13, +0.79] | 82 / 58 / 58 |
| I | 198 | +0.55 | [+0.11, +0.99] | 83 / 60 / 55 |
| **H + I (the pre-registered test)** | 396 | **+0.43** | **[+0.12, +0.75]** | 165 / 118 / 113 |

| cause, H + I (as above) | rules at 9aab0f0 | the fix + `recover=1` |
| --- | --- | --- |
| games (mean depth) | 395 (5.44) | 400 (5.86) |
| took the stairs raging or spent, died within 50 turns | 101 (26%) | 27 (7%) |
| walked into the last fight already spent | 57 (14%) | 82 (21%) |
| raged in the last fight, the rage ran out first | 116 (29%) | 171 (43%) |
| died still raging | 46 (12%) | 46 (12%) |
| killed in melee, never raged | 27 (7%) | 34 (9%) |
| poisoned; from range or a spell; autofight refused | 11; 3; 6 | 13; 7; 3 |
| *not a death*: 1,500 choices on one level | 22 (21 on D:1–3) | 5 (other dead ends) |
| *not a death*: nothing the brain can do | 6 | 12 |

- No stale save on any side of any run in this section. The baseline arm was checked to be the old code: its
  protocol logs show the typed-ahead Esc + Y and the lag (15% and 12% of keys), and a 14-game replay of block A
  with it gave the same game as `A-rules-h` in 13.
- The tuning blocks put the fix at +0.36 and `recover=1` on top at +0.24; the fresh test measures only the
  sum, so how H + I's +0.43 splits between the two is not known. The 13 dungeons stuck on a staircase under
  the old rules gain +4.85 each, +0.16 over all 396; the 128 that never cancelled a prompt (where only
  `recover=1` can act) gain +0.94 each; the 255 others are level (−0.04).
- What the rules lose is unchanged: a rage that runs out with the fight still on is now 43% of all endings.
- **Verified**: every count and table here; that each staircase loop on A and C follows a typed-ahead cancel
  and "Unknown command." (protocol logs); that the fix sends Esc and Y apart and leaves no reply unread (the
  14 + 29 "Unknown command." left on A, C, H, I all come after a shaft's popup and are read by the new catch-up
  in the same step); that unaffected games replay the same (129 of 130); the tests.
- **Inferred**: that the Y is not taken because it arrives before the question is up (the protocol shows the
  question open after it and the Y run later as a command, but DCSS's input handling was not read); that the
  32% of the fix's gain outside stuck games comes from seeing the game as it is (it is where the lag was).
- Blocks H (590000–) and I (620000–) are now spent. Runs: `runs/brain/v5/games/{A,C}-fix`, `-fix-calm`,
  `-fix-rec1`, `-fix-calm-rec1`, `-fix-rec2`, `{H,I}-fix-rec1`, `{H,I}-rules-old`; smoke games in
  `runs/brain/v5f/smoke/`. Scripts (`chain.sh`, `arms.py`, `cancels.py`, `lag.py`, `vscan.py`, `verify_main.py`,
  `split.py`, `unknown.py`, `proto.py`, `diverge.py`, and copies of `gather.py`, `flags.py`, `causes.py`), the
  old code and the copied morgues are in the job's `brain-v5f/` scratch directory.

#### Fights around a rage: going up when a rage runs out (2026-11-15)

**Summary.**

- **The pre-registered test does not pass: `recover=1 retreat=2` is +0.30 [−0.03, +0.64]** against HEAD defaults
  on the fresh blocks J and K (393 dungeons). It is ahead on both blocks (+0.39, +0.21) and on the tuning blocks
  (+0.33 [+0.02, +0.66]), but the fresh interval reaches below zero. All new switches stay off.
- **What marks a deadly rage is the size of the fight.** When the hostiles in view have more HP left between them
  than the character's maximum, a rage runs out or ends in death 40% of the time (10% otherwise), and 22% are
  followed by death within 50 turns (4%). After a rage runs out with two or more left, 42% die.
- **Going up the stairs when a rage runs out mid-fight helps only when they are close.** With two or more hostiles
  left and the stairs within 8 steps, deaths within 50 turns fall from 49% to 31% (A + C); on longer walks, slowed
  and followed, they rise (35% → 42%). Hence `retreat=2` (stairs within 8 steps): +0.08 [−0.04, +0.21] on top of
  `recover=1` on A + C, touching about one dungeon in nine. `retreat=1` (any distance) is −0.10; walking to the
  stairs before a big fight (`stairs=1`) adds nothing.
- **`recover=1` as a default is still not settled** by the pre-registered standard: every comparison with it is
  ahead by about +0.25 to +0.33, none has passed on fresh blocks on its own.
- **A measurement bug: about 1 game in 100 (6 in one run) was played on a random dungeon**, the first game an
  account plays in a run, resuming a turn-0 throwaway save. Such games are now left out of every pairing (morgue
  check). The H + I result is unchanged by it.

**What the saved games show** (step logs of `{A,C}-fix-rec1`, the fix with `recover=1`: 395 games that did not
resume a save; "died" means within 50 turns; scripts `events.py`, `summ.py`, `summ2.py`, `distinguish.py`).

- **The rules rage 5,331 times; 7% of rages are followed by death.** 86% of rages end with nothing left in view,
  13% run out with the fight still on, 1% end in death. 346 of the 378 deaths came within 50 turns of starting a
  rage.
- **What marks a deadly rage is the size of the fight, not where it is fought.** The best single sign is the
  estimated HP the hostiles in view have left between them (`policy.foe_hp`: each one's average HP times what its
  damage level leaves) against the character's maximum HP. Rages begun against more than that (14% of rages) run
  out or end in death 40% of the time, against 10%, and are followed by death 22% of the time, against 4%.

| at the rage's start | share of deadly rages | of the others | died when true (rages) | when false |
| --- | --- | --- | --- | --- |
| hostiles' HP left ≥ the character's max HP | 45% | 12% | 22% (735) | 4% (4,596) |
| 4+ hostiles in view | 44% | 21% | 13% (1,184) | 5% (4,147) |
| a threat-3 (red) hostile | 26% | 9% | 16% (548) | 5% (4,783) |
| XL below the depth | 19% | 6% | 18% (377) | 6% (4,954) |
| a unique | 22% | 10% | 13% (581) | 6% (4,750) |
| HP under 80% | 15% | 8% | 12% (458) | 6% (4,873) |
| no stairs up known | 12% | 5% | 14% (315) | 6% (5,016) |
| in a corridor (walls on two opposite sides) | 26% | 34% | 5% (1,779) | 7% (3,552) |
| 2+ adjacent | 15% | 15% | 6% (820) | 7% (4,511) |
| a known teleport scroll held | 38% | 36% | 7% (1,923) | 6% (3,408) |

- **When a rage runs out with hostiles in view (701 times), 29% die**: 19% with one left, 32% with two or three,
  62% with four or more; 54% under half HP, 19% at 80% or more. Stairs up were known in 654 of the 701. The rules
  went on fighting at once in 82% (first action `fight` 573, `quaff_heal` 44, `descend` 36, `flee_up` 21). In a
  corridor or the open made little difference (27% and 30%).
- **Fights met while spent** (nothing in view, then hostiles, with `-Berserk`): 936, 13% died; almost all (882)
  with one hostile. A rage spent on an easy fight (every hostile threat 0–1, HP over half: 811 rages, 15%) came
  before 160 of them, and 9 of those died, so saving the rage for real threats has little to gain.
- **qw, for reference** (its decision logs, `runs/qw/held6-a-base`, 200 games, same character, other dungeons;
  `qw_rage.py`): 3,434 rages, 5% followed by death. Its rages run out with enemies in view more often than ours
  (31% of rages against 13%) but it dies after only 8% of those (one left 4%, two or three 10%, four or more 22%).
  It fled up the stairs within 15 actions in 28% of them (3% died) and took a tactical step in 43%.
- **qw's rules, as read in its source** (`qw.lua`; a reference, not data): it goes berserk when HP is under half
  with an enemy within two squares it can reach, when a "scary" enemy is best fought berserk, or when the total
  threat passes a level that is lower at low XL. It flees to stairs up (`want_to_flee`) when it has a reason to rest
  (HP under 90%, exhausted, slowed, on berserk cooldown) but only if no melee enemy within two squares can follow
  and no enemy would gain on it on the way; it keeps walking there for 10 turns, then rests to full. In melee it
  steps to a square where two fewer enemies can reach it ("outnumbered"), not while berserk.

**The candidate rules** (opt-in `Style` switches, off by default; `src/ladder/brain/policy.py`: `Style.retreat`,
`Style.stairs`, `foe_hp`, `big_fight`, `BrainTiers.fight_moves`, and the `retreat` / `rest_out` / `to_stairs`
arguments of `baseline`; tests in `tests/test_brain.py`, the block "the opt-in fight rules"). Not tried, for want of
evidence: fighting from a corridor (5% against 7% of rages followed by death, 27% against 30% after a rage ran out)
and saving the rage for real threats (above). Resting before exploring on while spent is `recover=2`, already level.

1. **`retreat=1`: when a rage runs out with two or more hostiles still in view and stairs up known, go up them,
   then rest the exhaustion off.** "Runs out" is `Berserk` at one choice and not at the next. The level is marked
   to be left: while the character is still `recovering`, every choice there with something in view heads for the
   stairs (`flee_up`; a healing potion first when at half HP or under), so one step back to fight doesn't undo it.
   With nothing in view, on any level, it rests until `Berserk`, `-Berserk` and `Slow` are gone, as `recover=2`
   would. Upstairs it fights whatever followed (only adjacent monsters do).
2. **`retreat=2`: the same, only when the stairs up are within 8 steps** (`STAIRS_NEAR`). Added after block A's
   `retreat=1` games showed the walk paying only when short (table below).
3. **`stairs=1`: before a fight bigger than one rage, walk to stairs up within 8 steps first.** "Bigger" is
   `big_fight`: the hostiles in view have more HP left between them than the character's maximum. Only while no
   rage or exhaustion is on and nothing is adjacent, and once per fight (until on the stairs or something is
   adjacent; it may walk again once nothing is in view), so a monster that doesn't come can't hold it there. It
   acts in about a game in four and is meant to put `retreat` a step from the stairs.

**A measurement bug found on the way: some games are played on a random dungeon.** The first game an account plays
in a run follows `selfplay._clear_save`, which, with nothing saved, starts a throwaway game and quits it. Sometimes
the quit doesn't take, the next seeded start resumes the throwaway save at turn 0 ("Welcome back, ladderbrain1"
in the protocol log; a new game says "Welcome, …" and "Game seed: 500010 (custom seed)"), and the `turn > 1`
stale check lets it through. Its morgue carries a random seed. It hit 1–3 games in most runs and 6 of 7 accounts
in `A-fix-rec1-ret2`. From here on a game also counts as stale unless a morgue on its own custom seed with its turn
count exists (`brain-v5g/seeds.py`). That check and the "Welcome back" text agree on every run of this section
(the morgue check also drops hung games, which leave none). Re-scored this way, H + I's test is unchanged: +0.43
[+0.11, +0.75] on 395 dungeons. Not fixed in the code (fixed later, with a different cause: section "The wrong
dungeon fixed", below). The likely cause (inferred, not traced) is that `act()` now
stops at a bare yes/no question and `Connection.quit_game` answers only the typed "quit" prompt, so a brand-new
character's yes/no "really quit?" goes unanswered. The fix would be to answer `blocking == "yesno"` in
`quit_game`, or to raise `StaleSave` on "Welcome back".

**Tuning on blocks A and C** (whole games; paired by dungeon over games both finished and neither stale in the new
sense; 95% bootstrap over dungeons, 10,000 resamples). Baselines: HEAD defaults (`{A,C}-fix`) and the fix with
`recover=1` (`{A,C}-fix-rec1`), both played earlier with code whose default play is this tree's: a 14-game replay
of block A with the switches off gave the same game in all 11 dungeons where both sides were on their seed.
Run-level means are over all finished games.

| arm | block | finished (hung) | mean depth | XL | turns | died | died on D:1–3 / 4–6 / 7+ | stuck at the limit | not on their seed or resumed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HEAD defaults (`A-fix`) | A | 200 (0) | 5.88 | 5.96 | 2173 | 193 | 33 / 89 / 71 | 3 | 2 |
| `recover=1` | A | 200 (0) | 6.21 | 6.80 | 3226 | 190 | 26 / 84 / 80 | 3 | 0 |
| `recover=1 retreat=1` | A | 200 (0) | 6.04 | 6.75 | 3269 | 190 | 30 / 81 / 79 | 3 | 1 |
| `recover=1 retreat=2` | A | 200 (0) | 6.34 | 6.91 | 3370 | 190 | 25 / 80 / 85 | 3 | 6 |
| `recover=1 retreat=2 stairs=1` | A | 200 (0) | 6.25 | 6.87 | 3300 | 189 | 26 / 81 / 82 | 3 | 2 |
| HEAD defaults (`C-fix`) | C | 199 (1) | 5.73 | 5.91 | 2072 | 193 | 40 / 79 / 74 | 1 | 1 |
| `recover=1` | C | 199 (1) | 5.86 | 6.38 | 3042 | 191 | 44 / 60 / 87 | 2 | 1 |
| `recover=1 retreat=1` | C | 198 (1; 1 error) | 5.82 | 6.43 | 3071 | 191 | 44 / 61 / 86 | 2 | 0 |
| `recover=1 retreat=2` | C | 199 (1) | 5.95 | 6.44 | 3109 | 191 | 44 / 60 / 87 | 2 | 1 |
| `recover=1 retreat=2 stairs=1` | C | 199 (1) | 5.99 | 6.49 | 3181 | 190 | 44 / 59 / 87 | 2 | 1 |

| A + C, paired | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| `recover=1` − HEAD defaults | 394 | +0.26 | [−0.05, +0.56] | 165 / 112 / 117 |
| `recover=1 retreat=1` − HEAD defaults | 393 | +0.13 | [−0.18, +0.46] | 161 / 98 / 134 |
| **`recover=1 retreat=2` − HEAD defaults** | 389 | **+0.33** | **[+0.02, +0.66]** | 164 / 103 / 122 |
| ... A alone, C alone | 193, 196 | +0.43, +0.24 | [−0.03, +0.87], [−0.23, +0.70] | |
| `recover=1 retreat=2 stairs=1` − HEAD defaults | 392 | +0.32 | [−0.01, +0.65] | 166 / 106 / 120 |
| `recover=1 retreat=1` − `recover=1` | 396 | −0.10 | [−0.28, +0.07] | 48 / 288 / 60 |
| ... A alone, C alone | 199, 197 | −0.16, −0.05 | [−0.41, +0.09], [−0.29, +0.20] | |
| **`recover=1 retreat=2` − `recover=1`** | 391 | **+0.08** | [−0.04, +0.21] | 27 / 347 / 17 |
| ... A alone, C alone | 194, 197 | +0.09, +0.08 | [−0.08, +0.25], [−0.10, +0.26] | |
| `recover=1 retreat=2 stairs=1` − `recover=1 retreat=2` | 392 | −0.01 | [−0.14, +0.12] | 32 / 329 / 31 |

- **Going up from a rage that ran out pays only when the stairs are close.** The rules otherwise go on fighting;
  `retreat` walks there slowed, with whatever is adjacent hitting it on the way. Rage endings with two or more
  hostiles left, A + C, died within 50 turns (and went up within 50 turns):

| stairs up when the rage ran out | `recover=1` | `recover=1 retreat=1` | `recover=1 retreat=2` |
| --- | --- | --- | --- |
| within 8 steps | 95: 49% died (5% went up) | 106: 33% (79%) | 109: 31% (80%) |
| further | 195: 35% (2%) | 201: 42% (42%) | 200: 36% (2%) |
| none known | 23: 65% | 28: 57% | 24: 62% |

  `retreat=1` saves deaths near the stairs and loses more on long walks; `retreat=2` keeps only the first part.
  The 8-step limit was chosen from block A's `retreat=1` games. C alone shows the same (within 8 steps: 45% died
  with `recover=1`, 49 endings; 35% with `retreat=1`, 60; 36% with `retreat=2`, 53), but the limit is tuned, not
  confirmed.
- **The rule touches few games**: 347 of 391 dungeons play the same with and without it. The gain on the others
  (27 deeper, 17 shallower) is real in direction but small: +0.08 overall.
- **Walking to the stairs before a big fight (`stairs=1`) adds nothing** (−0.01; it walked in 100 of the 400
  games, 304 steps in all) and stays off.
- Deaths move rather than vanish, as with `recover` before. A + C, cause table's rules (deaths without a matching
  morgue, and stale games, left out):

| cause | HEAD defaults | `recover=1` | `recover=1 retreat=1` | `recover=1 retreat=2` |
| --- | --- | --- | --- | --- |
| games (mean depth) | 396 (5.81) | 398 (6.04) | 397 (5.93) | 392 (6.14) |
| took the stairs raging or spent, died within 50 turns | 100 (25%) | 27 (7%) | 42 (11%) | 36 (9%) |
| walked into the last fight already spent | 61 (15%) | 76 (19%) | 76 (19%) | 75 (19%) |
| raged in the last fight, the rage ran out first | 124 (31%) | 151 (38%) | 140 (35%) | 131 (33%) |
| died still raging | 51 (13%) | 58 (15%) | 54 (14%) | 61 (16%) |
| killed in melee, never raged | 18 (5%) | 37 (9%) | 38 (10%) | 36 (9%) |
| poisoned; from range or a spell; autofight refused | 13; 10; 6 | 13; 13; 5 | 13; 11; 6 | 14; 14; 7 |
| *not a death*: 1,500 choices on one level; nothing the brain can do | 4; 9 | 5; 13 | 5; 12 | 5; 13 |

  Going up after a rage counts as "took the stairs spent" when the character dies within 50 turns of arriving
  upstairs, which is why that row rises with `retreat` (27 → 36) while "the rage ran out first" falls (151 → 131).
- **Chosen for the fresh blocks: `recover=1 retreat=2`**, the arm furthest ahead of HEAD defaults among those not
  behind `recover=1` (`stairs=1` on top was level, so the simpler arm).

**Pre-registered (written before any game on block J or K).** Configuration: this working tree's code with
`--style recover=1 retreat=2`, no model, no random choices. Baseline: HEAD defaults, the same code with no
switches (the reply fix on, as it is by default; `recover`, `retreat`, `stairs`, `calm`, `teleport` all 0). The
test measures `recover=1` and `retreat=2` together against the defaults, so a pass confirms the pair, not
`retreat=2` alone. 200 games per block from seeds 630000 (block J, 630000–630199) and 640000 (block K,
640000–640199), 9 workers asked (7 accounts log in), one run after another in the order J configuration, J
baseline, K configuration, K baseline. Both blocks are played whatever J shows. Analysis: paired by dungeon over
games both finished (not hung or crashed) and neither stale, where a game is stale if it resumed a save (first step
after turn 1) or was not played on its own seed (no morgue on that custom seed with the game's turn count: the
"Welcome back" games, below); 95% bootstrap over dungeons, 10,000 resamples (`brain-v5g/arms.py`). **Pass: the
pooled J + K interval's lower end is above zero.** Analysed once. Reported alongside, outside the pass rule: each
block, mean depth, XL, deaths by band and the death-cause table.

**Result: does not pass.** `recover=1 retreat=2` is **+0.30 [−0.03, +0.64]** against HEAD defaults on the fresh
blocks J and K (393 dungeons). The lower end is below zero.

| fresh blocks | finished (hung) | mean depth | XL | turns | died | died on D:1–3 / 4–6 / 7+ | stuck at the limit | not on their seed | arrivals raging or spent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| J, HEAD defaults | 200 (0) | 5.42 | 5.55 | 1905 | 192 | 46 / 79 / 67 | 1 | 2 | 56% |
| J, `recover=1 retreat=2` | 200 (0) | 5.85 | 6.49 | 3187 | 191 | 37 / 77 / 77 | 0 | 0 | 5% |
| K, HEAD defaults | 199 (1) | 5.85 | 6.08 | 2122 | 194 | 44 / 74 / 76 | 0 | 2 | 47% |
| K, `recover=1 retreat=2` | 198 (2) | 6.05 | 6.62 | 3191 | 191 | 38 / 76 / 77 | 1 | 1 | 7% |

| `recover=1 retreat=2` − HEAD defaults | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| J | 198 | +0.39 | [−0.08, +0.87] | 77 / 62 / 59 |
| K | 195 | +0.21 | [−0.27, +0.68] | 68 / 60 / 67 |
| **J + K (the pre-registered test)** | 393 | **+0.30** | **[−0.03, +0.64]** | 145 / 122 / 126 |

| cause, J + K (the cause table's rules) | HEAD defaults | `recover=1 retreat=2` |
| --- | --- | --- |
| games (mean depth) | 395 (5.64) | 397 (5.95) |
| took the stairs raging or spent, died within 50 turns | 97 (25%) | 40 (10%) |
| walked into the last fight already spent | 63 (16%) | 85 (21%) |
| raged in the last fight, the rage ran out first | 121 (31%) | 149 (38%) |
| died still raging | 53 (13%) | 59 (15%) |
| killed in melee, never raged | 19 (5%) | 21 (5%) |
| poisoned; from range or a spell; autofight refused | 21; 4; 5 | 11; 8; 8 |
| *not a death*: 1,500 choices on one level; nothing the brain can do | 1; 11 | 1; 15 |

- Outside the test, as described: on J + K, rage endings with two or more left and stairs up within 8 steps died
  within 50 turns 37% of the time with the chosen arm (120 endings, 76% went up) against 55% under the defaults
  (82); further from the stairs, 38% against 43%. The arms differ by `recover=1` too, so this is not `retreat`'s
  alone.
- **What it says about `recover=1` as a default.** By the pre-registered standard, not settled. Every comparison of
  arms with `recover=1` against the same code without it has come out ahead (+0.26 on A + C, +0.24 before the seed
  check; +0.33 on A + C and +0.30 here with `retreat=2`), none has cleared zero on fresh blocks on its own, and the
  one fresh test that cleared zero
  (H + I) measured it together with the reply fix. At this spread (half-width about 0.33 on 393 dungeons) a true
  gain of +0.3 would need about 1,000 paired dungeons to pass four times in five (inferred from the interval's
  width, not simulated).
- No stale save, and 5 games not on their seed in all, on J and K. `retreat=1`, `retreat=2` and `stairs=1` stay
  off by default.
- **Verified**: every count and table in this section; that the switches off replay HEAD defaults (11 of 11 games
  on their seed in both runs; unit tests); that each wrong-dungeon game is one whose protocol says "Welcome back"
  and whose morgue has a random seed (all runs here); that `retreat` goes up, fights what followed and rests (smoke
  games, step logs); the tests (`uv run pytest`, `uv run ruff check`).
- **Inferred**: that qw's lower death rate after a rage comes from where and when it flees (it plays other dungeons
  and has more tools: throwing, wands, tactical steps); that the throwaway save survives because `quit_game` doesn't
  answer a yes/no; that the 8-step limit generalises (chosen on block A); the dungeon count above.
- Blocks J (630000–630199) and K (640000–640199) are now spent. Runs: `runs/brain/v5/games/{A,C}-fix-rec1-ret`,
  `-fix-rec1-ret2`, `-fix-rec1-ret2-st`, `{J,K}-rec1-ret2`, `{J,K}-defaults`; smoke games in `runs/brain/v5g/smoke/`.
  Scripts in the job's `brain-v5g/` scratch directory: `events.py`, `summ.py`, `summ2.py`, `distinguish.py`,
  `qw_rage.py` (step 1); `arms.py`, `seeds.py`, `welcome.py`, `mindex.py`, `refresh.sh` (pairing and the seed
  check); `triggers.py`, `retreat_split.py`, `retreat_pool.py`, `stairs_check.py`, `show.py` (what the rules did);
  copies of `gather.py`, `flags.py`, `causes.py`; `chain.sh`, `after.sh` and the job files; the copied morgues.

#### The wrong dungeon fixed, and a larger replication of `recover=1 retreat=2` (2026-11-15)

**Summary.**

- **The replication passes: `recover=1 retreat=2` is +0.45 [+0.24, +0.65] deeper than HEAD defaults** on 996 fresh
  dungeons (seeds 650000–650999, pre-registered below). All five blocks of 200 are ahead (+0.18 to +0.58); three
  clear zero on their own. Mean depth 5.97 against 5.53, XL 6.53 against 5.83. The defaults are not changed here:
  that is the orchestrator's call (what would change is listed at the end).
- **The wrong dungeon is fixed at the root.** The quit of the throwaway game returned before the game had taken
  the word "quit" (a dcss-api read that returns at once), the socket closed, and the server saved the game instead;
  the next seeded start resumed it. `quit_game` now waits for the game to end, and a guard refuses to record any game
  whose opening doesn't say it is a new game on its seed. In 2,042 games since, none was off its seed or stale, and
  the guard never had to act.

**The wrong dungeon, traced.** The suspicion above was wrong: a brand-new character's Ctrl-Q asks for the typed
word "quit" too, and `quit_game` typed it. What went wrong came after. `quit_game` then waited for the lobby with
`read_until("go_lobby")`, and that read returned at once: dcss-api 0.4.1 (`read_until` in its `lib.rs`) marks the
awaited message found when it sees it in a frame, raises if the same frame also holds a prompt, and leaves the mark
set, so the next `read_until`, whatever it waits for, returns at once. The Ctrl-Q read stopped at the text prompt in
a frame that also held an `input_mode`, so the quit returned about a millisecond after the last key was sent, and
`_clear_save` closed the socket. Webtiles hangs up on a game whose socket closes; if DCSS has not yet taken the
typed word, it saves the game instead of ending it. The next seeded start resumed that turn-0 save ("Welcome back"),
on its random dungeon. A race, so it depends on load: one account in seven lost it when seven throwaways were quit
at once (live, recorded), 6 of 7 in `A-fix-rec1-ret2`, none when one account was quit alone. Shown live: the
throwaways that kept a save left no morgue (the ones that quit leave a turn-0 morgue), a `.cs` file was left in the
server's `saves/`, and a `read_until` for a message that never comes returned at once in that state.

- **The fix** (`Connection.quit_game` and the new `Connection.wait_game_end`, `src/ladder/conn.py`): after the
  word, answer the screens a quit shows, one prompt at a time (a --more--, the inventory menu, a --more-- over the
  "game-over" summary), and return only once the server sends `game_ended` or `go_lobby`; after the summary, wait
  for the lobby rather than another prompt, since a game that exits asks for nothing more. It returns whether the
  game ended. This also covers every quit at the choice or turn limit (`selfplay._play`, `games.run`), which had
  the same race.
- **The guard** (`selfplay.not_on_seed`, called in `selfplay._play`): a game counts as started on its seed only if
  its opening messages say "Game seed: <seed> (custom seed)" and not "Welcome back". Otherwise `StaleSave` is
  raised, the save is quit and the game started again once; if that fails too the game is recorded as an error,
  never as that seed. A restart is kept in `results.json` as `restarted`.
- **Tests**: `tests/test_conn.py` (a fake of dcss-api 0.4.1's `read_until`, mark included, playing the recorded
  quit screens; the old `quit_game` fails it), `tests/test_brain.py` (`not_on_seed`; a turn-0 "Welcome back" start
  raises `StaleSave` in `_play`).
- **Live**: 70 throwaway quits on 7 accounts at once (10 rounds), then a seeded start on each: 70 new games on
  their seed, no save left on the server (a first version that waited for a prompt after the summary hung once in
35 quits; hence the wait for the lobby). Three self-play runs of 14 games on training seeds (470000–470013,
470100–470113, 470200–470213, the last with `recover=1 retreat=2`; 21 first
  games of an account in a run, one game quit at the limit): 42 of 42 on their seed by the protocol, the step log
  and the morgue; the guard never had to restart a game; no save left.

**Pre-registered (written before any game on seeds 650000–650999).** This is a replication of the J + K test
above, unchanged, on a larger fresh sample. Configuration: this working tree's code after the wrong-dungeon fix
(below), `--style recover=1 retreat=2`, no model, no random choices. Baseline: the same code with the default
style (no switches: `recover`, `retreat`, `stairs`, `calm`, `teleport` all 0; the reply fix on). Dungeons: seeds
650000–650999 (1,000 dungeons, never used before), played as five blocks of 200 (650000, 650200, 650400, 650600,
650800), each block by both arms one run after the other, the arm that goes first alternating from block to block
so that machine conditions balance; 9 workers asked, the accounts that log in play (the ones that fail are not
repaired). Analysis: paired by dungeon over games both finished (not hung, crashed or an error) and neither stale
nor off its seed (a game is stale if its first step is after turn 1; off its seed if no morgue on that custom seed
with the game's turn count exists); 95% bootstrap over dungeons, 10,000 resamples; analysed once, after all games
are played, with no early stopping. **Pass: the interval's lower end is above zero** (all five blocks pooled). J
and K are not pooled into the pass decision; a pooled J + K + new figure may be reported, as description only.
Reported alongside, outside the pass rule: mean depth, XL, deaths by depth band, the death-cause table, the counts
of wrong-seed and stale games (expected zero), and each block's difference.

**Result: passes.** `recover=1 retreat=2` is **+0.45 [+0.24, +0.65]** against HEAD defaults on 996 dungeons (the
four left out are the 5 hung games' dungeons; one dungeon hung in both arms). Analysed once, after all 2,000 games.

| arm, blocks R1–R5 (650000–650999) | finished (hung) | mean depth | XL | turns | died | died on D:1–3 / 4–6 / 7+ | stuck at the limit | not on their seed | stale |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HEAD defaults | 997 (3) | 5.53 | 5.83 | 2069 | 965 | 224 / 408 / 333 | 5 | 0 | 0 |
| `recover=1 retreat=2` | 998 (2) | 5.97 | 6.53 | 3218 | 960 | 204 / 338 / 418 | 9 | 0 | 0 |

| `recover=1 retreat=2` − HEAD defaults | first arm played | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- |
| R1 (650000–650199) | `recover=1 retreat=2` | 199 | +0.40 | [−0.05, +0.85] | 72 / 64 / 63 |
| R2 (650200–650399) | defaults | 200 | +0.18 | [−0.27, +0.64] | 76 / 58 / 66 |
| R3 (650400–650599) | `recover=1 retreat=2` | 199 | +0.55 | [+0.10, +1.02] | 81 / 55 / 63 |
| R4 (650600–650799) | defaults | 199 | +0.58 | [+0.14, +1.03] | 78 / 60 / 61 |
| R5 (650800–650999) | `recover=1 retreat=2` | 199 | +0.54 | [+0.06, +1.00] | 80 / 59 / 60 |
| **R1–R5 (the pre-registered test)** | | 996 | **+0.45** | **[+0.24, +0.65]** | 387 / 296 / 313 |
| *J + K + R1–R5, description only* | | 1,389 | +0.41 | [+0.23, +0.59] | 532 / 418 / 439 |

Per block, mean depth (defaults → chosen arm): R1 5.44 → 5.83, R2 5.53 → 5.71, R3 5.65 → 6.18, R4 5.55 → 6.12, R5
5.48 → 6.03. The arm that played first made no visible difference (+0.50 when the chosen arm went first, +0.38 when
the defaults did, each well inside the other's noise).

| cause, R1–R5 (the cause table's rules) | HEAD defaults | `recover=1 retreat=2` |
| --- | --- | --- |
| games (mean depth) | 997 (5.53) | 998 (5.97) |
| took the stairs raging or spent, died within 50 turns | 239 (24%) | 95 (10%) |
| walked into the last fight already spent | 172 (17%) | 183 (18%) |
| raged in the last fight, the rage ran out first | 291 (29%) | 374 (37%) |
| died still raging | 139 (14%) | 146 (15%) |
| killed in melee, never raged | 56 (6%) | 88 (9%) |
| poisoned; from range or a spell; autofight refused | 36; 17; 15 | 36; 20; 18 |
| *not a death*: 1,500 choices on one level; nothing the brain can do | 5; 27 | 9; 29 |

- **The gain is the same one as before, now clearly above zero.** Going down the stairs raging or exhausted and
  dying there falls from 24% of games to 10%; the deaths move a level or two deeper, mostly to fights where the rage
  runs out first (29% → 37%) and to melee without a rage (6% → 9%), as on A + C and J + K. Deaths on D:7 and below
  rise from 333 to 418 because more characters get there.
- **Settled**: J + K (+0.30 [−0.03, +0.64]) was not a miss of a null effect but a sample too small for it; this
  sample, two and a half times larger, gives a narrower interval (half-width 0.21) and a similar mean.
- No game on the wrong dungeon, no stale save, and no restart by the guard in the 2,000; 5 games hung mid-game
  (exploring), all on their seed, and are left out as the rule says.
- **Verified**: every number in the tables (`brain-v5h/arms.py`, `pooled.py`, `gather.py`, `causes.py`); each game's
  seed three ways (`verify.py`: the protocol's greeting, the first step's turn, the morgue); J and K re-scored with
  the same scripts give their earlier figures exactly; the traced cause and the fix (live recordings, dcss-api's
  source, the server's save files and morgues); the tests (`uv run pytest`, `uv run ruff check`).
- **Inferred**: that DCSS saves rather than ends a game hung up on before it has taken the typed word (seen as a
  save left behind and no morgue; not read in DCSS's source); that the first-played arm doesn't matter (5 blocks).
- Seeds 650000–650999 are now spent. Runs: `runs/brain/v5h/R{1..5}-{defaults,rec1-ret2}` and
  `runs/brain/v5h/verify{1,2,3}`. Scripts in the job's `brain-v5h/` scratch directory: `trace_quit.py`,
  `par_clear.py`, `par_quit.py`, `par_rounds.sh`, `golobby*.py`, `head.py` (the trace); `verify.py`, `seeds.py`,
  `refresh.sh`, `mindex.py` (seed checks); `arms.py`, `pooled.py`, `gather.py`, `flags.py`, `causes.py` (analysis);
  `chain.sh` and the job files.

**What turning them on would change** (not done; for the orchestrator to decide):

- `src/ladder/brain/policy.py`, `Style`: `recover: float = 0.0` → `1.0` and `retreat: float = 0.0` → `2.0`, and
  their comments' "Off by default". That changes every game played without `--style`: self-play, `evaluate`, the
  cockpit's `--brain`, and the rules of thumb a model falls back on (so also the "what the rules would do" field
  in new step logs).
- Tests that pin the defaults and fail with the flip (tried, then put back): `test_recover_is_off_by_default`,
  `test_recover_switch_is_a_style_and_old_runs_still_match`, `test_retreat_and_stairs_are_off_by_default_and_play_as_before`
  (`tests/test_brain.py`); the other 456 pass.
- Saved runs: `cli.evaluate` reuses a saved run when `{**Style().to_dict(), **saved_style}` equals the style asked
  for, so a key missing from a saved run is read as today's default. Runs saved before `recover` or `retreat`
  existed (played with 0) would then be read as played with 1 and 2, and reused wrongly. Runs saved since carry
  `recover: 0.0` and `retreat: 0.0` and would be replayed, which is right. The safe change is to fill missing keys
  with the value they had when the key was added (0 for both), not with the current default.

#### New default rules, and a model retrained on clean games (2026-11-15, morning)

**Summary.**

- **For the first time a model beats the rules of thumb in a pre-registered test: `v6-clean3` at `margin=0.6` is
  +0.14 [+0.06, +0.23] deeper than the new default rules alone on 600 fresh dungeons** (seeds 660000–660599; 54
  deeper, 521 the same, 25 shallower). It does it by leaving the rules at 0.1% of choices, almost all to read
  teleportation when spent after a rage, hurt and facing several dangerous monsters. 97% of the gain is in the
  games where it did that. `models/brain.json` is not replaced; that is the orchestrator's call.
- **The new rules are the defaults**: `recover=1 retreat=2` (`Style`), with saved runs that lack the keys read as
  played with them off (`Style.saved`). With no `--style`, block A replays the saved `recover=1 retreat=2` games
  exactly (every game that was on its seed in both runs: 8 of 8 in 14, 193 of 194 in 200).
- **The champion (`iter2`) hurts on top of the new rules at its default margin**: −0.30 [−0.65, +0.04] on A + C,
  mostly by going for the stairs instead of resting out a rage (`rest → descend`, 4,000+ times a block), which
  undoes `recover`. At `margin=1.0` it is +0.08 [−0.05, +0.21], again from teleport reads. So `--brain` with the
  champion at its default margin should not be used over the new rules.
- **A clean corpus**: 2,600 self-play games played with today's code and rules (no reply lag, no wrong dungeon,
  live sight fields on every row: no `reobserve`), 1.36M rows. Trained on it alone, the `s12` recipe predicts
  death and depth better than any earlier model on held-out clean games, and its bias toward the stairs is a third
  of the version 5 models'. At the default margin it still dives and loses (−0.28 on A + C); adding the old
  corpus makes it worse (−0.53).
- A bug found on the way: a map cell's `bg` can come as a pair of numbers (flags past 32 bits), and
  `state.in_view` raised on it (1 game in 2,000). Fixed.

**The defaults** (`src/ladder/brain/policy.py`, `src/ladder/brain/cli.py`; tests in `tests/test_brain.py`).
`Style.recover` is 1 and `Style.retreat` 2 by default; `--style recover=0 retreat=0` plays the rules as before (the
tests pin both). `Style.saved(d)` is the style a saved run was played with: a key missing from it takes the value it
had when it was added (`STYLE_ADDED_AS`: `recover` 0, `retreat` 0; every other key's default has never changed),
and `cli.evaluate` compares with that, so an old run saved without the keys is not reused for today's defaults. No
other place reloads a saved style: self-play writes the full style into each run, the corpus reads the logged
`baseline` action, and training's `Style().weights()` takes only outcome weights (unchanged). The cockpit's and
`games.py`'s `--brain` and fork continuations take the current defaults, which is intended.

**Task: does the champion help on top of the new rules?** Blocks A (500000–500199) and C (540000–540199), both
tuning blocks for the rules, so description only. All games with this tree's code, no random choices; paired by
dungeon over games both finished and neither stale nor off its seed; 95% bootstrap, 10,000 resamples.

| arm | A: mean depth | C: mean depth | XL (A, C) | turns (A, C) | leaves the rules | commonest changes | − new rules, A + C | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| new default rules (`recover=1 retreat=2`) | 6.29 | 5.93 | 6.89, 6.43 | 3367, 3092 | | | | | |
| champion `iter2`, `margin=0.25` | 5.89 | 5.71 | 6.10, 6.01 | 2184, 2184 | 17.8% | `quaff_unknown` → `descend` 16,070, `rest` → `descend` 8,358, `wear` → `descend` 8,102 | −0.30 | [−0.65, +0.04] | 142 / 95 / 162 |
| champion `iter2`, `margin=1.0` | 6.36 | 6.02 | 6.92, 6.52 | 3391, 3171 | 0.1% | `fight` → `read_teleport` 160, `flee_up` → `read_teleport` 21 | +0.08 | [−0.05, +0.21] | 39 / 335 / 24 |

A alone, C alone: −0.40 [−0.89, +0.07] and −0.20 [−0.68, +0.29] at the default margin; +0.07 [−0.10, +0.24] and
+0.09 [−0.11, +0.29] at 1.0. At its default margin the champion arrives on a new floor raging or spent at 32% of
arrivals (the new rules 9%), so it takes back most of what `recover` gave. At 1.0 all of its gain is in the 107
games where it read teleportation (+0.32 each).

**The clean corpus** (`runs/brain/v5i/clean/`, training seeds only, 12 workers asked, 10 accounts play).

| round | seeds | games | who plays | random choices | rows | choices left to the model |
| --- | --- | --- | --- | --- | --- | --- |
| 0 | 100000–101999 | 2,000 | the new default rules | `--epsilon 0.2` (14% of rows) | 1,116,249 | |
| 1 | 110000–110599 | 600 | `v6-r03` (round 0's `s12` ensemble, seeds 0–2), `margin=0.25` | `--epsilon 0.2` | 247,417 | 8.4% (`quaff_unknown` → `descend` most) |
| all | | 2,600 (2,535 deaths) | | | **1,363,666** (277,731 held out by dungeon) | |

The version 5 corpus had 3,333 games (about 1,170 self-play games, the rest forks) and 810,581 rows. Cut, for time:
forks (each costs about one game; earlier forks changed nothing) and further rounds. Every row has live sight
fields (1,363,666 live, 0 from sidecars, 0 missing), so `reobserve` is not needed for new games. Every game's
protocol greets its own seed and none resumed a save; 1 game errored (the `bg` bug, fixed during the round) and 3
hung. The round-0 models are in the job's scratch directory, not in `models/`.

**Offline**, on the clean corpus's held-out games (277,731 rows; default value `depth_end − died_soon` of the
action taken; true value mean 2.69, 4.3% of rows die within 30 turns). `v6-clean` is trained on the clean corpus
alone; `v6-mix` on the clean corpus and the version 5 corpus together (2.17M rows; the held-out rows are the same).

| model | R² died_soon | AUC died_soon | R² depth_end | danger AUC | value: mean pred − true | slope (true on pred) | true value in the lowest / highest fifth of predictions |
| --- | --- | --- | --- | --- | --- | --- | --- |
| champion `iter2` (version 4) | 0.252 | 0.868 | 0.118 | 0.782 | −0.32 | 0.95 | 1.31 / 3.76 |
| `v5-seen` | 0.251 | 0.871 | 0.139 | 0.780 | −0.29 | 0.94 | 1.26 / 3.85 |
| `v5-ens5` | 0.297 | 0.894 | 0.159 | 0.789 | −0.25 | 1.07 | 1.18 / 3.86 |
| `v5-forks3` | 0.315 | 0.898 | 0.184 | 0.800 | +0.05 | 1.09 | 1.07 / 3.86 |
| `v6-clean` seeds 0 / 1 / 2 | 0.309 / 0.307 / 0.308 | 0.900 / 0.895 / 0.888 | 0.195 / 0.200 / 0.199 | 0.812 / 0.809 / 0.816 | −0.16 / −0.01 / −0.09 | 1.00 / 0.93 / 0.96 | |
| **`v6-clean3`** (ensemble) | **0.328** | **0.911** | 0.206 | **0.819** | −0.09 | 0.99 | 1.00 / 3.92 |
| `v6-mix` seeds 0 / 1 / 2 | 0.305 / 0.310 / 0.307 | 0.903 / 0.896 / 0.895 | 0.202 / 0.197 / 0.204 | 0.808 / 0.808 / 0.812 | −0.06 / −0.09 / −0.02 | 0.97 / 1.05 / 0.97 | |
| `v6-mix3` (ensemble) | 0.325 | 0.907 | **0.208** | 0.815 | −0.06 | 1.03 | 0.99 / 3.94 |

Preference for `descend` over `explore` at the 19,577 moments of the new rules' block-A games where the rules
explored with the stairs known (`gap.py`):

| model | value gap | above 0.25 | above 0.6 |
| --- | --- | --- | --- |
| champion `iter2` | +0.11 | 9.5% | 0.1% |
| `v5-seen` / `v5-ens5` | +0.30 / +0.20 | 64% / 28% | 1.8% / 0.1% |
| `v6-clean` seeds 0 / 1 / 2 | +0.08 / +0.19 / +0.06 | 8% / 30% / 4% | 0.1% / 0.2% / 0% |
| `v6-clean3` / `v6-mix3` | +0.11 / +0.12 | 9.5% / 4.4% | 0% / 0% |

- The clean models are the best predictors yet on clean games (in their own distribution, which favours them),
  and the two ensembles are nearly unbiased in value. The old corpus adds nothing offline.
- The seed still moves the stairs bias (+0.06 to +0.19), and the ensembles keep a positive one, about the
  champion's. No fork rows exist in the clean corpus, so fork regret was not measured.

**Tuning on A and C** (each ensemble at three margins against the new rules alone; the same rules as above).

| arm | A: mean depth | C: mean depth | leaves the rules (A, C) | commonest changes | − new rules, A + C | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `v6-clean3`, `margin=0.25` | 6.02 | 5.63 | 5.2%, 4.7% | `explore` → `descend` 2,761, `fight` → `descend` 2,711, `rest` → `descend` 1,523, `fight` → `flee_up` 1,354 | −0.28 | [−0.55, −0.02] | 121 / 140 / 138 |
| **`v6-clean3`, `margin=0.6`** | **6.56** | **6.04** | 0.1%, 0.1% | `fight` → `read_teleport` 136, `explore` → `descend` 34, `flee_up` → `read_teleport` 26 | **+0.19** | **[+0.05, +0.33]** | 41 / 344 / 14 |
| `v6-clean3`, `margin=1.0` | 6.41 | 5.94 | 0.03%, 0.03% | `fight` → `read_teleport` 67, `flee_up` → `read_teleport` 12 | +0.07 | [+0.03, +0.12] | 13 / 384 / 2 |
| `v6-mix3`, `margin=0.25` | 5.46 | 5.67 | 11.1%, 10.4% | `quaff_unknown` → `descend` 4,641, `berserk` → `fight` 4,850, `wield` → `descend` 2,788 | −0.53 | [−0.91, −0.17] | 142 / 81 / 175 |
| `v6-mix3`, `margin=0.6` | 6.37 | 5.88 (9 hung) | 0.8%, 1.2% | `wield` → `descend` 2,583, `fight` → `read_teleport` 59 | +0.06 | [−0.12, +0.25] | 55 / 287 / 49 |
| `v6-mix3`, `margin=1.0` | 6.33 | 5.91 | 0.01%, 0.01% | `read_teleport` from several, 25 in all | +0.01 | [−0.03, +0.05] | 6 / 390 / 3 |

`v6-clean3` at 0.6, A alone +0.27 [+0.09, +0.46], C alone +0.11 [−0.09, +0.31]. Split by game: the 102 games where
it read teleportation instead of the rules' choice gain +0.73 each, 99% of the gain; the 293 with no override play
the same. At 1.0 the same, fewer (65 games, +0.42 each). `v6-mix3` at 0.6 gains in its teleport games (+1.02 each)
and loses it again in the games where it skips wielding for the stairs (−0.71 each), an override that repeats
because the rules offer `wield` again at every choice. C's 9 hangs in that run are one burst (seeds 540050–540068).

`v6-clean3`'s teleport reads (A + C, 180): the rules would have fought (136), gone up (26) or drunk a potion (10);
138 were spent after a rage (`-Berserk` and `Slow`, the plain `teleport=1` rule's condition), at median 42% HP
(100 under half), median 3 hostiles in view, a monster of threat 2 or 3 in view in 166, around D:8 and XL 8. The plain
rule reads at every spent moment with monsters in view, whatever the HP and the threat, and was level on fresh
blocks F and G (with the old rules and the reply lag). The model is choosier.

**Pre-registered (written before any game on seeds 660000–660599).** Configuration: this working tree's code
(the default rules are now `recover=1 retreat=2`, and `state.in_view` reads a two-part `bg`), playing the model
`models/v6-clean3.json` (the `s12` recipe at training seeds 0–2 on the clean corpus only, outputs averaged) with
`--style margin=0.6`, no random choices. Baseline: the same code with no model and the default style (the new
default rules alone). Dungeons: seeds 660000–660599 (600, never used before), played as three blocks of 200
(660000, 660200, 660400), each block by both arms one run after the other, the arm that goes first alternating
from block to block (configuration first on 660000 and 660400, baseline first on 660200); 12 workers asked, the
accounts that log in play (the two that fail are not repaired). Analysis: paired by dungeon over games both
finished (not hung, crashed or an error) and neither stale nor off its seed (stale: its first step is after
turn 1; off its seed: no morgue on that custom seed with the game's turn count); 95% bootstrap over dungeons,
10,000 resamples (`brain-v5i/arms.py`); analysed once, after all 1,200 games are played, with no early stopping.
**Pass: the interval's lower end is above zero.** Reported alongside, outside the pass rule: each block's
difference, mean depth, XL, deaths by depth band, override rate and what is overridden. Chosen because it is the
furthest above zero on the tuning blocks A + C of the configurations tried (+0.19 [+0.05, +0.33], tables below);
`models/brain.json` is not replaced whatever the result.

**Result: passes.** `v6-clean3` at `margin=0.6` is **+0.14 [+0.06, +0.23]** deeper than the new default rules alone
on 600 fresh dungeons, all 600 paired (no game hung, stale or off its seed). Analysed once, after all 1,200 games.

| fresh blocks (660000–660599) | finished (hung) | mean depth | XL | turns | died | died on D:1–3 / 4–6 / 7+ | leaves the rules |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1, new rules | 200 (0) | 5.96 | 6.54 | 3122 | 194 | 36 / 76 / 82 | |
| F1, `v6-clean3` `margin=0.6` | 200 (0) | 6.22 | 6.75 | 3192 | 195 | 34 / 72 / 89 | 0.10% |
| F2, new rules | 200 (0) | 5.75 | 6.41 | 3070 | 195 | 48 / 75 / 72 | |
| F2, `v6-clean3` `margin=0.6` | 200 (0) | 5.80 | 6.46 | 3126 | 195 | 48 / 75 / 72 | 0.08% |
| F3, new rules | 200 (0) | 5.72 | 6.33 | 2917 | 196 | 46 / 80 / 70 | |
| F3, `v6-clean3` `margin=0.6` | 200 (0) | 5.83 | 6.43 | 3033 | 196 | 46 / 75 / 75 | 0.07% |

| `v6-clean3` `margin=0.6` − new rules | first arm played | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- |
| F1 (660000–660199) | the model | 200 | +0.27 | [+0.12, +0.43] | 25 / 170 / 5 |
| F2 (660200–660399) | the rules | 200 | +0.05 | [−0.10, +0.21] | 11 / 176 / 13 |
| F3 (660400–660599) | the model | 200 | +0.12 | [−0.03, +0.26] | 18 / 175 / 7 |
| **F1–F3 (the pre-registered test)** | | 600 | **+0.14** | **[+0.06, +0.23]** | 54 / 521 / 25 |

- **What it overrides** (346 of 412,201 choices): `fight` → `read_teleport` 212, `flee_up` → `read_teleport` 32,
  `explore` → `descend` 44, `quaff_heal` → `read_teleport` 17, `wait` → `read_teleport` 9. Split by game: the 173
  games with a teleport read gain +0.49 each (97% of the gain; 51 deeper, 24 shallower), the 17 with only other
  overrides +0.29 each, and 409 of the 410 with no override play the same game.
- **The moments** (279 teleport reads): spent after a rage in 229, median HP 48% (145 under half), median 4 hostiles
  in view, a monster of threat 2 or 3 in 258, median D:8, XL 8, as on the tuning blocks. 33 were read while a teleport
  was already coming (`Tele`), which wastes the scroll; the plain rule doesn't, the model's `available` allows it.
- Read with care: the gain is small (one dungeon in eleven is deeper, one in twenty-four shallower) and comes from
  one kind of choice the rules lack, not from the model's estimate in general (at the default margin the same
  model loses). That fits "use the network only where it is confident and mine its overrides for rules" (Next,
  3(b)).
- **Verified**: every number in this section (`brain-v5i/arms.py`, `overrides.py`, `attrib.py`, `teleports.py`,
  `offline.py`, `gap.py`; the batched forward pass matches `TrainedNet.forward` within 2e-6); each fresh game's seed
  three ways (`verify.py`); the default style replaying the saved `recover=1 retreat=2` games (14 and 200 on block A:
  every game on its seed in both runs identical, but one in 194); the `bg` bug (the game's protocol; a test with the
  live value); the tests (`uv run pytest`, `uv run ruff check`).
- **Inferred**: that the gain comes from the teleport reads (an attribution by game, not a test of the reads alone);
  that the clean data is why this model's confident overrides help where the champion's at `margin=1.0` were level
  (+0.08 on A + C; never tested fresh); that the model's narrower teleport moments are why it works where the plain
  rule didn't (the plain rule was tested with the old rules and the reply lag).
- Seeds 660000–660599 are now spent. Runs: `runs/brain/v5i/{A,C}-rules`, `-brain`, `-brain-m1`, `-v6-{clean,mix}-m{0.25,0.6,1.0}`,
  `F{1,2,3}-rules`, `F{1,2,3}-v6-clean-m0.6`, `A14-default` (the replay check); the clean corpus's games in
  `runs/brain/v5i/clean/`, its corpus `runs/brain/v5i/corpus-clean.npz` and the merged one `corpus-mix.npz`. Models:
  `models/v6-clean-s{0,1,2}.json`, `v6-clean3.json` (manifest), `models/v6-mix-s{0,1,2}.json`, `v6-mix3.json`, each
  member with its parity file. Scripts in the job's `brain-v5i/` scratch directory: `chain.sh` and the `jobs-*.txt`
  files, `build_train.sh`, `train3.py`, `merge.py`, `offline.py`, `check_offline.py`, `gap.py`, `overrides.py`,
  `attrib.py`, `teleports.py`, `same.py`, `usedseeds.py`, and copies of `arms.py`, `seeds.py`, `verify.py`,
  `refresh.sh`, `mindex.py`; the round-0 models in `brain-v5i/models/`.

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

`recover=1` (**on by default since 2026-11-15**) rests out a rage and the exhaustion after it (`Berserk`,
`-Berserk` or `Slow`, `policy.recovering`) with nothing in view before taking the stairs; `recover=2` before
exploring on as well; `--style recover=0` turns it off. `retreat=2` (**on by default since 2026-11-15**) goes up
stairs within 8 steps when a rage runs out with two or more hostiles in view, then rests the exhaustion off;
`retreat=1` at any distance, `retreat=0` off. Together they passed a pre-registered test on 996 fresh dungeons
(+0.45 [+0.24, +0.65]; "The wrong dungeon fixed", above). `--style recover=0 retreat=0` plays the rules as they
were before. A saved run whose style lacks either key was played with it at 0, and `evaluate` reads it so
(`Style.saved`, `STYLE_ADDED_AS`).

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
| `src/ladder/brain/policy.py` | `available`, `baseline`, `baseline_wiki`, `teleport_rule`, `recovering`, `foe_hp`, `big_fight`, `Style`, and `BrainTiers` (with `fight_moves` for the opt-in fight rules), which sits in Reflex where `StubTiers` did |
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
| `models/v6-*.json` | trained on clean games (2026-11-15): `v6-clean3` (clean corpus only) and `v6-mix3` (clean + version 5 corpus) are manifests of three seeds each; `v6-clean3` at `margin=0.6` passed a fresh test |
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
   *Diagnosis (2026-11-14, night; "Where the rules of thumb lose games"): the rules lose fights qw survives
   at the same level and depth, mostly once a rage has run out with monsters left. A rage blocks explore
   and sends the rules down the stairs spent; resting it out first (`recover=1`) is +0.29 [−0.01, +0.59] on
   the tuning blocks and is the next fresh-block candidate. Then: fix the staircase dead end (5, below), and
   retreat up the stairs when a rage runs out mid-fight.*
   *(2026-11-15) The staircase fix and `recover=1` together pass on fresh blocks H and I (+0.43 [+0.12,
   +0.75]). A rage running out mid-fight is now 43% of all endings: retreating then is next.*
   *(2026-11-15, later) Retreating up close stairs (`retreat=2`) with `recover=1` is +0.30 [−0.03, +0.64] on fresh
   blocks J and K: not a pass. Going up pays only within about 8 steps, and few rage endings are that close. Next,
   cheapest first: (a) fix the throwaway save that the first game of a run resumes (`quit_game` and a yes/no; or
   `StaleSave` on "Welcome back"); (b) a larger fresh test for `recover=1` alone against HEAD defaults (about 1,000
   dungeons for a +0.3 gain); (c) more to do in the fight itself, since the deadly rages are the ones begun against
   more HP than the character has, and neither rage timing nor stairs fixes those.*
   *(2026-11-15, night) (a) done: the quit now waits for the game to end, and a guard checks every start's seed.
   Instead of (b), `recover=1 retreat=2` was replicated unchanged on 1,000 fresh dungeons and passes (+0.45 [+0.24,
   +0.65]). Next: decide on the defaults (fill missing style keys in saved runs with 0 first), then (c).*
   *(2026-11-15, morning) Done: `recover=1 retreat=2` are the defaults (`Style.saved` reads old runs as played with
   0). A model trained only on clean games, `v6-clean3` at `margin=0.6`, passes a pre-registered fresh test against
   the new rules (+0.14 [+0.06, +0.23], 600 dungeons), all but 3% of it from reading teleportation when spent, hurt
   and outnumbered. Next, cheapest first: (a) decide whether `--brain` plays `v6-clean3` at `margin=0.6` (the
   champion at its default margin is behind the new rules); (b) don't let `read_teleport` be chosen while a teleport
   is already coming (`Tele`: 33 of the 279 fresh reads); (c) write the model's teleport moments down as a rule
   (spent, HP under about half, 3+ hostiles with one of threat 2–3) and test it against the model on fresh seeds,
   since the plain `teleport=1` failed with the old rules; (d) more clean rounds with the new model playing, and
   forks on them, to see if the default margin can be trusted again; then (c) of the earlier list, more to do in
   the fight.*
4. **Promote on more than 60 dungeons.** Differences under 0.3 depths can't be seen with 60; the same
   baseline replayed varies by 0.1. 200 evaluation dungeons would take about 15 minutes per model.
5. **The remaining dead ends**: games that hang (1 in 20 with random choices in round 4, 1 in 40
   without), unreachable stairs,
   "You can't go down here!".
   *(2026-11-15) "You can't go down here!" is fixed (the reply a key behind, after a typed-ahead cancel), and
   with it most hangs (9 → 1 on A and C). Left: about 1 game in 100 at the choice limit, pacing between
   `explore` and `fight` with a monster that steps in and out of view, or nothing possible.*
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
