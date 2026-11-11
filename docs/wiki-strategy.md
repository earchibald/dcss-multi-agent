# What the DCSS wiki says, and where it lands in the brain

Read 2026-11-10: the wiki's [FAQ](https://crawl.chaosforge.org/Frequently_Asked_Questions) and the
strategy guides it links to. This page keeps only what bears on the trained brain
(`docs/trained-brain.md`): a Minotaur Berserker of Trog that dies around D:5–6. Each piece of advice
is sorted by what it would take to use it: a rule the brain can follow today, a new action, a new
input, or a fact for the consumables design (`docs/brain-consumables.md`).

The first group is built and measured: `--style wiki=1` plays the rules of thumb with the wiki's
advice worked in (`policy.baseline_wiki`). The default rules of thumb are unchanged.

## Sources

| page | wiki says it describes | used for |
| --- | --- | --- |
| [Frequently Asked Questions](https://crawl.chaosforge.org/Frequently_Asked_Questions) | 0.33 | beginner characters, weapon classes, colours, branch order, stats |
| [Walkthrough](https://crawl.chaosforge.org/Walkthrough) | 0.31 | threats by depth, branch order |
| [Escaping from (and avoiding) trouble](https://crawl.chaosforge.org/Escaping_from_%28and_avoiding%29_trouble) | 0.30 | resting, stairs, corridors, every escape item |
| [Tips and tricks](https://crawl.chaosforge.org/Tips_and_tricks) | 0.34 | fighting rules, dangerous monster classes, stairs |
| [Identification](https://crawl.chaosforge.org/Identification), [Potion](https://crawl.chaosforge.org/Potion), [Scroll](https://crawl.chaosforge.org/Scroll), [Scroll of identify](https://crawl.chaosforge.org/Scroll_of_identify) | 0.34, 0.33, 0.31, 0.30 | trying unknown items, rarities |
| [Early](https://crawl.chaosforge.org/Early_Game_Character_Building), [Mid](https://crawl.chaosforge.org/Mid_Game_Character_Building), [Late](https://crawl.chaosforge.org/Late_Game_Character_Building) Game Character Building | 0.34, 0.31, 0.31 | skills, armour, weapons |
| [Weapon choice](https://crawl.chaosforge.org/Weapon_Choice), [Specialization](https://crawl.chaosforge.org/Specialization) | 0.33, 0.34 | attack delay, when to switch weapon |
| [Beginner characters](https://crawl.chaosforge.org/Background_and_race_combinations_for_beginners), [Choosing a god](https://crawl.chaosforge.org/Choosing_a_god), [Character guides](https://crawl.chaosforge.org/Character_guides) | 0.34, 0.30, mixed | Trog, the Minotaur Fighter guide |
| [H's Minotaur Fighter Guide](https://crawl.chaosforge.org/H%27s_Minotaur_Fighter_Guide), [Trog](https://crawl.chaosforge.org/Trog), [Berserk](https://crawl.chaosforge.org/Berserk) | 0.33 | berserk numbers, Trog's abilities and conduct |
| [Vaults](https://crawl.chaosforge.org/Vaults), [Zot:5](https://crawl.chaosforge.org/Zot:5), [Mega-Zig](https://crawl.chaosforge.org/Mega-Zig) | 0.31, 0.34, 0.32 | nothing yet: far below where the bot dies |

The game here is 0.34. Pages marked older may be out of date; where a number below comes from one, the
catalog or a test game should confirm it before it is hard-coded. There is no Minotaur Berserker
guide on the wiki. The Minotaur Fighter guide is the nearest, and parts of it reached me as a summary,
not the page's words (marked *MiFi* below). Not read: Kiting, Pillar dancing, Multizap, Sprint guide,
Berder's Tips (0.16) and the video guides, which the FAQ does not link.

The guides give almost no numbers for *when*: no HP threshold for resting, retreating or drinking.
The thresholds in the rules below (50%, 30%, four steps to the stairs) are mine.

## 1. Rules the brain can follow today (`--style wiki=1`)

| the wiki says | the rules of thumb did | with `wiki=1` |
| --- | --- | --- |
| Explore only at full HP: "a monster dangerous at 100% HP is more dangerous at 75%". Turns don't matter. (Escaping) | rested below 80% | rest whenever hurt |
| Nothing can be drunk, read or invoked in a rage. Use Trog's Hand and Brothers in Arms before it. (Berserk, Trog) | at half HP: berserk first, then the potion can't be drunk | drink the healing potion first, berserk next turn |
| "If you're going to berserk, do it early. Berserking at 50% HP is likely to be fatal." If nothing better is left, berserk anyway. (Berserk) | berserk at half HP, or at something tough within 2 squares, or with 3 near | the same triggers, after the potion and the stairs |
| Only adjacent monsters follow up stairs; the stairs take about 2.5 turns, so walk to them *before* anything is adjacent. (Escaping, *MiFi*) | `flee_up` was the last thing tried | at half HP, stairs up within 4 steps and nothing adjacent: go up |
| Teleport early; it takes 3–5 turns. (Escaping, Scroll) | never read teleportation | at 30% HP when berserk is spent or refused |
| In an emergency with nothing better, try unknown potions, then unknown scrolls: "a bad mutation is better than dying". (Identification) | never | at 30% HP after teleport |
| Try the most numerous unknown first: several found apart are likelier a common kind. (Identification) | first stack in the pack | largest stack |

### Measured

2026-11-10, the 60 evaluation dungeons (seeds 500000–500059), against the same seeds played without it:

| | games | mean depth | median | best | mean XL | game turns | vs the same without `wiki=1`: deeper / same / shallower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| rules of thumb | 60 | 5.58 | 6 | 12 | 5.73 | 1966 | |
| rules of thumb, `wiki=1` | 60 | 5.20 | 5.5 | 11 | 5.68 | 2141 | 12 / 29 / 19 |
| `iter2` (the champion) | 59 | 5.86 | 6 | 12 | 5.76 | 1804 | |
| `iter2`, `wiki=1` | 59 | 5.53 | 6 | 10 | 5.66 | 1785 | 15 / 21 / 22 |

**The wiki's rules did not help, and may have hurt.** Both pairings came out about 0.4 depths behind,
which is one standard error of the paired difference (−0.38 ± 0.34 and −0.36 ± 0.32): not a proven
loss, but the same direction twice, so `wiki` stays 0 by default. What changed in play, per game,
rules of thumb against rules of thumb:

| per game | without | `wiki=1` |
| --- | --- | --- |
| `rest` choices / game turns spent resting | 20 / 222 | 33 / 351 |
| `flee_up` | 1.2 | 8.6 |
| `berserk` | 8.4 | 9.5 |
| `quaff_heal` | 0.4 | 0.6 |
| `read_teleport` | 0.04 | 0.23 |
| games that ended stuck on a level, not dead | 2 of 60 | 4 of 60 |

What I take from it:

- **Going up the stairs is where it most likely loses.** It is the rule that changed most (seven times
  as often), it shows up in the last six choices of 12 of 56 deaths where it used to show in almost
  none, and one of the two new stuck games is a loop of going up, exploring and waiting on D:2. The
  wiki's version has a second half this rule lacks: rest upstairs, then come back for what followed.
  The bot goes up hurt, with the monster a step behind, and has no plan for the top of the stairs.
- **Resting to full costs 60% more turns resting and buys nothing visible.** The guides say turns are
  free. Here they aren't quite: Trog's piety decays, and wandering monsters arrive.
- **Teleport was read in 12 of 56 deaths' last six choices.** At 30% HP with a rage already spent,
  three to five turns is too long. "Teleport early" is the part of the advice that matters.
- Both stuck games that were already there are still there (unreachable stairs, "You can't go down
  here!"); the other new one is the second of those on a different seed.

So the cheap half of the wiki's advice is in and measured, and the result is the same as rounds 3 and 4
in `trained-brain.md`: thresholds on the actions the brain already has don't move it. The advice that
experienced players stress hardest (sections 2 and 3: corridors, stairs *before* the fight, knowing an
orc priest from an orc) needs actions and inputs the brain lacks. Each rule above can be tried alone
by splitting `baseline_wiki`, but at 60 dungeons no single rule will show; that wants the 200-dungeon
evaluation (Next 4).

## 2. Advice that needs an action the brain doesn't have

These sharpen "More to do in a fight" (`trained-brain.md`, Next 2). In the order the wiki stresses them:

1. **Fight in a corridor.** "Never fight more than one monster if you can help it. Always back into a
   corridor." Doorways are weaker: clever monsters walk past to let their friends in. An action
   `step_back` (one step toward the nearest known square with two or fewer open neighbours, never
   toward unexplored floor) is possible from the map Reflex already holds. Retreat goes toward known
   territory, "not into the black", even at the cost of a hit.
2. **Fight on the stairs up.** With no corridor, stand on `<` and fight there: going up splits a group,
   since only the adjacent follow. "Fighting 2 orcs, resting, then 3 orcs is far better than all 5."
   This is a `descend`/`flee_up` pair the brain has, but nothing walks it to the stairs *before* a
   fight. An action `to_stairs_up` when hostiles are in view and none is adjacent would.
3. **Rest and try unknowns on the stairs.** For any long wait stand on a staircase. Read unknown
   scrolls standing on stairs up that lead to a cleared level, on a level not yet explored (teleport
   and noise can be walked away from, and revelation isn't wasted), with nothing in view, friend or
   foe (immolation), and a weapon in hand worth enchanting.
4. **Trog's Hand and Brothers in Arms.** Hand: regeneration and +80 willpower, at 2 stars of piety; it
   can outlast lethal poison. Brothers: berserk allies at 4 stars, "summon early, and summon often",
   with a failure chance that falls as piety rises; they don't follow on stairs. Both only *before*
   a rage, so `available` must offer them only while not berserk, and the rules of thumb must try them
   ahead of `berserk`. The piety figures beside each ability on the Trog page are not labelled as costs.
5. **Throw things.** A stone pulls one monster out of a group. About 2 Throwing is enough early;
   javelins are the good ones, 1.0 delay at 10 Throwing. Heavy armour doesn't slow throwing.
6. **Wait, or step away, by the monster's speed.** One empty square from a normal-speed monster: wait,
   and take the first swing. From a fast one (jackal, quokka, adder; bats can't be escaped at all):
   step away, or it gets a free hit. `wait` exists; the speed is not an input (section 3).
7. **Leave it.** "You do not have to kill every monster, now or ever." Sigmund or a pack with an orc
   priest is a reason to skip D:2 or D:3 by another staircase and come back stronger. Today the unique
   card goes to Authority; the brain could own it (Next 7).
8. **Wands.** A wand of paralysis works on D:3 with no Evocations; used early it saves the potions.
   Iceblast, roots and the lightning rod can't miss. There is no evoke action and wands aren't picked up.

Not worth an action: pillar dancing (attacks of opportunity ended it), yelling, digging corridors.

## 3. Advice that needs something the brain can't see

For "More to see" (Next 3). A monster is seen as its distance, the game's threat colour and its name
hashed into 24 buckets, so the wiki's named threats collide. It names these classes, and each asks for
a different response, so each is a flag worth having per monster:

| class | early examples | what to do |
| --- | --- | --- |
| hits from a distance while it sees you | orc priest (smites for up to 17 a turn, from D:3), orc wizard, centaur (D:5, outruns you) | close to melee, or break line of sight round a corner, whichever is quicker; never stand and wait |
| one hit can end the game | ogre (up to 39 a hit, D:4, slow to swing) | berserk early or don't fight |
| fast | jackal, quokka, adder (poison: keep a curing), bats | can't be outrun; step away, not wait |
| paralyses | Grinder, floating eyes | kill first or leave |
| unique | Sigmund (D:2, "extremely dangerous"), Grinder, Ijyb (carries a wand) | read it, then decide; skipping the level is allowed |
| blinks | | don't berserk at it: the rage runs out in the chase |
| pack with a caster | orcs with a priest | "do not fight a full orc pack that includes a priest" |

The game's own colour (the `threat` input) is the FAQ's first signal: red or purple means stop and
think. It is computed and can be wrong.

Other inputs the guides imply:

- **Attack delay, or weapon skill.** Delay is base delay less half the skill; reaching 1.0 is the
  breakpoint, because above it a normal-speed monster gets double turns. Skill needed for 1.0:
  `(base delay − 1.0) × 20`, so 8 for a mace or flail, 10 for a morningstar or eveningstar, 14 for a
  great mace. `gear.py` ranks by damage with a small delay penalty and will take a great mace at skill 3.
  It should hold a slower weapon back until the skill is there, which needs skills in the observation.
- **Berserk's clock.** A rage lasts 10–19 turns, as few as 3 if turns go on anything but attacking; each
  kill may extend it under Trog. Afterwards: slowed for 14–36 turns and unable to rage for twice that.
  `Slow` and `-Berserk` are inputs already; turns since the rage began is not, and neither is "stairs up
  within 3–4 steps", which the Trog page gives as the reach of a rage.
- **Whether the level is explored**, for teleport: don't on an unexplored level. This is an input.
- **Stairs seen.** A normal level has three down and three up. Fewer seen means unexplored.

## 4. What the guides say about choices already made

- **The character.** Minotaur Berserker is the wiki's first suggestion for a beginner, and "much
  stronger in the early game" than the Fighter. Its pick of weapon for a Minotaur is axes (they hit
  every adjacent enemy for 70%). The bot uses maces and flails, which the FAQ credits with better
  damage and with not multiplying hydra heads in the Lair. Not worth changing before the bot reaches
  packs it can't thin; noted for "other characters" (Next 9).
- **Skills.** The rc leaves training automatic. The Early Game guide wants the weapon skill to the 1.0
  breakpoint first, then Fighting ("a must for everyone"), then Armour and Shields, with weapon skill
  kept on throughout; a few cheap levels of Dodging; Invocations not at all for Trog. Setting this once
  at turn 0 through the skill menu is a rule, not learning, and is the cheapest untested change here.
  Trog punishes training any magic skill, which automatic training could do if the bot ever cast.
- **Stat points.** Strength for heavy melee (FAQ; *MiFi*: at level 3 and every 6 after). Worth checking
  what the stat card answers today.
- **Armour.** "The heaviest armour and shield they can wear without seriously affecting damage output":
  what `gear.py` does. Horns rule out helmets but not hats. A shield wants Shields about 10 for a kite
  shield and 15 for a tower shield; one-hander and shield is the guides' default for this character.
- **Weapons.** Keep to the trained class unless the find is exceptional: a branded or well-enchanted
  weapon of another class beats a plain one of your own (their example: a +6 flail of flaming over a
  +0 hand axe). `gear.py` adds 2 for a brand and never looks outside the mace family. Artefacts with
  *Slow, *Rage or *Silence are the ones to refuse, which it does by refusing all artefacts. Trog
  dislikes magical staves and pain-branded weapons.
- **Depth as the measure.** The Walkthrough's order is D:1–10 or 11, then the Lair, then the Orcish
  Mines and the rest of the Dungeon to D:15, then the two Lair rune branches, Vaults 1–4, Depths, a
  third rune, Zot. `BRANCH_BASE` (Lair 9, Mines 10) agrees with where the entrances are (D:8–11 and
  D:9–12). "Stay in the Dungeon until you find a threat that is too much, then go to the Lair" is a
  rule the brain will need once it lives to D:10; a model rewarded for depth alone will walk past the
  Lair. Early portals (Sewer, Ossuary, Bailey) are timed and optional.
- **Piety.** Trog loses 1 piety per 340 turns of inactivity on average, the only cost the guides put
  on resting to full.

## 5. For the consumables design

Worked into `docs/brain-consumables.md` where they change it. In full:

- **How common things are**, per item found (0.34 Identification, 0.33 Potion, 0.31 Scroll pages):
  potions: curing 18.4%, heal wounds 10.0%, the uncommon ones 6.4% each (attraction, enlightenment,
  haste, lignification, might, moonshine, mutation, brilliance), the rare ones 3.3% (ambrosia, berserk
  rage, cancellation, invisibility, magic, resistance), experience 0.2%. Scrolls: identify 26.1%,
  teleportation 13.1%, most others 4.7%, the rare ones 2.0% (brand weapon, poison, silence, torment),
  acquirement 1.2%. These are the prior for "what is this unknown stack", and belong in the catalog's
  seed row for each kind.
- **Stack size.** Several found separately are likelier a common kind. Two or three found on one
  square are one find, and no likelier. The pack doesn't record where a stack came from; the step log could.
- **The last unknown kind is identified by the game**, and a scroll of identify is useless once
  everything is known. It names one potion or scroll kind, in the pack or on the floor.
- **A known scroll that opens a prompt can be cancelled with Esc at no cost** (Scroll and Scroll of
  identify pages; both older than 0.34). That is one of the design's two open questions.
- **Scrolls of summoning and butterflies never both exist in one game.**
- **What each does, as the guides use it:**
  - Heal wounds: about 25 HP (at least 10); strong early. Curing: a few HP, ends poison and confusion.
  - Might: adds damage, "does not help at low HP". Haste: for running, pairs with fog, also for the fight.
  - Berserk rage: a rage like Trog's with the same aftermath, so it blocks potions and scrolls too. For
    killing, or for 2–3 squares to the stairs, never as a substitute for speed.
  - Teleportation: 3–5 turns' delay; read early; not on an unexplored level; a second read cancels it.
  - Blinking: "the most reliable early escape". From the middle of a pack to its edge, toward stairs or
    a corridor.
  - Fear: checks willpower, nothing against undead or the nonliving; for packs.
  - Fog: cuts off ranged attackers and forces them to come close.
  - Butterflies: pushes enemies back and puts bodies in the way.
  - Noise and immolation: "underrated", and can save better items. Immolation and poison help only when
    nothing is adjacent and there is a ranged attack, which this character lacks.
  - Silence: stops Trog's abilities too. "Very risky."
  - Ambrosia: confuses, restores HP while it lasts; only with a few turns before the next monster.
- **Emergency order.** Unknown potions before unknown scrolls, until most emergency potions are known;
  then scrolls. Helpful unknowns: potions of curing, heal wounds, might, haste, lignification,
  invisibility, berserk rage; scrolls of teleportation, blinking, fear, summoning or butterflies.
- **Mutation is the reason people don't drink blind**, and the only lasting harm from a trial.
- **Enchant scrolls.** Weapon Choice: save enchant and brand scrolls for a top-tier weapon if you are
  killing comfortably; if not, spend them now. The bot is not, so the design's "use at once" stands.
  *MiFi* orders armour enchants boots, gloves, hat, cloak, then body, against the design's body first.
- **Buying to identify** is a use for a shop, if the brain ever shops.

## 6. Not used

Spell advice throughout (Trog forbids it). Other gods' escapes. Vaults:5, Zot:5 and the Mega-Zig: each
wants resistances, haste, cancellation and a plan the bot is twenty floors from needing. One line from
them is general: teleport "early and often", and stair-dancing stops working where monsters seal stairs.
