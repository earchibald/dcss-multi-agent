# What makes qw win

Research note, 2026-11-15. qw is the DCSS devteam's Lua bot (github.com/crawl/qw). Here it plays a
Minotaur Berserker of Trog with a mace on our 0.34 container. The question: what separates a qw
win from the usual qw death? Marks: **[V]** verified (seen in our data or in the code), **[I]**
inferred.

## Summary

- **We have 3 wins.** They come from 19,335 saved full games (18,523 MiBe^Trog games that did not
  quit, which are 8,623 distinct trajectories over 1,843 seeds). The 3 wins are on **two seeds**:
  100443 (`s2-zerk_early`) and 600058 (`held6-a-base` and `held6-a-t10`). The 4,210 fork games
  have no wins. [V]
- **Reaching Zot is the real filter.** 36 distinct trajectories reached Zot:1, and 3 of them won
  (1 in 12). All 33 deaths with three runes are in Zot. [V]
- **Up to Zot, a winning game looks like the best losing games.** At D:10, the Lair end, the first
  rune, Vaults:1, Depths:1 and Zot:1, the wins and the three-rune deaths have the same XL (within
  0.5) and the same turn count (within about 1,500). [V]
- **In Zot, the escape fails.** Teleport in Zot takes 8–12 turns, not 3–5: `you_teleport()` in
  `spl-transloc.cc` adds 5+random(5) when `orb_limits_translocation()` (`orb.cc`:83), and that is
  true anywhere in Zot. qw's `want_to_teleport()` does not know this. 26 of the 33 Zot deaths read
  teleportation in their last 15 turns. Among deaths at XL 15+ elsewhere, 797 of 2,318 (34%) did. [V]
- **The winners got through the same delays with more defence and more healing.** All 3 end with
  AC+EV+SH of 110–120; every one of the 33 Zot deaths is at 100 or less. They also drank more heal
  wounds in Zot (mean 6 against 2.7). [V for the numbers]
  - This is weak evidence. Values at death can be lowered by drain and corrosion, the winners'
    numbers are taken after the orb run, and there are only 2 winning seeds. [I]
- **Luck counts most early.** In the cleanest comparison (stage 2: 298 seeds, 9–10 settings each,
  67% distinct trajectories), the seed explains:
  - about half of the spread in final XL (ICC 0.49) and in dying by D:5 (0.47);
  - very little of whether a rune is taken (0.07) or three runes (0.13). [V]
- **A dungeon that allows three runes still mostly kills qw.** The seeds that gave three runes at
  least once gave them in only 1 to 5 of their 10–14 runs. [V]
- **qw nearly always dies inside a rage or just after one.** At XL 15+, 40% die berserk and 52% die
  on berserk cooldown (slowed). 62% die holding heal wounds and 68% holding teleportation. While
  berserk, the game allows no drinking, reading or invoking. [V]
- **qw's public games show the same Zot pattern** (section 7). On CDI (0.29–0.33) qw won 0.03%
  of its games, and 19 of the 219 that reached Zot (8.7%). 81 of 96 Zot deaths there had a
  teleport still pending ("about to teleport"). On CAO in 2016–17 (0.18–0.21-a) the win rate was
  1.1%, and Minotaur Berserkers of Trog won 4 of their 97 games. [V]
  - In 13 of 15 combos, the median winner ended with more AC+EV+SH than the median Zot death of
    the same combo (combos with at least 4 such games). It is not a clean line, though: some
    deaths had more than any win. [V]
  - Winners drank more heal wounds in Zot in total (3.3 against 2.8) but stayed over twice as
    long. Per turn in Zot, the deaths drank more. [V] So the extra drinking looks like a result of
    the longer stay, not its cause. [I]

## 1. How rare are wins

Our data (`runs/qw/*/games/*/logfile.txt` and `morgue.txt`; container `/data/qw/runs` holds the
same games):

| Set | Games | Wins | Rate |
|---|---|---|---|
| All saved full games (all builds, settings and combos) | 19,335 | 3 | 0.016% |
| MiBe^Trog distinct trajectories, quits excluded | 8,623 | 3 | 0.035% |
| Seeds | 1,843 | 2 | 0.11% |
| Latest build (`lib-zk`), tuned settings, held-out seeds 600000–600599 (`held6-*`, 6 runs) | 1,183 | 2 (one seed) | 0.17% |
| `held6-*-base` alone | 591 | 1 | |
| `held6-*-t10` (risk-alarm teleport stance) alone | 592 | 1 | |
| Stage 2 of the settings search (1800 s limit, older build), all 11 runs | about 3,180 | 1 (`s2-zerk_early`) | |
| Fork games (partial replays) | 4,210 | 0 | |

The funnel over the distinct trajectories (n = 8,623) [V]:

| Reached | Count | Share |
|---|---|---|
| D:5 | 7,059 | 82% |
| Lair:1 | 4,522 | 52% |
| D:10 | 3,836 | 44% |
| Lair:5 | 3,398 | 39% |
| First rune | 556 | 6.4% |
| Vaults:1 | 545 | 6.3% |
| Second rune | 216 | 2.5% |
| Depths:1 | 214 | 2.5% |
| Zot:1, three runes | 36 | 0.42% |
| Picked up the Orb | 6 | 0.07% |
| Won | 3 | 0.035% |

- Every three-rune game takes the runes the same way: the first Lair-branch end, then Vaults:1–4,
  then the second Lair-branch end, then Depths, then the Vaults:5 silver rune third. This is qw's
  `goal_normal_next` (goals.lua:4–133). [V]
- The first rune came from Swamp 182 times, Spider 134, Shoals 128 and Snake 112. [V]

**Public record.** Section 7 has qw's public games. In short: 1.1% of qw's 10,600 games on CAO
in 2016–17 won, against 0.03% of its 62,579 games on CDI in 2022–24. On CDI, 19 of the 219 games
that reached Zot won (8.7%), close to our 3 of 36. [V]

## 2. Wins against losses at the same stage

Cohorts are distinct MiBe^Trog trajectories:

- **Won**: 3 (2 seeds).
- **3R died**: three runes, died (33).
- **1–2R**: one or two runes, died (520).
- **Lair**: reached the Lair, no rune (3,966).
- **pre-Lair**: died before the Lair (4,101).

Each snapshot is taken at the first note made on that level (`stages.py`).

Columns:

- **Heavy body**: plate, crystal plate or dragon scales.
- **Shield**: wearing one.
- **Weapon +**: the wielded weapon's enchantment.
- **Gifts**: Trog gifts so far.
- **Low HP**: notes with HP at 25% or less so far.
- **Rages**: berserks so far.
- **BiA**: Brothers in Arms invocations so far.

| Stage | Cohort | n | XL | Turn | Heavy body | Shield | Weapon + | Gifts | Low HP | Rages | BiA |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D:5 | Won | 3 | 6.7 | 4,118 | 67% | 100% | 0 | 0 | 0.7 | 3.3 | 0 |
| | 3R died | 33 | 6.6 | 3,743 | 18% | 39% | 0.9 | 0 | 0.2 | 3.1 | 0 |
| | Lair | 3,966 | 6.6 | 3,598 | 26% | 40% | 0.8 | 0 | 0.6 | 3.0 | 0 |
| | pre-Lair | 2,537 | 6.4 | 3,603 | 24% | 40% | 0.5 | 0 | 0.7 | 2.8 | 0 |
| D:10 | Won | 3 | 10.3 | 9,288 | 100% | 100% | 0 | 0 | 1.0 | 5.7 | 0 |
| | 3R died | 33 | 11.9 | 11,951 | 67% | 79% | 2.3 | 0.6 | 1.4 | 14.0 | 2.1 |
| | Lair | 2,848 | 11.4 | 11,094 | 76% | 76% | 1.9 | 0.7 | 2.3 | 11.6 | 1.1 |
| Lair:5 | Won | 3 | 13.0 | 14,756 | 100% | 100% | 3.0 | 2.3 | 1.0 | 8.7 | 1.3 |
| | 3R died | 33 | 13.0 | 14,360 | 73% | 85% | 2.4 | 1.4 | 1.3 | 15.2 | 2.5 |
| | 1–2R | 520 | 12.9 | 14,409 | 74% | 88% | 2.9 | 1.3 | 2.1 | 16.3 | 2.4 |
| | Lair | 2,842 | 12.9 | 14,470 | 78% | 81% | 2.4 | 1.3 | 2.9 | 14.9 | 1.5 |
| First rune | Won | 3 | 17.7 | 31,421 | 100% | 100% | 4.0 | 9.3 | 5.3 | 22.3 | 7.0 |
| | 3R died | 33 | 17.6 | 31,521 | 64% | 100% | 5.2 | 9.3 | 4.6 | 35.2 | 12.6 |
| | 1–2R | 520 | 17.5 | 32,083 | 73% | 99% | 4.9 | 8.8 | 6.6 | 36.3 | 11.5 |
| Depths:1 | Won | 3 | 20.7 | 40,546 | 100% | 100% | 4.0 | 15.0 | 6.0 | 31.0 | 16.0 |
| | 3R died | 33 | 20.4 | 41,284 | 91% | 100% | 5.5 | 13.8 | 6.7 | 46.3 | 26.9 |
| Zot:1 | Won | 3 | 23.0 | 50,004 | 100% | 100% | 4.0 | 19.7 | 9.0 | 42.7 | 32.7 |
| | 3R died | 33 | 23.1 | 51,464 | 97% | 100% | 5.8 | 17.5 | 9.9 | 61.9 | 49.5 |

All numbers are [V]; what they mean is [I] at n = 3:

- **Pace and XL**: the same at every stage from the Lair end on.
- **Heavy armour and a shield early**: in all 3 wins, which is luck of the floor.
  - 600058 put on **+10 shadow dragon scales** (an artefact) on D:3 at turn 2,972, a kite shield on
    D:1 and a tower shield on D:5.
  - 100443 had chain mail on D:1, plate armour on D:7 and a morningstar on D:2.
- **Fewer rages**: the wins raged about a third less than the three-rune deaths (22 against 35 by
  the first rune; 43 against 62 by Zot:1).
- **Trog gifts**: the same number. Trog gifts arrive at about one per level from the Lair on, so
  every deep game gets a good weapon (an eveningstar or demon whip by the first rune). The gift is
  not what separates the wins.

### In Zot

From `zotstock.py`. The stack sizes come from qw's own "DRINKING n potions" and "READING n
scrolls" notes.

| | Won (3) | Three runes, died (33) |
|---|---|---|
| Turns in Zot | 7,712 / 10,094 / 9,511 | median 1,471; 13 died on Zot:1 |
| Heal wounds held at the last use before Zot | 5 / 9 / 4 (mean 6.0) | mean 4.3, median 3 |
| Heal wounds drunk in Zot | 5 / 10 / 3 (mean 6.0) | mean 2.7, median 1 |
| Teleport read in the last 15 turns of the game | (not applicable) | 26 of 33 |
| Final AC / EV / SH | 45–47 / 31 / 32–42 | AC 28–55, EV 9–29, SH 0–34 |
| AC+EV+SH | 110, 110, 120 | all ≤ 100 (median 88) |
| rElec at the end | 3 of 3 | 13 of 33 |
| rPois at the end | 3 of 3 | 26 of 33 |
| Picked up the Orb | 3 of 3, all escaped | 3 died on Zot:5 holding it |

- **Killers in Zot**: draconians kill 17 of the 33 (mostly breath and beams). Then deathcaps 2,
  orbs of winter 2, Orb Guardians 2, storm dragons 2, and one each of orb of fire, balrug, ancient
  lich, tentacled monstrosity, protean progenitor, death cob, profane servitor. One poison death
  has no killer recorded. [V]
- **Deaths by Zot level**: Zot:1 13, Zot:2 7, Zot:3 4, Zot:4 3, Zot:5 6. [V]

**The best matched pair: seed 100443, the same dungeon, three ways.**

- Under `s2-zerk_early` the game won. Under `s2-heal55` and `s2-zerk_hp70_zerk_early_bia7` it died
  on Zot:1 with three runes. The milestone timelines run close to the end.
- In both losses:
  - qw stairdanced between Depths:4 and Zot:1, raged, was slowed once the rage ended, and read
    teleportation.
  - The game said "You feel the Orb delaying your translocation!".
  - qw died 6–7 turns later, to a deathcap's draining and to a purple draconian shifter.
- The winner on the same seed was at 41/360 HP on Zot:3. It read teleportation and drank 6, 5 and
  then 4 heal wounds while the teleport was delayed, and lived.
- The winner also wore a +7 tower shield {Dex+5} from Swamp:2 and Dex+3 gloves (Dex 25, EV 31,
  SH 34). The losses had Dex 16, EV 20–21 and SH 26–27. Swamp:2 rolled a different shield after
  the games diverged. [V for the facts; that the shield decided it is I]
- Morgues:
  - `runs/qw/s2-zerk_early/games/100443/morgue.txt`
  - `runs/qw/s2-heal55/games/100443/morgue.txt`
  - `runs/qw/s2-zerk_hp70_zerk_early_bia7/games/100443/morgue.txt`

**Seed 600058** (`runs/qw/held6-a-base/games/600058/morgue.txt`, `held6-a-t10/...`) won both times
it was played, with diverging trajectories. On Zot:3 and Zot:5 it went to 4–11% HP. It survived by
drinking heal wounds stacks of 10 down to 5 between teleport reads, and it held 20 teleport
scrolls. [V]

**Near-deaths in the wins.**

- 100443: 4/187 HP against Rupert on Lair:5.
- 600058-t10: 1/184 HP against a naga warrior on Snake:4.
- So the wins also survive coin flips. [V]

## 3. Luck of the dungeon against qw's decisions

**How much of the outcome the seed explains.** This is the intraclass correlation (ICC): the share
of the spread between games that lies between seeds (`luck.py`). [V]

| Outcome | Stage 2 (298 seeds × 9–10 settings, 67% distinct) | lib-zk era (395 seeds × 10–19 runs, 36% distinct) |
|---|---|---|
| Died by D:5 | 0.47 | 0.81 |
| Final XL | 0.49 | 0.76 |
| Reached the Lair | 0.36 | 0.66 |
| At least 1 rune | 0.07 | 0.32 |
| 3 runes | 0.13 | 0.20 |

- The lib-zk column is inflated, because most of its "different" runs replay the identical game.
- Reading of stage 2: the dungeon decides much of the early game, which is when a dangerous pack or
  unique turns up and whether armour is found. Past the Lair, the dice and the decisions dominate.
  [I]

**Conditional rates** (`cond.py`, distinct trajectories) [V]:

| At | Feature | Outcome rate |
|---|---|---|
| D:5 | weapon: mace 60%, morningstar 65%, eveningstar 86%, demon whip 88% | reach the Lair |
| D:5 | XL <6: 55%, 6–7: 64%, ≥8: 70% | reach the Lair |
| D:5 | low-HP events so far: 0: 66%, 3: 53%, 4+: 49% | reach the Lair |
| D:5 | body armour light 59%, chain/scale 65%, heavy 65% | reach the Lair |
| D:10 | XL 10–11: 12.1%, ≥12: 20.3% | at least 1 rune |
| D:10 | slower than 12,000 turns: 19.7%, faster: 12.2% | at least 1 rune |
| D:10 | Trog gift already: 17–18%, none: 12.7% | at least 1 rune |
| D:10 | low-HP events: 0: 17.9%, 3+: 9–11% | at least 1 rune |
| Lair:5 | shield: 17.5%, none: 11.1% | at least 1 rune |
| Lair:5 | low-HP events: 0: 22.1%, 3+: 11–12% | at least 1 rune |
| First rune | XL, armour, weapon, enchantment, gifts, pace | all about 6.5%: nothing separates them |

- A good early weapon is luck, and it matters for getting to the Lair (+25 points), not for runes.
  [V]
- Slower descent (more clearing and XP) and fewer near-deaths before the Lair predict runes. That
  is a decision qw could make. [V for the rates, I for the cause]
- Early uniques barely matter except **Sigmund** (met on D:1–6 in 2,428 games; kills 9%; 214
  deaths) and **Jeremiah** (kills 12% of the 363 who meet him). [V]
- Once a rune is in hand, kit no longer predicts three runes. The Zot gate (section 2) and the rune
  branches are what remain. [V]

## 4. Which of qw's rules do the heavy lifting

Paths are in the upstream clone `runs/qw/src/source/` (commit 8698adc, which is still upstream
master). The deployed build is `/data/qw/lib` = `/data/qw/lib-zk`, `runs/qw/build-zk/qw.lua`.

**Early, D:1–5**

- **The rage.**
  - `want_to_berserk` (plans-emergency.lua:779–802) is last in the emergency cascade.
  - Our tuning: HP ≤70% with an enemy within 2, and `const.high_threat` 7, not 10
    (`runs/qw/combo1-lua/MiBe_mace.lua`).
  - Upstream never rages (the `can_berserk` precedence bug; `tools/qw/patches.py`). Fixing it was
    worth +2.5 levels (docs/qw-teacher.md). [V]
- **Equipment valuation.**
  - `weapon_value` (equipment-compare.lua:451–677) stays within one weapon skill.
  - `armour_base_value` (:296–406) follows a heavy-armour plan. `SHIELD_CRAZY` means a shield is
    always worn and two-handers are refused.
  - It is why the early chain, plate and kite-shield finds go on at once. [V]
- **Reading and drinking unknown items** (plans-items.lua:617–654): qw identifies consumables
  early, which is how it has teleportation and heal wounds later. [V]

**Mid game: Lair, Orc, D to 15**

- **Order** (`goal_normal_next`): D:1–11, then the Lair when found (`ready_for_lair`,
  goals.lua:663–688, has **no XL gate**), then D:12–15, then Orc (`LATE_ORC`). [V]
- **Brothers in Arms** at threat 7 (`bia7`) and **Trog's Hand** against casters
  (`want_to_trogs_hand`, :761–770). [V]
- **Flee to the upstairs and stairdance** (move-flee.lua:55–114; plans-stairs.lua:172–237). In
  forks, fighting on the upstairs was the best new action (+0.14 ± 0.06 in fatal fights,
  docs/qw-teacher.md). [V]

**Rune branches**

- The branch order is a coin flip (`lair_branch_order`, :714–745). Nothing looks at rPois or rElec.
  [V]
- The poison cures are patched: zk cures lethal poison anywhere and before a rage; zr adds a
  `cure_lethal_poison` plan at the head of the cascade (in lib-zr only). [V]

**Vaults and Depths**

- The −Move fix (bolas) and the flee-search memo fix are ours. Without them the best games stalled
  in Vaults (docs/qw-teacher.md). [V]
- Shopping: qw buys teleportation and enchant scrolls (plans-items.lua:674–752). The wins spent
  3,814 and about 4,950 gold. [V]
- Enchant scrolls go on armour pieces first (:493–543). [V]

**Zot and the orb run** (plans-orbrun.lua:4–25)

- With the orb, qw does not rest for HP. It drinks heal wounds at ≤25% HP (≤50% while teleporting)
  and teleports at ≤33% HP with an enemy within 2. [V]
- **There is nothing for draconians**, except a resistance potion for rElec against black
  draconians before XL 20. [V]
- **There is nothing for the teleport delay in Zot**: `want_to_teleport` (plans-emergency.lua:627–667,
  build line 12187) treats a Zot teleport like any other. [V]
- What carried the wins was stock (heal wounds to bridge 8–12 turns), defence, and the dice. [I]

## 5. Where the non-winning games die

Distinct MiBe^Trog trajectories, 8,620 deaths (`deaths.py`) [V]:

| Place | Deaths | Share | Median XL | Top killers |
|---|---|---|---|---|
| D:1–5 | 1,907 | 22% | 5 | gnoll 426, Sigmund 214, orc wizard 141, orc priest 113 |
| D:6–10 | 1,999 | 23% | 9 | gnoll 121, wight 115, electric eel 108, killer bee 96 |
| Lair | 1,738 | 20% | 12 | death yak 184, cane toad 152, yak 101, komodo dragon 83 |
| Orc | 352 | 4% | 15 | orc warrior 78, orc priest 72, orc knight 49 |
| D:11–15 | 672 | 8% | 14 | Nessos 34, centaur warrior 33, skeletal warrior 32 |
| Lair rune branches | 1,221 | 14% | 16 | the naga family (about 210), merfolk impaler 36 |
| Vaults | 311 | 4% | 19 | vault warden 25, ironbound thunderhulk 22, frostheart 21 |
| Depths | 137 | 2% | 21 | tengu reaver 8, caustic shrike 6 |
| Abyss | 159 | 2% | 13 | laughing skull 16, bone dragon 15 |
| Zot | 33 | 0.4% | 24 | draconians 17 |

**Deaths qw's code tries to prevent and does not** [V]:

| Death | What qw does | Why it fails |
|---|---|---|
| Dies in or just after a rage (XL 15+: 40% berserk, 52% on cooldown) | Rages last in the cascade, rages often | In a rage nothing can be drunk, read or invoked, and no tactical step is taken (move-tactics.lua:269). After it, qw is slowed |
| Dies holding escape items (62% heal wounds, 68% teleport at XL 15+) | Heal wounds at ≤25% HP, teleport at ≤25% with immediate danger | The thresholds are late, and teleport is skipped when `will_flee()` |
| Teleport in Zot (26/33) | Reads teleport as usual | The 8–12 turn delay in Zot is unknown to qw |
| Poison in Spider, Snake and Swamp | Patched cures | The resistance potion only fires against swamp drakes (monsters.lua:233); branch order ignores rPois |
| Sigmund, gnoll packs on D:1–5 | Rage, flee to the upstairs | Packs of 4+ are 74% of deaths, and 93% of fatal fights start at full HP (docs/qw-teacher.md) |
| Never drinks might | `want_to_might` | Dead code: it tests the undefined global `danger` (build line 11945). The winner 100443 ended holding 3 potions of might |

## 6. What this means for our bot

Ranked by evidence and by how much of the funnel each one affects:

1. **Survive the early game by fighting where the pack cannot surround you.** 45% of deaths come by
   D:10, from packs. Fight on the upstairs and leave by them (forks: +0.14 in fatal fights). Treat
   Sigmund, gnoll packs and Jeremiah as leave-the-level threats. [V]
2. **Rage early, and plan the exit from the rage.** Raging sooner is the largest tuning gain
   measured (+1.6 XL). Nearly every death happens in a rage or just after it, so:
   - drink and read *before* raging when poisoned or low;
   - do not rage in a poison cloud or against poisoners without rPois;
   - have the escape ready for the slowed turns afterwards. [V for the rates; the remedy is I]
3. **Escape earlier, while there is still time to spend.** Most XL 15+ deaths hold heal wounds and
   teleportation. Use teleport at higher HP, and never count on a teleport in Zot: it takes 8–12
   turns there. In Zot the exits are stairs, heal wounds to bridge the delay, and not getting
   caught on Zot:1. [V]
4. **Build defence on purpose: AC+EV+SH, Dex and a shield.** A shield by the Lair end raises the
   rune rate (17.5% against 11.1%). All 3 wins ended with AC+EV+SH 110–120, against ≤100 for every
   Zot death. Train Shields and Dodging, value Dex and evasion rings, and wear the best shield.
   [V for the rates, I for the cause]
5. **Go slower before the Lair: clear levels, come in at XL 12+, fewer near-deaths.** At D:10, XL
   12+ gives 20% runes against 12%, and a slow pace 20% against 12%. Each near-death roughly halves
   the later chances. qw has no XL gate for the Lair; ours should have one. [V for the rates]
6. **Stock up for the end.** Keep about 6+ heal wounds and 15+ teleportation for Zot. Buy
   teleportation in shops, which qw does. [V for the stock the wins had]
7. **Pick rune branches and fights by resistances.** Use rPois for Spider, Snake and Swamp, and
   rElec and rF for Zot. qw flips a coin. [I]
8. **Drink might.** It is free damage qw throws away. [V for the bug; any gain is I]

**What cannot be copied (dungeon luck)** [V]:

- An artefact body armour or shield on D:1–5 (600058's +10 shadow dragon scales on D:3).
- An early eveningstar or demon whip (+25 points of reaching the Lair).
- Which uniques sit on D:2–5.
- What a level rolls after the games diverge (the Dex+5 tower shield on Swamp:2).
- The coin flips that the wins also survived (4/187 against Rupert, 1/184 on Snake:4).

The seed explains about half of early outcomes and little of the late ones (section 3).

## 7. Public record

qw plays as the account `qw` on public servers. Two servers keep its games:

- **CAO** (crawl.akrasiac.org): 2016–17, versions 0.18 to 0.21-a, elliptic's era.
- **CDI** (crawl.dcss.io): 2022–24, versions 0.29 to 0.33-a, run by the devteam. Most of its
  games went to separate "bot" logfiles.

The counts below come from the servers' raw logfiles, filtered to `name=qw` with quits dropped.
The scripts are in `/Users/earchibald/.claude/jobs/1cdb9134/tmp/qw-wins/public/scripts/`
(`stats.py`, `funnel.py`, `deep.py`, `bychar.py`, `mibe.py`, `zotbatch.py`, `zotagg.py`).
Two caveats apply to every figure:

- The god is the god at the end of the game. A game that dies before an altar counts as godless,
  so per-god rates are too high.
- CDI's games are mostly devteam test runs: qw was being rewritten and tried on weak combos, such
  as 8,182 DEHu games with no win. [I]

### Win rate by server and version [V]

| Server, version | Logfile | Games | Wins | Win rate | Reached Zot:1 | Wins / Zot:1 |
|---|---|---|---|---|---|---|
| CAO 0.18.1 | [logfile18](https://crawl.akrasiac.org/logfile18) | 253 | 3 | 1.19% | | |
| CAO 0.19-a | [logfile-git](https://crawl.akrasiac.org/logfile-git) | 5,231 | 80 | 1.53% | | |
| CAO 0.19 | [logfile19](https://crawl.akrasiac.org/logfile19) | 585 | 5 | 0.85% | | |
| CAO 0.20-a | logfile-git | 532 | 2 | 0.38% | | |
| CAO 0.20 | [logfile20](https://crawl.akrasiac.org/logfile20) | 1,835 | 25 | 1.36% | | |
| CAO 0.21-a | logfile-git | 2,164 | 5 | 0.23% | | |
| **CAO total** | | **10,600** | **120** | **1.13%** | | |
| CDI 0.29 | [crawl-bot-0.29](https://crawl.dcss.io/crawl/meta/crawl-bot-0.29/logfile) | 11,227 | 3 | 0.03% | 41 | 3/41 |
| CDI 0.30-a | [crawl-bot-git](https://crawl.dcss.io/crawl/meta/crawl-bot-git/logfile) | 2,352 | 0 | 0 | 62 | 0/62 |
| CDI 0.30 | [crawl-bot-0.30](https://crawl.dcss.io/crawl/meta/crawl-bot-0.30/logfile) | 1,975 | 1 | 0.05% | 34 | 1/34 |
| CDI 0.31-a | crawl-bot-git | 22,175 | 9 | 0.04% | 67 | 9/67 |
| CDI 0.31 | [crawl-bot-0.31](https://crawl.dcss.io/crawl/meta/crawl-bot-0.31/logfile) | 8,018 | 3 | 0.04% | 6 | 3/6 |
| CDI 0.32-a | [crawl-git](https://crawl.dcss.io/crawl/meta/crawl-git/logfile) | 12,588 | 2 | 0.02% | 4 | 2/4 |
| CDI 0.32 | [crawl-0.32](https://crawl.dcss.io/crawl/meta/crawl-0.32/logfile) | 8 | 1 | | 1 | 1/1 |
| CDI 0.33-a | crawl-git | 4,236 | 0 | 0 | 4 | 0/4 |
| **CDI total** | | **62,579** | **19** | **0.030%** | **219** | **19/219 (8.7%)** |
| *Ours, MiBe^Trog, 0.34 (section 1)* | | *8,623* | *3* | *0.035%* | *36* | *3/36* |

- Zot:1 counts come from the matching `milestones` files (`br.enter` into Zot). The CAO
  milestones were not fetched, so CAO has no Zot column.
- With quits counted, the totals are 10,715 CAO games and 62,885 CDI games. They match the
  [CAO scoring page](https://crawl.akrasiac.org/scoring/players/qw.html): 42,946 games and 153
  wins in all, which also counts CSZO (2013–15, 26 wins) and 7 of the 19 CDI wins.
- **Runes.** CAO's wins: 117 with 3 runes, 1 with 4, and 2 with 15 (GrFi^TSO, 0.20). The scoring
  page adds a 4-rune and a 5-rune GrBe win on CSZO. Every CDI win has 3 runes.

### By combo [V]

| Combo | Where | Games | Wins | Rate | Games with 3+ runes | Won of those |
|---|---|---|---|---|---|---|
| **MiBe** (all wins with Trog) | CAO 0.18–0.20 | 97 | 4 | 4.1% | 7 | 4 |
| **MiBe** (all wins with Trog) | CDI 0.29 | 808 | 1 | 0.12% | 17 | 1 |
| DDFi | CAO 0.19-a/0.20 | 327 | 23 | 7.0% | 59 | 23 |
| DDFi^Makhleb (god at end) | CAO | 183 | 18 | 9.8% | | |
| GrBe (all wins with Trog) | CAO 0.18–0.19-a | 184 | 14 | 7.6% | 23 | 14 |
| MiFi (11 gods) | CAO | 1,852 | 17 | 0.9% | 33 | 17 |
| GrFi | CAO 0.20–0.21-a | 1,144 | 6 | 0.5% | 127 | 6 |
| GrFi | CDI 0.29–0.32 | 7,304 | 3 | 0.04% | 149 | 3 |
| GrHu (all wins with Okawaru) | CDI 0.31 | 4,347 | 7 | 0.16% | 20 | 7 |

- **MiBe in 0.19-a won 4 of its 6 three-rune games.** MiBe in 0.29 won 1 of 17, and the other 16
  died in Zot.
- **The "15%" in `docs/accomplishments.md` is not in the public logs.** The best public rate for a
  combo with 100+ games is DDFi^Makhleb at 9.8% (CAO 0.19-a), and that is biased up by
  god-at-end. The 15% is probably an offline or shorter-window figure. [I]
- **qw's public MiBe funnel (0.29) against ours (0.34)** [V; that the versions explain the
  difference is I]:

| Reached | Public 0.29 (808 games) | Ours (8,623) |
|---|---|---|
| Died on D:1–5 | 26% (gnoll 33, Sigmund 25, orc wizard 16) | 22% (gnoll, Sigmund, orc wizard) |
| Lair | 46% | 52% |
| First rune | 5.9% | 6.4% |
| Zot:1 | 2.1% | 0.42% |
| Won | 0.12% | 0.035% |

  Up to the first rune the two match. After it, the public 0.29 games reached Zot 5 times as often
  (17 of 48 games with a rune, against our 36 of 556). Only 20 of the 808 died in Vaults, against
  our 311 of 8,620 deaths.

### Morgues read

All morgues are qw's own. Losses L1–L5 are MiBe^Trog games with three runes, picked as the deep
deaths.

- W1–W8 and L1–L7 were each read in their header, inventory, final notes and final messages, plus
  their Zot notes in full, by script (`morgue.py`) and by eye.
- All 96 CDI Zot deaths with three runes and all 19 CDI wins were then parsed by `zotbatch.py`.
- AC/EV/SH and HP are values at the end of the game.

**Wins**

| # | Morgue | Version, combo | Turns | AC/EV/SH (sum) | Resists at end | Kit | Left at end: HW / tele | Lowest HP | In Zot |
|---|---|---|---|---|---|---|---|---|---|
| W1 | [20220913-002803](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220913-002803.txt) | 0.29 MiBe^Trog | 71,339 | 56/19/29 (104) | rF+ rC+ rPois, no rElec, Reflect | +9 war axe of protection, +11 gold dragon scales, tower shield | 0 / 4 | 20/231 on Vaults:5; 45/273 on Zot:4 | 9,817 turns. 3 teleport reads, each bridged by heal wounds (stacks 12→11, 11→6, 6→5). 25 rages |
| W2 | [20220911-050638](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220911-050638.txt) | 0.29 GrDe^Oka | 56,867 | 56/9/29 (94) | rF+ rC+ rElec rPois rCorr | +9 vampiric broad axe, gold dragon scales, tower shield | 8 / 17 | 2/32 on D:3 | 6,019 turns. No teleport, no heal wounds |
| W3 | [20240120-013941](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20240120-013941.txt) | 0.31 GrHu^Oka | 45,598 | 55/41/0 (96) | rElec rPois, no rF/rC | +10 longbow, quicksilver dragon scales | 17 / 14 | 35/176 on Vaults:5 (its only low-HP note) | 6,207 turns, never low |
| W4 | [20240124-012829](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20240124-012829.txt) | 0.31 DjHu^Oka | 43,509 | 31/40/0 (71) | rF+++ rC+ rPois rCorr, no rElec | +27 heavy crossbow "Sniper", swamp dragon scales | 4 / 8 | 13/175 on Depths:2; 31/200 on Zot:2 | 1 teleport read, 2 heal wounds |
| W5 | [20240202-063259](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20240202-063259.txt) | 0.31 DgHu (no god) | 42,872 | 15/83/5 (103) | rC+ only | arbalest "Damnation", leather armour, two +6 rings of dexterity | 8 / 21 | 32/174 on Depths:2; 48/198 on Zot:1 | 7 teleport reads and 7 heal wounds (stack 14→9) |
| W6 | [20230520-020802](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20230520-020802.txt) | 0.30 GrFi^Oka | 62,467 | 73/22/27 (122) | rF+ rC+ rElec rPois | +9 vampiric war axe, +11 gold dragon scales, tower shield | 5 / 22 | 7/88 on Lair:5; 34/171 on Zot:2 | 1 teleport read, 3 heal wounds |
| W7 | [20160531-015616](https://crawl.akrasiac.org/rawdata/qw/morgue-qw-20160531-015616.txt) | 0.19-a MiBe^Trog | 61,551 | 53/27/0 (80) | rF+ rC+ rElec rPois | +9 vampiric battleaxe, +5 plate, no shield; also wands of teleportation and heal wounds (0.19 items) | 3 / 19 | 27/273 on Zot:5 (Orb Guardian) | No teleport, no heal wounds. 17 rages |
| W8 | [20160603-140931](https://crawl.akrasiac.org/rawdata/qw/morgue-qw-20160603-140931.txt) | 0.19-a MiBe^Trog | 71,178 | 34/33/28 (95) | rF+ rC+ only | +8 broad axe of speed, +5 plate, large shield | 0 / 0 | 2/146 on Snake:2 (Aizul); 18/271 on Zot:4 | 3 teleport reads and 3 heal wounds, using up both |

The CAO morgues (W7, W8) are served gzip-compressed under a `.txt` name.

**Losses**

| # | Morgue | Version, combo | Turns | AC/EV/SH (sum) | Resists at end | Kit | Left at end: HW / tele | Death | Status at death, last turns |
|---|---|---|---|---|---|---|---|---|---|
| L1 | [20220904-102411](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220904-102411.txt) | 0.29 MiBe^Trog | 61,447 | 48/21/28 (97) | rF++ rC+ rN+ rPois rCorr, no rElec | +14 obsidian axe, +16 plate of the Crypt, tower shield | 0 / 12 | Zot:5, orb of fire | About to teleport, berserk cooldown, slowed. Read 4 teleports and drank 8 heal wounds in its last 52 turns; died 8 turns after the last read |
| L2 | [20220906-054518](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220906-054518.txt) | 0.29 MiBe^Trog | 68,482 | 37/18/28 (83) | rF+ rC+ rN+ rElec rPois | +4 broad axe, gold dragon scales, tower shield | 0 / 0 | Zot:2, white draconian | Berserk cooldown. Banished from Zot:2 to the Abyss, returned, died 21 turns later with no healing or teleport left |
| L3 | [20220907-003446](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220907-003446.txt) | 0.29 MiBe^Trog | 59,324 | 42/12/26 (80) | rF+++ rC+ rN+ rElec rPois rCorr | +5 broad axe, +8 plate, tower shield | 13 / 9 | Zot:1, red draconian scorcher, 33 turns after entering Zot | Raged, then slowed; read teleport; "You feel the Orb delaying your translocation!"; died the same turn holding 13 heal wounds |
| L4 | [20220912-210912](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220912-210912.txt) | 0.29 MiBe^Trog | 61,750 | 24/18/36 (78) | rF+++ rC++ rElec rPois | +9 vampiric broad axe, chain mail, +8 tower shield | 0 / 5 | Zot:5, Orb Guardian | About to teleport, berserk cooldown, slowed. At 3/242 HP, drank its last 7 heal wounds over 7 turns, then read 2 more teleports and died 1 turn after the last |
| L5 | [20220908-193156](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220908-193156.txt) | 0.29 MiBe^Trog | 62,317 | 58/13/29 (100) | rF+ rC+ rPois, no rElec | +8 broad axe, +11 gold dragon scales, tower shield | 2 / 12 | Zot:1, yellow draconian knight | About to teleport, berserk cooldown, slowed. Stairdanced from Zot:2, read teleport, drank 3 heal wounds, died 4 turns after the read |
| L6 | [20240119-223626](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20240119-223626.txt) | 0.31 GrHu^Oka | 46,735 | 52/2/0 (54) | rF+ rC++ rN+ rElec rPois | +6 arbalest "Damnation", ring mail | 1 / 20 | Zot:5, green draconian monk | Paralysed by a dread lich, about to teleport, slowed. Read teleport, drank 6 heal wounds, died 9 turns later |
| L7 | [20240202-191055](https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20240202-191055.txt) | 0.31 SpHu^Oka | 41,633 | 9/66/0 (75) | rF+++ rC+++ rN+ rElec rPois rCorr | +8 hand cannon, troll leather armour | 5 / 5 | Zot:1, black draconian, 100 turns after entering Zot | About to teleport. Retreated for at least 18 turns, read teleport, drank 3 heal wounds, died 5 turns later |

What these 15 morgues show [V for each fact; the reading is I]:

- 6 of the 7 losses died with a teleport pending. The seventh (L2) had no teleport left.
- All 5 MiBe losses died on berserk cooldown, and 4 of them slowed: the same rage-then-slowed
  death as ours.
- Draconians killed 5 of the 7 losses. An orb of fire and an Orb Guardian killed the other two,
  both on Zot:5.
- The winners' worst moments in Zot (45/273, 31/200, 48/198, 34/171, 27/273, 18/271) were often
  milder than their worst moments earlier (2/32, 7/88, 13/175, 2/146).
  - W2, W3 and W7 never read a teleport in Zot. In the 19 CDI wins, 6 never read one there.

### All 96 CDI Zot deaths with three runes against the 19 CDI wins [V]

From `zotbatch.py` over the morgues in `public/morgues/cdi-all/` (3 quit games dropped).

| | 19 wins | 96 Zot deaths |
|---|---|---|
| AC+EV+SH at end, median (range) | 96 (60–122) | 97.5 (24–134) |
| Heal wounds drunk in Zot, mean / median | 3.3 / 3 | 2.8 / 1 |
| Turns in Zot, mean | 6,751 | 3,158 |
| Teleports read in Zot, mean | 1.7 | 2.3 |
| Read a teleport in the last 15 turns | – | 79 (median 2 turns before death, at most 14) |
| "About to teleport" at death | – | 81 |
| "Orb delaying your translocation" in the final message block | – | 45 |
| Died holding heal wounds / holding teleportation | – | 49 / 92 |
| rElec at end | 15 | 79 |
| Died on Zot:1 / 2 / 3 / 4 / 5 | – | 28 / 16 / 14 / 15 / 23 |

Pooled across combos, the defences are the same. GrFi, with high AC, is 47 of the 96 deaths and
only 3 of the 19 wins. Within a combo, the median win is higher [V]:

| Combo | Wins: AC+EV+SH | Zot deaths: median (max) | Deaths at or above the best win |
|---|---|---|---|
| MiBe (CDI 0.29) | 104 | 85.5 (106) of 16 | 1 |
| GrFi (CDI) | 103, 114, 122 | 108 (134) of 47 | 6 |
| GrHu (CDI) | 81–101, median 94 | 81 (101) of 11 | 1 |
| MiBe (CAO, from xlog) | median 96.5 of 4 | 70 of 3 | |
| DDFi (CAO) | median 82 of 23 | 79 of 31 | |
| GrBe (CAO) | median 97.5 of 14 | 84 of 5 | |
| CAO, all combos | median 96 of 120 | 82 of 99 | |

In CAO, the medians favour the wins in 8 of the 10 combos with 4+ such games. The exceptions are
MfBe and VpFi.

### Our claims against the public record

| Our claim | Verdict | Evidence |
|---|---|---|
| Zot is where three-rune qw games die | **Supported** for games aimed at a three-rune win | CDI bot logs: 91 of the 118 three-rune deaths were in Zot; the rest were in Tomb, Slime and Depths on longer goal lists. MiBe 0.29: 16 of 16 in Zot. CAO: 99 of 189, plus 47 in Ziggurats, where qw's goals went past three runes. [V] |
| Reaching Zot is the real filter, about 1 in 12 then wins | **Supported** for current qw | CDI: 19 of 219 (8.7%); MiBe 0.29: 1 of 17. Old qw converted far more: in CAO 0.19-a, 80 of 163 three-rune games won, MiBe 4 of 6. [V] |
| Winners have more defence (AC+EV+SH) | **Partly supported** | Within a combo the median win is higher in 13 of 15 combos. Pooled on CDI there is no difference (96 against 97.5). Our "every Zot death ≤ 100" does not hold as a rule: a public MiBe death had 106, above its win's 104. These are end values, and drain and corrosion lower the deaths'. [V] |
| Winners drink more heal wounds in Zot | **Not supported as a cause** | CDI wins drank more in total (3.3 against 2.8), but over twice as many Zot turns. 5 of the 19 wins drank none. 49 of 96 deaths still held heal wounds. W1 (MiBe) did bridge each teleport with heal wounds, like our 600058. [V] |
| The Zot teleport delay defeats qw's escape | **Supported** | 81 of 96 CDI Zot deaths were "about to teleport", and 79 had read a teleport within 15 turns (median 2). The delay message appears in 0.29 on Zot:1 without the Orb (L3), so the rule is not new in 0.34. 92 of 96 died holding teleport scrolls. [V] Whether CAO 0.19-a had the delay cannot be told from these morgues. |
| Early luck matters most | **Cannot tell** | Every public game has its own seed (all 62,571 CDI games that record a seed have distinct ones), so the seed's share cannot be measured. What is visible: early deaths dominate (MiBe 0.29: 26% die on D:1–5 to gnolls, Sigmund and orc wizards, as in ours). [V for the counts] |
| qw dies in or just after a rage | **Supported** for MiBe | All 5 public MiBe losses read died on berserk cooldown, 4 slowed. CDI Zot deaths overall: 34 of 96 slowed, 21 on berserk cooldown. Most are Okawaru games, which cannot rage. [V] |

### Sources that failed or were not used

- **dcss-stats.com** returned 429 (the earlier fetch) and its API returned nothing. Its per-player
  breakdowns are not used.
- **crawl.develz.org/scoring/players/qw.html**: 404.
- **CSZO** (crawl.s-z.org, 2013–15): unreachable, so its games are not counted. Only its 26 wins
  are known, from the CAO scoring page. qw's CSZO win rate is unknown.
- **The `qwqw` morgues** that `accomplishments.md` lists for 0.29 returned 404. qwqw's 0.29 games
  on CDI are not in the logfiles we read (one qwqw line in all of them).
- **Sequell** is IRC-only and was not queried. Its numbers may differ in which servers and
  accounts it counts.
- **The CAO milestones** (several GB for trunk) were not fetched, so CAO has no Zot-entry count.
- **Devteam posts and the Tavern** were not searched. No tournament page lists qw.
- **Not checked**: the other servers (CXC, CUE, CBRO). The accomplishments page says online wins
  are tracked under `qw`, and all 153 scoring-page wins are on CSZO, CAO or CDI.

## Sources and what is missing

- **Our games.**
  - `runs/qw/*/games/*/{logfile.txt,morgue.txt}`: 23,545 games, of which 4,210 are forks.
  - Container `dcss-multi-agent-dcss-1:/data/qw/runs`: 19,740 xlog lines, all already in the host
    copy.
  - The scripts and derived JSON are in `/Users/earchibald/.claude/jobs/1cdb9134/tmp/qw-wins/`
    (`agg.py`, `morgues.py`, `cohort.py`, `stages.py`, `cond.py`, `luck.py`, `deaths.py`,
    `zotstock.py`, `tele.py`, `uniques.py`).
- **Morgues read in full or in their key sections**: the 3 wins, the 2 same-seed 100443 losses,
  and the Orb-holding deaths `runs/qw/held6-a-base/games/600069/morgue.txt` and
  `runs/qw/zr1-fix/games/100056/morgue.txt`. The other 31 Zot deaths were read through their notes
  only.
- **qw source**: `runs/qw/src` (8698adc; GitHub crawl/qw master has nothing newer), our patches in
  `tools/qw/patches.py`, and the deployed `runs/qw/build-zk/qw.lua`. `/data/qw/lib` is now the zk
  build (same md5 as lib-zk), not fix1 as docs/qw-teacher.md says.
- **DCSS 0.34 source** (container `/crawl`): `spl-transloc.cc`:930–962 and `orb.cc`:83.
- **Public games** (section 7):
  - Logfiles and milestones from crawl.akrasiac.org and crawl.dcss.io (links in section 7).
  - The morgue trees `crawl.akrasiac.org/rawdata/qw/` and `crawl.dcss.io/crawl/morgue/qw/`.
  - The copies are in `/Users/earchibald/.claude/jobs/1cdb9134/tmp/qw-wins/public/`
    (`dl/`, `morgues/`). An earlier fetch is in `.../qw-wins/web/`; it has the same CAO and CDI
    counts.
- **Not established**:
  - qw's win rate on CSZO (2013–15, unreachable); only its 26 wins are known.
  - Zot-entry counts for CAO (milestones not fetched).
  - Sequell's own figures (not queried) and dcss-stats.com (429).
  - Whether qw's 0.19-era Zot had the teleport delay.
  - How much of the outcome the seed decides in public games: every public game has its own seed.
- **Caveats**:
  - n = 3 wins on 2 seeds. Every win-against-loss difference in section 2 is suggestive, not
    significant.
  - The stage snapshots take the kit from qw's own WEARING and WIELDING notes. Armour taken off
    without a note is missed.
  - The defences at death are values at death.
