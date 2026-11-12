# What the knowledge bots and LearnDB say, and where it lands in the brain and in qw

Read 2026-11-12: the Knowledge Bots page in the sidebar of crawl.develz.org, the bots guide it links to,
and the LearnDB, checked against the 0.34.0 source in the `dcss-multi-agent-dcss-1` container. This page
keeps what bears on the trained brain (`docs/trained-brain.md`: a Minotaur Berserker of Trog that dies
around D:5–6) and on the qw teacher (`docs/qw-teacher.md`: same character, stops in the first rune
branches at XL 15–18, mostly through poison and slowness during and after berserk). As in
`docs/wiki-strategy.md`, each finding is sorted by what it would take to use it.

Marks: **(src)** read in the 0.34.0 source or changelog; **(ldb)** LearnDB only; **(both)** LearnDB
says it and the source agrees; **(inferred)** my reading, not checked against games.

## Sources

| source | what it is | maintained by | version it reflects | how to query | offline / programmatic, without IRC |
| --- | --- | --- | --- | --- | --- |
| [Knowledge Bots](https://crawl.develz.org/wordpress/bots) (sidebar) | one line: "Information about monsters, uniques, items and more" with a link to `crawl.develz.org/info/` | the crawl.develz.org site | none | the link returned **404** on 2026-11-12; the page has nothing else | no: the web interface is gone |
| [Guide to the DCSS knowledge Bots](https://github.com/crawl/crawl/wiki/Guide-to-the-DCSS-knowledge-Bots) | how to use the bots below | crawl GitHub wiki, last edited 2025-10-30 (11 revisions) | current | read it | yes, it's a web page |
| **Sequell: LearnDB** | user-written knowledge base: 4,975 topics, 11,863 entries in the copy read. Anyone can edit from Libera `#crawl` or `#crawl-sequell` | the community | **none as a whole.** Entries carry their own "since 0.xx" notes; 115 mention 0.33–0.35, others describe 0.14 or older | `??topic`, `??topic[n]`, `??topic[text]`, `?/text` (search), on IRC or through a relay bot | **yes, as a dump.** The one-page copy, `loom.shalott.org/learndb.html`, does **not resolve** (NXDOMAIN, 2026-11-12). The Internet Archive holds full copies up to 2025-11-10 (`web.archive.org/web/20251110005923id_/https://loom.shalott.org/learndb.html`, "Updated on Mon, 10 Nov 2025"); the 2026-05-27 capture is 3 KB, not the dump. It parses with two regexes: `<dt>` opens a topic, each `<li>` is an entry |
| **Sequell: game tracking** | `!lg` (finished games), `!lm` (milestones), `!won`, `!stats MiBe` (starting stats), `!apt Mi`, `-log` (morgue), `-tv` (FooTV replay), `&dump` | Sequell's operators | all versions played online | IRC, or the relays | **not checked.** Per-player HTML pages exist at `crawl.akrasiac.org/scoring/players/<name>.html`. This is the route for "learn from human play"; nothing here uses it yet |
| **Gretell** | monster lookup: `@?name` (stable), `@??name` (trunk), `@0.N?name` (back to 0.19), with DES `MONS` modifiers (`@??orc ; spells:...`) | Gretell's operators | the version asked for | IRC, or the relays | **yes, from source.** The lookup is crawl's own `util/monster` program (`util/monster/monster-main.cc`, Makefile target `monster`), present in the container's `/crawl`. Not built here (that would change the container). `tools/knowledge/monsters.py` reads the same data files: see section 6 |
| **NotCheibriados** | `%git <ref>`, `!gitgrep` | its operators | trunk | IRC | yes: `git log` of crawl |
| relays: **beem** (WebTiles chat, `!subscribe`), **Cerebot** (Roguelikes Discord), **LomLobot** (Twitch) | pass commands to the IRC bots | their operators | as above | chat | no |
| crawl 0.34.0 source and docs, container `/crawl` and `/docs` | `mon-data.h` (generated from `dat/mons/*.yaml`), `mon-spell.h`, `mon-pick-data.h`, `dat/des/builder/uniques.des`, `melee-attack.cc`, `player.cc`, `changelog.txt` | the devteam | **0.34.0** (2026-02-05) | read-only `docker exec cat` | yes; this is what everything below was checked against |

The game here is 0.34. The LearnDB copy is three months older than 0.34.0's release but was already
being written for 0.34 trunk (entries for clockroach, chonchon and the 0.34 bone dragon are in it). I did
not join IRC or query any bot. The guide's own advice is to look in game first: `x`+`v` on a monster,
`?/` for anything.

## 1. Rules the brain or qw can follow today

These use inputs and actions that exist (`Pois`, `Slow`, `Berserk`, `-Berserk` in `STATUSES`,
`poison_survival`, `quaff_heal`, `rest`, `wait`, `berserk`), or one line in qw's patches.

1. **When a rage ends, current HP is multiplied by 2/3.** (src: `player_end_berserk` calls
   `calc_hp(true)`, which rescales HP to the new maximum.) Remaining poison is not scaled. So poison that
   is survivable during the rage becomes lethal at its end once it exceeds 2/3 of the HP shown, and the
   next action is taken slowed. While berserk, poison is lethal-after-the-rage once
   `poison_survival <= hp / 3`, not `<= 0`. This is the mechanism behind qw's "the poison turns lethal
   mid-rage ... dies as the rage ends", and LearnDB lists "You are too berserk!" under
   *famous last messages*. Poison already present when the rage starts is the smaller worry: it drains
   a fifth of itself every turn, so most of it ticks off inside a 10–19 turn rage, against HP that the
   rage's end then scales by 2/3 as well (inferred from the two rules). What kills is poison that lands
   during the rage, which matches qw's "six of the eight poison deaths left are poison landing during
   the rage". So the checks that matter are: before raging, are poisoners in view (the table's `poison`
   tag, section 2) and is there curing; during the rage, poison against 2/3 of HP; and the first action
   after a rage, with `Pois`, is curing.
2. **Nothing can be drunk, read or invoked in a rage; only move, doors, attack, (un)wield, drop, pick
   up.** (both) Already in `available` (`calm`) and in `wiki-strategy.md`.
3. **Each non-attacking action in a rage costs 1, then 2, then 3... more turns of rage; any attack
   resets the count.** (both: `_do_berserk_no_combat_penalty` in `main.cc`, reset in
   `player_attempted_attack`.) Four steps or waits in a row take 14 turns off a rage that lasts 10–19
   (10 extra, plus the 4 that pass anyway). Berserk only with the target adjacent or one step away;
   never berserk and then walk (`flee_up`, `descend`, `wait` while `Berserk` all spend the rage).
4. **After the rage: slowed 12+2d12 turns (14–36), no new rage for twice that.** (src; agrees with
   `wiki-strategy.md`.) LearnDB: "Don't wander around slowed or exhausted." Rule: while `Slow` and no
   hostiles, `rest`/`wait`, not `explore` or `descend`.
5. **Don't berserk at anything that blinks; berserk early, not as a reaction; lead the fight to a safe
   spot first so it doesn't draw more.** (ldb, berserk[2], [3]) Matches `wiki-strategy.md` sections 2
   and 3. The "blinks" half needs the monster flag (section 2).
6. **Curing and heal wounds are different potions.** (src) Curing heals 5–11 and ends poison and
   confusion, not slowness. Heal wounds heals 10+random2avg(28,3) (10–37, about 23) and cures nothing.
   `features.HEALING` counts both as `heal`, so `quaff_heal` may drink heal wounds while lethally
   poisoned. With `Pois` or `Conf`, drink curing; with neither, heal wounds first.
7. **rPois stops 2 of 3 poisonings outright and does nothing to the third.** (src: `poison_player`; the
   same 2/3 guards curare and the slow/paralysis riders.) LearnDB's *strong poison* entry ("rPois merely
   reduces it to medium poison") is outdated. Poison per landed bite, from `mons_do_poison`, applied on
   1 hit in 3: normal HD×2 to HD×4, strong HD×11/3 to HD×13/2. That is 4–8 for an adder, 14–28 for a
   black mamba, 33–58 for a redback, 36–65 for a sea snake, 28–56 for an emperor scorpion. Poison
   then drains 1/5 of what is left every 10 aut (`poison_denom`), so a slowed character takes more of
   it per action.
8. **Only hostiles directly adjacent follow you on stairs, and only if they are hunting you and not
   still recovering from their last action. Summons never do.** (src: `_mons_can_follow_player_from`,
   `mons_can_use_stairs`.) This agrees with `wiki-strategy.md`; LearnDB's *stairs* entry (a flood fill
   that takes every chained monster) describes older code. Two 0.34 changes the wiki pages predate
   (src, changelog): monsters left behind now **gather round the last staircase you took**, and after
   you take any stairs, monsters on the new floor that you haven't seen before skip their first turn.
   Going up to rest and coming back down meets the pack at the bottom of the stairs; that may be part
   of why `flee_up` lost under `wiki=1` (inferred).
9. **Luring:** wake one monster and back off to the upstairs to fight it there. (ldb) This is
   `wiki-strategy.md`'s "fight on the stairs up" again; it needs `to_stairs_up` (section 2 there).
10. **Ogres swing slowly** (attack energy 15: 1.5 turns per swing; also two-headed ogre and Sigmund).
    (src) LearnDB: "if you step away after it swings, you might create a gap." Needs a step action.

## 2. Advice that needs a new input or action

### A monster table by name (built: `docs/data/monsters-0.34.json`)

`features.encode` hashes a monster's name into 24 buckets and adds the game's threat colour. The game's
own data says much more, and a lookup by name gives it to the brain with no learning: speed, attack
flavours and spells reduce to a handful of flags that each call for a different answer. Section 6 has
the table's fields; the `tags` field already reduces each monster to these words:

| tag | from (0.34) | the answer |
| --- | --- | --- |
| `fast` | speed above 10 | can't be outrun; step away or fight, never `wait` one square off |
| `poison` | poison attack flavours, poison/venom spells | cure before raging; count it against 2/3 HP in a rage |
| `slows` | speed drain, poison-paralyse, Slow spell, Concentrate Venom (curare), torpor snail aura | the rune-branch killer (section 3) |
| `paralyses`, `confuses`, `mesmerises`, `forces berserk` | flavour or spell | kill first or leave |
| `blinks` | blink flavours or spells | don't berserk at it |
| `smites`, ranged spells (`spells` list) | spellbook | close in or break line of sight |
| `slow attacks` | attack energy above 10 | step back after a swing |
| `summons`, `hastes`, `unique` | spellbook, flags | read it, then decide |

**The threat colour is a function of XP value and your level, nothing else.** (src: `mons_threat_level`)
tension = the monster's XP value (scaled a little by its HP roll) / (1 + sqrt(XP needed for your
level / 30)); trivial ≤ 1, easy ≤ 5, tough ≤ 32, nasty above. LearnDB's *threat level* entry gives the
same formula with "≤ 0" for trivial; 0.34's changelog says that threshold went up. Poison, speed,
ranged attacks and slowing count only as far as they raised the XP value. Worked out for a Minotaur
(XP aptitude −1) from the table's `exp`, ignoring the HP roll:

| monster | XP | XL 3 | XL 5 | XL 7 | XL 9 | XL 12 | XL 15 | XL 18 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| adder | 13 | easy | easy | easy | trivial | trivial | trivial | trivial |
| orc wizard, Natasha | 35 | tough | tough | easy | easy | trivial | trivial | trivial |
| orc priest | 42 | tough | tough | tough | easy | trivial | trivial | trivial |
| ogre | 119 | nasty | nasty | tough | tough | easy | trivial | trivial |
| Sigmund | 229 | nasty | nasty | nasty | tough | tough | easy | easy |
| redback | 181 | nasty | nasty | tough | tough | tough | easy | trivial |
| black mamba, guardian serpent | 456 | nasty | nasty | nasty | nasty | tough | tough | easy |
| wolf spider | 564 | nasty | nasty | nasty | nasty | tough | tough | easy |
| naga ritualist, bog body, sea snake | 684–739 | nasty | nasty | nasty | nasty | tough | tough | tough |

So the colour says little where the brain dies (at XL 3–7 Sigmund and an ogre read "nasty", Natasha
and an orc priest "tough", an adder "easy", whatever each one does) and plays down the Spider Nest's
commonest monster where qw dies (a redback is "easy" at XL 15). Both are arguments for the flags above
over more training on `threat`.

### Other inputs

- **Poison amount, and HP as it will be after a rage.** `poison_survival` is there; while `Berserk`,
  the number that matters is `poison_survival - hp/3`: at or below zero, the poison is lethal once the
  rage ends (section 1, item 1).
- **Which healing potion.** Split `heal` into `curing` and `heal_wounds` (section 1, item 6). Changing
  `inventory` and `encode` bumps `FEATURE_VERSION`.
- **Turns of rage left.** Not shown; the penalty rule (section 1, item 3) makes it computable from the
  turn the rage began and the actions since.
- **Forced rage.** A moth of wrath's bite (Spider) sends you berserk on 1 hit in 3 (src: `AF_RAGE`),
  so potions stop working without the bot choosing it. Clarity prevents it (both: `can_go_berserk`
  refuses an unintentional rage under clarity), and so does berserk cooldown.

## 3. The four rune branches, for qw

From `mon-pick-data.h` (random generation only; bands and vaults add more). Weight is relative within
a branch. qw's 29 rune-branch deaths: Spider 13, Snake 10, Shoals 4, Swamp 2.

**Spider Nest (4 floors, from Lair:2–3).** 18 of its 21 monsters are faster than you (speed 12–20);
the four commonest are speed 15. During a rage you are hasted; after it you are slowed for 14–36 turns,
and a speed-15 monster then acts about 2.25 times per action of yours (inferred from the speeds).
Poison: redback (the commonest, strong poison, 33–58 a bite), wolf spider, emperor scorpion, meliai.
Slowing: jorogumo (poison-paralyse: each hit poisons 1 time in 3, and also slows for 1–3 turns 5 times
in 6 or paralyses for 1–3 turns 1 time in 6, each resisted 2 in 3 by rPois), the torpor snail's aura
(slowed while near it), and the moth of wrath's forced rage, which ends in the same slowness.
Confusion: tarantella (1 hit in 3, not stopped by rPois; both). LearnDB: "Expect them to hit hard and
move much faster than you; running is not an option if you're normal speed ... Bring plenty of potions
of curing regardless, for redback poison and tarantella confusion"; "rPois is not nearly as important
here as in Snake, but it still helps." qw dies here more than in Snake, so the second sentence is
doubtful for this character (inferred).

**Snake Pit.** Black mamba (commonest, speed 18, 14–28 poison), nagas of every kind (spit poison; slow
movers but speed-10 attackers), anaconda (18), shock serpent and mana viper (15, 14). Slowing: naga
mages cast Concentrate Venom, which turns their allies' poison bites and spit into curare (src:
poison, 2d6 damage and 10–16 turns of slow; rPois resists 2 in 3); guardian serpents cast Slow and
blink allies round you. Naga ritualists: Virulence, which LearnDB says multiplies current poison and
can't be resisted (not checked in source). Nagarajas cast Dimension Anchor (stops blinking and
teleporting; ldb). Vashnia (Snake:2-) casts Blink Other at you. LearnDB: rPois matters most here.

**Swamp** (shares a game with Shoals, 50/50). The 0.26 rework stands in 0.34: hydra, goliath frog, tyrant
leech, bog body (casts Slow and Bolt of Cold, weight 1000), bunyip (speed 15, three 40-damage bites,
long recovery), eleionoma, spriggan riders and druids, swamp dragons (poison clouds), swamp drakes
(noxious clouds: confusion; LearnDB: clarity helps), fenstrider witch (Paralyse). The hornet's
poison-paralyse (5 in 6 slow, 1 in 6 paralysis) comes out of shambling mangroves (ldb). LearnDB's
resists for Swamp: rPois, rElec; clarity. LearnDB's main *swamp* entry still names the pre-0.26 set.

**Shoals.** Sea snakes (speed 12, strong poison 36–65), harpies (speed 25, packs), merfolk impalers
(attack energy 6: quick hits), aquamancers, sirens (mesmerise), snapping turtles (reach), formless
jellyfish (paralysis). No monster in its random list carries a `slows` tag, unlike the other three
(src); its deaths in qw are 4 of 29. LearnDB: wait out a kraken until low tide.

What follows for qw's Next 3 (no berserk in a poison cloud or without rPois in Spider, Snake and Swamp):
the source adds that rPois only cuts poisonings to a third, so "has rPois" does not make a rage safe in
Spider; the count of `fast` + `poison` + `slows` monsters in view is the more direct test (inferred).

## 4. Uniques the brain meets (D:2–10)

Placement from `uniques.des` (0.34); what they do from the spellbooks; one line of LearnDB where it adds
something. Uniques are never placed on D:1.

| unique | where | what to expect |
| --- | --- | --- |
| Jessica | D:2–3 | Pain, Slow, Haste, Blink. LearnDB: "a pushover or worse than Sigmund" |
| Terence | D:2–3 | plain fighter; dangerous only with a wand (ldb) |
| Natasha | D:2–4 | Magic Dart, Slow, Call Imp; comes back after death, weaker each time (ldb) |
| Robin | D:2–4 | hobgoblin pack, Battlecry, throws allies at you |
| Sigmund | D:2–6 | Magic Dart, Throw Flame, Confuse, Invisibility; slow swings. LearnDB: "notoriously lethal" |
| Crazy Yiuf | D:2–7 (his cottage) | quarterstaff of chaos; can hit for about 35, paralyse or banish (ldb) |
| Grinder | D:3–6 | Pain, Paralyse, Blink. LearnDB: beats Sigmund for kills |
| Ijyb | D:3–5 | guaranteed a wand, possibly a strong one (ldb) |
| Pargi | D:3–4 | troll, three attacks |
| Duvessa + Dowan | D:4–7 | Duvessa rages for good once Dowan dies; Dowan hastes when she dies (ldb) |
| Edmund, Eustachio, Menkaure | D:4–6/7 | Eustachio summons and blinks; Menkaure: Pain, Haste, Symbol of Torment |
| Pikel | D:4–9 | with four lemures (ldb) |
| Blorkula the orcula | D:5–8 | vampire orc with Haste and five bolts; revives from bats (ldb). LearnDB's *Blork* is gone |
| Prince Ribbit | D:5–9 | blink frog, speed 14 |
| Maggie | D:6–10 | Bolt of Fire, Mesmerise |
| Jeremiah | D:6–9 | Blink Range, Smiting; new in 0.31 |
| Joseph | D:7–10 | sling and pain bullets (ldb) |
| Sprozz | D:7–11 | clockwork bee; new |
| Amaemon | D:8–11, Lair:1–3 | summons scorpions and makes their stings curare (slow) |
| Erica | D:8–11, Orc, Lair | Venom Bolt, Slow |
| Gastronok | D:8–12, Orc, Lair | Slow, Airstrike; HD 20, speed 5 |
| Cassandra | D:9–14, Lair:1 | doom; on death seals the level's stairs for up to 30 turns (ldb) |

## 5. Where the sources disagree

| claim | LearnDB | `wiki-strategy.md` | 0.34 source | so |
| --- | --- | --- | --- | --- |
| orc wizard spells | three sets, two with Slow and Haste | — | one book: Magic Dart, Throw Flame, Confuse, Invisibility | orc wizards no longer slow or haste |
| strong poison against rPois | reduced to medium | — | blocked 2 times in 3, otherwise full | LearnDB outdated |
| who follows on stairs | a chain of followers | only the adjacent | only adjacent hostiles that are hunting you; summons never | wiki right; and 0.34 left-behinds gather at the stairs |
| hornet | "briefly paralyzes" | — | 1 in 6 paralysis, 5 in 6 slow, plus poison | mostly slow |
| trivial threat | ≤ 0 | — | ≤ 1 | changelog confirms the change |
| paralysing early monsters | — | "Grinder, floating eyes" | floating eyes have no spawn entry and no vault in `dat/des` | none met at random in 0.34 |
| throwing stones | — | "a stone pulls one monster out of a group" | changelog: "Stones are now much less common" | weaker plan in 0.34 |
| orc priests | — | "from D:3" | random spawn D:4–12; also in orc bands led by a plain orc, band minimum depth 2 | from D:2 in a band (depth meaning of the band entry inferred) |
| rage length | 100–195 aut | 10–19 turns | (20 + random2avg(19,2)) / 2 turns: 10–19 | wiki right |
| uniques list | "In 0.28", includes Maud and Blork | — | Maud removed; Blork is now Blorkula; the list lacks Cassandra, Jeremiah, Sprozz, Amaemon and Lodul (some have entries of their own) | use `uniques.des` |
| Swamp monsters | swamp drakes, hydras, swamp dragons | — | section 3 | entry predates the 0.26 rework (the entry says so) |

LearnDB and `wiki-strategy.md` also agree on these. Checked in source: heal wounds (LearnDB 10–37, wiki
"about 25"), curing 5–11, Lair at D:8–11 five deep, Orc at D:9–12 two deep, S branches from Lair:2–3
four deep. Not checked: teleport delay 2+d3 × 10 aut (both say 3–5 turns), Trog's piety decay (1/17
every 20 turns = 1 per 340), Trog's Hand giving regeneration and Will.

One thing in our code to check against the source: `features.BRANCH_BASE` puts Lair:1 at 10 and
Orc:1 at 11, while the game rates both as the same depth (`absdepth` 10 for both; rune branches 15,
which `DEEP_BRANCH` matches). Harmless for a progress measure; worth knowing if depth is ever used as
difficulty.

## 6. The monster table

`uv run python tools/knowledge/monsters.py` (or `--src <crawl-ref/source>`) reads the 0.34 files from
the container with `docker exec ... cat` and writes `docs/data/monsters-0.34.json`: 671 monsters,
one per line. Fields: `name`, `enum`, `glyph`, `colour`, `hd`, `hp` (average), `ac`, `ev`, `will`,
`speed`, `energy` (only costs that differ from 10; lower is faster), `attacks` (type, flavour, max
damage before weapons), `resists`, `flags` (unique, see invisible, flies, fast regeneration...),
`holiness`, `intel`, `habitat`, `size`, `uses`, `god`, `exp` (the XP value the threat colour uses),
`tags` (section 2), `spells` (name, frequency, kind), `spawns` (branch, depth range, weight, shape) and,
for uniques, `placed` (the `DEPTH` lines of `uniques.des`).

Spot-checked by eye against `mon-data.h`, `mon-spell.h`, `mon-pick-data.h` and `uniques.des`: orc
priest, adder, black mamba, redback, hydra, ogre, Sigmund, jackal. Every field compared (HD, HP, AC,
EV, Will, speed, energy, attacks, resists, spellbook, spawn ranges, placement) matched.

Not in it: bands (an orc priest with its orcs), vault-placed monsters, equipment (`mon-gear.cc`: a
centaur's bow, Sonja's curare), resistances that come from holiness (the `rPois` tag adds undead,
nonliving and demonic), hydra heads, and effects that live in code rather than data apart from the
torpor snail's aura. A `from` below 1 in `spawns` widens the weighting; it doesn't place a monster above
the branch's first floor.

## 7. Not used, and not verified

- **Not verified in source** (LearnDB only): Virulence irresistible; Cassandra's stair sealing; Crazy
  Yiuf's damage; Ijyb's wand; bloated husk 8d8 explosion; Lernaean hydra in a quarter of Swamp endings
  (the monster is in `swamp.des`, the rate is not checked); orc wizards' venom daggers; random spawns
  arriving through the stairs you stand on. Everything else marked (ldb) above.
- **The live LearnDB.** Only the archived copy of 2025-11-10 was read; entries changed since then,
  including any written for the 0.34.0 release, are not here.
- **Not queried:** any bot, the Sequell game logs (`!lg`/`!lm`), Gretell's formatted output. The
  game-log route is the one worth a separate look for learning from human play (MiBe games, deaths by
  place); it needs IRC, a relay, or the servers' logfiles, none of which was tried.
- **Most of LearnDB:** jokes, IRC quotes, player and server lore, and many entries for spells, gods and
  items this character never uses. Read here: berserk, Trog and his abilities, poison and curing,
  rPois, slow, stairs, luring, threat level, the early uniques, and the monsters of D:1–10, Lair, Orc
  and the four rune branches.
