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

**Public record.** The agent fetching qw's public games and Sequell-style stats had not reported
when this was written, so public win rates, by version and combo, are **not established here**.
What is verified comes only from the qw clone's own `docs/accomplishments.md`:

- It lists online wins for about 60 combos, including **MiBe^Trog** and many Fighters of Okawaru.
- It says "Historically qw's best 3-rune winrate was 15% with DDFi^Makhleb".
- It links winning morgues on crawl.dcss.io, for example the 0.29 MiBe win
  `https://crawl.dcss.io/crawl/morgue/qw/morgue-qw-20220913-002803.txt`. That morgue was not read
  for this note.

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
- **Not established**:
  - qw's public win rate by version and combo (Sequell, the scoring pages, the crawl.dcss.io morgue
    directories). That research had not reported when this was written.
  - Public winning and losing morgues, which were not read.
- **Caveats**:
  - n = 3 wins on 2 seeds. Every win-against-loss difference in section 2 is suggestive, not
    significant.
  - The stage snapshots take the kit from qw's own WEARING and WIELDING notes. Armour taken off
    without a note is missed.
  - The defences at death are values at death.
