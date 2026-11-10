# The trained brain

A small neural network, trained on this machine from the ladder's own games, that chooses Reflex's
next action. It is not a language model and makes no API calls: it reads numbers about the moment and
runs in numpy in well under a millisecond. It is the same idea as the trained brain in
`~/Code/s1-battle`, moved to a game that can't be forked.

## Where it stands

Measured 2026-11-09 on this Mac, Minotaur Berserker, 60 fixed evaluation dungeons (seeds 500000–500059)
that training never sees. "Depth" is the deepest floor reached. A dungeon replays identically for the same
choices, so the last column compares model and baseline on the same dungeons.

| | games | mean depth | median | best | mean XL | game turns | vs baseline: deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **Rules of thumb** (`baseline`, no model) | 56 | **4.36** | 4 | 10 | 4.66 | 1664 | |
| `iter0`: first model, 326 games, trained to epoch 40 | 58 | 3.78 | 4 | 10 | 2.66 | 634 | 16 / 16 / 24 |
| `iter0b`: same data, early stopping and dropout | 55 | 3.75 | 4 | 7 | 4.25 | 1983 | 18 / 10 / 24 |
| `iter0b`, `margin=0.3` | 53 | 4.30 | 5 | 9 | 4.89 | 1986 | 19 / 17 / 14 |
| `iter1`: + 455 replay forks | 59 | 4.27 | 4 | 8 | 3.46 | 788 | 18 / 19 / 19 |
| `iter1`, `margin=0.3` | 59 | 4.05 | 4 | 8 | 4.03 | 946 | 17 / 19 / 19 |

**No model beats the rules of thumb yet, so none has been promoted**: `models/brain.json` does not exist
and `--brain` plays the rules of thumb. One standard error on a mean depth here is about 0.25, so
`iter1` and `iter0b margin=0.3` are level with the baseline and `iter0` is behind it. What the numbers say:

- `iter0` overrode two thirds of the baseline's choices, mostly "fight" with "descend", "wait" or
  "flee_up". It had only seen what diving leads to when the *baseline* plays on afterwards, never the
  under-levelled character its own diving makes. It also memorised its training games: validation loss
  rose from epoch 5 on. Early stopping fixed the second part (R² on unseen games went from negative to
  0.17–0.32 per outcome; danger AUC 0.75).
- `iter1` reaches the same depth as the baseline in half the game turns, two experience levels lower.
  It has learned that descending is how depth is gained, not how to stay alive at depth 5. On held-out
  forked moments its top-rated action loses 1.67 value units against the best action tried there, a
  random one 1.92, and what the game actually did 2.21 (59 moments, so indicative only).
- The ceiling for both is the same: this character, with these eleven actions and no equipment changes,
  dies around D:4–5. That points at the action list as much as at the model (see Next).

The rules of thumb are themselves new in this branch, and a large step from the stub they replace: the
stub's games ended in an escalation on D:1–4 and never died or went on; the baseline plays every game
to its end, reaching D:8–15 in its best games (15 in one of the 240 exploratory games).

Throughput: about 3 s per game with 6 parallel games (240 games in 14 minutes), about 2 s per fork with 10.
Training takes 12 s. A model is 103 KB (37k weights, float16) and matches torch to 5 decimal places.

## What carried over from s1-battle, and what couldn't

| s1-battle | here |
| --- | --- |
| A set encoder: one shared sub-network per opponent, pooled, so order doesn't matter | The same, per monster in view (up to 8, nearest first) |
| The network predicts several outcomes per option, not one score | Six outcomes per action (below) |
| A *style* weighs the outcomes at decision time, so behaviour changes without retraining | `policy.Style`, set with `--style key=value` |
| float16 weights in a JSON file, forward pass re-implemented without the training framework, parity-checked | `models/*.json` (~100 KB), numpy forward pass in `net.py`, `check_parity` on every training run |
| Expert iteration: the current model plays, the next one learns from those games too | `ladder brain iterate` |
| Labels from **counterfactual rollouts**: fork the simulator once per option and play each out | DCSS can't be cloned mid-game, but a seeded game **replays identically**, so `forks.py` replays a recorded game to a choice and takes another action there. A fork costs a replay of everything before it (about 2 s), where s1's cost microseconds |

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
| `quaff_heal` | drink a known potion of curing or heal wounds |
| `quaff_unknown` | drink an unidentified potion |
| `read_unknown` | read an unidentified scroll |
| `read_teleport` | read a known scroll of teleportation |
| `wait` | pass one turn (`s`) |
| `berserk` | Trog's Berserk (`a`, `a`) |

Decision cards (stairs, altars, uniques, the stat prompt) still go through `Hooks.decide` and Authority
as before. Where the stub raised an escalation (HP at half with monsters in view, an action that makes
no progress) the brain picks another action instead, so a game runs until the character dies.

The **rules of thumb** (`policy.baseline`) are what plays when there is no model, and what the model is
measured against: berserk when hurt or facing something tough, drink a healing potion at half HP, fight,
rest below 80%, read and drink unknowns when safe, explore, then go down.

## What it sees

`features.observe` writes the moment as a JSON dict (this is what the step log keeps); `features.encode`
turns it into numbers:

- **About the character**: HP and MP fractions, level and progress, AC/EV/SH, stats, depth, 18 status
  flags, Trog and piety, healing potions / unknown potions / unknown scrolls / teleports carried.
- **About the place**: on stairs or not, walking distance to known up and down stairs, open neighbours
  (corridor or open floor), level explored, choices and turns spent on this level.
- **About the fight**: how many hostiles, how many adjacent, nearest, worst and total threat, a unique.
- **Recent history**: HP change since the last choice, the last action, which actions are possible.
- **Per monster** (a set): distance, direction, adjacent, unique, webtiles' threat level (0–3), and its name
  hashed into 24 buckets.

It does not see the map, monster HP, equipment, skills or spells. Those are the obvious next features.

## What it predicts

For each action, six numbers about what follows (`corpus.label` computes them from the rest of the game):

| component | meaning |
| --- | --- |
| `died_soon` | died within 30 game turns |
| `hp_lost` | deepest HP drop within 30 turns, as a fraction of max HP |
| `xp_soon` | experience levels gained within 100 turns |
| `depth_go` | new depths reached later, each discounted by exp(−turns / 1500) |
| `xp_go` | experience gained later, discounted the same way |
| `died_go` | exp(−turns until death / 400); 0 if the game didn't end in death |

plus `danger` (the chance of losing a quarter of max HP within 30 turns) and a `prior` (which action the
recorded player took here). The default style is

    value = depth_go + 0.5·xp_go + 0.5·xp_soon − 2·died_go − 2·died_soon − 0.5·hp_lost

`--style died_go=-4 margin=0.1` and so on change it for a run. `human=1` adds the prior's log-probability,
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

## Files

| | |
| --- | --- |
| `src/ladder/brain/features.py` | actions, components, `observe` (state to dict) and `encode` (dict to numbers) |
| `src/ladder/brain/net.py` | model file format, numpy forward pass, parity check |
| `src/ladder/brain/policy.py` | `available`, `baseline`, `Style`, and `BrainTiers`, which sits in Reflex where `StubTiers` did |
| `src/ladder/brain/steplog.py` | `steps.jsonl` writer shared by self-play, `spike` and the cockpit |
| `src/ladder/brain/selfplay.py` | parallel games, one process each, with a watchdog for hung reads |
| `src/ladder/brain/forks.py` | picks the moments to fork and writes the replay scripts |
| `src/ladder/brain/humanplay.py` | a person's recorded game to a step log |
| `src/ladder/brain/corpus.py` | step logs to labelled training rows |
| `src/ladder/brain/train.py` | PyTorch training and export |
| `src/ladder/brain/cli.py` | `ladder brain ...`, including the iterate loop |
| `models/brain.json`, `models/brain.ledger.json` | the champion (none yet) and the record of every `iterate` round |
| `models/iter0.json`, `iter0b.json`, `iter1.json` | the candidates in the table above, each with its parity vectors |

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

Still open: about 3% of games hang on prompts no one answers yet (the acquirement menu, a yes/no after
some scrolls). The watchdog drops them after 60 quiet seconds.

## Next

In the order I would take them:

1. **Give it more to do.** The baseline and every model die at D:4–5 with the starting mace and animal
   skin. Wielding and wearing what it finds is the biggest gap from a person's play; then Trog's Hand and
   Brothers in Arms, throwing, wands, and stepping back into a corridor. Each is an action in
   `features.ACTIONS`, a line in `available`, and keys in `perform`.
2. **Reward living, not diving.** `depth_go` pays for a descent whoever survives it. Counting a new depth
   only once the character has lasted some turns there, or putting more weight on `died_go`, would stop the
   shortcut `iter1` found. The style can be searched against the evaluation dungeons without retraining.
3. **Many more forks, on the model's own games.** 455 forks moved the model from behind to level. s1's
   brain learned from 300,000 forked moments; an overnight run here is about 15,000. Forks of the
   *champion's* games, continued by the champion, are what make this expert iteration.
4. **More to see.** A local map patch, monster HP, what's wielded and worn, skills.
5. **Answer the prompts.** Identify and acquirement scrolls are wasted today, and are 3% of games lost.
6. **Answer the decision cards.** Stairs, uniques and altars are the same kind of choice; the brain could
   be the recommendation Authority shows, and the player's answers would be labels.
7. **Learn from more people.** Your recordings are in the loop but few (11 rows from the first four
   files). Other servers' games are public as ttyrecs and spectator streams, which have states but not keys.
8. **Other characters.** Everything so far is a Minotaur Berserker. Species and background would need to be
   inputs, and the action list would need spells.
