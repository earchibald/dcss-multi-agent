# Design: the brain learns when to use scrolls and potions

Status: proposed, 2026-11-10. Nothing here is built. It extends `docs/trained-brain.md` and covers
three things: when to read a scroll of identify (and on what), when to read the other scrolls once
they are known, and when to drink the other potions once they are known. The second includes a
**catalog**: a record, built from the brain's own games, of what each scroll and potion does.

## What the games say today

From the 232 rules-of-thumb games already recorded on the evaluation dungeons
(`runs/brain/eval-baseline`, Minotaur Berserker), counted from the protocol recordings:

| | |
| --- | --- |
| Known consumables the brain can use | 2 kinds of potion (curing, heal wounds) and 1 scroll (teleportation) |
| Times it used them | `quaff_heal` 101, `read_teleport` 9 (the rules of thumb never pick teleport; only a random choice or a model does) |
| Unknown scrolls read / unknown potions drunk | 1,314 / 993 |
| Scrolls found by reading whose kind opens a prompt | identify 191, enchant armour 76, enchant weapon 63, blinking 53, brand weapon 17: 400 of the 1,314 reads |
| What happens to those | The prompt is cancelled and "waste the scroll?" answered yes |
| Scrolls of identify still in the pack at the end | 329, in 128 of the 232 games |
| Games that ended holding a known fight or escape item | 109 of 232 (47%). Teleportation alone: 115 scrolls in 46 games |
| Unknown items left at the end | 24 scrolls, 0 potions: everything is tried the moment it is safe |

So three separate things are wrong, and only the last needs learning:

1. **The prompts aren't answered.** About 30% of unknown-scroll reads are thrown away, including 0.6
   of an enchant scroll per game.
2. **Nothing known is ever used**, apart from healing. Identify can't be: its second copy has no action,
   and by then nothing is unknown anyway, because unknowns are tried on sight.
3. **Nothing decides when.** A teleport is in the pack in a fifth of deaths.

## The design in brief

- A **catalog** names every scroll and potion kind, says how to use it (the prompt it opens, when it is
  possible at all), and collects what was measured each time one was used.
- Every catalogued kind worth using gets an **action** (`read:fear`, `quaff:haste`). Identify gets two:
  `identify:potion` and `identify:scroll`.
- **Prompts are answered by fixed rules** (which item to identify or enchant, where to blink), in the
  way `gear.py` decides *what* to wield while the brain decides *when*.
- **When** is learned as everything else is: outcome components per action, with **forks aimed at the
  moments an item could have been used**, since ordinary play almost never contains them.
- The network's output for items moves to a **shared item head**, so a kind used 15 times borrows from
  the others, and adding a kind stops being a contract break.

It lands in four steps, each measured before the next. The first is rules only and should pay on its own,
as equipment did.

## 1. The catalog

New module `src/ladder/brain/consumables.py`, two parts.

**Seed facts**, written by hand, one row per kind. This is the only place the code names an item:

```python
KINDS = {
  "scroll:fear":    Kind(use="fight",   prompt=None,       needs="hostiles"),
  "scroll:blinking":Kind(use="fight",   prompt="blink",    needs="hostiles"),
  "scroll:enchant weapon": Kind(use="at_once", prompt="enchant_weapon", needs="ranked_weapon"),
  "scroll:identify":Kind(use="identify",prompt="identify", needs="unknown_stack"),
  "potion:haste":   Kind(use="fight",   prompt=None,       needs="hostiles"),
  "potion:mutation":Kind(use="trial_only"),
  ...
}
```

`kind_of(item)` maps an inventory item to its key, or `None` while it is unidentified. It replaces the
string tests in `features.inventory` and `humanplay.item_action`.

`use` is one of:

| class | meaning | first set (0.34, Minotaur Berserker) |
| --- | --- | --- |
| `fight` | has an action, possible with hostiles in view; when is learned | potions: curing, heal wounds, haste, might, resistance. scrolls: teleportation, blinking, fear, fog, summoning, butterflies |
| `at_once` | has an action, possible when nothing hostile is in view; the rules of thumb use it as soon as they can | scrolls: enchant weapon, enchant armour, brand weapon, revelation. potion: experience |
| `identify` | the two identify actions | scroll of identify |
| `trial_only` | no action; only ever used while unknown, and catalogued when it is | potions: attraction, lignification, mutation, moonshine, brilliance, magic, berserk rage, cancellation, enlightenment, ambrosia, invisibility. scrolls: immolation, vulnerability, poison, noise, torment, silence, amnesia |

Each seed row also carries the kind's **rarity** from the wiki (`docs/wiki-strategy.md`, section 5):
the share of potions or scrolls found that are this kind (curing 18.4%, heal wounds 10.0%; identify
26.1%, teleportation 13.1%). With the kinds already known this game, that gives the chance that an
unknown stack is each remaining kind, which is what the identify-or-try choice turns on. Two facts
narrow it further: the game names the last unknown kind itself, and summoning and butterflies never
both exist in one game.

`trial_only` is where a kind starts when I can't say it helps this character. The wiki's list of
unknowns worth trying in an emergency adds lignification, invisibility and berserk rage to the potions
I had as `fight`; they stay `trial_only` until measured, since a potion of berserk rage has Trog's
aftermath and blocks every other item while it lasts. The catalog's measured
effect is the evidence for moving one up (immolation and invisibility are the likely first).
Acquirement stays as it is today; choosing from its menu is a different problem.

**Measured effects**, built by `ladder brain catalog` from step logs into `models/catalog.json`, with a
readable `docs/consumables-catalog.md` beside it. This is the "what does this scroll actually do" record.
Each use of an item adds one field to its step row:

```json
"item": {"kind": "scroll:fear", "how": "known", "target": null,
         "msgs": ["You assume a fearsome visage.", "The orc looks frightened!"]}
```

`how` is `trial` (it was unknown and this read identified it), `known` (a later copy) or `identify`
(named by a scroll of identify, not used). Nothing else is stored: the builder reads the effect from
the observations that follow in the same game, per kind and per `how`:

| measured | from |
| --- | --- |
| uses, and how many were trial / known | step rows |
| statuses gained on the next step (`Fast`, `Might`, `Tele`...) | `obs.status` |
| squares moved on the next step (blink, teleport) | new `obs.pos` |
| hostiles in view, adjacent, total threat: before, +1, +5 choices | `obs.mons` |
| HP change over the next 30 turns; died within 30 | as `corpus.label` |
| game turns the use took (0 = refused or cancelled) | `obs.turn` |
| the three commonest message lines | `item.msgs` |
| **uplift**: over forked pairs from one moment, outcome with the item minus outcome without | forks (section 4) |

A trial use happens in safety, so it shows the mechanism (a status, a jump, a message) and says little
about value. A known use in a fight is confounded by the fight. Only the forked pairs say what the item
was worth, which is why uplift is its own column with its own count.

The catalog can be started from what is already on disk: every game's protocol recording holds its
"It was a scroll of ..." lines and the inventory before and after. `ladder brain catalog --from-recordings`
replays them through `GameState` (as `humanplay.py` does) to get about 2,300 trial uses from the baseline
evaluation games alone, before any new game is played.

What the catalog is used for:

- `available` reads `needs` from it, so a new kind is a row, not code.
- The seed flags and a few measured numbers are the item head's per-kind input (section 5).
- `min_count` reads per-kind use counts from it.
- The cockpit and the docs can show it. It is the first thing here a person can read and correct.

## 2. Actions and prompts

`policy.perform` gets one path for all of them: `through_menu(conn, verb, letter)`, then, if the kind
has a `prompt`, the answer from `consumables.answer(kind, state, worn)`. Cancelling and wasting stays
as the fallback when no rule has an answer. This also covers a **trial** read: when `read_unknown`
opens a prompt, the prompt names the kind (`conn.classify_error` already tells them apart), so the same
answer is given and the scroll is no longer wasted.

| prompt | answer |
| --- | --- |
| identify | the item given by the identify rule below |
| enchant weapon, brand weapon | the wielded weapon, if `gear.weapon` ranks it (brand only if it has none). Otherwise cancel **without** wasting when the scroll was known |
| enchant armour | the worn piece `gear.py` scores highest among those that can still take a plus; body armour first. (The wiki's Minotaur Fighter guide goes the other way: boots, gloves, hat, cloak, then body, since the small pieces are kept all game and the body armour is replaced. Try both in step 1) |
| blinking | the visible, walkable, unoccupied square that is furthest from the nearest hostile; ties go to the one nearer known stairs. Deterministic, so replays and forks hold. The wiki's version: out of the middle of a pack to its edge, toward stairs or a corridor, so a square with two or fewer open neighbours should win a tie as well |

### Identify

Two actions, possible when a scroll of identify is known, nothing hostile is in view and a stack of
that class is unknown:

- `identify:potion`: the largest unknown potion stack
- `identify:scroll`: the largest unknown scroll stack

That puts half of "what" in the model's hands (potions or scrolls) and leaves the rest to a rule.

The alternative to identifying is trying, which the brain already does. So what has to be learned
is a three-way choice at each safe moment with unknowns in the pack: identify it, try it, or keep it.
The costs differ by class. A tried scroll is mostly a wasted one (teleport, blinking, fear, fog), now
that prompts are answered. A tried potion wastes the emergency ones (heal wounds, haste, might,
resistance), and those are what the character dies without.

Rules of thumb, replacing "read and drink unknowns when safe":

1. Read unknown scrolls first, as now. One of them may be identify.
2. With identify known: `identify:potion` while an unknown potion stack exists, then `identify:scroll`.
3. Without it: drink unknown potions only from a stack of two or more, or when no scroll of identify
   has been seen by the time the level is explored. (Today: always, at once.)

The wiki's Identification guide (`docs/wiki-strategy.md`) agrees with the shape of these and adds
four things. Try the **largest** stack first, for potions and scrolls alike (built: `--style wiki=1`).
Read unknown scrolls standing on stairs up, on a level not yet explored, with nothing in view, friend
or foe, and a weapon in hand worth enchanting. In an emergency with nothing better left, drink unknown
potions, then read unknown scrolls (built, at 30% HP). And mutation is the only lasting harm from a
trial, which is the case for rule 3.

Rule 3 is a guess, and it is the one the model is most likely to improve on. The network sees what it
needs to (section 3): the sizes of the unknown stacks, how many identify scrolls are held, and how many
kinds are already known this game, which is what makes an unknown likely to be one of the few left.

### Fight items

Each `fight` kind is possible with hostiles in view, the character not berserk, and for scrolls not
silenced or confused (today's `calm` and `can_read`). `quaff_heal` splits into `quaff:curing` and
`quaff:heal wounds`, which do different things. `read_teleport` becomes `read:teleportation`.

**Berserk is the competing choice, and the reason this needs a model.** A berserk Minotaur can't read or
drink, and the rules of thumb go berserk at the first sign of trouble. So every fight item has to be
used *before* berserk or *instead of* it, and which is right depends on the fight.

The rules of thumb get a deliberately small set, so the baseline moves and the rest is left to learn:

- `read:teleportation` at HP ≤ 30% when berserk isn't possible (exhausted, or already used and worn off).
  Built as `read_teleport` under `--style wiki=1`. The wiki says to read it early, since it takes 3 to 5
  turns, and not on an unexplored level; both are for the model to weigh (`level_explored` is an input).
- `quaff:heal wounds` at HP ≤ 50%, `quaff:curing` when poisoned and `poison_survival` is low, or at ≤ 50%
  with no heal wounds.
- `quaff:haste` or `quaff:might` in place of `berserk` when the rage condition holds and berserk isn't
  possible.
- Nothing else. Fear, fog, blinking, summoning, butterflies and resistance are reached by exploration
  and forks only, until the model or the catalog's uplift says where they belong.

### At-once items

Possible with nothing hostile in view. The rules of thumb use them ahead of `rest`. The brain still has
a "when" to learn for two of them: `read:revelation` (on arriving, or only when explore is stuck) and
`read:enchant armour` (now, or after the next `wear`).

## 3. What the brain sees

Added to `features.observe` (additive, so old step logs still encode, with zeros):

- `inv.kinds`: `{kind: quantity}` for every identified scroll and potion. Replaces `heal` and `teleport`.
- `inv.unknown`: for potions and for scrolls, the number of unknown stacks and the size of the largest.
- `inv.known_kinds`: how many potion kinds and scroll kinds have been identified this game.
- `pos`: the character's square, for the catalog's "squares moved".
- Statuses the items give that aren't in `STATUSES` yet: resistance, lignified, attraction, ambrosia
  (the exact strings to be read off the recordings).
- `berserk_ready`: whether `berserk` is possible now. It is in `avail` already, but it is the one
  availability the item decisions turn on, so it gets its own input.

`encode` turns `inv.kinds` into one capped count per catalogued kind and passes the kind list to the
item head. `FEATURE_VERSION` goes to 5.

## 4. How "when" is learned

Ordinary play won't teach this. The rules of thumb use a fight item in a handful of situations, the
effect on `depth_end` of one potion is small next to the spread between games, and the model has no
rows at all for kinds nobody chose. The method is the one that worked for `depth_end`: compare actions
from the same moment.

**Forks at item moments.** `forks.plan` gets a third pool beside "late" and "anywhere": moments where
an item action was possible. Proposed split of fork points: 50% late, 30% item moments, 20% anywhere.
At an item moment the alternatives are not three at random but:

- each item action possible there (up to four, fight items first), and
- if the recorded game used an item there, the rules of thumb's choice without it.

A late moment (the last 40 choices before a death) that also has an item action possible always includes
those actions among its alternatives. Those are the 109-in-232 deaths with something unused in the pack,
and the forks that say directly whether the item would have saved the game.

Forks play to the end of the game, so a fork that spends the teleport now also pays for not having it
later. That is the whole opportunity cost of a consumable, and it is why no new "wasted" label is needed.

Cost: a fork is about 18 s of one worker. 100 item moments at about 3 alternatives is 300 forks, about
15 minutes with 6 workers, per round.

**Exploration.** Self-play's random choice is uniform over what is possible, which with 16 more actions
would burn the pack. Item actions leave the uniform pool and get their own small coin: `--epsilon-item`
(default 0.03 per choice with hostiles in view, for `fight` kinds; 0.1 per safe choice for the identify
and trial decisions). Forks, not random play, carry most of the weight.

**Labels.** Unchanged: the seven components. For fight items the low-variance ones (`died_soon`,
`hp_lost`) carry most of the signal, and `Style` already lets them be weighed in for a run.

**Human games.** `humanplay.py` drops a person's item use today unless it is healing or teleport
(`item_other`). With `kind_of` every use maps to its action, and an identify to its target class. People
use these items well and often, so this is where the `prior` output starts to mean something. It also
feeds the catalog: a spectated game from another server has no keys, but a stack that shrinks beside a
"You read/drink" message is a use with its effect, which is all the catalog needs.

**Trusting it.** As now: an item action replaces the rules of thumb only when predicted `margin` better
and seen `min_count` times. With the shared head the count is taken per class of kind as well as per
kind, so a kind seen 10 times in a class seen 400 times may act, at twice the margin.

## 5. The network

Today `head2` is `Linear(H, A × K)`: every action has its own output weights and learns alone. Thirty
actions, half of them seen a few dozen times, won't train that way.

- The 11 actions that aren't a catalogued kind (`read_unknown` and `quaff_unknown` among them) keep the present head.
- Item actions share one small head: `q(kind) = item_head([trunk, e_kind])`, where `e_kind` is a learned
  8-number embedding joined to the catalog's seed flags (class, prompt, potion or scroll) and three
  measured numbers (statuses gained, squares moved, change in hostiles in view). Kinds that do similar
  things start with similar inputs.
- The kind table is written into the model file. A kind added to the catalog later is a new row trained
  from its flags, not a new contract: old models simply have no action for it.

`net.py`'s numpy forward pass grows by the one extra head, and the parity check covers it. About 3k more
weights on 39k.

## 6. Order of work, and what each step must show

Each step is compared on the same evaluation dungeons with `ladder brain versus`. A depth of 0.3 is
one standard error at 60 games, so steps 1 and 2 should be read at 200 dungeons (`docs/trained-brain.md`,
Next 4) and by the item numbers below, which move by far more than their noise.

| step | what | learning? | must show |
| --- | --- | --- | --- |
| 0 | `consumables.py` seed table and `kind_of`; `item` field in step rows; `ladder brain catalog --from-recordings`; the counting script behind the table at the top as `ladder brain items <run>` | none | a catalog of trial uses from existing games; the numbers above reproduced |
| 1 | Answer the identify, enchant, brand and blink prompts; `identify:*`, the at-once actions and identify rules 1 to 3 | none | scrolls wasted at a prompt: 400 → about 0. Identify left at death: 1.4 per game → under 0.3. Mean depth not lower |
| 2 | Fight-item actions, the small rules of thumb for them, new observations, `FEATURE_VERSION` 5, corpus rebuilt | none | deaths holding a known fight item: 47% → lower. New baseline measured: this is what models are now compared with |
| 3 | Item-moment forks, item exploration, shared item head, train, evaluate | yes | on held-out forked item moments the model picks the best action tried more often than the rules of thumb do. Catalog uplift per kind with its count. Then depth |
| 4 | Human games mapped per kind; catalog from spectated games; promote `trial_only` kinds the uplift supports | yes | `prior` accuracy on held-out human item uses |

Steps 0 and 1 are a day's work and independent of everything else in the queue. Step 3 shares its
machinery with "forks to the end, in volume" (Next 1) and should run in the same overnight rounds.

## Risks and open questions

- **It may not show in mean depth.** Games end around D:5–6 after about 2,000 turns, and a character
  that reads fear once may still die on the next floor. That is why step 3 is judged first on forked
  pairs, where the comparison is within one moment, and only then on depth.
- **Longer games, new hangs.** Every new prompt is a new way to wait forever (equipment found six).
  Each answer needs the `catch_up` discipline and a cancel path. Blinking's target prompt is the least
  like anything handled today.
- **The blink rule is crude.** "Furthest from the nearest hostile" can blink into a dead end. If the
  catalog's uplift for blinking comes out at zero, the rule is the first suspect, not the scroll.
- **Rule 3 (holding single unknown potions) may cost early games** where the first heal wounds found
  would have been identified by drinking. Step 1 measures it; the fallback is today's behaviour.
- **This is one character.** Brilliance, magic and amnesia are `trial_only` because a Berserker has no
  spells. The class of a kind should move into a per-character table when a second character arrives.
- **0.34 facts to confirm before step 1**: whether a known enchant or brand scroll can be cancelled
  without losing it, and what identify does when it is the only unknown thing in the pack. The wiki
  answers both, from pages older than 0.34: Esc on a known scroll's prompt costs nothing, and identify
  names one potion or scroll kind, so with nothing else unknown it is useless (the game names the last
  unknown kind of a class by itself). One test game should still confirm the first.

## Files

| | |
| --- | --- |
| `src/ladder/brain/consumables.py` (new) | seed table, `kind_of`, `answer` (prompt rules), catalog builder |
| `src/ladder/brain/features.py` | `inventory` by kind, new observations, item inputs, `FEATURE_VERSION` 5 |
| `src/ladder/brain/policy.py` | `available` from the catalog, rules of thumb, `perform` answers prompts, item exploration |
| `src/ladder/brain/forks.py` | item-moment pool and its alternatives |
| `src/ladder/brain/humanplay.py` | every item use mapped by kind |
| `src/ladder/brain/train.py`, `net.py` | shared item head, kind table in the model file |
| `src/ladder/brain/corpus.py` | per-kind counts in the corpus meta |
| `src/ladder/brain/cli.py` | `ladder brain catalog`, `ladder brain items` |
| `models/catalog.json`, `docs/consumables-catalog.md` | the catalog and its readable form (generated) |
