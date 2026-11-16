# The trained brain

A small neural network, trained on this machine from the ladder's own games, that chooses Reflex's
next action. It is not a language model and makes no API calls: it reads numbers about the moment and
runs in numpy in well under a millisecond. It is the same idea as the trained brain in
`~/Code/s1-battle`, moved to a game that can't be forked.

## Where it stands

**2026-11-15, late night: no game can be played until the game server has disk space.** The Docker VM's disk is full
(98 GB; 51 GB of it the self-play accounts' ttyrecs, which nothing reads), and every game since about 22:53 hangs at its
start; this is also what hung the last section's forks (all in its final two minutes). Before that, the fights the rules
start were counted on 998 games of today's defaults, and two opt-in switches were built for the largest pools:
`--style avoid=k` (read teleportation instead of starting a rage against k times the character's maximum HP: at 1.5,
346 rages in 212 games, 26% followed by death) and `--style retreat=3` (go up close stairs from a fight met while
exhausted: 348 fights in 262 games, 26% died in them). Untested in play; no default changed. Section "The fights the rules
start", below.

**2026-11-15, night: stepping out of fire and away from what can't be seen passes a pre-registered fresh test.** A
re-diagnosis of the current rules found that a game in seven (13%) ends within 30 turns of the character being hurt by
something not in view, and the rules waiting in it: burning from a bombardier beetle's spray (DCSS refuses rest and
explore while on fire, and every step shakes some of it off) or hit by an invisible orc wizard or unseen horror (with
nothing in view, the scroll and the stairs were not even possible). `--style unseen=2` walks toward the stairs while
burning, and when HP falls at two choices running with nothing in view, reads teleportation or goes up the stairs. It
is **+0.17 [+0.04, +0.31]** deeper than the default rules on 598 fresh dungeons (seeds 680000–680599; +0.24 [+0.07,
+0.41] on the tuning blocks). It is off by default; making it a default is the orchestrator's call (as a default it would need
`STYLE_ADDED_AS["unseen"] = 0`, so saved runs keep reading as played without it). Paired forks on training seeds,
switch on against off from the first moment it acts, show the fire part paying (+0.75 [+0.08, +1.46]) and leave the
unseen-hit part unproven on its own (−0.04 [−0.48, +0.37]). Section "Hurt by what it can't see", below.

**2026-11-15, evening: the model's teleport habit, written as a one-threshold rule, passes a pre-registered fresh test
and plays as well as the model.** `--style teleport=3` (read teleportation when exhausted after a rage and the
hostiles in view have at least 1.5 times the character's current HP left between them) is **+0.24 [+0.16, +0.34]**
deeper than the rules alone on 600 fresh dungeons (seeds 670000–670599), and +0.00 [−0.10, +0.10] against `v6-clean3`
at `margin=0.6`, which replicated its own gain there (+0.24 [+0.15, +0.35]). On the saved runs the rule fires in 82%
of the spells of exhaustion where the model reads, and the model reads in 83% of those it fires in; on the tuning
blocks the model adds nothing on top of it (+0.00). It was tested as an opt-in switch and is the default since the commit after that test (`--style teleport=0` turns
it off; saved runs from before are read as played with it off)
(section "The model's teleport reads as a rule", below). Forks that read or fight from the same exhausted,
outnumbered state put one read at +0.29 [+0.00, +0.58] deeper where the rule would read (+0.35 [+0.12, +0.62] where the
model would; +0.91 with 6+ hostiles), so the reads themselves pay.

**2026-11-15, afternoon: `v6-clean3` at `margin=0.6` is still the best configuration; its successor `v7-clean3` is not
ahead on the tuning blocks, so no fresh seeds were spent** (section "No second teleport scroll, a second clean round
with forks, and `v7-clean3`", below). `read_teleport` is no longer possible while a teleport is coming (+0.05 [+0.02,
+0.09] for `v6-clean3` on A + C). The clean corpus grew to 3.09M rows with a round played by `v6-clean3` and 1,792
forks. `v7-clean3`, trained on it, predicts a little better and no longer dives at the default margin (+0.16 [−0.04,
+0.37] against the rules on A + C), but it has lost the confident teleport reads, and against `v6-clean3` at 0.6 it is
−0.06 [−0.27, +0.16] at 0.25 and −0.24 at 0.6.

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

#### No second teleport scroll, a second clean round with forks, and `v7-clean3` (2026-11-15, afternoon)

**Summary.**

- **Nothing new beats `v6-clean3` at `margin=0.6` on the tuning blocks, so the fresh seeds 670000–670599 were not
  played** and nothing was pre-registered. The best new configuration, `v7-clean3` at the default margin (0.25), is
  −0.06 [−0.27, +0.16] against `v6-clean3` at `margin=0.6` on A + C; at 0.4 it is −0.10 [−0.26, +0.05], and at 0.6 and
  0.8 it is −0.24 and −0.23, since there it hardly leaves the rules at all.
- **`read_teleport` is no longer possible while a teleport is already coming** (`Tele` showing; a second scroll
  cancels the first: "You feel strangely stable"). This changes the model's games only from such a moment on, and
  the rules' games mainly where every other action was blocked and the scroll was their fallback (8 of 400 games on A + C, and 4 more that part later in a game with a `Tele` moment). `v6-clean3` at `margin=0.6`
  with the fix is +0.05 [+0.02, +0.09] on A + C against itself without it (10 deeper, 389 the same, 0 shallower).
- **The clean corpus is more than twice as large**: 1.36M → 3.09M rows. A second round of 1,800 self-play games
  played by `v6-clean3` (margins 0.6 and 0.25, `--epsilon 0.2`), plus 1,792 forks of those games (600 stairs moments
  forked both ways, 300 other moments with up to 3 other actions), played on by `v6-clean3` at `margin=0.6`.
- **`v7-clean3`** (the `s12` recipe at 3 seeds on it) predicts a little better on held-out clean games, has almost no
  pull toward the stairs (+0.04 against +0.11), and **no longer dives at the default margin**: +0.16 [−0.04, +0.37]
  against the rules alone on A + C, where `v6-clean3` at 0.25 was −0.28. But it has lost `v6-clean3`'s confident
  teleport reads: at the moments `v6-clean3` reads, `v7-clean3` rates the read +0.09 above fighting (median), where
  `v6-clean3` rated it +0.73. At the default margin it mostly skips the rules' rage (`berserk → fight`).
- Fork regret, now measurable on 160 held-out fork moments, does not favour `v7-clean3` (1.84, against 1.52 for
  `v6-clean3` and 1.67 for choosing at random); 160 moments are too few to separate the models.

**Task 1: no second teleport scroll** (`src/ladder/brain/policy.py`, `available`; test
`test_read_teleport_is_not_available_while_a_teleport_is_coming` in `tests/test_brain.py`). `read_teleport` now needs
`Tele` absent from the status line, as the opt-in `teleport_rule` already did. That DCSS cancels a pending teleport on
a second read was checked in a saved game's protocol (seed 660043: "You feel strangely stable" after the model's
second read). What changes, by replaying A and C with this tree:

| replay on A + C (400 dungeons) | games not identical | first difference at a moment with `Tele` showing | `Tele` earlier in the game | no `Tele` |
| --- | --- | --- | --- | --- |
| rules alone | 13 | 8 (every other action blocked, so the rules' fallback was the scroll; now `wait` or a rage) | 4 | 1 |
| `v6-clean3`, `margin=0.6` | 29 | 27 (a read the model can no longer make) | 2 | 0 |

The 40-game check run first (seeds 500000–500039, rules alone) was 40 of 40 identical. One game in 200 differs on
replay with nothing changed (found before); the one rules game with no `Tele` is that. In round 2's 950,343 choices,
3,564 had `Tele` showing and in none of them was `read_teleport` offered. The rules alone on A + C with the fix: +0.01
[+0.00, +0.01] and +0.03 [+0.00, +0.08] against the saved runs; every comparison below uses the replays with the fix.

**Task 2: the second clean round** (training seeds 120000–121799, not used before; `runs/brain/v6b/clean/` and
`runs/brain/v6b/forks/`; 12 workers asked, 10 accounts play).

| part | seeds | games | who plays | rows added | notes |
| --- | --- | --- | --- | --- | --- |
| self-play, `margin=0.6` | 120000–120599, 120800–121199, 121400–121599 | 1,200 | `v6-clean3`, `--epsilon 0.2` | | mean depth 4.6–5.4 a block; it leaves the rules at 0.02% of choices (block c2-0) |
| self-play, `margin=0.25` | 120600–120799, 121200–121399, 121600–121799 | 600 | `v6-clean3`, `--epsilon 0.2` | | mean depth 4.8–5.1; 3.5% overrides, mostly toward the stairs (block c2-3) |
| self-play, both | | 1,800 (3 hung) | | 950,343 | 132,196 of them random choices |
| stairs forks | moments in those games | 1,200 (3 hung, 2 left the recorded game) | `v6-clean3` `margin=0.6` after the fork | | 600 explore-or-descend moments, each forked both ways with `commit` |
| other forks | moments in those games | 592 | the same | | 300 moments (70% within 40 choices of a death), up to 3 other actions each |
| forks, both | | 1,792 (1,789 finished) | | 776,850 | the replayed steps before each fork are not rows |
| **clean corpus, rounds 0–2** | | 6,190 games and forks (6,046 deaths) | | **3,090,859** (581,241 held out by dungeon) | every row with live sight fields; no old pre-fix rows |

About 3 hours of machine time (10:27–13:16). Training: 3 × about 5 minutes; each member kept epoch 3 of 20, as
`v6-clean3`'s kept 2–3.

**Task 3: `v7-clean3`, offline**, on the enlarged corpus's held-out games (581,241 rows: the earlier held-out clean
games and round 2's; true value mean 2.72, 4.7% die within 30 turns). Columns as in the morning's table.

| model | R² died_soon | AUC died_soon | R² depth_end | danger AUC | value: mean pred − true | slope | true value in the lowest / highest fifth |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `v6-clean3` | 0.322 | 0.911 | 0.174 | 0.819 | −0.26 | 0.96 | 1.08 / 3.97 |
| `v7-clean` seeds 0 / 1 / 2 | 0.325 / 0.321 / 0.326 | 0.898 / 0.905 / 0.907 | 0.182 / 0.185 / 0.181 | 0.822 / 0.824 / 0.822 | +0.17 / +0.07 / +0.13 | 0.94 / 0.94 / 0.88 | |
| **`v7-clean3`** (ensemble) | **0.341** | **0.915** | **0.190** | **0.827** | +0.12 | 0.94 | 1.05 / 3.95 |

Fork regret on the 160 held-out fork moments (by dungeon, the same split; regret = value of the best action tried
there − value of the action chosen; lower is better):

| chooser | stairs moments (115) | other moments (45) | all (160) | best action picked (all) |
| --- | --- | --- | --- | --- |
| at random | 1.70 | 1.60 | 1.67 | |
| what the game did | 2.35 | 2.71 | 2.45 | |
| the rules' action | 1.72 | 2.53 | 1.95 | |
| `v6-clean3`, its top action | 1.56 | 1.42 | 1.52 | 49% |
| `v7-clean` seeds 0 / 1 / 2, top action | 2.04 / 1.71 / 1.61 | 1.84 / 1.96 / 1.42 | 1.98 / 1.78 / 1.56 | 43% / 44% / 49% |
| `v7-clean3`, its top action | 1.70 | 2.20 | 1.84 | 44% |

At margins 0.4–0.8 both ensembles keep the rules' action at almost every fork moment, so their regret there is the
rules' (1.92–1.95). The other forks are mostly the last moments before a death, which is why what the game did there
is so bad. Preference for `descend` over `explore` where the rules explored with the stairs known (block A's rules
games, 19,577 moments; `gap.py`): `v6-clean3` +0.11 (9.5% above 0.25), `v7-clean3` +0.04 (0% above 0.25; seeds −0.01,
+0.07, +0.06).

**Task 4: tuning on A (500000–500199) and C (540000–540199).** All with this tree's code (the fix included), no random
choices; paired by dungeon over games both finished and neither stale nor off their seed (`arms.py`; 399 of 400, C
has one hung game in every arm); 95% bootstrap, 10,000 resamples. Description only: these blocks are spent.

| arm | A: mean depth | C: mean depth | leaves the rules (A, C) | commonest changes | − rules alone, A + C | 95% interval | − `v6-clean3` 0.6, A + C | 95% interval |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rules alone (`recover=1 retreat=2`) | 6.29 | 5.96 | | | | | | |
| **`v6-clean3`, `margin=0.6`** | **6.64** | **6.05** | 0.1%, 0.1% | `fight` → `read_teleport` 136, `explore` → `descend` 36, `flee_up` → `read_teleport` 29 | **+0.22** | **[+0.09, +0.36]** | | |
| `v7-clean3`, `margin=0.25` | 6.62 | 5.96 | 0.8%, 1.2% | `berserk` → `fight` 2,016, `quaff_heal` → `fight` 225, `berserk` → `wait` 48+, `fight` → `read_teleport` 46+ | +0.16 | [−0.04, +0.37] | −0.06 | [−0.27, +0.16] |
| `v7-clean3`, `margin=0.4` | 6.33 | 6.17 | 0.04%, 0.06% | `quaff_heal` → `fight` 60, `fight` → `read_teleport` 37 | +0.12 | [+0.01, +0.24] | −0.10 | [−0.26, +0.05] |
| `v7-clean3`, `margin=0.6` | 6.29 | 5.93 | 0.01%, 0.01% | `quaff_heal` → `fight` 10, `fight` → `read_teleport` 7 | −0.02 | [−0.05, +0.01] | −0.24 | [−0.38, −0.10] |
| `v7-clean3`, `margin=0.8` | 6.29 | 5.94 | 0%, 0.00% | `wait` → `read_teleport` 2 | −0.01 | [−0.04, +0.00] | −0.23 | [−0.38, −0.10] |

By block, against the rules alone: `v6-clean3` 0.6 A +0.35 [+0.15, +0.56], C +0.09 [−0.10, +0.28]; `v7-clean3` 0.25 A
+0.33 [+0.04, +0.62], C +0.00 [−0.29, +0.27]; 0.4 A +0.03, C +0.21. Split by the kind of override in a game (a game
counts under each kind it has; `attrib2.py`), `v7-clean3` at 0.25: games with a skipped rage 102, +0.81 each; with a
teleport read 90, +1.16; with a skipped healing potion 58, +0.26; 223 games with none play the same. At 0.4 the
skipped potions cost (20 games, −0.80 each) and the teleport reads gain (51 games, +1.06 each).

- **Does the model now have useful confident choices beyond teleport reads?** Not at 0.6 or above: `v7-clean3` there
  is the rules. At 0.25 its confident choices are to fight on without raging and without drinking, and those games
  come out ahead on average, but so much changes after the first override that this split is not evidence for any
  one of them.
- **Does a lower margin stop losing?** Yes for the new model: at 0.25 it is level or ahead of the rules (+0.16
  [−0.04, +0.37]) where `v6-clean3` at 0.25 lost (−0.28 [−0.55, −0.02]), and it no longer goes for the stairs (`→
  descend` is 9% of its overrides, 257 of 2,974; `v6-clean3` at 0.25: 81%, 7,901 of 9,743).
- **Why the teleport reads went**: at the 140 moments in round 2 where `v6-clean3` read teleportation and the rules
  wouldn't have, both models predict the read about right (`v6-clean3` 0.88, `v7-clean3` 0.65; what followed 0.99),
  but `v7-clean3` rates the rules' action there much higher (0.58 against 0.26), so the gap shrinks from +0.62 to
  +0.07 (`readvalue.py`). Which estimate of fighting on is right can't be told from these rows; `v6-clean3`'s games say
  the read pays.

**Task 5: not run.** No configuration was ahead of `v6-clean3` at `margin=0.6` on A + C, so no pre-registration was
written and seeds 670000–670599 are unused.

- **Verified**: every number in this section (`brain-v6b/arms.py`, `overrides.py`, `attrib2.py`, `offline.py`,
  `forkregret.py`, `gap.py`, `telegap.py`, `readvalue.py`, `same.py`, `telediff.py`); that the fix changes games only
  from a `Tele` moment on (the replay table above); DCSS's "strangely stable" on a second read (one saved protocol); the
  tests (`uv run pytest`, `uv run ruff check`).
- **Inferred**: that `v7-clean3` lost the teleport reads because the larger corpus moved its estimate of fighting on,
  not of reading (an average over 140 moments, not a test); that its skipped rages help (an attribution by game).
- Runs: `runs/brain/v6b/{A,C}-rules`, `-v6-m0.6`, `-v7-m{0.25,0.4,0.6,0.8}`, `chk-A40-rules`; round 2 in
  `runs/brain/v6b/clean/c2-{0..8}` and `runs/brain/v6b/forks/f2-{stairs,any}`; the corpus `runs/brain/v6b/corpus-clean2.npz`.
  Models: `models/v7-clean-s{0,1,2}.json` (each with its parity file) and the manifest `models/v7-clean3.json`. Scripts in
  the job's `brain-v6b/` scratch directory: `round2.sh`, `build7.sh`, `chain.sh` and the `jobs-*.txt` files, and the
  analysis scripts named above. Seeds spent: training 120000–121799; evaluation seeds replayed: A and C only.

#### The model's teleport reads as a rule: `teleport=3` (2026-11-15, evening)

**Pre-registered (written at 16:20, after the tuning runs on A and C and before any game on seeds 670000–670599).**
Configuration: this working tree's code, the rules of thumb (default style, `recover=1 retreat=2`) with `--style
teleport=3`, no model, no random choices. `teleport=3` reads teleportation first in a fight (after a cure and a
retreat up close stairs) when exhausted after a rage (`-Berserk` showing) and the hostiles in view have at least 1.5
times the character's current HP left between them (`foe_hp`; `policy.OUTMATCHED`), never while `Tele` shows.
Baseline: the same code with no model and the default style (the rules alone). A third arm, descriptive only:
`models/v6-clean3.json` at `--style margin=0.6` with the default style otherwise (no `teleport` rule). Dungeons: seeds
670000–670599 (600, never used before), played as three blocks of 200 (670000, 670200, 670400); each block by all
three arms one run after the other, the order rotated by block (670000: rule, rules alone, model; 670200: rules
alone, model, rule; 670400: model, rule, rules alone); 12 workers asked, the accounts that log in play (the two that
fail are not repaired). **Primary comparison: (rules + `teleport=3`) − rules alone**, paired by dungeon over games
both finished (not hung, crashed or an error) and neither stale nor off its seed (stale: its first step is after turn
1; off its seed: no morgue on that custom seed with the game's turn count); 95% bootstrap over dungeons, 10,000
resamples (`brain-v6c/arms.py`); analysed once, after all 1,800 games are played, with no early stopping. **Pass: the
interval's lower end is above zero.** Secondary, descriptive, outside the pass rule: rule − `v6-clean3` 0.6, and
`v6-clean3` 0.6 − rules alone (a replication of the earlier +0.14), each with the same pairing; per-block differences,
reads per arm. Chosen because on the tuning blocks A + C it is +0.27 [+0.14, +0.41] against the rules alone and +0.05
[−0.08, +0.18] against `v6-clean3` at 0.6 (tables below). Style defaults are not changed whatever the result.

**Task 1: where the model reads.** Source: every moment in the saved runs where `read_teleport` could be chosen with
no teleport already coming (147,384 moments in 14 runs: `v6-clean3` at 0.6 and the rules alone on A and C in
`runs/brain/v5i` and `v6b`, and on 660000–660599). At each, the model's choice was recomputed offline with the batched
forward pass and `prefer`'s rule (margin 0.6, `min_count` 40); in the model's own games it matches the logged choice at
all 71,728 moments. The model would read at 3,105 of them (`moments.py`).

| at the moment | moments | model reads | HP (median) | hostiles (median) | threat 2+ in view | foes' HP left ÷ own HP (median) | holding a healing potion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| spent (`-Berserk` and `Slow`), model reads | | 2,517 | 33% | 3 | 93% | 2.6 | 17% |
| spent, model doesn't read | 21,133 | | 80% | 1 | 61% | 0.4 | 40% |
| `-Berserk` only (no longer slowed) | 4,380 | 287 (6.6%) | | | | | |
| not after a rage | 119,354 | 301 (0.3%) | 64% (reads) | 2 (reads) | 96% (reads) | 2.0 (reads) | |

While spent, the read rate climbs with every measure of being outmatched (HP under 10%: 92%; 90%+: 1.2%; 8+ hostiles:
60%; one hostile: 4%), but none separates the reads as cleanly as the hostiles' HP left against the character's own,
`foe_hp` (the estimate `big_fight` already uses: each monster's average HP times the share its damage level leaves):
under 1×, 1.3% read; 1–2×, 22%; 2–3×, 59%; 3×+, 79–100%. A grid over the status gate, that ratio, HP fraction,
hostile count and worst threat (`fit.py`) puts one threshold on that ratio first; adding the others moves F1 by 0.01.

Precision and recall against the model's reads (`prtable.py`, `spellx.py`). "Moments" counts each moment; a "spell" is
one spell of exhaustion in one game (moments with `-Berserk` under 40 turns apart; 3,414 spells, 857 with a model
read), where a condition "fires" if it holds at some moment of the spell. A rule reads once and the spell is over, so
the spell view is the one that matters for play.

| condition | moments it holds | precision | recall | spells it fires in | precision | recall | first holds at / before / after the model's first read |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `teleport=1`: spent (`-Berserk` and `Slow`) | 23,650 | 11% | 81% | 3,242 | 26% | 99% | 271 / 574 / 0 |
| `teleport=2`: spent, or 3+ hostiles with one of threat 2+ | 33,046 | 8% | 90% | 3,250 | 26% | 99% | 273 / 574 / 0 |
| spent, HP ≤ 50%, 3+ hostiles, one of threat 2+ (the morning's guess) | 1,290 | 72% | 30% | 414 | 87% | 42% | 151 / 72 / 136 |
| best without foes' HP: `-Berserk`, HP ≤ 40%, one of threat 2+ | 2,700 | 55% | 48% | 717 | 73% | 61% | 198 / 123 / 201 |
| **`-Berserk`, foes' HP ≥ 1.5 × own HP (`teleport=3`)** | 3,675 | **60%** | **71%** | 854 | **83%** | **82%** | 421 / 191 / 93 |
| `-Berserk`, foes' HP ≥ 2 × own HP | 2,469 | 74% | 59% | 685 | 89% | 71% | 339 / 108 / 162 |
| `-Berserk`, foes' HP ≥ 1.5 ×, one of threat 2+ | 3,263 | 62% | 66% | 769 | 84% | 75% | 381 / 173 / 93 |

- The old rules read at the first spent moment of every spell; the model reads in a quarter of them. That is the
  difference between `teleport=1` (level on fresh blocks) and the model.
- `teleport=3` agrees with the model in 4 spells of 5 either way, and when both read in a spell, it reads at the same
  moment in 60% of them and earlier in 27%. By block the moment-level precision and recall hold: A 54% / 74%, C 64% /
  69%, the fresh 660000–660599 63% / 71%.
- What it misses: about 300 reads not after a rage (median HP 64%, nearly all with a threat-2+ monster), and reads at
  moments a single strong monster is in view (median 1 hostile, foes' HP 1.1× own). Where it holds and the model
  doesn't read, the character more often holds a healing potion (38% against 16%); the model prefers the potion
  there (of the moments where the condition holds and the rules would drink, the model reads at 138 of 368, against
1,715 of 2,555 where they would fight).

**Task 2: `teleport=3`** (`src/ladder/brain/policy.py`: `teleport_rule`, `OUTMATCHED = 1.5`; `Style.teleport`'s
comment). Level 3 is not cumulative: it replaces level 1's spent condition with the outmatched one, in the same place
in the fight order (after curing serious poison and after `retreat`'s walk up close stairs, before a rage and the
healing potion), and has no crowded clause. `Tele` still blocks it. Off by default (`Style().teleport == 0`); no
default changed. Tests in `tests/test_brain.py`: `test_outmatched_reads_teleportation_at_level_3`,
`..._needs_exhaustion_and_more_foe_hp_than_its_threshold` (the threshold, damage already done, the monster table
fallback), `..._is_not_the_spent_or_crowded_rule`, `..._keeps_the_guards` (`Tele`, confusion, no scroll, blocked, retreat
and cure first).

**Task 3: tuning on A (500000–500199) and C (540000–540199).** All with this tree's code, no random choices; the rules
alone and `v6-clean3` 0.6 are the afternoon's runs (`runs/brain/v6b/{A,C}-rules`, `-v6-m0.6`, same code but for the
new switch, which is off there); paired by dungeon over games both finished and neither stale nor off their seed
(`arms.py`; 399 of 400, C's one hung game in every arm); 95% bootstrap, 10,000 resamples. Description only.

| arm | A: mean depth | C: mean depth | teleport reads (A, C) | games with a read (A, C) | − rules alone, A + C | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rules alone | 6.29 | 5.96 | 9, 23 (fallbacks) | 5, 14 | | | |
| `v6-clean3`, `margin=0.6` | 6.64 | 6.05 | 106, 107 | 59, 55 | +0.22 | [+0.09, +0.36] | 47 / 338 / 14 |
| **rules + `teleport=3`** | **6.63** | **6.17** | 85, 92 | 48, 52 | **+0.27** | **[+0.14, +0.41]** | 43 / 342 / 14 |
| `v6-clean3` 0.6 + `teleport=3` | 6.69 | 6.11 | 116, 118 (43 and 50 the model's own) | 62, 57 | +0.27 | [+0.12, +0.43] | 54 / 325 / 20 |

| comparison, A + C | difference | 95% interval | deeper / same / shallower | A | C |
| --- | --- | --- | --- | --- | --- |
| rules + `teleport=3` − rules alone | **+0.27** | **[+0.14, +0.41]** | 43 / 342 / 14 | +0.34 [+0.14, +0.55] | +0.21 [+0.06, +0.37] |
| rules + `teleport=3` − `v6-clean3` 0.6 | +0.05 | [−0.08, +0.18] | 30 / 339 / 30 | −0.01 [−0.18, +0.15] | +0.12 [−0.08, +0.32] |
| `v6-clean3` 0.6 + `teleport=3` − rules + `teleport=3` | +0.00 | [−0.11, +0.10] | 22 / 361 / 16 | +0.06 | −0.06 |
| `v6-clean3` 0.6 + `teleport=3` − `v6-clean3` 0.6 | +0.05 | [−0.02, +0.13] | 15 / 372 / 12 | +0.04 | +0.06 |

- **The rule carries the model's whole gain on the tuning blocks**, and on block C a little more. All of it comes from
  the 87 games where the rule read more scrolls than the rules alone (+1.25 each, 43 deeper / 31 same / 13 shallower);
  297 of the 299 games with no read in either are the same game (`ruleattrib.py`).
- **The model adds nothing once the rule exists** (+0.00 [−0.11, +0.10]). On top of the rule it still overrides at
  0.03–0.06% of choices, mostly to read where the rule doesn't.

**Task 4: result on 670000–670599: passes.** Rules + `teleport=3` is **+0.24 [+0.16, +0.34]** deeper than the rules
alone, all 600 dungeons paired (no game hung, stale or off its seed in any of the nine runs: `verify.py` three ways).
Analysed once, after all 1,800 games (16:30–17:56).

| fresh blocks | arm (order played) | finished (hung) | mean depth | XL | turns | died on D:1–3 / 4–6 / 7+ | teleport reads | games with a read |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| P1 (670000–) | rules + `teleport=3` (1st) | 200 (0) | 6.07 | 6.58 | 3213 | 42 / 75 / 74 | 101 | 53 |
| | rules alone (2nd) | 200 (0) | 5.82 | 6.45 | 3066 | 43 / 78 / 70 | 9 (fallbacks) | 7 |
| | `v6-clean3` 0.6 (3rd) | 200 (0) | 6.01 | 6.59 | 3223 | 42 / 73 / 77 | 104 (99 the model's) | 60 |
| P2 (670200–) | rules alone (1st) | 200 (0) | 5.78 | 6.39 | 2995 | 44 / 74 / 78 | 4 | 3 |
| | `v6-clean3` 0.6 (2nd) | 200 (0) | 6.11 | 6.59 | 3188 | 43 / 68 / 85 | 113 (107) | 71 |
| | rules + `teleport=3` (3rd) | 200 (0) | 6.09 | 6.62 | 3239 | 43 / 67 / 86 | 91 | 58 |
| P3 (670400–) | `v6-clean3` 0.6 (1st) | 200 (0) | 6.29 | 6.79 | 3472 | 34 / 68 / 84 | 100 (93) | 55 |
| | rules + `teleport=3` (2nd) | 200 (0) | 6.25 | 6.76 | 3473 | 34 / 70 / 82 | 69 | 45 |
| | rules alone (3rd) | 200 (0) | 6.08 | 6.67 | 3373 | 34 / 76 / 76 | 4 | 2 |

| comparison | P1 | P2 | P3 | **P1–P3 (600 dungeons)** | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- |
| **rules + `teleport=3` − rules alone (the pre-registered test)** | +0.24 [+0.09, +0.41] | +0.32 [+0.15, +0.50] | +0.17 [+0.04, +0.33] | **+0.24 [+0.16, +0.34]** | 57 / 529 / 14 |
| rules + `teleport=3` − `v6-clean3` 0.6 (descriptive) | +0.05 [−0.10, +0.20] | −0.01 [−0.20, +0.17] | −0.04 [−0.20, +0.13] | +0.00 [−0.10, +0.10] | 40 / 513 / 47 |
| `v6-clean3` 0.6 − rules alone (replication, descriptive) | +0.20 [+0.06, +0.34] | +0.33 [+0.14, +0.54] | +0.21 [+0.04, +0.40] | +0.24 [+0.15, +0.35] | 73 / 505 / 22 |

- **Passes the pre-registered rule**: the lower end is +0.16. Each block on its own is above zero too, whichever arm
  played first.
- **The rule is level with the model** (+0.00 [−0.10, +0.10]), and the model's earlier result replicates, larger
  (+0.24 here against +0.14 on 660000–660599).
- All of the gain is in the games where the rule read: 148 games with more reads than the rules alone, +0.95 each
  (55 deeper / 79 same / 14 shallower), 96% of the difference; 443 of the 444 games where neither read are the same
  game (`ruleattrib.py`). Deaths on D:4–6 fall (228 → 212 over the three blocks) and more games reach D:7+.
- So the gain no longer depends on one model keeping a habit: a two-line rule, with one threshold, plays as well.
  Whether reading itself is what helps, rather than what the rule's moments have in common, is task 5.

**Task 5: forks that read or fight from the same state** (`forks.plan(kind="teleport")`, `ladder brain forks --kind
teleport`; test `test_plan_teleport_forks_read_and_fight_once_per_spell`). Source: 600 new games of the rules alone
(default style, no random choices) on training seeds 130000–130599 (`runs/brain/v6c/src-{0,1,2}`; every game on its
seed three ways, 1 hung). Moments: exhausted after a rage (`-Berserk`), 2 or more hostiles in view, `read_teleport`
and `fight` both possible; one at random from each spell of exhaustion: 371 moments in 184 games. Each was forked to
`read_teleport` and to `fight`, both played on to the end by the rules alone (no `teleport` rule), 742 forks
(`runs/brain/v6c/forks/tp-rules`; none hung, none left the recorded game, the two forks' states identical in all 371
pairs). Outcome: deepest floor of the read fork − the fight fork; 95% bootstrap over source games (10,000 resamples;
`forkdiff.py`). This is the paired, causal estimate of one read against fighting on there.

| moments | pairs | depth: read − fight | 95% interval | deeper / same / shallower | died within 30 turns: read − fight |
| --- | --- | --- | --- | --- | --- |
| all | 371 | +0.21 | [−0.06, +0.50] | 120 / 158 / 93 | −7 points |
| HP ≤ 25% | 43 | +0.09 | [+0.00, +0.29] | 1 / 42 / 0 | 0 |
| HP 25–50% | 46 | +0.59 | [−0.06, +1.29] | 15 / 25 / 6 | −30 |
| HP 50–75% | 97 | −0.23 | [−0.83, +0.37] | 30 / 33 / 34 | −3 |
| HP 75–100% | 185 | +0.38 | [+0.01, +0.77] | 74 / 58 / 53 | −5 |
| 2 hostiles | 190 | +0.13 | [−0.24, +0.51] | 58 / 80 / 52 | −2 |
| 3 hostiles | 74 | −0.04 | [−0.69, +0.64] | 21 / 31 / 22 | −8 |
| 4–5 hostiles | 72 | +0.36 | [−0.13, +0.80] | 29 / 27 / 16 | −14 |
| 6+ hostiles | 35 | +0.91 | [+0.31, +1.57] | 12 / 20 / 3 | −17 |
| HP ≤ 50% and 3+ hostiles | 55 | +0.55 | [+0.19, +0.95] | 13 / 39 / 3 | −16 |
| **where `teleport=3` would read** | 108 | **+0.29** | **[+0.00, +0.58]** | 23 / 72 / 13 | −13 |
| where it would not | 263 | +0.18 | [−0.17, +0.55] | 97 / 86 / 80 | −5 |
| where `v6-clean3` 0.6 would read | 85 | +0.35 | [+0.12, +0.62] | 15 / 66 / 4 | −16 |
| where it would not | 286 | +0.17 | [−0.19, +0.53] | 105 / 92 / 89 | −4 |

- **Reading is worth something where the rule and the model read**: +0.29 (rule) and +0.35 (model) a moment; the read
  fork is deeper in 23 pairs and shallower in 13 (rule), 15 and 4 (model), with 13–16 points fewer deaths within 30
  turns. Where either would not read, the estimate is smaller and much noisier (+0.17–0.18, intervals across zero):
  at high HP with two hostiles the two forks part often and either way.
- **Outmatched is where it pays most**: 6+ hostiles +0.91 [+0.31, +1.57]; HP under half with 3+ hostiles +0.55 [+0.19,
  +0.95]. At HP ≤ 25% the two forks nearly always end on the same floor (42 of 43). The middle HP band is the one
  without a gain (−0.23, wide).
- These are per read at one moment. A game with the rule reads about 1.8 scrolls, which fits the +0.95 per reading game
  in task 4 only loosely; the fork estimate is the cleaner number.
- The model's predicted gap (read − fight) at these moments averages +0.31, close to the measured +0.21, but does not
  rank the moments: its correlation with the pairs' outcome differences is 0.00 (one pair's outcome is mostly noise).
  The fork rows are the comparison the model needs to learn from; they are on training seeds and can go into the
  next corpus as they are. No retraining this round.

**Summary of the section.**

- Task 1: one threshold reproduces `v6-clean3` 0.6's reads: exhausted after a rage and the hostiles' HP left at 1.5×
  the character's or more. Per spell of exhaustion, 83% precision and 82% recall (`teleport=1`: 26% and 99%).
- Task 2: it is `--style teleport=3`, off by default, with tests.
- Task 3: on A + C it is +0.27 [+0.14, +0.41] against the rules alone and +0.05 [−0.08, +0.18] against the model; the
  model adds +0.00 [−0.11, +0.10] on top of it.
- Task 4: pre-registered on 670000–670599 and **passes, +0.24 [+0.16, +0.34]**; level with the model (+0.00 [−0.10,
  +0.10]), whose own gain replicates (+0.24 [+0.15, +0.35]).
- Task 5: one read against fighting on, from the same state, is +0.29 [+0.00, +0.58] where the rule would read, +0.35
  [+0.12, +0.62] where the model would, +0.91 with 6+ hostiles; +0.21 [−0.06, +0.50] over all exhausted-and-outnumbered
  moments.
- **Verified**: every number in this section (scripts below); the offline model choices against the logged ones
  (71,728 of 71,728); every fresh and source game on its seed three ways (`verify.py`: protocol greeting, first step,
  morgue), no stale, hung or off-seed game in the nine fresh runs; that with no read the rule's games are the rules'
  games (297 of 299 on A + C, 443 of 444 fresh); the fork pairs' identical states; the tests (`uv run pytest`, `uv run
  ruff check`).
- **Inferred**: that the gain of both the rule and the model is the reads themselves, not something that comes with
  their moments: the forks support it where they read (+0.29 and +0.35 a moment, the lower ends at 0.00 and +0.12)
  but do not separate those moments from the others (+0.18 there, wide), so the rule's threshold is shown to pick
  moments where reading helps, not shown to be the best place to put it. That the model adds nothing on top of the
  rule rests on the tuning blocks only.
- Runs: `runs/brain/v6c/{A,C}-rules-t3`, `{A,C}-v6-m0.6-t3` (tuning), `P{1,2,3}-{rules,t3,v6}` (fresh), `src-{0,1,2}`
  and `forks/tp-rules` (forks). Scripts in the job's `brain-v6c/` scratch directory: `moments.py` (the 147,384 moments,
  `moments.jsonl`), `explore.py`, `fit.py`, `prtable.py`, `spellx.py`, `bybase.py`, `reads.py`, `ruleattrib.py`,
  `forkdiff.py`, `plancount.py`, `chain.sh`, `after.sh`, the `jobs-*.txt` files, and copies of `arms.py`, `seeds.py`,
  `verify.py`, `refresh.sh`, `mindex.py`, `offline.py`, `overrides.py`. Seeds spent: evaluation 670000–670599 (task 4);
  training 130000–130599; evaluation seeds replayed: A and C only.

#### Hurt by what it can't see: burning and invisible attackers (2026-11-15, night)

**Task 1: where the current rules lose games.** Source: the 999 finished games of the rules with `teleport=3` (today's
defaults: `recover=1 retreat=2 teleport=3`) on A, C and the fresh 670000–670599 (`runs/brain/v6c/{A,C}-rules-t3`,
`P{1,2,3}-t3`; none stale or off its seed, 1 hung left out), each death's morgue matched by seed and turn count (954
of 954). Cause table as in "Where the rules of thumb lose games" (one cause per game, first that applies; the bound is
the same back-of-envelope ceiling). Scripts `gather.py`, `causes.py`, `diag.py` in the job's `brain-v6d/`.

| cause | games | share | D:1–3 / 4–6 / 7+ | mean depth | arrived below qw's median XL | known teleport held at death | healing potion held at death | bound if avoided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| raged in the last fight, the rage ran out before the fight did | 320 | 32.0% | 56 / 106 / 158 | 6.47 | 222 | 65 | 10 | +1.00 |
| walked into the last fight already spent | 203 | 20.3% | 35 / 83 / 85 | 6.16 | 125 | 49 | 7 | +0.65 |
| died still raging | 174 | 17.4% | 56 / 52 / 66 | 6.03 | 112 | 53 | 59 | +0.58 |
| took the stairs raging or spent, died within 50 turns | 106 | 10.6% | 9 / 48 / 49 | 6.71 | 70 | 16 | 2 | +0.32 |
| killed in melee, never raged | 84 | 8.4% | 17 / 26 / 41 | 7.01 | 60 | 26 | 3 | +0.25 |
| poisoned; from range or a spell; autofight refused | 32; 23; 12 | 6.7% | | | | | | +0.22 |
| *not a death*: nothing possible; 1,500 choices on one level | 33; 12 | 4.5% | | | | | | +0.18 |

Against the night of 2026-11-14 (plain rules): taking the stairs spent fell from 25% to 11% of games (`recover`), and
the rage running out is now the largest cause (29% → 32%). New at the top of the killers: **unseen horror** (21 of
the 84 "never raged" deaths) and **bombardier beetle** (39 deaths, 26 of them "walked in spent").

The state in the last fight ("the last fight" is the run of choices on the death level since nothing was last in view;
HP as a share of the maximum):

| cause | fresh / raging / spent at its start | HP at its start (median) | hostiles at most (median) | foes' HP ≥ own max at its start | killer in view at some point | stairs up within 8 at its start | at death, held and known: healing / teleport / unknown scroll |
| --- | --- | --- | --- | --- | --- | --- | --- |
| all deaths (954) | 58% / 7% / 35% | 100% | 4 | 16% | 82% | 37% | 11% / 24% / 11% |
| rage ran out first | 97% / 0% / 3% | 100% | 6 | 21% | 98% | 32% | 5% / 20% / 10% |
| walked in spent | 0 / 0 / 100% | 55% | 1 | 2% | **61%** | 39% | 4% / 24% / 10% |
| died raging | 90% / 2% / 9% | 100% | 6 | 28% | 98% | 37% | **34%** / 30% / 13% |
| took the stairs spent | 2% / 1% / 97% | 32% | 3 | 24% | 78% | 55% | 3% / 15% / 12% |
| never raged | 51% / 48% / 1% | 81% | 1 | 4% | **54%** | 30% | 6% / 31% / 11% |

- **What the rules chose in the last 30 choices** (all deaths): fight 56%, descend 11%, wait 9%, explore 9%, rest 7%,
  flee_up 3%, berserk 3%, quaff_heal 1%, read_teleport 1%. In the deaths walked into spent, wait was 14% and rest 11%;
  in the never-raged ones wait 21% and explore 19%.
- **No unknown potion was held at any death** (the rules drink them out of combat); an unknown scroll at 11%. A known
  healing potion was held at 11% of deaths, and in 107 deaths (11%) the character was raging at or under half HP with
  one in the pack, which a rage forbids drinking. But rages begun at or under half HP with a potion held are few (67 of
  15,105 rages; 21% followed by death within 50 turns), so drinking before the rage would touch little.
- **When the rage ran out mid-fight** (361 deaths): HP 51% median, 2 hostiles left, their HP left 1.43× the
  character's (just under `teleport=3`'s 1.5); a teleport scroll held in 29%, a healing potion in 32%, stairs up within
  8 in 27%.
- **Rages begun against more than the character has**: foes' HP left ≥ 1.5× its maximum at the rage, 790 rages, 29%
  followed by death within 50 turns (all rages: 6%); with a teleport scroll held, 341 and 23%.

**The new finding: a death in seven follows damage from something not in view, and the rules wait in it.** In 147 of
the 954 deaths (poison aside) the killer was never among the hostiles the brain saw in the last fight
(`active_hostiles`), and in 133 games (13.3%) the
character died within 30 turns of HP falling at two or more choices running with nothing in view (not poisoned, not
the HP a rage's end takes). The game's messages say what it is (protocol logs):

| hurt with nothing in view, then dead within 30 turns | games | share | mean depth | what the rules chose from the first hit (nothing in view) | killers |
| --- | --- | --- | --- | --- | --- |
| burning (`Fire`: DCSS's sticky flame) | 34 | 3.4% | 4.32 | wait 79%, descend 13%, explore 4% | bombardier beetle 26 |
| something invisible, or out of reach | 99 | 9.9% | 6.76 | wait 55%, explore 18%, descend 14%, rest 12% | orc wizard 32, unseen horror 24, Sigmund 16, vampire 7 |

- **Burning.** A bombardier beetle's spray sets the character on fire (`Fire`, "The liquid fire burns you!"). While it
  burns DCSS refuses rest and explore ("You are on fire!", `i_feel_safe`), so after two refusals both are set aside and
  `wait` is all that is left: it stands in the fire until it dies. Every step taken shakes six turns of the fire off
  (`shake_off_sticky_flame`); qw's movement planner steps to put it out ("sticky fire").
- **Invisible.** "Something hits you", "You hear some strange, mumbled words. A magic dart appears from out of thin
  air!": orc wizards turn invisible, unseen horrors always are, and a Minotaur can't see invisible. With nothing in view
  `read_teleport` and `flee_up` are not possible at all, rest and explore are refused, and the rules wait: in game
  500177 it waited out its death on D:3 one step from the stairs up, holding two scrolls of teleportation. qw attacks
  the square it was hit from (`plan_flail_at_invis`).
- Over whole games (not only deaths), spells of HP falling at two or more choices with nothing in view: 764 not
  burning (318 games, 23% followed by death within 30 turns) and 124 burning (107 games, 29%); with a single fall, 3%.

**Against qw** (its five base runs, 988 games, other dungeons; `qwcmp.py`). XL on first arrival is still a level under
qw's from D:5, and the rules' chance of dying on a level climbs from 13% on D:4 to 40% on D:9 where qw's stays at 6–10%:

| depth | rules: arriving | XL | died there | qw: arriving | XL | died there |
| --- | --- | --- | --- | --- | --- | --- |
| D:3 | 872 | 3.3 | 11% | 860 | 3.6 | 10% |
| D:4 | 776 | 4.5 | 13% | 776 | 4.9 | 8% |
| D:5 | 659 | 5.7 | 16% | 705 | 6.4 | 8% |
| D:6 | 548 | 6.7 | 25% | 648 | 7.6 | 6% |
| D:7 | 418 | 7.4 | 23% | 606 | 8.5 | 9% |
| D:8 | 322 | 8.1 | 31% | 556 | 9.1 | 10% |
| D:9 | 221 | 8.7 | 40% | 446 | 10.2 | 8% |

Killed by, per 1,000 games (rules, qw): unseen horror 25, 1; bombardier beetle 39, 5; orc wizard 78, 31; killer bee
43, 13; wight 33, 7; gnoll 93, 91; ogre 41, 26. The three the rules can't see or put out are 142 against 37 per 1,000:
about a tenth of all games.

**The largest remaining mechanisms, by share of games, each with a candidate change:**

| | mechanism | share of games | candidate rule change |
| --- | --- | --- | --- |
| 1 | a rage runs out with the fight still on | 32% | read teleportation at a lower `foe_hp` ratio than 1.5 (the forks put a read at +0.18 [−0.17, +0.55] where `teleport=3` doesn't read: unproven); none of the earlier levers is left untried |
| 2 | died raging, against more than one rage can finish | 17% | read teleportation instead of raging when the foes' HP left is at least 1.5× the character's maximum and a scroll is held (341 such rages, 23% followed by death); needs forks first |
| 3 | hurt by something not in view and waiting in it: invisible attackers and sticky flame | 13% (of deaths within 30 turns), more of the "walked in spent" and "never raged" rows | **`unseen`**: when burning with nothing in view, walk toward the stairs; when HP keeps falling with nothing in view, read teleportation, else go up the stairs (implemented below) |
| 4 | walked into the last fight spent (overlaps 3: 69 of its 203) | 20% | rest out the exhaustion before exploring on (`recover=2`, level before; untested with today's rules) |
| 5 | raging at under half HP with a healing potion that the rage forbids | 11% of deaths | drink before raging at under half HP: touches only 67 rages in 999 games, not worth a test |

Chosen for task 2: mechanism 3. It is the one where the rules do something plainly wrong (waiting while burning or
being hit), the change is two lines in `available` and `baseline` and a counter, and it touches only the moments it is
for.

**Task 2: `--style unseen=1|2`** (`src/ladder/brain/policy.py`: `Style.unseen`, `BrainTiers.assailed`, `BURNING`,
`UNSEEN`, `UNSEEN_HITS = 2`, and the `assailed` arguments of `available` and `baseline`; tests in
`tests/test_brain.py`, block "the opt-in rule for being hurt with nothing in view"). Off by default; no default
changed.

- `assailed` is worked out at every choice. With a hostile in view it is nothing (and the count below starts again).
  With nothing in view: BURNING when `Fire` shows (level 1 and up); UNSEEN (level 2) when the HP fraction has fallen at
  2 choices running (a choice where it stayed put doesn't break the run, one where it rose does, and so does a new
  level or a choice while burning), not counting a fall while poisoned or at the choice a rage ended.
- What it changes: with nothing in view, `flee_up` becomes possible (a step toward the stairs up, or up them; never
  out of the dungeon from D:1), and when UNSEEN, `read_teleport` too (not while `Tele` shows). The rules then choose,
  before anything else but a cure: BURNING, `flee_up`, else `descend` (toward the stairs down); UNSEEN,
  `read_teleport`, else `flee_up`. Otherwise as before.
- Checked in the games: with the switch on, "You shake off some of the fire as you move" and "You shake off the liquid
  fire" appear 205 times in block A's protocols against 158 without; 118 of the 119 block-A games where the switch never
  acted are the same game as without it (134 of 136 on C).
- One fix made during tuning: in the first round (`A-u2`, `C-u2`) the fire's own damage counted toward UNSEEN, so a
  character whose fire had just gone out walked on to the stairs. Now a choice while burning ends the run. The rerun
  (`A-u2b`, `C-u2b`, this tree) is −0.01 [−0.10, +0.09] against the first round: the same.

**Task 3: tuning on A (500000–500199) and C (540000–540199)**, against the default rules with `teleport=3`
(`runs/brain/v6c/{A,C}-rules-t3`; a replay of block A with this tree and the switch off, `runs/brain/v6d/A-rules`, is
+0.01 [+0.00, +0.01] against it, 199 of 200 the same). Paired by dungeon over games both finished and neither stale nor
off their seed (`arms.py`); 95% bootstrap, 10,000 resamples. Description only: these blocks are spent.

| arm | A: mean depth | C: mean depth | XL (A, C) | − rules, A | − rules, C | **− rules, A + C** | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rules (`teleport=3`, the defaults) | 6.63 | 6.17 | 7.08, 6.57 | | | | |
| `unseen=1` (burning only) | 6.87 | 6.24 | 7.25, 6.66 | +0.23 [+0.06, +0.43] | +0.07 [−0.08, +0.22] | +0.15 [+0.04, +0.28] | 39 / 343 / 17 |
| `unseen=2`, first round | 7.02 | 6.26 | 7.37, 6.71 | +0.39 [+0.11, +0.68] | +0.09 [−0.14, +0.32] | +0.24 [+0.06, +0.42] | 71 / 291 / 37 |
| **`unseen=2`** (with the fix) | **7.00** | **6.27** | 7.37, 6.73 | +0.36 [+0.10, +0.64] | +0.11 [−0.12, +0.33] | **+0.24 [+0.07, +0.41]** | 71 / 295 / 33 |

| comparison, A + C | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- |
| `unseen=2` − `unseen=1` | +0.08 | [−0.05, +0.22] | 40 / 339 / 20 |
| `unseen=2` − its first round | −0.01 | [−0.10, +0.09] | 15 / 370 / 14 |

- **Where it acts** (`unseen=2`, A + C): in 144 of 399 games; 180 steps out of fire, 348 walks toward the stairs with
  something unseen hitting, 63 teleport reads. Split by game (`uattrib.py`): games where it only stepped out of fire,
  47, +0.91 each; games where it acted on unseen hits, 97, +0.56 each (46 deeper, 28 same, 23 shallower); the 255 where
  it never acted, −0.01 each.
- **Deaths** (A + C; the cause table's rules; `unseen2.py` counts deaths within 30 turns of HP falling twice with
  nothing in view): burning 14 → 4 with either level; something unseen 40 → 41 with `unseen=1` and 27 with `unseen=2`
  (its first round; the counts in this bullet and the protocol count above are from that round).
  Deaths walked into spent 84 → 70, never raged 34 → 24; the rage running out rises 131 → 145, as saved characters
  meet their next fight.
- Burning alone is worth about two thirds of the gain and is the surer part (its interval is narrower); the unseen
  part adds +0.08, not separable from zero on 399 dungeons.

**Pre-registered (written at 20:55, after the tuning runs on A and C and before any game on seeds 680000–680599).**
Configuration: this working tree's code, the rules of thumb (default style: `recover=1 retreat=2 teleport=3`) with
`--style unseen=2`, no model, no random choices. Baseline: the same code with no model and the default style (the rules
alone; `unseen` 0). Dungeons: seeds 680000–680599 (600, never used before: no morgue, step log or results file has
them), played as three blocks of 200 (680000, 680200, 680400), each block by both arms one run after the other, the arm
that goes first alternating by block (configuration first on 680000 and 680400, baseline first on 680200); 12 workers
asked, the accounts that log in play (those that fail are not repaired). Analysis: paired by dungeon over games both
finished (not hung, crashed or an error) and neither stale nor off its seed (stale: its first step is after turn 1; off
its seed: no morgue on that custom seed with the game's turn count); 95% bootstrap over dungeons, 10,000 resamples
(`brain-v6d/arms.py`); analysed once, after all 1,200 games are played, with no early stopping. **Pass: the
interval's lower end is above zero.** Reported alongside, outside the pass rule: each block's difference, mean depth,
XL, deaths by depth band, what the switch did, and the burning and unseen deaths. Chosen because it is the furthest
ahead of the rules on A + C (+0.24 [+0.07, +0.41]); `unseen=1` (+0.15) is not tested. Style defaults are not changed
whatever the result.

**Task 4: result on 680000–680599: passes.** Rules + `unseen=2` is **+0.17 [+0.04, +0.31]** deeper than the rules
alone, on 598 of 600 dungeons (two dungeons left out for a hung game, none stale or off its seed). Analysed once, after
all 1,200 games (20:56–21:58). Every game's seed checked three ways (`verify.py`: protocol greeting, first step,
morgue).

| fresh blocks | arm (order played) | finished (hung) | mean depth | XL | turns | died on D:1–3 / 4–6 / 7+ |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 (680000–) | rules + `unseen=2` (1st) | 200 (0) | 6.26 | 6.77 | 3456 | 39 / 64 / 84 |
| | rules alone (2nd) | 200 (0) | 6.06 | 6.63 | 3246 | 40 / 73 / 75 |
| Q2 (680200–) | rules alone (1st) | 199 (1) | 6.22 | 6.72 | 3269 | 33 / 66 / 88 |
| | rules + `unseen=2` (2nd) | 199 (1) | 6.38 | 6.92 | 3528 | 33 / 67 / 91 |
| Q3 (680400–) | rules + `unseen=2` (1st) | 200 (0) | 6.18 | 6.83 | 3424 | 34 / 66 / 92 |
| | rules alone (2nd) | 199 (1) | 6.01 | 6.69 | 3315 | 37 / 68 / 85 |

| rules + `unseen=2` − rules alone | dungeons | difference | 95% interval | deeper / same / shallower |
| --- | --- | --- | --- | --- |
| Q1 | 200 | +0.20 | [−0.01, +0.41] | 31 / 151 / 18 |
| Q2 | 199 | +0.16 | [−0.07, +0.39] | 23 / 157 / 19 |
| Q3 | 199 | +0.16 | [−0.11, +0.44] | 24 / 152 / 23 |
| **Q1–Q3 (the pre-registered test)** | 598 | **+0.17** | **[+0.04, +0.31]** | 78 / 460 / 60 |

- **Passes the pre-registered rule**: the lower end is +0.04. No block clears zero on its own; all three are ahead by
  about the same amount, whichever arm played first.
- **What the switch did** (`uattrib.py`): it acted in 223 of 599 games: 219 steps out of fire, 783 walks toward the
  stairs with something unseen hitting, 97 teleport reads. 372 of the 376 games where it never acted are the same game
  as without it.
- **Where the gain is, by game:** games where it acted on unseen hits, 170, +0.67 each (62 deeper / 66 same / 42
  shallower), all of the difference and more; games where it only stepped out of fire, 52, −0.29 each (14 / 20 / 18).
  On the tuning blocks the split was the other way round (fire +0.91, unseen +0.56 a game). A game-level split after a
  game has parted is noisy (one death more or less moves it), so neither part is shown on its own; the pass is for the
  two together.
- **Deaths** (cause table's rules, `unseen2.py`): deaths within 30 turns of HP falling twice with nothing in view,
  burning 18 → 6, something unseen 59 → 44 (of 598 and 599 games); deaths in the last 10 choices while burning 27 → 15.
  By cause: walked into the last fight spent 114 → 107, never raged 34 → 29; the rage running out 213 → 223 and died
  raging 93 → 100, as the saved characters meet their next fight.

**Task 5: forks with the switch on and off from the first moment it acts** (`forks.plan(kind="unseen")`, `ladder brain
forks --kind unseen`; a fork job may now carry style keys of its own, `"style"` in `selfplay._play`; test
`test_plan_unseen_forks_the_first_moment_on_and_off`). Source: 599 games of rules + `unseen=2` on new training seeds
140000–140599 (`runs/brain/v6d/src-{0,1,2}`, 1 hung; mean depth 6.23–6.29). Moment: in each game, the first choice with
nothing in view and either burning or the switch's walk or read; up to there the game is the plain rules' game. Each
was forked "on" (the recorded action, played on with `unseen=2`) and "off" (the choices before it replayed, then played
on by the rules with `unseen=0`), both to the end: 218 moments, 436 forks (`runs/brain/v6d/forks/un-rules`; 22:29–23:00).
35 forks hung, 17 "on" and 18 "off", far more than whole games do (cause not looked into); 1 left the recorded game; 198
pairs remain. Outcome: deepest floor, on − off; 95% bootstrap over moments (one per game), 10,000 resamples (`ufork.py`).

| moments | pairs | depth: on − off | 95% interval | deeper / same / shallower | died within 30 turns: on − off |
| --- | --- | --- | --- | --- | --- |
| all | 198 | +0.29 | [−0.10, +0.68] | 73 / 75 / 50 | −9 points |
| burning | 83 | **+0.75** | **[+0.08, +1.46]** | 40 / 20 / 23 | −16 points |
| hit by something unseen | 115 | −0.04 | [−0.48, +0.37] | 33 / 55 / 27 | −3 points |
| ... the "on" fork went for the stairs | 157 (both kinds) | +0.48 | [+0.06, +0.91] | 59 / 61 / 37 | −11 points |
| ... the "on" fork read teleportation | 39 | −0.46 | [−1.38, +0.41] | 13 / 14 / 12 | 0 |
| unseen, HP at most half | 19 | +0.42 | [−0.32, +1.32] | 4 / 12 / 3 | −21 points |
| unseen, HP over half | 96 | −0.14 | [−0.62, +0.33] | 29 / 43 / 24 | 0 |

- **Stepping out of fire is shown to pay from the moment it first acts** (+0.75 [+0.08, +1.46], 16 points fewer deaths
  within 30 turns). The unseen-hit part is not shown either way at its first moment (−0.04, wide); its reads look worse
  than its walks to the stairs, on 39 pairs. This disagrees with the by-game split of the fresh test (where the unseen
  games carried the gain); both splits are noisy and the fresh pass is for the two together.
- These measure the switch from its first act to the end of the game, not one choice: with the switch on it acts
  again at every later moment, so a one-choice fork would change little.

**Summary of the section.**

- Task 1: the largest remaining mechanisms are the rage running out mid-fight (32% of games), walking into the last
  fight spent (20%), dying raging against more than one rage can finish (17%), and, newly found, **being hurt by
  something not in view while the rules wait (13% of games die within 30 turns of it)**: sticky flame from bombardier
  beetles, and invisible orc wizards and unseen horrors. The rules die to those three killers at 142 per 1,000 games,
  qw at 37.
- Task 2: `--style unseen=1|2`, off by default, with tests.
- Task 3: on A + C, `unseen=2` is +0.24 [+0.07, +0.41] and `unseen=1` (fire only) +0.15 [+0.04, +0.28] against the
  default rules.
- Task 4: pre-registered on 680000–680599 and **passes, +0.17 [+0.04, +0.31]** (598 dungeons).
- Task 5: a fork kind `unseen`; on 198 paired forks from the first moment the switch acts, stepping out of fire is
  +0.75 [+0.08, +1.46], the unseen-hit part −0.04 [−0.48, +0.37].
- **Verified**: every number in this section (scripts below); every fresh game on its seed three ways (`verify.py`), no
  stale or off-seed game in the six fresh runs, 3 hung; that games where the switch never acted are the rules' games
  (118 of 119 and 134 of 136 on A and C, 372 of 376 fresh); that the steps put the fire out (DCSS's own messages, more
  of them with the switch); that rest and explore are refused while burning (`i_feel_safe` in the DCSS source, and the
  refused choices in the step logs); the replay of block A with the switch off (199 of 200 the same); the tests (`uv run
  pytest`, `uv run ruff check`).
- **Inferred**: that the HP lost with nothing in view comes from invisible or out-of-reach attackers (read in the
  protocol messages of the games looked at, "Something hits you" and spells "from out of thin air", not counted over
  all of them); which part of the switch carries the gain (the by-game splits and the forks disagree); qw's comparison,
  which is on other dungeons; why 8% of the forks hung.
- Runs: `runs/brain/v6d/{A,C}-u1`, `{A,C}-u2`, `{A,C}-u2b`, `A-rules` (tuning and replay check), `Q{1,2,3}-{u2,rules}`
  (fresh), `src-{0,1,2}` and `forks/un-rules` (task 5). Scripts in the job's `brain-v6d/` scratch directory: `gather.py`,
  `flags.py`, `causes.py`, `diag.py`, `show.py`, `unseen.py`, `unseen2.py`, `assailed.py`, `fire.py`, `rages.py`,
  `pmsgs.py`, `qwcmp.py` (task 1); `arms.py`, `seeds.py`, `verify.py`, `mindex.py`, `refresh.sh`, `uattrib.py`,
  `ushow.py`, `percause.sh`, `percause3.sh` (tuning and the test); `ufork.py`, `after.sh` (forks); `chain.sh` and the
  `jobs-*.txt` files; the copied morgues. Seeds spent: evaluation 680000–680599 (task 4); training 140000–140599 (task
  5); evaluation seeds replayed: A and C only.

#### The fights the rules start: candidates counted, two switches, and a full server disk (2026-11-15, late night)

**Stopped before any game: the game server's disk is full.** The Docker VM's disk (`/` and `/data` in
`dcss-multi-agent-dcss-1`) is at 100% (98 GB of 98 GB). 51 GB of it is `/data/rcs/ttyrecs`, almost all the
`ladderbrain*` self-play accounts' terminal recordings (2.6–6.3 GB each); `/data/qw` is 13 GB. Every game since about
22:53 hangs: the worker waits forever in `_clear_save`'s `start_game`, and the parent records `hung` after 60 s. Nothing
in the pipeline reads those ttyrecs (it reads the protocol logs kept beside each step log, and the morgues), but they
are not this task's to delete, so no tuning game, fresh test or fork was played. Tasks 3–5 wait for space.

**This also explains the 8% of forks that hung in the last section.** Of the 35 hung forks in
`runs/brain/v6d/forks/un-rules`, 25 never made a game directory (they hung in `_clear_save`, as every game does now) and
the other 10 all started at 22:53–22:54, the run's last two minutes; the one read ends with the key `<` (a level change,
which writes the save) and nothing after. Before 22:53 no fork hung. So the hangs were the disk filling, not something
about forks (inferred from the timing and the last key; the server's own log was not read).

**Task 1: what each candidate would touch.** Source: the 998 finished games of today's defaults (`recover=1 retreat=2
teleport=3 unseen=2`) on A and C (`runs/brain/v6d/{A,C}-u2b`) and on 680000–680599 (`Q{1,2,3}-u2`), none stale or off
its seed; every choice read (`cand.py`, then `ana_a.py`, `ana_b.py`, `ana_c2.py`, `why_desc.py`, `stalls.py` in the job's
`brain-v6e/`). "Died" is within 50 turns of the moment unless said otherwise. Mean depth 6.42; cause table as before:
the rage running out first 37%, walked into the last fight spent 18%, died raging 17%, took the stairs spent 10%,
melee without a rage 5%.

| | candidate | moments | games touched | how they end now | verdict |
| --- | --- | --- | --- | --- | --- |
| a | finish exploring before the stairs down (`calm=1`, with or without `recover=2`; both exist) | 2,494 of 6,114 levels left down unexplored | 790 | see the table below | worth a re-check: the mechanism is clear and large, but the same switch was level under the older rules |
| b | read teleportation instead of starting a rage, foes' HP ≥ 1.5× max, scroll held (`avoid=1.5`, new) | 346 rages | 212 | 26% died (all rages 6%) | **built**; the largest pool where a scroll is in hand |
| b | the same at ≥ 1.0× max | 892 rages | 334 | 18% died | a tuning level of the same switch |
| b | named uniques (qw's leave-the-level list) | Sigmund 178 rages, 12% died; Jeremiah 41, 32%; 3+ gnolls 602, 15% | | | not built: the foes' HP ratio already covers packs, and the uniques other than Jeremiah are no deadlier than an average large rage |
| c | fights begun exhausted with 2+ hostiles and stairs up within 8 (`retreat=3`, new) | 348 fights | 262 | 26% died in the fight (fled in it: 13%) | **built** |
| c | walk to the stairs before a big fresh fight (`stairs=1`, exists) | 1,119 fights with foes' HP ≥ max and stairs within 8 | | 14–16% died, no gradient with distance (on the stairs 14%, 9–20 steps 13%) | not re-tested: nothing says where the fight starts matters, and it was level before |
| d | `teleport=3` at a lower ratio (1.0–1.5× current HP) | 259 spells of exhaustion, 103 with a scroll | about 100 | 16–20% died within 30 turns | not built: too few games to see (a read is worth about +0.3 where it fires) |
| d | spent before the fight starts | 2,538 fights begun exhausted; 235 deaths (median 71% HP, 3 hostiles, foes' HP 0.91× max) | 741 | 9% died; 2+ hostiles 21% | covered by `retreat=3` (stairs) and `teleport=3` (outmatched) |
| e | rest out exhaustion before exploring on (`recover=2`) | the fights begun exhausted came after `rest` 1,711 times (121 deaths), `descend` 299 (56), `flee_up` 292 (39), `explore` only 73 (6) | | | dropped: the character is already resting when the fight finds it |
| f | drink the healing potion before raging at ≤ 50% HP | 88 rages | 76 | 18% died | dropped: too few |

**(a) in detail.** The rules leave most levels from D:4 on before exploring them, spending half qw's turns per level and
arriving 0.5–2.5 levels under qw from D:5 (qw: its five base runs, other dungeons, `brain-v5e/qw_pace.json`):

| level left down | levels | explored to the end | turns there, median (qw) | XL on arrival below (qw) | died on the next level: after exploring / not |
| --- | --- | --- | --- | --- | --- |
| D:3 → 4 | 843 | 67% | 612 (856) | 4.6 (4.9) | 10% / 14% |
| D:4 → 5 | 704 | 46% | 482 (941) | 5.9 (6.4) | 15% / 10% |
| D:5 → 6 | 623 | 33% | 384 (998) | 6.9 (7.6) | 13% / 18% |
| D:6 → 7 | 499 | 32% | 375 (987) | 7.6 (8.5) | 20% / 19% |
| D:7 → 8 | 408 | 37% | 401 (954) | 8.3 (9.1) | 28% / 27% |
| D:8 → 9 | 259 | 39% | 442 (995) | 8.9 (10.2) | 27% / 23% |
| D:9 → 10 | 215 | 47% | 275 (1018) | 9.4 (11.3) | 14% / 30% |

- Why: a rage that outlasts its fight makes DCSS refuse autoexplore ("Calm down first, please."), two refusals set
  `explore` aside for 50 turns, and by the time it may be tried again the rules have rested and walked to the stairs.
  On A + C, 4,376 of the 4,745 times explore was set aside it was during a rage. At the first step toward the stairs of
  an unexplored departure (D:3 on, 1,311 on A, C and Q1), explore was not possible in 1,297, with nothing in view and,
  in 1,114, no rage or exhaustion left.
- Dying on the next level is not clearly lower after a full exploration (the two columns cross), so the case for
  exploring rests on XL, which the earlier `calm=1` test (+1.0 XL, the same depth) did not turn into depth.

**Task 2: two opt-in switches** (`src/ladder/brain/policy.py`; off by default; no default changed).

- **`--style avoid=k`** (`Style.avoid`, `avoid_rule`): in a fight, neither raging nor exhausted, no teleport coming, with
  the hostiles in view at `k` times the character's maximum HP or more (`foe_hp`), read teleportation before the rage.
  It sits where `teleport=3`'s read does in the fight order (after a cure and a retreat), so the two never both apply.
  The scroll takes a few turns to work; on the next choice `Tele` shows, the rule is quiet, and the rules rage as they
  would have (a rage does not cancel a coming teleport: DCSS's `go_berserk` leaves `DUR_TELEPORT` alone).
- **`--style retreat=3`** (`BrainTiers.fight_moves`): as `retreat=2`, and the level is also marked to be left whenever
  two or more hostiles are in view while exhausted (`-Berserk`, not raging) with the stairs up within 8 steps, not only
  at the choice the rage runs out. The rest (up the stairs, a potion first at half HP, rest off the exhaustion upstairs)
  is `retreat`'s as before.
- Tests in `tests/test_brain.py`: `test_retreat_level_3_also_leaves_a_fight_met_while_exhausted`,
  `test_avoid_is_off_by_default_and_off_plays_as_before`, `..._reads_teleportation_instead_of_raging_against_k_times_max_hp`,
  `..._keeps_to_fresh_characters_and_its_guards`, `..._reaches_the_rules_inside_brain_tiers`,
  `test_avoid_and_retreat_3_are_styles_and_old_runs_still_match`.

**Tasks 3–5: not done** (the disk). The tuning that was planned on A and C against the defaults replayed with this tree
(`runs/brain/v6e/{A,C}-ref`): `avoid=1.5`, `avoid=1.0`, `retreat=3`, `calm=1`, `calm=1 recover=2`, then the best two
together. Seeds 690000–690599 are unspent; no fork was played.

- **Verified**: every count above (scripts in the job's `brain-v6e/`); that every game started since about 22:53 hangs in
  `_clear_save` (a stack dump after 40 s, `diag_clear.py`) and that the container's disk is full (`df`, `du`); the hung
  forks' start times (`forkhangs.py`); the tests (`uv run pytest`, `uv run ruff check`).
- **Inferred**: that the full disk is what hangs `start_game` and the level change (not read in the server's log); that
  the 10 forks that hung mid-game hung on the disk.
- Runs: none. (An abandoned start of `A-ref`, 50 games all `hung` at once, left no files; its empty directory was
  removed.) Seeds spent: none.

#### The fights the rules start, tuned: no candidate is ahead (2026-11-16, small hours)

With space on the server again (46 GB free, terminal recording off; the disk stayed at 52% through every run below),
the previous section's tasks 3–5 were run. **Result: none of the five candidates, nor the best two together, is
ahead of today's defaults on the tuning blocks, so no fresh test was played and seeds 690000–690599 are still
unspent.** No default was changed.

**What each switch does** (`src/ladder/brain/policy.py`, `Style`; checked against the code before playing):
`avoid=k` and `retreat=3` are as the previous section describes. `calm=1` is not literally "finish exploring before
the stairs down": with nothing in view it rests out a rage instead of trying to explore (which DCSS refuses, "Calm
down first, please."), and a refusal for the rage no longer counts toward setting `explore` aside. The effect is the
one (a) asks for: levels are explored to the end far more often (table below). `recover=2` adds resting out the
exhaustion after the rage before exploring on.

**Method.** This working tree's code, no model, no random choices, 9 workers (`ladderbrain*` accounts), each arm on A
(500000–500199) and C (540000–540199), played one after another (23:30–03:21; `chain.sh`, `jobs-tune.txt`,
`jobs-combo.txt`). Reference: the defaults (`recover=1 retreat=2 teleport=3 unseen=2`) replayed with this tree,
`runs/brain/v6e/{A,C}-ref`; against yesterday's `v6d/{A,C}-u2b` it is −0.01 [−0.01, +0.00], 397 of 399 dungeons the
same depth. Each candidate − the reference, paired by dungeon over games both finished and neither stale nor off its
seed (`arms.py`); 95% bootstrap over dungeons, 10,000 resamples. Description only: these blocks are spent.

| arm (`--style`) | A: mean depth | C: mean depth | − reference, A | − reference, C | **− reference, A + C** | deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- |
| reference (the defaults) | 6.99 | 6.27 | | | | |
| `avoid=1.5` | 6.87 | 6.27 | −0.12 [−0.31, +0.06] | +0.00 [−0.12, +0.13] | **−0.06 [−0.17, +0.05]** | 27 / 337 / 35 |
| `avoid=1.0` | 6.79 | 6.08 | −0.20 [−0.48, +0.07] | −0.19 [−0.43, +0.05] | **−0.20 [−0.38, −0.02]** | 39 / 295 / 65 |
| `retreat=3` | 6.92 | 6.24 | −0.07 [−0.33, +0.18] | −0.03 [−0.20, +0.14] | **−0.05 [−0.20, +0.10]** | 41 / 322 / 36 |
| `calm=1` | 6.49 | 6.24 | −0.50 [−1.00, +0.01] | −0.06 [−0.51, +0.40] | **−0.28 [−0.62, +0.07]** | 134 / 98 / 167 |
| `calm=1 recover=2` | 6.49 | 6.25 | −0.51 [−1.01, +0.01] | −0.05 [−0.50, +0.41] | **−0.28 [−0.61, +0.07]** | 135 / 98 / 166 |
| `retreat=3 avoid=1.5` (the best two) | 6.86 | 6.19 | −0.13 [−0.43, +0.16] | −0.08 [−0.29, +0.14] | **−0.10 [−0.29, +0.08]** | 53 / 281 / 63 |

Dungeons paired: 399 in every row (200 on A, 199 on C: seed 540052 hangs in the reference, as it has in every C run)
except the last, 397: two games of that arm, 500173 and 540196, died in under 130 turns and their morgues are stamped
7 s before the game's directory, outside `seeds.py`'s 5-second window. Their morgues are on the right seed with the
right turn count, and both seeds end the same in every arm, so leaving them out changes nothing. Every game of the 14
runs was checked on its seed three ways (`verify.py`): no "Welcome back", no protocol without its seed, no first step
after turn 1; 5 games hung, all on 540052.

**Where each one acts** (`cattrib.py`: games whose choices are the reference's are the same game, difference 0 in all
of them; the rest "part", and the first choice where they part says which rule did it; `avoidafter.py`, `calmdiag.py`):

- **`avoid`**: it reads in about a quarter of games (1.5: 68 reads in 50 games on A, 54 in 40 on C; 1.0: 119 in 75,
  114 in 66), and all but 1–4 of the games that part do so at one of these reads. Those games are −0.46 (A) and +0.00 (C) each
  at 1.5, −0.54 and −0.55 at 1.0. After 94–96% of the reads the rules rage anyway within the next few choices (the
  scroll takes a few turns, and the rule allows it), and in 74–80% the character is soon alone, so the rage is spent with
  nobody to hit and the scroll is gone. Deaths within 50 turns of a read are 11–19%, under the 18–26% the previous
  section counted after rages begun in the same state, but that does not carry through to depth (inferred: what the
  read costs later outweighs the death it saves now).
- **`retreat=3`**: it parts 64 games on A (−0.22 each) and 50 on C (−0.10), every one at a walk up the stairs with
  hostiles in view while exhausted. Games that die with their last fight begun exhausted fall (A 50 → 41, C 46 → 37),
  but depth does not rise: level within ±0.2.
- **`calm=1`**: it changes nearly every game (190 of 200 on A, 185 of 199 on C part from the reference, all at a rest
  in a rage with nothing in view). What it changes:

| run | levels left down (D:3 on) explored to the end | XL on first arrival at D:4 / 5 / 6 / 7 / 8 | turns | died on D:1–3 / 4–6 / 7+ |
| --- | --- | --- | --- | --- |
| A reference | 361 of 873 (41%) | 4.6 / 5.8 / 6.7 / 7.5 / 8.3 | 4011 | 22 / 67 / 101 |
| A `calm=1` | 612 of 750 (82%) | 4.6 / 6.1 / 7.2 / 8.0 / 8.7 | 4404 | 25 / 90 / 77 |
| C reference | 305 of 721 (42%) | 4.5 / 5.7 / 6.8 / 7.5 / 8.1 | 3374 | 42 / 54 / 95 |
| C `calm=1` | 563 of 706 (80%) | 4.8 / 6.2 / 7.2 / 7.9 / 8.7 | 4204 | 41 / 66 / 86 |

  It does what (a) wanted: twice as many levels explored to the end and the character arrives 0.3–0.6 XL higher from
  D:5 on. But more of the games end on D:4–6 (A 67 → 90, C 54 → 66), and depth falls on A and is level on C. The
  extra exploring meets more fights at the same depth, and the XL it buys doesn't pay for them. This is the earlier
  finding again (+1.0 XL, the same depth, under older rules), now with the defaults.
- **`recover=2` on top of `calm=1`** parts nearly every game from `calm=1` alone (at a rest while exhausted) but ends
  them the same: +0.01 [−0.05, +0.07] against `calm=1`, 392 of 400 at the same depth.
- **The best two together** (by the pooled difference: `retreat=3` −0.05, `avoid=1.5` −0.06) are −0.10 [−0.29,
  +0.08] against the reference and −0.06 [−0.19, +0.08] against `retreat=3` alone: the two do not add up to a gain.

**No fresh test.** The plan was to pre-register a test on 690000–690599 only for a candidate clearly ahead on A + C.
None is ahead: the best point estimate is −0.05, and no interval's upper end is above +0.10. So nothing was
pre-registered and **seeds 690000–690599 were not played; they are still unused.**

**Summary of the section.**

- On A + C against today's defaults: `avoid=1.5` −0.06 [−0.17, +0.05], `avoid=1.0` −0.20 [−0.38, −0.02], `retreat=3`
  −0.05 [−0.20, +0.10], `calm=1` −0.28 [−0.62, +0.07], `calm=1 recover=2` −0.28 [−0.61, +0.07], `retreat=3
  avoid=1.5` −0.10 [−0.29, +0.08]. None ahead; `avoid=1.0` is behind.
- Reading teleportation instead of starting a rage (`avoid`) doesn't work as built: the rules rage anyway while the
  scroll takes effect, and the rage is then wasted. Leaving a fight met exhausted (`retreat=3`) saves some deaths and
  costs as much elsewhere. Exploring every level (`calm`) buys XL but not depth.
- **Measured**: every number above (scripts below); the reference against yesterday's runs; every game on its seed
  three ways; the two morgues stamped early (on the server, on their seed, with their turn counts); the tests (`uv
  run pytest -q`: 478 passed, 5 deselected; `uv run ruff check`: clean).
- **Inferred**: why `avoid` loses (the rage after the read and the lost scroll, read from the choices after it, not
  forked); why `calm`'s extra XL doesn't turn into depth (the death bands and turns, not a cause table); that
  `retreat=3`'s saved deaths are paid back later (the count of deaths falls while depth stays level).
- Not measured: forks for any of these; a `teleport=3` at a lower ratio ((d) of the previous section); `avoid` with a
  rule that holds the rage until the scroll takes effect.
- Runs: `runs/brain/v6e/{A,C}-{ref,av15,av10,r3,calm,calmrec2,r3av15}`. Scripts in the job's `brain-v6e/` scratch
  directory: `chain.sh`, `jobs-ref.txt` (not used on its own: the reference is the first two lines of
  `jobs-tune.txt`), `jobs-tune.txt`, `jobs-combo.txt`, `arms.py`, `seeds.py`, `verify.py`, `refresh.sh`,
  `mindex.py` (copies), and new: `cattrib.py`, `avoidafter.py`, `calmdiag.py`, `oddseeds.py`. Seeds spent: none;
  evaluation seeds replayed: A and C only.

#### Why `calm=1` dies more on D:4–6, and three switches against it: none helps (2026-11-16, morning)

`calm=1` explores twice as many levels to the end and arrives 0.3–0.6 XL higher from D:5, yet ends level with the
defaults or below them (−0.28 [−0.62, +0.07] on A + C), because more characters die on D:4–6 (A 67 → 90, C 54 → 66).
This section asks why, from the games already played, and tries a rule against each of the largest causes. **Result:
the extra deaths come from the extra exploring itself: more fights, in parts of levels the defaults leave unvisited,
more of them with uniques, each a little deadlier. Each of the three switches removes the deaths it aims at, and as
many come back elsewhere on the same levels. None is ahead of the defaults or of `calm=1` alone, so no fresh test was
played and seeds 690000–690599 are still unspent.** No default was changed.

**Why: the games already played** (`runs/brain/v6e/{A,C}-{ref,calm}`, 399 paired dungeons, scripts in the job's
`brain-v6f/`; "D:4–6" is the deepest level reached, as in `arms.py`, unless said otherwise).

- *Not more fights, deadlier ones* (`fights.py`; band by the level the fight is on). On D:4–6 `calm=1` spends 14% (A)
  and 41% (C) more turns but begins only 5–9% more fights (A 4,012 → 4,219, C 3,219 → 3,517), since much of the extra
  time is rest. Deaths per 100 fights rise (A 1.67 → 2.16, C 1.62 → 1.85), and all of the rise is in fights begun
  fresh (A 1.16 → 1.49, C 0.82 → 1.31). Fights begun exhausted are as many and as deadly as before. On D:7+ it is the
  other way round: deaths per 100 fights fall (A 5.54 → 3.73, C 6.83 → 4.43), which is the XL paying off, too late.
- *Uniques.* Fights on D:4–6 with a unique in view rise by half (A 156 → 225, C 125 → 184) at the same 8–10% death
  rate, so about 17 more deaths (A 12 → 21, C 11 → 19). First sightings of a unique on D:4–6: A 182 → 243, C 143 → 190.
- *Where.* The calm character spends turns 200–600 of a level on ground the defaults have left by then. Deaths on
  D:4–6 after 400 turns on that level: A 7 → 19, C 5 → 20 (`budget.py`).
- *Signs of danger don't predict the deaths* (`danger.py`). Fights on a level that has already shown a rage, a unique,
  a threat-3 monster or HP under half are no deadlier than fights on one that hasn't. So "leave a level after a bad
  sign" has nothing to work with. 96–97% of D:4–6 levels see a rage in both arms.

**Categories.** The deaths where `calm=1` died on D:4–6 and the reference got deeper ("target", 88: 53 on A, 35 on C)
against the reverse ("control", 61: the reference died there and `calm=1` got deeper). Each death is put in the first
category that fits, over its fatal episode: the choices since the last `explore` with nothing in view on that level
(`deaths.py`).

| category of the fatal episode (first that applies) | target | control | target, killer never in the reference's view on that level or met after more turns there than the reference spent in all |
| --- | --- | --- | --- |
| exhausted at ≤ 35% HP with a known teleportation scroll readable, not read | 14 | 2 | 6 |
| a unique in the fight | 24 | 12 | 12 |
| threat-3 monster, or the foes' HP ≥ the character's maximum | 23 | 19 | 10 |
| begun exhausted (`-Berserk`) | 18 | 19 | 8 |
| begun raging or under 80% HP | 6 | 6 | 4 |
| ordinary fight | 3 | 3 | 2 |
| **all** | **88** | **61** | **42** (control 13) |

- The excess (88 − 61 = 27) sits in two categories: the unread scroll (+12) and uniques (+12). Not in exhaustion
  (begun exhausted, any category: 29 vs 22; and `calm=1 recover=2`, which rests it off, has 87 target deaths against
  88). Not in HP at the start either: the median fatal episode begins at full HP in both.
- A known teleportation scroll was held at the start of 30 target episodes against 9 control ones. Exploring finds
  and identifies more scrolls, and the rules don't read them: `teleport=3` waits for foes' HP of 1.5× the character's
  HP now, and these characters were exhausted at 10–35% against foes with mostly 0.8–1.3× that.
- The killer was never in the reference's view on that level in 40 target deaths (control 13).
- XL when the fatal episode began, against the reference's on arrival at that depth: +0.6 (control +0.0).
- Read end to end (`tell.py`): 540134 (waits out a rage, explores on exhausted and slowed, meets an orc warrior with
  two scrolls and a potion in the pack, reads at 8/60 HP and dies the same turn); 500069 (the same walk after a rage,
  into Edmund at 26 steps from the stairs up, no scroll); 500187 (a gnoll and orc pack 400 turns into D:4, which the
  reference left after 44 turns; nothing in the pack would have helped); 540067 (Jeremiah seen at 3 steps while
  standing on the stairs up with a scroll in the pack; the rage runs out, and the character fights on exhausted for 20
  turns, drinks both potions, and reads at 4 HP); 500003 (exhausted at 26/56 against two orc priests, scroll unread,
  killed by their smiting); 540021 (reads at 23/74, the teleport works, and the character, still exhausted and slowed,
  lands next to an iguana and dies there with two scrolls left). The categories hold in all six. 540021 also shows the
  mechanism that defeats `escape` below.

**Three opt-in switches** (`src/ladder/brain/policy.py`, `Style`; all off by default; no default changed; no
`STYLE_ADDED_AS` entry, since none was flipped):

- **`--style escape=h`** (`escape_rule`) targets the unread scroll. In a fight, exhausted after a rage (`-Berserk`,
  not raging), at h × max HP or under, with no teleport coming: read teleportation whatever the foes' HP. It sits where
  `teleport=3`'s read does (after a cure and a retreat, before the healing potion). Tuned at h = 0.5.
- **`--style unique=1`** (`unique_rule`, `dangerous_unique`) targets uniques. A unique the game rates threat 3 in view,
  not adjacent, the character not raging, no teleport coming: read teleportation. While that teleport is coming and
  the unique is still in view and not adjacent, don't rage: drink the potion at half HP, else walk toward the stairs up,
  else wait. Once the scroll is read, `BrainTiers` marks the level explored, so the rules head down rather than
  explore back into it. Adjacent, or with no scroll, the rules play as before.
- **`--style calmfor=T`** targets the late turns on a level. `calm` holds only for the first T turns of each visit to
  a level (`obs["level_turns"]`). After that, a rage's "Calm down" refusals count toward setting `explore` aside again,
  as without `calm`, so the next rage ends the exploring there. Tuned at T = 400.
- Tests in `tests/test_brain.py`: `test_escape_is_off_by_default_and_off_plays_as_before`,
  `..._reads_teleportation_when_exhausted_and_low_whatever_the_foes`, `test_escape_reaches_the_rules_inside_brain_tiers`,
  `test_unique_is_off_by_default_and_off_plays_as_before`,
  `..._reads_teleportation_at_a_dangerous_unique_and_keeps_away_while_it_comes`,
  `..._reaches_the_rules_inside_brain_tiers_and_leaves_the_level_after_reading`,
  `test_calmfor_limits_calm_to_the_first_turns_on_a_level`,
  `test_escape_unique_and_calmfor_are_styles_and_old_runs_still_match`.

**Tuning.** Each switch together with `calm=1`. Same method as the last section: this tree, no model, epsilon 0,
`ladderbrain*` accounts (9 workers asked; `ladderbrain7` and `9` refuse the login, as in every v6e run, so 7 played),
A (500000–500199) and C (540000–540199) only, 03:48–06:17 (`chain.sh`, `jobs-tune.txt`). Each arm is compared with
the existing `v6e/{A,C}-ref` (the defaults) and `v6e/{A,C}-calm`, paired by dungeon over games both arms finished,
neither stale nor off its seed. 95% bootstrap over dungeons, 10,000 resamples. Analysed after all six runs (`arms.py`).
Description only: these blocks are spent.

| arm (`--style`) | A: mean depth | C: mean depth | − defaults, A | − defaults, C | **− defaults, A + C** | **− `calm=1`, A + C** | died D:1–3 / 4–6 / 7+ (A + C) | levels left down (D:3+) explored |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| defaults (`v6e/*-ref`) | 6.99 | 6.27 | | | | | 64 / 121 / 196 | 41% / 42% |
| `calm=1` (`v6e/*-calm`) | 6.49 | 6.24 | −0.50 [−1.00, +0.01] | −0.06 [−0.51, +0.40] | **−0.28 [−0.62, +0.07]** (399) | | 66 / 156 / 163 | 82% / 80% |
| `calm=1 escape=0.5` | 6.43 | 6.21 | −0.56 [−1.09, −0.03] | −0.09 [−0.53, +0.36] | **−0.33 [−0.67, +0.02]** (399) | −0.05 [−0.19, +0.10] (400) | 65 / 151 / 167 | 80% / 81% |
| `calm=1 unique=1` | 6.47 | 6.08 | −0.52 [−1.00, −0.04] | −0.19 [−0.64, +0.27] | **−0.36 [−0.69, −0.02]** (399) | −0.09 [−0.23, +0.05] (400) | 65 / 153 / 167 | 83% / 81% |
| `calm=1 calmfor=400` | 6.21 | 6.28 | −0.78 [−1.30, −0.28] | +0.00 [−0.45, +0.45] | **−0.39 [−0.75, −0.05]** (398) | −0.12 [−0.40, +0.15] (399) | 77 / 138 / 169 | 64% / 66% |

Dungeons paired in brackets. Out of the pairs: 540052, which hangs in the reference as it has in every C run, and
500173 of `calmfor=400`, whose morgue (right seed, 125 turns, died on D:1 as in every arm) is stamped 6 s before the
game's directory, outside `seeds.py`'s 5-second window, as two were last time. Every game of the six runs was checked on its seed (`verify.py`): no "Welcome back", no protocol
without its seed, no first step after turn 1, none hung.

**What each did** (`fires.py`, `uniq.py`, `deaths.py`, `calmdiag.py` on the new runs):

- **`escape=0.5`** read in 54 games on A (80 reads) and 43 on C (64), where `teleport=3` would not have. Within 30
  turns of its reads 16% died, against about 26% at the same moments under `calm=1` alone (`would.py`). The unread-scroll
  category fell from 14 target deaths to 3, but target deaths stayed at 88: the same characters died a little later,
  in the "threat-3 or big fight" category (23 → 30). 166–168 of 200 games end at the same depth as `calm=1`'s.
- **`unique=1`** read in 59 games on A (101 reads) and 47 on C (80). Within 100 turns of a read, 5–8% died, against
  14–16% at the same moments under `calm=1` alone. Deaths within 100 turns of first seeing a unique on D:4–6 fell
  (A 45 → 37, C 29 → 27), but D:4–6 deaths overall did not (A 90 → 86, C 66 → 67), and the target set is 86 with
  24 still in the unique category. The level is left after the read, but the exploring hardly falls (83% / 81%).
- **`calmfor=400`** brings the exploring halfway back (64–66% of levels explored to the end) and D:4–6 deaths down
  (156 → 138). But XL on arrival stays where `calm=1` has it (D:5 6.1, D:6 7.1). Depth is lower on A (−0.28 against
  `calm=1`), level on C, and deaths on D:1–3 rise (66 → 77; that cap also applies there).

**No fresh test.** The rule was to pre-register a test on 690000–690599 only for a configuration clearly ahead on A + C
(pooled interval mostly above zero, both blocks positive). Every arm is below the defaults on A + C, with the best
point estimate −0.33. So nothing was pre-registered and **seeds 690000–690599 were not played; they are still unused.**

**Summary of the section.**

- `calm=1`'s extra deaths on D:4–6 are the cost of the extra exploring: about the same number of fights, more of them
  in places the defaults never go, half again as many with uniques, and a scroll in hand more often that the rules
  don't read in time. The XL it buys pays off on D:7+ (fewer deaths per fight there), but by then too many have died.
- Three rules that remove the deaths where they act (an unread scroll at low HP, a threat-3 unique, the late turns on
  a level) don't change depth. The characters they save die soon after on the same levels. Against the defaults:
  `calm=1 escape=0.5` −0.33 [−0.67, +0.02], `calm=1 unique=1` −0.36 [−0.69, −0.02], `calm=1 calmfor=400`
  −0.39 [−0.75, −0.05]. Against `calm=1` alone all are within ±0.15.
- **Measured**: every count and difference above; that every game was on its seed; the tests (`uv run pytest -q`: 486
  passed, 5 deselected; `uv run ruff check`: clean).
- **Inferred**: that the saved characters die later "because" they remain weak on a dangerous level without the scroll
  (read from where the deaths moved, not forked); that the extra fights are in the part of each level the defaults skip
  (from turns on the level and from killers the reference never saw, not from map coverage, which the step log doesn't
  keep); that `calmfor`'s extra D:1–3 deaths are its doing rather than chance (11 games, not tested).
- Not measured: forks at the rules' moments; other values of h or T; `escape` or `unique` without `calm` (by
  `would.py`, `escape`'s moments are 113 and 94 fights on A and C under the defaults against 138 and 108 under `calm=1`;
  `unique`'s 83 and 65 against 126 and 91).
- Runs: `runs/brain/v6f/{A,C}-calm-{esc50,uniq,for400}`. Scripts in the job's `brain-v6f/` scratch directory: copies
  of `arms.py` (main guarded so it can be imported), `seeds.py`, `verify.py`, `gather.py`, `flags.py`, `calmdiag.py`,
  `cattrib.py`, `mindex.py`, `chain.sh`, `refresh.sh` (now lists the morgues with `find`, since the shell's argument
  list overflowed); new: `load.py`, `fights.py`, `fightfeat.py`, `deaths.py`, `danger.py`, `budget.py`, `uniq.py`,
  `tele.py`, `would.py`, `fires.py`, `tell.py`, `jobs-tune.txt`. Seeds spent: none; evaluation seeds replayed: A and C
  only. The server's disk stayed at 52%.

#### What qw does differently on the same dungeons, and two of its habits as switches: neither helps (2026-11-16, day)

Seven hand-written rules in a row failed, so this section stops guessing and asks a narrower question: **on the same
dungeons, what does qw do on D:3–7 that our rules don't?** qw played block A (500000–500199) on the `zk` build with
its tuned Minotaur settings (`runs/qw/zk-heldout-200`, 2026-11-12). The same seed gives the same dungeon, so the two
bots' games can be compared level by level. **Result: the largest measured differences are in how qw fights: it
rages in a quarter as many fights, and late (median 67% HP, against our 100%), and it waits for an enemy to come
in 45% of its fights where our rules walk up to it in 92%. Both habits can be expressed with our actions, so both
were built as opt-in switches and tuned on A and C. Both lose depth: raging at 70% HP −0.68 [−1.07, −0.31], at
90% HP −0.48 [−0.90, −0.07], waiting −0.39 [−0.75, −0.01]. So qw's habits don't carry over one at a time.** What
keeps qw alive seems to be the combination: more armour, a shield, thrown weapons, stepping out of a surround, and
Trog's Hand. Our bot has no actions for any of these. No default changed; no fresh test; seeds 690000–690599 are still
unspent.

**Data.** qw: `runs/qw/zk-heldout-200`, 200 games. Each game has a state line (`QWS`) and a plan (`QWACT`) for every
decision qw makes, plus its morgue (199 of them; one game ran into the 3,600 s limit). qw's
morgue notes also log its own item use ("WEARING", "READING", "STAIRDANCE"). Our bot:
`runs/brain/v6e/A-ref` (the defaults) and `v6e/A-calm` (`calm=1`), with step logs and morgues. These really are the
same dungeons. Both characters start with 19 HP, AC 2 and EV 11 and meet the same endoplasm on turn 8 of 500000. On
500005 both find the altar of Trog on D:2, and Sigmund and Tus Rium's shop on D:3. qw's other block, 600000–600599
(`held6-*`), was never played by our bot, so it can't be paired and isn't used. Scripts are in the job's `brain-v6g/`
scratch directory. "Fight" means the same for both bots: a run of choices with a hostile in view on one level,
ended by 20 turns with none or by a level change (`fights2.py`). It includes the lulls inside a fight.

**Survival per level** (`cmp.py`; the Dungeon level each death happened on; all 200 dungeons):

| level | qw: reached / died there | defaults | `calm=1` |
| --- | --- | --- | --- |
| D:2 | 198 / 21 (11%) | 198 / 12 (6%) | 197 / 12 (6%) |
| D:3 | 176 / 8 (5%) | 180 / 7 (4%) | 176 / 10 (6%) |
| D:4 | 167 / 13 (8%) | 172 / 16 (9%) | 167 / 28 (17%) |
| D:5 | 154 / 9 (6%) | 152 / 21 (14%) | 137 / 28 (20%) |
| D:6 | 145 / 10 (7%) | 133 / 30 (23%) | 110 / 35 (32%) |
| D:7 | 136 / 11 (8%) | 101 / 23 (23%) | 75 / 13 (17%) |

qw's deepest Dungeon level is 9.22 against the defaults' 6.97: +2.26 [+1.49, +3.02], paired. qw dies *more* on D:2
and about as often on D:3–4. The gap opens on D:5–7, where its death rate per level stays at 6–8% while ours rises to
14–23%. The defaults died on D:4–6 in 67 dungeons. qw got deeper in 49 of them, died earlier in 14 and died on the same
level in 3. For `calm=1`'s 91 the counts are 63, 18 and 9.

**On arrival at each level** (`cmp.py`; means over the dungeons where all three bots reached the level; qw / defaults /
`calm=1`):

| level (dungeons) | XL | max HP | AC | SH | heal wounds held | curing held | teleportation held | piety (stars) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D:4 (133) | 4.9 / 4.5 / 4.6 | 45 / 44 / 45 | 9.2 / 8.2 / 8.4 | 1.2 / 0.4 / 0.4 | 0.5 / 0.2 / 0.2 | 1.0 / 0.6 / 0.7 | 0.7 / 0.5 / 0.6 | 2.1 / 1.9 / 1.9 |
| D:5 (89) | 6.3 / 5.8 / 6.1 | 55 / 53 / 55 | 10.6 / 9.5 / 10.0 | 1.6 / 0.4 / 0.6 | 0.6 / 0.2 / 0.3 | 1.3 / 0.7 / 0.9 | 1.0 / 0.7 / 0.8 | 2.5 / 2.0 / 2.0 |
| D:6 (61) | 7.3 / 6.7 / 7.1 | 64 / 59 / 62 | 12.4 / 10.4 / 11.0 | 1.7 / 0.1 / 0.4 | 1.0 / 0.3 / 0.4 | 1.8 / 0.8 / 1.0 | 1.3 / 0.7 / 1.0 | 2.8 / 2.0 / 2.1 |
| D:7 (37) | 8.3 / 7.3 / 7.8 | 73 / 64 / 69 | 14.4 / 10.8 / 12.1 | 1.9 / 0.3 / 0.2 | 1.1 / 0.2 / 0.3 | 2.3 / 0.9 / 1.3 | 1.8 / 0.9 / 1.4 | 3.1 / 1.9 / 2.1 |

- EV is the same for all three (8–9). qw always arrives at full HP and never raging, exhausted or slowed. Our bot
  arrives in one of those states 6–10% of the time on D:4–7.
- `calm=1` spends about as many turns per level as qw (median from first arrival on D:k to first arrival on D:k+1,
  over dungeons all three passed: D:4 862 / 496 / 836, D:5 896 / 527 / 844, D:6 976 / 320 / 764). So it isn't
  a matter of time spent: on D:4 `calm=1` dies at twice qw's rate after the same number of turns.

**How each bot fights on D:3–7** (`fights2.py`, `rage.py`; a fight counts toward a row if the action happened at least
once in it):

| | qw | defaults | `calm=1` |
| --- | --- | --- | --- |
| fights | 6,650 | 4,049 | 4,720 |
| fatal (per 100 fights) | 51 (0.77) | 97 (2.40) | 114 (2.42) |
| started a rage | 938 (14%) | 2,255 (56%) | 2,568 (54%) |
| HP at the first rage, median | 67% (78% of rages at ≤ 70%) | 100% (96% above 70%) | 100% |
| begun exhausted after an earlier rage | 42 (0.6%), 2 fatal | 172 (4.2%), 13 fatal | 144 (3.1%), 12 fatal |
| waited for an enemy to come (`melee_wait_for_enemy`; ours `wait`) | 3,010 (45%) | 89 (2%) | 73 (2%) |
| walked up to an enemy | 2,460 (37%) | 3,719 (92%) | 4,319 (92%) |
| a tactical step (out of a surround, a cloud, sight of a ranged enemy) | 2,292 (34%) | no action | no action |
| threw a javelin or boomerang | 2,066 (31%) | no action | no action |
| fled toward the stairs up | 576 (8.7%) | 141 (3.5%) | 168 (3.6%) |
| left the level upward after the fight | 278 (4.2%) | 47 (1.2%) | 56 (1.2%) |
| zapped a wand | 165 (2.5%) | no action | no action |
| Trog's Hand / Brothers in Arms | 35 / 10 | no action | no action |
| haste / curing, cancellation or resistance | 129 / 63 | no action | no action |
| healing potion / teleportation read | 27 / 44 | 95 / 44 | 117 / 69 |
| two or more enemies adjacent at some point | 1,377 (21%) | 1,015 (25%) | 1,156 (24%) |

- **qw rages late and rarely.** Its fights without a rage: 5,712, of which 6 were fatal (0.1%). Our rules don't
  rage in only 1,794 fights, mostly small ones. Above 70% HP qw raged at 11–18% of its decisions when the enemies
  within two squares had its maximum HP or more between them (by the monster table), and at 0.2–1.2% otherwise
  (`qwrage.py`).
- **After a fight qw rests to full HP and waits out the exhaustion.** Every one of its 4,465 first explores after a
  fight is at full HP and not recovering. Ours: 92% at full, and 7.1% raging, exhausted or slowed.
- **Stairs.** qw went up a level 634 times on D:2–8, in 155 games, 338 of them with enemies in view. Ours: 72 times in
  47 games (`calm=1` 74 in 49). In its morgue notes qw stairdanced 308 times by D:7.

**Uniques and killers on D:3–7** (`uniq2.py`, `hand.py`; from each bot's morgue notes: "Encountered", "Killed",
"Slain by").

- **Uniques: qw meets more and dies to fewer.** It met 517 and killed 467 (90%); 7 killed it. The defaults met 308,
  killed 260 (84%) and died to 13. `calm=1` met 366, killed 313 (86%) and died to 24. qw doesn't avoid uniques: it
  meets more of them and kills them.
- **The same unique on the same dungeon.** Of the defaults' 13 deaths to a unique, qw killed that unique 9 times on
  the same dungeon. For `calm=1` it was 17 of 24 (Edmund 5 deaths of 25 met, against qw's 31 killed of 31; Maggie 3
  of 9 against qw's 22 of 24, none fatal).
- **Killers on D:3–7 the parse could name.** qw (31): gnoll 7, orc 3, orc wizard 3, Jeremiah 3. Defaults (66 of 97):
  wight 10, gnoll 7, orc 6. `calm=1` (81 of 114): gnoll 12, wight 8, Edmund 5.
- **Trog's Hand monsters.** In the deaths on D:4–6, the fatal fight had in view a monster on qw's Trog's Hand list
  (`hand_monsters`: Grinder, orc wizards and sorcerers, ogre mages…) in 21 of the defaults' 67, 24 of `calm=1`'s 91
  and 7 of qw's 32. It had a wight in 11, 10 and 2.

**Items on D:1–7.**

- **qw (its morgue notes, 200 games).** It put on armour or jewellery 1,176 times:
  - body armour about 420;
  - rings 283 and amulets 64;
  - shields 115 (orb, buckler, kite, tower);
  - cloaks 77, gloves and boots 166.
- It also wielded a better weapon 279 times. It read enchantment scrolls onto its gear 293 times, branded a weapon
  63 times and read acquirement 33 times. It bought 218 things in shops. By D:4 38% of its characters carried
  javelins or boomerangs, and by D:6 55%.
- **The defaults.** They chose `wear` 507 times and `wield` 151 times (choices, not items). They never wear
  jewellery: `gear.py` ranks none, and has no tower shield.
- An enchant, brand or acquirement scroll read as unknown has its prompt cancelled and the scroll wasted
  (`ITEM_PROMPTS`). A known one is never read.
- Shops are fenced off (`fence_shops`).

**qw's rules for these, in its own source** (the deployed `runs/qw/build-zk/qw.lua`, with upstream
`runs/qw/src/source/` and the tuned overrides in `runs/qw/combo1-lua/MiBe_mace.lua`).

- **Rage.** `want_to_berserk` (qw.lua 12339–12362) plus the `zerk_hp70` override fires on any of:
  - HP ≤ 70% with an enemy within two that it has a melee path to (`check_berserkable_enemies`);
  - a scary enemy (threat ≥ 3) within two whose best answer is melee;
  - threat within two at or above `high_threat_level()` (7925–7927: 2 at XL ≤ 7, 7 from XL 10).

  It is last in the emergency cascade (`set_plan_emergency`, 12594–12644).
- **Waiting.** `plan_melee_wait_for_enemy` (11209–11270, plans-attack.lua:193–254) runs after melee. It waits while
  an enemy can't be hit yet, has a path to the character, has no more reach than the character and is further away
  than its own reach (`player_can_wait_for_melee`, 7796–7805). It stops and moves in when a ranged enemy is in view,
  and after 10 waits in a row. It holds whatever square it stands on: qw has no corridor logic for a melee character.
- **Tactical steps.** `choose_tactical_step` (9941–10005, move-tactics.lua:259–323) never runs while raging. Its
  reasons:
  - out of fire or a cloud;
  - away from a ranged enemy, "hiding";
  - out of sight of sleeping monsters, "stealth";
  - "outnumbered": two or more adjacent, and the step cuts adjacent plus ranged enemies by two.
- **Throwing.** `plan_throw` (11189–11201) throws at a threat-3 enemy when that cuts its threat most, otherwise at any
  target in line of sight when nothing can be hit in melee. qw picks up javelins, boomerangs and large rocks
  (`want_missile`, 5503–5510).
- **Fleeing and stairdancing.**
  - `want_to_flee` (8701–8760, move-flee.lua:55–114) never flees with a melee enemy within two. It flees only along
    a route no pursuer can catch.
  - `want_to_stairdance_up` (14688–14741) goes up from the stairs when it wants to flee. It also goes up to fight the
    adjacent followers alone.
- **Resting.** `should_rest` and `reason_to_rest` (14311–14376) rest to full HP and through berserk cooldown and
  slowness, before any exploring or stairs.
- **Trog's Hand.** `want_to_trogs_hand` (12321–12330) fires at a `hand_monsters` enemy in view (8065–8095), at
  piety ≥ 2.
- **Equipment.**
  - `upgrade_equipment` (13431–13444) and the heavy-armour valuation (`armour_base_value`, 2068–2178).
  - `SHIELD_CRAZY` makes it always wear a shield.
  - `use_good_consumables` (13685–13725) reads enchant, brand and acquirement scrolls.

**Ranked differences**, by how many of our D:4–6 deaths each touches (the fatal fight, `deaths2.py`; defaults 67,
`calm=1` 91, qw 32 for comparison). "Touches" is an upper bound: the difference was present in that death, not
shown to have caused it.

| rank | difference | count | D:4–6 deaths touched: defaults / `calm=1` (qw) | measured or inferred | our actions can express it? |
| --- | --- | --- | --- | --- | --- |
| 1 | raging at full HP at the first threat-2 enemy within two, not at 70% HP | rage in 56% vs 14% of fights; median HP 100% vs 67%; fights begun exhausted 4.2% vs 0.6% | first rage above 70% HP in 54 / 72 (7); begun exhausted 8 / 10 (0) | measured | yes: built as `rage` |
| 2 | walking up to an enemy instead of waiting for it | walked in 92% vs 37% of fights, waited 2% vs 45% | walked up to a non-ranged enemy in 49 / 61 (11) | measured | yes: built as `hold` |
| 3 | fighting surrounded instead of stepping out | 2+ adjacent in 25% vs 21% of fights; qw stepped tactically in 34% | 2+ adjacent in 54 / 65 (23); 3+ in 34 / 37 (16) | measured (the step's effect inferred) | no: needs a step to a chosen square |
| 4 | less armour, no shield, no jewellery, enchant scrolls wasted, no shops | AC −1.0 at D:4 to −3.6 at D:7; SH 1.2–1.9 vs 0.1–0.4; 0 vs 347 rings and amulets, 0 vs 293 enchantments by D:7 | every death (inferred: a lower AC makes every fight costlier) | measured gap, inferred effect | partly: `wear` exists, but jewellery, enchant prompts and buying don't |
| 5 | no ranged attack | qw threw in 31% of fights, 55% carry missiles by D:6 | a ranged enemy in view in 48 / 74 (23) | measured gap, inferred effect | no: needs `throw` |
| 6 | no Trog's Hand | 35 qw fights on D:3–7 | a Hand monster in view in 21 / 24 (7) | measured gap, inferred effect | no: needs `trogs_hand` |
| 7 | fewer trips up the stairs, no stairdance | 634 vs 72 trips up on D:2–8 | stairs up within 8 at the start in 29 / 27 (4); went up in it 6 / 16 | measured | partly: `flee_up` exists; `retreat=3` and `stairs=1` were level |
| 8 | exploring on before full HP and before the exhaustion ends | 0% vs 7.1% of explores after a fight while recovering | begun exhausted 8 / 10 (0) | measured | yes, and tried: `recover=2`, `calm=1` were level or behind |
| 9 | the healing potion drunk at half HP, not at a quarter | drunk in 95 vs 27 fights; held at D:6 0.3 vs 1.0 | heal wounds held at the start of 4 / 11 (14) | measured | yes, untested; qw's own heal thresholds were within noise (`docs/qw-teacher.md`) |

**Two opt-in switches** (`src/ladder/brain/policy.py`, `Style`; both off by default; no default changed, no
`STYLE_ADDED_AS` entry).

- **`--style rage=h`** (`late_rage`). The rules start a rage only with a hostile within two squares and one of:
  - HP at h × max or under (and always at half, as before);
  - the hostiles within two have the character's maximum HP or more left between them (`foe_hp` of those alone,
    which `foe_hp` now accepts);
  - one of them is threat 3.

  It no longer rages at the first threat-2 monster, or at three small ones, within two.
- **`--style hold=k`** (`hold_ground`, `BrainTiers.holds`). The rules wait (`s`) instead of walking up when all of
  these hold:
  - hostiles are in view;
  - every one is three or more squares away (`HOLD_FROM`);
  - none attacks from range or with reach by the monster table;
  - one is awake, not unaware or fleeing, and able to move.

  It allows up to k waits in a row, then one step toward them, and it may wait again, as qw's `wait_count` does.
  The rage and the potion still come first.
- Tests in `tests/test_brain.py`:
  - `test_rage_and_hold_are_off_by_default_and_off_plays_as_before`
  - `test_rage_waits_for_hp_to_fall_or_the_fight_up_close_to_be_big`
  - `test_hold_waits_for_awake_melee_hostiles_to_come`
  - `test_hold_caps_the_waits_in_a_row_inside_brain_tiers`
  - `test_rage_and_hold_are_styles_and_old_runs_still_match`

**`hold` was built twice.** The first version waited with nothing *adjacent*, as qw does. On A it lost 1.86 levels.
Gnolls carry spears and halberds and hit from two squares, and nothing in view says which ones carry a polearm (qw
reads the monster's actual reach). 68 of that run's deaths had "hits you from afar" in the last messages, against 16
under the defaults. The second version waits only while every hostile is three or more away (`HOLD_FROM`): 14 such
deaths. Both are in the table.

**Tuning.**

- **Method.** The same as the last two sections: this tree, no model, epsilon 0, 9 workers asked (7 played; see
  below), A and C only, 06:46–09:07 (`chain.sh`, `jobs-tune.txt`, `jobs-hold2.txt`).
- **Reference.** Each arm is paired against `v6e/{A,C}-ref` (the defaults) by dungeon, over games both finished
  and neither stale nor off its seed. 95% bootstrap over dungeons, 10,000 resamples (`arms.py`). Description only:
  these blocks are spent.
- **The planned arms changed after `rage=0.7` came in.** The plan was `rage=0.7`, `hold=10`, the two together and
  `rage=0.5`. The combination and `rage=0.5` (a still later rage) were replaced by `rage=0.9` (a rage after the first
  hits). That change was made before any `hold` result was in.

| arm (`--style`) | A: mean depth | C: mean depth | − defaults, A | − defaults, C | **− defaults, A + C** | deeper / same / shallower | died D:1–3 / 4–6 / 7+ (A + C) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| defaults (`v6e/*-ref`) | 6.99 | 6.27 | | | | | 64 / 121 / 196 |
| `rage=0.7` | 6.11 | 5.82 | −0.90 [−1.47, −0.38] | −0.46 [−0.99, +0.08] | **−0.68 [−1.07, −0.31]** (398) | 122 / 95 / 181 | 85 / 144 / 152 |
| `rage=0.9` | 6.12 | 6.17 | −0.86 [−1.47, −0.24] | −0.09 [−0.66, +0.47] | **−0.48 [−0.90, −0.07]** (397) | 146 / 74 / 177 | 93 / 122 / 168 |
| `hold=10`, waiting at two | 5.13 | 4.70 | −1.86 [−2.41, −1.32] | −1.58 [−2.06, −1.11] | **−1.72 [−2.09, −1.36]** (398) | 87 / 83 / 228 | 141 / 154 / 87 |
| `hold=10`, from three (`HOLD_FROM`) | 6.58 | 5.89 | −0.39 [−0.94, +0.16] | −0.38 [−0.87, +0.10] | **−0.39 [−0.75, −0.01]** (397) | 135 / 105 / 157 | 73 / 134 / 171 |

- **Dungeons left out of the pairs.**
  - 540052 hangs in the reference, as in every C reference run. It didn't hang in any of this section's C runs.
  - Hung here: 500124 (`rage=0.7`, which also ran 500155 to the choice limit), 500010 (`rage=0.9`) and 500039 (the
    first `hold`).
  - Three games of 41–150 turns have no morgue within `seeds.py`'s 5-second window, as short games have had before:
    540091 (`rage=0.9`), 500059 and 540103 (the second `hold`).
- **Seed checks** (`verify.py`). Every game: no "Welcome back", no protocol without its seed, no first step after
  turn 1.

**What each one did** (`acts.py`, fights on D:3–7, A then C):

- **`rage=0.7`.**
  - Rages in 24% and 26% of fights, at a median 68% HP, against 56%.
  - Fewer fights begun exhausted: 1.9% and 2.5%, against 4.2% and 4.4%.
  - Arrives higher: XL on D:7 8.2 and 7.9, against 7.5 and 7.5.
  - But deaths per 100 fights rise (2.51 and 3.03, against 2.40 and 2.53), and deaths on D:1–3 rise from 64 to 85.
    A low-level character that waits until it is hurt dies before the rage comes.
- **`rage=0.9`.** It rages in 46–48% of fights, at 86% HP: the same fights, a few hits later. It loses on A (deaths
  on D:1–3 22 → 45) and is level on C.
- **`hold`.**
  - The second version waits in 68% of fights on A, about as often as qw (whose 45% counts its waits differently).
  - Deaths per 100 fights: 2.85 against 2.40.
  - XL on arrival is no higher.
- **Why they lose (inferred).** Each is one part of a style whose other parts our bot lacks. qw can let a fight come
  to it and go without a rage because it has 1–4 more AC, a shield, a thrown weapon for the approach, a step out of
  a surround, and Trog's Hand for casters. Its own tuning found that raging *sooner* than its upstream 50% gained +1.0
  levels (`docs/qw-teacher.md`, `zerk_hp70`). Our rules already rage sooner than qw.

**No fresh test.** The rule was to pre-register a test on 690000–690599 only for a configuration clearly ahead on
A + C: pooled interval mostly above zero, both blocks positive. Every arm is behind the defaults, all four with the
pooled interval wholly below zero. So nothing was pre-registered and **seeds 690000–690599 were not played;
they are still unused.**

**What would need a new action** (a new entry in `features.ACTIONS`, so a change to the model's contract: see
"Changing the contract"). In the order of the ranking above:

- **`step_out`, a tactical step (rank 3).**
  - Game command: one move key (`ladder.travel.DIRECTIONS`).
  - Choice of square: the adjacent floor square, not raging, where the fewest hostiles would be adjacent or have a
    clear shot, ties to the square nearer the enemy. This is qw's `assess_square`.
  - State: `state.cells` (walls, monsters and their positions) has all of it.
  - Fires when two or more are adjacent and a square cuts that by two, or to leave a cloud.
- **Jewellery, enchantment and shops (rank 4).**
  - `P` (put on) with a ranking of rings and amulets in `gear.py`. Leave unknown ones and teleportation alone. The
    menu text gives the item's name.
  - Answer the enchant, brand or acquirement prompt with the body armour's or weapon's letter, instead of
    `cancel_prompt` (`perform`). A known enchant scroll then becomes worth reading at a safe moment.
  - A tower shield and the other missing bases in `gear.ARMOURS`.
  - Buying would need the shop menu (`state` has no shop stock) and is the largest of these.
- **`throw` (rank 5).**
  - Game commands: `Q` then the missile's letter (quiver), then `f`, which fires at the nearest target, confirmed
    with `f` or `.`.
  - State: missiles in the inventory (base type missile: javelin, boomerang, large rock), monster positions (there).
  - Line of fire is the game's to refuse.
  - The rc's autopickup must take javelins and boomerangs and pick them back up after a fight. qw's autopickup does
    that while exploring.
- **`trogs_hand` (rank 6).**
  - Game command: `a`, then the letter the ability menu gives Trog's Hand (the menu text names it).
  - State: piety ≥ 2 (`obs["piety"]` is there), and no `Regen` status already on.
  - Fires on qw's `hand_monsters` names in view.
  - Brothers in Arms the same way at piety ≥ 4. On D:3–7 qw used it in only 10 fights.

**The two accounts that refuse login** (read-only; no secret was read or printed, and no account was changed).

- **Cause.** The webtiles server hashes passwords with its default `crypt_algorithm = "broken"`:
  - The setting is in `webtiles/config.py:83` in the container, and `webserver/config.py` doesn't override it.
  - `userdb.py:317–326` then uses *the password itself* as the DES salt.
  - DES salt characters must be in `[./0-9A-Za-z]`.
  - Our passwords come from `secrets.token_urlsafe(24)` (`src/ladder/keychain.py:28`). They can contain `-` and
    `_`.
  - When such a character falls in the salt, `crypt()` returns the failure token `*0`, which is stored as the hash.
    At login `crypt(pw, "*0")` gives something else, so the login fails every time.
- **Evidence.**
  - Every v6e/v6f run log (21 runs) and all 8 v6g runs leave both accounts out: "Could not log in or register
    'ladderbrain7' (and '9'): Failed to login".
  - The server log of 2026-11-10 shows 7, 8, 9, 10, 11 and 12 all registered within 30 ms, and only 7 and 9 have
    failed ever since. So the "registered at the same instant" explanation in "What it found on the way" is wrong.
  - Their rows exist with flags 0, so they are not banned.
  - A Keychain item exists for all of 1–9 (checked for existence only).
  - The container's `crypt` was tested with made-up passwords: `-b…`, `a_…` and `ab-…` give `*0`, while `Ab-…` and
    `ab_…` don't.
  - About 5% of `token_urlsafe` passwords are bad this way.
  - The earlier note's "two-character password hash" fits `*0`.
- **Measured and inferred.** The mechanism and the code paths are measured. That these two passwords begin badly is
  inferred, since checking it would mean reading the secret.
- **Fix, for a person to run.**
  1. Delete the two rows (`delete from dglusers where username in ('ladderbrain7','ladderbrain9')` in
     `/data/webserver/passwd.db3`) and their Keychain items (`security delete-generic-password -s dcss-ladder -a
     dcss-account/ladderbrain7`, and the same for 9). The next run re-registers them.
  2. To stop it recurring, make `get_or_create_dcss_password` generate salt-safe passwords, such as
     `secrets.token_hex(16)`.
  3. Optionally, set `crypt_algorithm = "6"` on the server, which affects new registrations only.

**Summary of the section.**

- On the same 200 dungeons qw reaches 2.3 levels deeper. Its death rate per level stays at 6–8% through D:7, while
  ours climbs to 14–23% from D:5.
- On arrival qw has more AC, a shield, more healing and teleportation, and somewhat more XL.
- In a fight it rages late and rarely, waits for the enemy, throws, steps out of surrounds, flees more, and uses
  Trog's Hand.
- It meets more uniques than our bot does and kills 90% of them.
- The two habits our actions can express both lose when taken alone: `rage=0.7` −0.68 [−1.07, −0.31], `rage=0.9`
  −0.48 [−0.90, −0.07], `hold=10` −0.39 [−0.75, −0.01] (and −1.72 when it waited at two squares). The rest need
  new actions: a tactical step, putting on jewellery and answering enchant prompts, throwing, and Trog's Hand.
- **Measured**:
  - every count and difference above;
  - that the dungeons are the same (start, first monster, altars, shops, uniques by level);
  - every tuning game on its seed;
  - the login mechanism in the server's code and with test passwords;
  - the tests: `uv run pytest -q` 491 passed, 5 deselected; `uv run ruff check` clean.
- **Inferred**:
  - that the D:4–6 deaths "touched" by each difference were caused by it (they are upper bounds);
  - that qw's lower death rate comes from the combination of kit and fight moves, and not from rage timing or
    waiting alone (read from the tuning, not tested by adding the missing actions);
  - that the 7 and 9 passwords begin with a bad salt.
- **Not done**: any of the new actions; a `hold` that also steps in at two against known polearm users; `rage`
  restricted to deeper levels.
- **Runs**: `runs/brain/v6g/{A,C}-{rage70,rage90,hold10,hold10b}`. Seeds spent: none; evaluation seeds replayed: A
  and C only. The server's disk stayed at 52%.
- **Scripts** in the job's `brain-v6g/` scratch directory:
  - new: `load2.py` (qw's state logs and the brain's step logs in one shape), `cmp.py`, `fights2.py`, `rage.py`,
    `qwrage.py`, `uniq2.py`, `deaths2.py`, `misc.py`, `hand.py`, `acts.py`, `jobs-tune.txt`, `jobs-hold2.txt`;
  - copies: `arms.py`, `seeds.py`, `verify.py`, `mindex.py`, `chain.sh` (now prints the server's disk after each
    run) and `refresh.sh`.

#### Kit and Trog's Hand: two things qw does that our bot couldn't, built as switches (2026-11-16, afternoon)

The previous section found that qw does things on the same dungeons that our bot has no way to do at all. This
section builds the two cheapest of them and measures them. **Kit (`kit=1`)**: put on rings and amulets, read enchant
and brand scrolls onto the gear in use, and wear a tower shield. **Trog's Hand (`hand=1`)**: invoke it at the
monsters qw invokes it at. **Result on the tuning blocks: `kit=1` is ahead, +0.64 [+0.31, +0.96] levels pooled over
A and C, and positive on both blocks. `hand=1` alone is level, −0.07 [−0.17, +0.03]. The two together, +0.70 [+0.37,
+1.04], are no better than `kit=1` alone (+0.06 [−0.03, +0.17]).** So `kit=1` was pre-registered and played on the
fresh seeds 690000–690599. **Fresh test: +0.51 [+0.22, +0.80] levels over 598 dungeons, so the pre-registered rule
passes.** No default was changed.

**What was built, and by which route.** Both are *automatic steps*, taken before the brain chooses, as `fence_shops`
already was (`BrainTiers.auto_step` in `src/ladder/brain/policy.py`). They are not actions.
- `features.ACTIONS`, the observation and the input vector are unchanged.
- An automatic step writes no step-log line, so the corpus never sees one.
- Saved models (`models/*.json`, `v6-*`, `v7-*`) load and choose as before, with the switches on or off.
- Each switch is a `Style` key, off by default. No default changed, and no `STYLE_ADDED_AS` entry is needed: a run
  saved before the keys existed was played with them off.
- A step that used no game time (a menu without the expected entry, say) is set aside for `BLOCK_TURNS` (50) turns.

The parts:

- **`kit=1`, jewellery** (`gear.JEWEL_VALUES`, `gear.jewel`, `gear.jewellery_choice`, `BrainTiers.put_on`).
  - When: nothing in view and no rage on.
  - What is worth wearing: a value per ring and amulet taken from qw's own valuation (`runs/qw/build-zk/qw.lua`:
    `item_property`, `linear_property_value`, `absolute_property_value`), for a Minotaur Berserker of Trog with a mace:
    - per point of plus: protection, evasion and slaying 50, strength 35, dexterity 15;
    - flat: amulet of faith 1000, poison resistance 225, reflection 220, see invisible, flight and regeneration 200,
      fire and cold protection 125, willpower, guardian spirit and the acrobat 100, resist corrosion 50, positive
      energy 25.
  - Never put on: anything else (intelligence, wizardry, magical power, stealth and the newer amulets are worth 0 to
    qw for this character), negative rings, artefacts, pieces the game marks useless, and a second ring of a kind
    already worn.
  - Jewellery is identified when picked up in 0.34 (every one in the reference runs' packs had its full name), so
    there is no unknown-ring risk to weigh.
  - How: `P` opens "Put on or remove which piece of jewellery?". Its lines end "(worn)" for what is on, and the bot
    reads that as the truth each time. `P` on a free slot's piece puts it on: "c - a +4 ring of protection (worn)".
  - `P` on a worn piece takes it off ("You remove your ..."). With both ring slots full, `P` on a third ring asks, as
    text, which to remove. The bot never does that. Instead it takes the worst ring off first, and only for a piece
    worth `JEWEL_GAIN` (50) more; the next step puts the new one on.
  - An amulet takes several turns. If something comes into view meanwhile, the game asks "Spend multiple turns
    changing equipment while enemies are nearby?", and the bot answers no, as `wear` does.
- **`kit=1`, enchant and brand scrolls** (`gear.enchant_target`, `BrainTiers.answer_enchant`, `policy.kit_scroll`).
  - Unknown scrolls: an unknown scroll that turns out to be enchant armour, enchant weapon or brand weapon now gets
    its item menu answered instead of cancelled.
    - The menus are "Enchant which item?", "Enchant which weapon?" and "Brand which weapon?". They list only what the
      scroll can still improve, marked "(worn)" or "(weapon)".
    - The answer is the body armour worn, else the shield, else another worn piece; for the weapon scrolls, the
      weapon in hand.
    - If nothing fits, the bot cancels as before.
  - Known scrolls: with nothing in view, no rage and able to read, the bot reads them by the same route. Brand weapon
    is read only onto a weapon with no brand yet.
  - Acquirement is still cancelled.
- **`kit=1`, the tower shield** (`gear.KIT_ARMOURS`, `gear.KIT_RC`).
  - Added to the armour ranking at 7, against the kite shield's 5 and the buckler's 3; the game's SH is 13, 8 and 3.
  - The weapon's handedness rules are unchanged: no shield with a two-handed weapon, no two-hander with a shield on.
  - The rc's autopickup takes one tower shield, by an extra rc block sent only with `kit=1` (`selfplay._play`).
  - The tower shield counts toward `wear`'s availability (`observe` with `ctx["kit"]`) only with `kit=1`.
- **`hand=1`** (`policy.HAND_MONSTERS`, `policy.hand_wanted`, `BrainTiers.trogs_hand`).
  - The monster list is qw's `hand_monsters` as written, by name, used while the character's XL is under the number
    qw gives: Grinder under 10; orc sorcerer and "wizard" under 17; ogre mage, liches, golden eye, deep elf sorcerer,
    sphinx, satyr, siren and the rest under 100.
  - It also needs, as qw's `can_trogs_hand` and `want_to_trogs_hand` do:
    - Trog, at piety rank 2 or more;
    - not raging, confused or silenced (`can_invoke`);
    - not already regenerating from the Hand (the status line's "Regen Will++");
    - no teleport coming.
  - Not at half HP or under with a healing potion held: qw drinks first (`plan_heal_wounds` comes before
    `plan_trogs_hand` in its emergency cascade).
  - How: `a`, then the letter the ability menu shows on the line naming "Trog's Hand" (it has been `b` in every game
    seen); Esc if no line names it.

**The prompts, seen in the real game.** A scenario game on the `laddertest` account (`probe.py`, `kit.yaml` in the
job's `brain-v6h/` scratch directory) was driven key by key: picking up rings, an amulet, three unknown scrolls and a
tower shield, putting the jewellery on, wearing the shield, and reading the scrolls. That showed:
- the `P` menu and its "(worn)" marks;
- the take-off on `P`, and the text prompt for a third ring;
- the multi-turn amulet;
- the three scroll menus and their answers: "Your +0 animal skin glows green for a moment.", "Your +0 mace glows red
  for a moment.", "Your +1 mace drips with poison. a - a +1 mace of venom (weapon)" (no further question);
- 0.34's separate letters for gear and consumables: a ring and a scroll can both be `c`, and each menu uses its own.

The Trog's Hand menu line is from the reference runs' protocol logs (" b - Trog's Hand   Piety-   3%"). Setting piety
in wizard mode for a scenario test hung the probe. The first `hand=1` games showed the whole round trip: the menu,
"Your skin crawls.", "You feel the effects of Trog's Hand fading."

**Play with the switches off is unchanged.**
- Nine block A dungeons (500000–500008) were replayed with no switches (`v6h/A-off`) and compared with
  `v6e/A-ref` (`same.py`). 9 of 9 were identical: the same deepest level, the same final turn, the same death or end,
  and the same choices step by step (296 to 1,495 of them per game).
- The `hand=1` arm, which can differ only where a Hand monster comes into view, reached the same depth as the
  reference in 181 of 200 A dungeons and 187 of 199 C dungeons.
- Tests in `tests/test_brain.py`:
  - `test_kit_and_hand_are_off_by_default_and_off_plays_as_before`
  - `test_kit_and_hand_add_no_action_and_change_no_input` (the action list is pinned)
  - `test_saved_models_still_load_and_choose_the_same_with_the_switches_on_or_off`: every `v6-*` and `v7-*` model
    present plus `brain.json`, up to six. Each one loads and gives the same choice, observation and values with
    `kit=1 hand=1` as with neither.
  - `test_jewel_values_follow_qw_and_skip_artefacts_useless_and_worthless_pieces`
  - `test_jewellery_choice_fills_free_slots_skips_repeats_and_swaps_only_for_much_better`
  - `test_enchant_target_picks_what_is_in_use_from_the_scrolls_menu`
  - `test_kit_answers_an_enchant_prompt_instead_of_cancelling_it`
  - `test_kit_reads_known_enchant_scrolls_and_puts_on_jewellery_with_nothing_in_view`
  - `test_put_on_reads_what_is_worn_from_the_menu_and_presses_the_right_letter`
  - `test_hand_wanted_follows_qws_rule`
  - `test_hand_reaches_brain_tiers_and_is_sent_by_the_letter_the_menu_gives`
  - `test_kit_and_hand_are_styles_and_old_runs_still_match`

**How often each fired** (`kitstats.py`, from the games' own messages and the end-of-game counts; whole games, not
only to D:7; 200 dungeons each):

| | `v6e/A-ref` | `A-kit` | `C-kit` | `A-hand` | `C-hand` | `A-both` | `C-both` | qw (block A, by D:7) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rings put on | 0 | 233 | 204 | 0 | 0 | 235 | 207 | 283 |
| amulets put on | 0 | 35 | 31 | 0 | 0 | 35 | 31 | 64 |
| taken off for a better one | 0 | 19 | 17 | 0 | 0 | 21 | 16 | |
| enchant armour landed | 0 | 135 | 114 | 0 | 0 | 138 | 120 | 293 enchant scrolls |
| enchant weapon landed | 0 | 116 | 110 | 0 | 0 | 119 | 114 | (with the line above) |
| brand weapon landed | 0 | 48 | 48 | 0 | 0 | 51 | 48 | 63 |
| enchant or brand prompt cancelled | 201 | 0 | 0 | 202 | 177 | 0 | 0 | |
| shields put on (tower) | 36 (0) | 48 (9) | 54 (8) | 36 (0) | 40 (0) | 46 (9) | 54 (7) | 115 |
| Trog's Hand | 0 | 0 | 0 | 35 | 22 | 31 | 23 | 35 fights on D:3–7 |

(`v6e/C-ref` cancelled 172 prompts and put on 40 shields, none tower.)

- **What is measured here.** The kit switch roughly closes the gap in how much jewellery and enchantment the bot uses
  (qw's counts are by D:7, ours over whole games, which mostly end by D:9).
- **Trog's Hand** fires about as often as qw uses it.
- **Shields** stay well below qw's: the bot wears one only when it finds one, and qw also buys them.

**AC and SH on first arrival** (step log; means over dungeons the bot reached the level in; qw's from the previous
section, over the dungeons all three bots reached):

| level | A-ref → A-kit: AC (paired dungeons) | SH, shield worn: A-ref → A-kit | C-ref → C-kit: AC (paired) | SH, shield worn: C-ref → C-kit | qw AC / SH |
| --- | --- | --- | --- | --- | --- |
| D:4 | 8.1 → 8.5 (163) | 0.4, 9% → 0.9, 15% | 8.3 → 8.4 (140) | 0.5, 11% → 0.9, 19% | 9.2 / 1.2 |
| D:5 | 9.1 → 9.7 (133) | 0.5, 11% → 1.1, 19% | 9.3 → 9.7 (106) | 0.5, 13% → 1.3, 25% | 10.6 / 1.6 |
| D:6 | 10.0 → 10.6 (107) | 0.6, 13% → 1.6, 26% | 10.3 → 10.6 (94) | 0.6, 15% → 1.6, 30% | 12.4 / 1.7 |
| D:7 | 11.0 → 12.1 (72) | 0.9, 20% → 1.9, 26% | 11.2 → 11.5 (72) | 0.7, 15% → 1.6, 28% | 14.4 / 1.9 |
| D:8 | 12.1 → 12.8 (52) | 0.9, 21% → 2.1, 29% | 11.9 → 12.5 (55) | 0.9, 17% → 2.0, 33% | |

- **SH reaches qw's level.** On arrival at D:5–7, SH is 1.1–2.0, which is qw's 1.6–1.9.
- **AC rises only 0.3–1.1, and qw's lead stays at about 2–3.** The enchantments go onto body armour that is often
  light (an animal skin can take +2 at most), and a ring of protection is uncommon. The rest of qw's AC lead
  comes from heavier body armour and from buying: inferred, not measured here.

**Tuning.**
- **Method.** This tree, no model, epsilon 0, 9 workers asked (7 played: `ladderbrain7` and `9` still refuse login),
  A (500000–500199) and C (540000–540199) only, 09:58–11:38 (`chain.sh`, `jobs-tune.txt`). The arm order alternated
  by block: A kit, C both, A hand, C hand, A both, C kit.
- **Analysis.** Each arm minus `v6e/{A,C}-ref` (the defaults), paired by dungeon over games both finished and neither
  stale nor off its seed (`arms.py`); 95% bootstrap over dungeons, 10,000 resamples. Description only: these blocks
  are spent.
- **Seed checks** (`verify.py`). Every game of the six runs: no "Welcome back", no protocol without its seed, no
  first step after turn 1, and a morgue on its seed. One game hung, 540052 in `C-hand`, as it does in every C
  reference.

| arm (`--style`) | A: mean depth | C: mean depth | − defaults, A | − defaults, C | **− defaults, A + C** | deeper / same / shallower | died D:1–3 / 4–6 / 7+ (A + C) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| defaults (`v6e/*-ref`) | 6.99 | 6.27 | | | | | 64 / 121 / 196 |
| `kit=1` | 7.42 | 7.09 | +0.42 [−0.04, +0.89] | +0.85 [+0.40, +1.31] | **+0.64 [+0.31, +0.96]** (399) | 156 / 144 / 99 | 50 / 106 / 225 |
| `hand=1` | 6.96 | 6.17 | −0.03 [−0.20, +0.12] | −0.10 [−0.21, −0.01] | **−0.07 [−0.17, +0.03]** (399) | 15 / 368 / 16 | 64 / 117 / 200 |
| `kit=1 hand=1` | 7.50 | 7.13 | +0.51 [+0.03, +0.98] | +0.89 [+0.44, +1.35] | **+0.70 [+0.37, +1.04]** (399) | 156 / 147 / 96 | 49 / 105 / 226 |

- `kit=1 hand=1` − `kit=1`: +0.09 [−0.06, +0.25] on A, +0.04 [−0.09, +0.17] on C, pooled +0.06 [−0.03, +0.17] over
  400 dungeons (12 + 10 deeper, 7 + 6 shallower, the rest the same).
- `kit=1` cuts deaths on D:1–3 (64 → 50) and on D:4–6 (121 → 106). More characters die on D:7 and below (196 → 225)
  because more get there.
- `hand=1` changes only the 31 of 399 dungeons where it fired in a way that mattered. Where it did, it was as often
  worse as better.

**Pre-registration of the fresh test** (written before any game on these seeds was played).
- **Configuration**: `--style kit=1`. Everything else is today's defaults, with no model and epsilon 0.
  - `kit=1` is clearly ahead: the pooled interval is wholly above zero and both blocks are positive.
  - `hand=1` is not tested. On its own it is level or slightly behind, and it adds nothing measurable to `kit=1`.
- **Baseline**: the defaults (no `--style`), played fresh with this same tree on the same seeds.
- **Seeds**: 690000–690599, once each per arm, in three blocks of 200. The arm order alternates per block:
  - 690000–690199: defaults, then `kit=1`;
  - 690200–690399: `kit=1`, then defaults;
  - 690400–690599: defaults, then `kit=1`.
- **Analysis**, done once, after all six runs have finished:
  - `kit=1` − defaults in deepest Dungeon level reached, paired by dungeon over the dungeons both arms finished and
    neither is stale nor off its seed (`arms.py`, `verify.py`);
  - 95% bootstrap over dungeons, 10,000 resamples, pooled over the three blocks.
- **Pass rule**: the pooled interval's lower end is above zero. If it is, `kit=1` is a candidate for a default; this
  section does not change any default either way.

**The fresh test** (played 11:41–12:58, after the pre-registration above was written into this file; analysed once,
by `arms.py` over the three block pairs, after all six runs had finished; runs `v6h/F{1,2,3}-{def,kit}`).

| block | defaults: mean depth | `kit=1`: mean depth | `kit=1` − defaults | deeper / same / shallower | dungeons |
| --- | --- | --- | --- | --- | --- |
| 690000–690199 (defaults first) | 6.33 | 6.62 | +0.30 [−0.18, +0.80] | 71 / 72 / 56 | 199 |
| 690200–690399 (`kit=1` first) | 6.47 | 7.16 | +0.68 [+0.15, +1.22] | 81 / 66 / 52 | 199 |
| 690400–690599 (defaults first) | 6.26 | 6.79 | +0.54 [+0.07, +1.02] | 70 / 66 / 64 | 200 |
| **pooled** | | | **+0.51 [+0.22, +0.80]** | 222 / 204 / 172 | 598 |

- **The pre-registered rule passes.** The pooled interval's lower end, +0.22, is above zero. All three blocks are
  positive, and two of them have intervals above zero on their own.
- **Deaths** (defaults → `kit=1`, three blocks together):
  - on D:1–3, 108 → 92;
  - on D:4–6, 187 → 177;
  - on D:7 and below, 280 → 298, since more characters get there.
- **Dungeons left out of the pairs.** Two of the 600 hung: 690134 under `kit=1`, and 690312 in both arms. Each
  verifies as on its seed in every other respect (`verify.py`): no "Welcome back", no protocol without its seed, no
  first step after turn 1, and a morgue on its seed for every finished game.
- **On the fresh seeds the kit fired as on the tuning blocks.** Per 200 dungeons:
  - 194–197 rings and 30–43 amulets put on;
  - 106–129 enchant armour, 113–134 enchant weapon and 41–53 brand weapon scrolls landed;
  - 3–6 tower shields.
- **AC on arrival** at D:5–7 (block 690000–690199, paired dungeons): 9.2 → 9.9, 10.1 → 11.0 and 11.1 → 12.1. SH
  rose from 0.6–0.7 to 1.1–1.6.
- **Seeds spent**: 690000–690599, once each per arm, as pre-registered. Unspent fresh seeds now start at 690600.

**No default was changed.** `kit=1` passed its pre-registered test and is a candidate for a default; making it one is
a separate decision. `hand=1` was not fresh-tested.

**Summary of the section.**
- Measured:
  - every count, mean and interval above;
  - the menus and their answers in the real game (the scenario probe; the protocol logs);
  - that play with the switches off is the same game, choice for choice, on 9 block A dungeons;
  - that saved models load and choose the same with the switches on or off (unit test);
  - that every tuning and fresh game was played on its seed;
  - the tests: `uv run pytest -q` 503 passed, 5 deselected; `uv run ruff check` clean.
- Inferred:
  - that the extra depth comes from the kit's effect on fights, through AC, SH, rings such as poison resistance, and
    an enchanted and branded weapon. The switch changes all of these at once, and they were not separated.
  - that the AC still missing against qw (about 2–3 at D:6–7) comes from heavier body armour and from shops.
- Not done:
  - buying (shops are still fenced off);
  - acquirement;
  - artefact jewellery (left alone);
  - Brothers in Arms;
  - a `hand=1` test on fresh seeds;
  - changing any default.
- Runs: `runs/brain/v6h/A-off` (switches-off check), `smoke-kh`, `{A,C}-{kit,hand,both}` (tuning) and
  `F{1,2,3}-{def,kit}` (fresh). The server's disk stayed at 52%.
- Scripts in the job's `brain-v6h/` scratch directory:
  - new: `probe.py` and `kit.yaml` (the scenario probe), `kitstats.py` (what fired, AC and SH on arrival), `same.py`
    (choice-by-choice comparison of two runs), `jobs-off.txt`, `jobs-smoke.txt`, `jobs-tune.txt`, `jobs-fresh.txt`;
  - copies: `arms.py`, `seeds.py`, `verify.py`, `mindex.py`, `chain.sh` and `refresh.sh`.

#### Throwing, a step out of a surround, and `calm=1` again, with the kit on by default (2026-11-16, evening)

The comparison with qw listed what our bot can't do. After the kit, the next two were throwing (qw throws in 31% of its
fights on D:3–7) and a tactical step (34%). This section builds both as opt-in automatic steps, as the kit was, and
replays `calm=1` now that the kit is on by default. **Result on the tuning blocks: none is ahead of the defaults.
`throw=1` is level, −0.12 [−0.37, +0.13] levels pooled over A and C. `step=1` is behind, −0.32 [−0.71, +0.07]: in 0.34
a monster the character steps away from gets a free hit ("attacks as it pursues you"), and the steps more than
quadrupled those hits. `calm=1` is now level, +0.07 [−0.32, +0.47] (it was −0.28 [−0.62, +0.07] before the kit). The
two that are not behind, together (`throw=1 calm=1`), are −0.18 [−0.57, +0.20].** So no fresh test was pre-registered or
played; seeds 690600–691199 are unspent. No default was changed.

**What was built.** Two `Style` keys, both off by default, both *automatic steps* taken before the brain's choice
(`BrainTiers.auto_step` in `src/ladder/brain/policy.py`), as `kit` and `hand` are.
- `features.ACTIONS`, the observation and the input vector are unchanged. An automatic step writes no step-log line,
  so the corpus never sees one, and saved models load and choose as before.
- Instead, each throw and step writes one `_ladder` line into the game's protocol recording (`BrainTiers.note`), so
  they can be found afterwards.
- No `STYLE_ADDED_AS` entry is needed: both were added off and are still off.
- Both come after the rules' emergencies. `BrainTiers.rules_now` works out what the rules of thumb would choose at
  this moment without changing anything. The step is taken only where that choice is `fight`, `wait` or `berserk`,
  and the throw only where it is `fight` or `wait`. qw orders them the same way: its tactical step comes after its
  heal, teleport and flight and before its rage (`set_plan_emergency`, qw.lua 12594–12644), and its throw is in its
  attack plans, after every emergency one (`set_plan_attack`, 11536–11553).

- **`throw=1`**: pick missiles up and throw them when qw would.
  - *Which missiles.* qw's `want_missile` (qw.lua 5503–5510) takes javelins, boomerangs and large rocks that are not
    useless. An extra rc block, sent only with the switch on (`gear.THROW_RC`, as `gear.KIT_RC` is), adds an
    autopickup function for those three. Explore's greedy pickup then also fetches the thrown ones back after a fight.
    No large rock was ever thrown (0 in every run). The game probably marks them useless to a Minotaur; that is
    inferred, not checked.
  - *When* (`policy.throw_wanted`, from qw's `plan_throw` 11189–11201 and `get_throwing_target_func` 587–605):
    - not raging, confused or held (`unable_to_throw` 15846–15856). The game refuses a throw in a rage.
    - Hostiles in view and none adjacent. With one to hit in melee, qw's throw "prefers melee"
      (`get_ranged_attack_target` 490–536).
    - Then either a threat-3 hostile is in view: out of the mace's reach, the throw is its best attack
      (`get_high_threat_target` 558–585, `monster_best_player_attack` 935–955).
    - Or the threat in view is under qw's moderate level for the XL: webtiles' threat summed over the hostiles, as
      qw's `assess_enemies` sums `minfo:threat()`, against 2 up to XL 7, rising to 5 at XL 10
      (`have_moderate_threat` 8366–8369, `moderate_threat_level` 7921–7923). Against more, qw closes in or waits.
      And no hostile in view attacks from range or with reach (monster table). qw walks up to one of those instead.
  - *Where.* An rc Lua function, `ladder_throw`, bound to a macro key (`gear.THROW_KEY`), does what qw's
    `throw_missile` does (11166–11187):
    - It picks a hostile in view, not adjacent, whose shot is clear: the game's own beam path (`spells.path`) reaches
      it before any other monster (`assess_ranged_position` 270–404).
    - It prefers a threat-3 one, else the nearest.
    - It fires with `crawl.do_targeted_command("CMD_FIRE", x, y, true)`, aimed at the target, so a javelin stops
      there.
    - With no clear shot it does nothing and no time passes. The throw is then tried again after `THROW_RETRY`
      (2) turns, not `BLOCK_TURNS`.
  - If the quiver doesn't hold one of these missiles, the bot first opens `Q` ("Quiver which action?") and picks the
    line "Throw: … javelins", else boomerangs (`gear.quiver_line`).
- **`step=k`**: a step out of a surround, qw's "outnumbered" step (`choose_tactical_step` 9941–10005, `step_reason`
  9798–9875 with the case at 9862–9870, `assess_square_enemies` 9686–9735), in `policy.step_square`.
  - Only with two or more hostiles adjacent, not raging (qw takes no tactical step in a rage), not confused.
  - A square's count is the hostiles that could hit there next turn: those adjacent to it, plus those two away that
    the monster table says are faster (qw's `a.ranged`).
  - The step goes to the free adjacent square whose count is k or more below the count here: walkable, no monster,
    no cloud, not a shut door, shallow water or a trap. Among those it takes the lowest count, then the square
    nearest a hostile (qw's `step_improvement`).
  - `step=1` is "fewer"; `step=2` would be qw's own cut of two.
  - At most `STEP_MAX` (3) steps per fight; the count starts again once nothing is in view. So it cannot loop.

**The prompts, seen in the real game** (job's `brain-v6i/probe.py`, `probe2.py`, `probe/throw.yaml`,
`probe/throw.rc`; `laddertest`).
- *Scenario games don't read the rc.* In a scenario game the macro key of the existing fence macro answered "Unknown
  function in macro: 'ladder_fence_shops'" (the account's saved macro without the rc's Lua), a new macro was "Unknown
  command.", and no autopickup function ran. So the rc parts were driven in a real seeded game on `laddertest`
  instead: 500078, a block A dungeon whose first room has javelins.
- Without the rc block, walking onto javelins and boomerangs only shows "You see here 6 javelins." With it,
  autoexplore picked them up ("c - 3 javelins") and the game quivered them on its own.
- `Q` opens a menu titled "Quiver which action? ([-] to clear)", tag `actions`. Its lines read "a - Throw: 6 javelins
  (quivered)", "b - Throw: 3 boomerangs", then the abilities ("Abil: Berserk"). These are menu letters, not inventory
  letters.
- `f` with a hostile in view opens the targeting mode, which sends no `input_mode`. `Connection.act` would then wait
  for ever (it did: the probe step timed out). That is why the throw goes through a Lua macro, as qw's does, and
  never through the targeting keys.
- The macro: "You throw a javelin. The javelin pierces through the hobgoblin. You kill the hobgoblin!", one turn. With
  no clear target, nothing happens and the turn doesn't pass.

**Play with the switches off is unchanged** (`same.py`).
- First, the reference. Nine block A dungeons (500000–500008) replayed with no `--style` before any change (`v6i/A-pre`)
  were identical to `v6h/A-kit` choice by choice. So `v6h/{A,C}-kit` are today's defaults and were used as the
  reference, not replayed.
- After the change, 500000–500008 with no `--style` (`v6i/A-off`) and 500009–500017 with `throw=0 step=0`
  (`v6i/A-off0`): 18 of 18 identical to `v6h/A-kit` (the same deepest level, final turn, death or end, and the same
  choices step by step, 296 to 1,739 per game).
- Tests in `tests/test_brain.py`:
  - `test_throw_and_step_are_off_by_default_and_off_plays_as_before`
  - `test_throw_wanted_follows_qws_rule`
  - `test_throw_reaches_brain_tiers_only_where_the_rules_would_walk_up`
  - `test_throw_quivers_a_missile_if_none_is_then_presses_the_throw_key`
  - `test_step_square_leaves_a_surround_for_fewer_attackers`
  - `test_step_reaches_brain_tiers_where_the_rules_would_fight_and_stops_after_step_max`
  - `test_throw_rc_is_sent_only_with_the_switch_on`
  - `test_throw_and_step_are_styles_and_old_runs_still_match`
  - `test_saved_models_still_load_and_choose_the_same_with_the_switches_on_or_off`, now with `throw=1 step=1` as
    well
  - and `test_kit_and_hand_add_no_action_and_change_no_input` still pins the action list.

**How often each fired, against qw** (`tsstats.py`; ours from the game's messages, our protocol notes and the
inventory replayed from the protocol; qw's from its logs, `qwtact.py`). A "fight" is defined as in the qw comparison:
a run of moments with a hostile in view on one level, ended by 20 turns without one or by a level change, on D:3–7.
A throw or step taken before the brain's first choice in a fight counts in that fight.

| | `A-throw` | `C-throw` | `A-step` | `C-step` | qw (block A) |
| --- | --- | --- | --- | --- | --- |
| games with a throw | 121 of 200 | 109 of 200 | | | 148 of 200 |
| throws (javelin / boomerang) | 5,470 (982 / 4,488) | 5,131 (923 / 4,208) | | | 33,360 (whole games) |
| fights on D:3–7 with a throw | 955 of 4,120 (23%) | 820 of 4,011 (20%) | | | 2,066 of 6,650 (31%) |
| steps | | | 2,206 | 2,226 | 3,746 "outnumbered" (whole games) |
| fights on D:3–7 with a step | | | 442 of 3,715 (12%) | 442 of 3,926 (11%) | outnumbered 366 (6%); any tactical step 2,292 (34%) |

- **Missiles carried on first arrival** (`A-throw` / `C-throw` / qw): D:2 12% / 7% / 14%, D:4 30% / 29% / 38%, D:6
  51% / 41% / 55%, D:7 48% / 49% / 57%, D:9 53% / 61% / 68%. Close to qw's.
- **Throws that hit.** About 56% of the throws are followed by "The javelin|boomerang hits|pierces through". Some 5%
  are reported missing; the rest have messages the count doesn't parse. A kill message came back in the reply to the
  throw key 1,037 times on A and 824 on C.
- **qw's 34% is mostly not this step.** Of qw's 42,684 tactical steps, 24,957 were "stealth" (out of sight of a
  sleeping monster) and 12,474 "hiding" (out of sight of a ranged one); 3,746 were "outnumbered" and 1,206 cloud or
  fire. Our `step=1` fires in twice as many fights as qw's outnumbered step, because it asks for a cut of one, not
  two.
- **What followed a step** (A / C):
  - hostiles adjacent: 2.12 / 2.13 before, 1.48 / 1.44 at the next choice;
  - the next choice was a rage after 30% / 27% of steps;
  - HP lost by the next choice: 1.6 per step;
  - 77 of `A-step`'s 189 deaths and 62 of `C-step`'s 187 came within 20 turns of a step.
- **The free hits.** "attacks as it pursues you" appeared 287 / 246 times in the defaults' games and 1,269 / 1,267 in
  `step=1`'s: about 0.45 free hits per step. One of `A-step`'s early deaths (500088, D:1, turn 73) shows it: three
  steps away from a quokka and a goblin, each followed by the pursuer's hit (16 → 5 HP), then a rage at 3 HP.

**Tuning.**
- **Method.** This tree, no model, epsilon 0, A (500000–500199) and C (540000–540199) only, 13:23–15:13 (`chain.sh`,
  `jobs-tune.txt`, `jobs-combo.txt`). The arm order was A-throw, C-calm, A-step, C-step, A-calm, C-throw, then
  C-tc, A-tc.
- **Workers.** 9 workers asked and **all 9 played**: no run left an account out. The morgues written during this
  section came from all nine accounts, `ladderbrain1` to `9`, 138–161 each.
- **Analysis.** Each arm minus `v6h/{A,C}-kit` (today's defaults), paired by dungeon over games both finished and
  neither stale nor off its seed (`arms.py`); 95% bootstrap over dungeons, 10,000 resamples. Description only: these
  blocks are spent.
- **Seed checks** (`verify.py`). Every game of the eight runs: no "Welcome back", no protocol without its seed, no
  first step after turn 1, and a morgue on its seed for every finished game. Two games hung: 500010 in `A-step` and
  500119 in `A-calm`.

| arm (`--style`) | A: mean depth | C: mean depth | − defaults, A | − defaults, C | **− defaults, A + C** | deeper / same / shallower | died D:1–3 / 4–6 / 7+ (A + C) | deaths per 100 fights, A / C |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| defaults (`v6h/*-kit`) | 7.42 | 7.09 | | | | | 50 / 106 / 225 | 2.08 / 1.98 |
| `throw=1` | 7.26 | 7.02 | −0.15 [−0.51, +0.20] | −0.07 [−0.42, +0.26] | **−0.12 [−0.37, +0.13]** (400) | 87 / 213 / 100 | 50 / 111 / 217 | 2.23 / 1.97 |
| `step=1` | 6.89 | 6.98 | −0.52 [−1.10, +0.07] | −0.12 [−0.64, +0.42] | **−0.32 [−0.71, +0.07]** (399) | 143 / 90 / 166 | 70 / 111 / 195 | 2.50 / 2.27 |
| `calm=1` | 7.67 | 7.00 | +0.24 [−0.30, +0.78] | −0.10 [−0.67, +0.47] | **+0.07 [−0.32, +0.47]** (399) | 156 / 96 / 147 | 73 / 102 / 201 | 1.54 / 1.74 |
| `throw=1 calm=1` | 7.17 | 6.96 | −0.24 [−0.79, +0.32] | −0.13 [−0.68, +0.39] | **−0.18 [−0.57, +0.20]** (400) | 143 / 111 / 146 | 70 / 115 / 196 | 1.79 / 1.77 |

- **The combination** was chosen after the four single arms were in. `step=1` was behind on its own and left out;
  `throw=1` and `calm=1` were the two not behind. Against `calm=1` alone it is −0.28 [−0.56, +0.00] (A −0.53
  [−0.93, −0.15], C −0.03). So throwing adds nothing on top of `calm=1` either.
- **`throw=1` changes little.** 213 of 400 dungeons end at the same depth. Deaths per 100 fights are 2.08 → 2.23 on
  A and 1.98 → 1.97 on C. Most throws are boomerangs (82%), whose damage is low. Our bot still walks up to every fight
  it throws in: qw throws while it waits for the enemy to come (`hold`), and that was −0.39 on its own.
- **`step=1` loses on A through early deaths** (D:1–3: 18 → 38). The free hits from stepping away fall hardest on a
  character with 20–40 HP. On C it is level.
- **`calm=1` with the kit.** Before the kit it lost on both blocks: −0.28 [−0.62, +0.07] (section of 2026-11-16,
  morning). It now dies less on D:4–6 than the defaults (102 against 106) but more on D:1–3 (73 against 50). It
  ends 0.2–0.5 XL higher (A 7.60 → 8.14, C 7.37 → 7.54) and has fewer deaths per fight (1.54 and 1.74, against 2.08 and 1.98), because it fights
  more fights (5,405 against 4,175 on A). The two blocks disagree (+0.24 and −0.10), and the pooled interval is
  centred near zero.

**No fresh test.** The rule was to pre-register a test on 690600–691199 only for a configuration clearly ahead on
A + C: pooled interval mostly above zero, both blocks positive. None qualifies. `calm=1`'s interval, +0.07 [−0.32,
+0.47], is centred near zero, and C is negative. So nothing was written as a pre-registration, and **seeds
690600–691199 were not played: they are still unused.**

**Summary of the section.**
- Measured:
  - every count, mean and interval above;
  - the quiver menu, the targeting mode's missing `input_mode`, the Lua throw and the autopickup in the real game
    (the probes);
  - that play with the switches off is the same game, choice for choice, on 18 block A dungeons, and that today's
    defaults reproduce `v6h/A-kit` on 9;
  - that saved models load and choose the same with the switches on or off (unit test);
  - that every tuning game was played on its seed;
  - that all nine accounts played;
  - the tests: `uv run pytest -q` 511 passed, 5 deselected; `uv run ruff check` clean.
- Inferred:
  - that `step=1` loses through the free hits on stepping away. The hits are measured, the early deaths are
    measured, and one game shows the chain; that the hits cause the lost depth is not tested separately;
  - that throwing does little because the bot walks up anyway and throws mostly boomerangs. This was not tested by a
    variant.
- Not done:
  - `step=2` (qw's cut of two). It would pay the same free hits, so it wasn't played;
  - qw's other step reasons (stealth, hiding, clouds, sticky fire);
  - throwing at a threat-3 hostile with something else adjacent (qw does);
  - throwing combined with `hold`;
  - wands;
  - changing any default.
- Runs: `runs/brain/v6i/A-pre` (the reference check), `smoke-ts`, `A-off` and `A-off0` (the switches-off checks),
  `{A,C}-{throw,step,calm,tc}` (tuning). The server's disk stayed at 52%.
- Scripts in the job's `brain-v6i/` scratch directory:
  - new: `probe2.py` (a probe on a real seeded game with an extra rc), `probe/throw.yaml`, `probe/throw.rc`,
    `findmiss.py` (seeds with missiles early), `qwtact.py` (qw's throws and steps by reason, per fight, missiles on
    arrival), `tsstats.py` (ours), `tail.py` (keys and messages at a game's end), `jobs-pre.txt`, `jobs-smoke.txt`,
    `jobs-off.txt`, `jobs-tune.txt`, `jobs-combo.txt`;
  - copies: `arms.py`, `seeds.py`, `verify.py`, `mindex.py`, `same.py`, `kitstats.py`, `probe.py` (now takes
    `$EXTRA_RC`), `chain.sh` and `refresh.sh`.

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
| `src/ladder/brain/policy.py` | `available`, `baseline`, `baseline_wiki`, `teleport_rule`, `recovering`, `foe_hp`, `big_fight`, `Style`, and `BrainTiers` (with `fight_moves` for the opt-in fight rules and `assailed` for `Style.unseen`), which sits in Reflex where `StubTiers` did |
| `docs/wiki-strategy.md` | the DCSS wiki's strategy guides, sorted by what the brain would need to use each piece of advice |
| `src/ladder/brain/steplog.py` | `steps.jsonl` writer shared by self-play, `spike` and the cockpit |
| `src/ladder/brain/selfplay.py` | parallel games, one process each, with a watchdog for hung reads |
| `src/ladder/brain/forks.py` | picks the moments to fork and writes the replay scripts (`kind="stairs"`: explore vs descend; `kind="teleport"`: read teleportation vs fight, exhausted and outnumbered; `kind="unseen"`: `Style.unseen` on vs off from the first moment it acts) |
| `src/ladder/brain/humanplay.py` | a person's recorded game to a step log |
| `src/ladder/brain/corpus.py` | step logs to labelled training rows |
| `src/ladder/brain/train.py` | PyTorch training and export |
| `src/ladder/brain/cli.py` | `ladder brain ...`, including the iterate loop |
| `models/brain.json`, `models/brain.ledger.json` | the champion (none yet) and the record of every `iterate` round |
| `models/iter<n>.json` | each round's candidate, with its parity vectors |
| `models/v5-*.json` | version 5 experiments, each with its parity file; `v5-ens5`, `v5-forks3`, `v5-pairs3` are ensemble manifests |
| `models/v6-*.json` | trained on clean games (2026-11-15): `v6-clean3` (clean corpus only) and `v6-mix3` (clean + version 5 corpus) are manifests of three seeds each; `v6-clean3` at `margin=0.6` passed a fresh test |
| `models/v7-*.json` | `v7-clean3`: the `s12` recipe at three seeds on the enlarged clean corpus (rounds 0–2 with forks, 2026-11-15, afternoon); not ahead of `v6-clean3` at `margin=0.6` on the tuning blocks |
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
   *(2026-11-15, afternoon) (b) done. (d) done once: `v7-clean3` (3.09M clean rows, 1,792 forks) no longer dives at
   the default margin (+0.16 [−0.04, +0.37] against the rules on A + C) but has lost the teleport reads and is not
   ahead of `v6-clean3` at 0.6 (−0.06 [−0.27, +0.16]); seeds 670000–670599 are still unused. Next, cheapest first:
   (a) (c) above, the teleport moments as a rule, now that the model that found them may not keep them; (b) test
   `v7-clean3`'s one big habit at the default margin, fighting on instead of raging (`berserk → fight`, 2,016 times on
   A + C), as a rule or a fork kind of its own; (c) forks that try `read_teleport` against `fight` at spent moments,
   so the estimate of fighting on there comes from paired outcomes and not from which games happened to read; (d) a
   mixed ensemble (`v6-clean3` + `v7-clean3`) is untried.*
   *(2026-11-15, evening) (a) done: `teleport=3` (exhausted, hostiles' HP left ≥ 1.5× own) passes on 670000–670599
   (+0.24 [+0.16, +0.34]) and is level with `v6-clean3` 0.6 there. (c) done once: 371 paired forks put a read at +0.29
   [+0.00, +0.58] where the rule reads. Next, cheapest first: (a) decide whether `teleport=3` becomes a default (it
   would need `STYLE_ADDED_AS["teleport"] = 0`, so saved runs keep reading as played with it off) and whether
   `--brain` then needs a model at all; (b) the fork rows (742, training seeds) into the clean corpus, and more teleport
   forks, so a retrained model learns the read from paired outcomes and keeps it; (c) the reads the rule misses: about
   300 model reads not after a rage, at median 64% HP with a threat-2+ monster in view, and lone strong monsters;
   forks there before any rule; (d) whether the healing potion or the scroll comes first when both are held (the model
   prefers the potion there); (e) (b) of the afternoon list, `berserk → fight`, still untested.*
   *(2026-11-15, night) `teleport=3` is a default. A re-diagnosis found a game in seven ending after damage from
   something not in view (fire, invisible attackers) while the rules waited; `unseen=2` passes on 680000–680599 (+0.17
   [+0.04, +0.31]). Next, cheapest first: (a) decide whether `unseen=2` becomes a default (`STYLE_ADDED_AS["unseen"] =
   0` with it); (b) the rage that runs out mid-fight is now 32–37% of games: read teleportation at a lower `foe_hp`
   ratio, or instead of raging when the foes' HP left is 1.5× the character's maximum and a scroll is held (790 such
   rages in 999 games, 29% followed by death), each as a fork kind first; (c) attack the square an unseen attacker hit
   from, as qw does (`plan_flail_at_invis`), which needs an action of its own; (d) `recover=2` (rest out exhaustion
   before exploring on) again under today's rules, since walking into a fight spent is still 18–20% of games.*
   *(2026-11-15, late night) Blocked by a full disk on the game server (section "The fights the rules start"). First:
   free space (the `ladderbrain*` ttyrecs under `/data/rcs/ttyrecs` are 51 GB and unread; deleting them is the owner's
   call). Then, on A + C against the defaults replayed with this tree: `avoid=1.5`, `avoid=1.0`, `retreat=3`, `calm=1`
   and `calm=1 recover=2` (the rage's "Calm down" is why most levels from D:4 on are left unexplored), the best two
   together, and a pre-registered test on 690000–690599 only if one is ahead. (d) above is dropped: the fights met while
   exhausted come after resting, not exploring.*
   *(2026-11-16) Done, with the server's disk freed: none is ahead on A + C (best `retreat=3` −0.05 [−0.20, +0.10];
   `avoid=1.0` −0.20 [−0.38, −0.02]; section "The fights the rules start, tuned"). 690000–690599 are still unspent.
   Left from the list: `avoid` that holds the rage until the scroll takes effect (as built, the rules rage anyway and
   waste it); forks before any new fight rule; `teleport=3` at a lower ratio.*
   *(2026-11-16, morning) Why `calm=1` dies more on D:4–6: the extra exploring meets more fights in places the defaults
   never go, more of them with uniques, with a scroll in hand that the rules don't read. Three opt-in switches against
   those causes (`escape=0.5`, `unique=1`, `calmfor=400`, each with `calm=1`) remove the deaths where they act, but as
   many come back on the same levels. None is ahead (section "Why `calm=1` dies more on D:4–6"), and 690000–690599
   are still unspent. What that suggests: a rescue is wasted while the character stays exhausted and alone on a
   dangerous level, so a rule worth trying pairs the scroll with leaving the level (up the stairs once it lands).
   Forks at those moments come first.*
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
