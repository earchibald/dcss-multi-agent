# What the official manual, FAQ and 0.34 source say, checked against the wiki digest

Read 2026-11-12. `docs/wiki-strategy.md` takes its numbers from wiki pages written for 0.30 to 0.34.
This page checks each of them against the official documentation and FAQ, and against the 0.34.0
source the ladder actually plays, before any of them is hard-coded. It also lists what the official
sources say that the wiki digest lacks, sorted the same way as the digest: a rule the brain (or qw)
can follow today, a new action, a new input, or a fact.

Anything I worked out rather than read is marked *(inferred)*.

## Sources

| source | version | what it covers |
| --- | --- | --- |
| [crawl.develz.org/wordpress/documentation](https://crawl.develz.org/wordpress/documentation) | a page of links; the manual, quickstart, options and macro guides it links to are **GitHub `master`** (trunk, after 0.34) | where the official docs live |
| [crawl.develz.org/wordpress/faq](https://crawl.develz.org/wordpress/faq) | **older than 0.34**: "altars on the first nine levels", "in DCSS 0.29 and later... damage rating", bug reports to the old tracker | goal, stairs per level, weapon choice, gods, Abyss |
| `master` `crawl_manual.rst`, `quickstart.md`, `options_guide.txt` (fetched from GitHub, diffed against the 0.34 copies) | trunk | manual differs from 0.34 only in species and backgrounds (Gale Centaurs, Metamorphs); quickstart identical; options add `rest_wait_ignore_mp`, `longwalk_range`, `autofight_stampede`. Nothing below depends on trunk |
| container `/docs/crawl_manual.rst` | 0.34.0 | D: resting, stairs. F: monsters. G: items, enchant limits. J: religion. K: mutations |
| container `/docs/quickstart.md` | 0.34.0 | five tactics for beginners |
| container `/docs/options_guide.txt` | 0.34.0 | rest, explore, interrupt, scroll targeter options |
| container `/docs/changelog.txt` | 0.34.0 (2026-02-05) back to 0.30 | what changed since the wiki pages were written |
| container `/crawl/dat/database/FAQ.txt` | 0.34.0 | the in-game FAQ (`?Q`), the 0.34 version of the website FAQ |
| container `/crawl/dat/descript/items.txt`, `gods.txt` | 0.34.0 | in-game item and god descriptions |
| container `/crawl/*.cc`, `*.h`, `dat/mons/*.yaml`, `dat/des/builder/uniques.des`, `dat/species/minotaur.yaml` | 0.34.0 (`build.h`: `CRAWL_VERSION_LONG "0.34.0"`) | every number below; file and function cited per row. `/crawl` is `crawl-ref/source` |

**The website is not the 0.34 documentation.** Its FAQ is a stale copy (pre-0.34) and its manual links
go to trunk. Where they differ from the container, the container wins. In practice the official prose
has almost no numbers; nearly every number below comes from the 0.34 source.

## Summary

85 claims checked: **65 confirmed** (several with a sharper number), **3 wrong**, **5 changed since
the wiki's version**, **12 not checkable** from these sources. The wrong and changed ones:

- Scroll of poison is **uncommon (4.7%)**, not rare (2.0%). The rare four are brand weapon, silence,
  torment, and whichever of summoning or butterflies the game has.
- The stairs take **one action plus a one-turn delay**, not about 2.5 turns. What decides who follows
  is who is adjacent when `<` is pressed, and still adjacent when the delay ends.
- A slower weapon does not give a normal-speed monster "double turns" above 1.0 delay: at delay *d* it
  gets *d* actions per swing *(inferred from the aut model)*.
- Trog no longer minds pain-branded weapons (0.31): the brand simply does nothing for his worshippers.
- Floating eyes are no longer generated (`cant_spawn`).
- Known scrolls of fear, silence, vulnerability, immolation and torment **open a targeter prompt** in
  0.34, so `scroll:fear` is not `prompt=None` as `brain-consumables.md` had it (corrected there
  2026-11-12 to `prompt="targeter"`).
- Monsters left behind now **gather at the staircase you used** (0.34), so "go up, rest, come back down
  the same stairs" walks into them.
- **Autoexplore already rests to full HP** and waits out Slow and `-Berserk` (0.34 defaults), so "explore
  only at full HP" is built into `explore`; the wiki rule only changes what happens before `descend`
  and fights *(inferred)*.

## 1. Verification table

"WS" is `docs/wiki-strategy.md`, "BC" is `docs/brain-consumables.md`, both by section.

### Berserk and Trog

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| B1 | Nothing can be drunk, read or invoked in a rage | WS 1, 2.4; BC 2 | Potions: "You are too berserk!" (`item-name.cc` `cannot_drink_item_reason`). Scrolls: same (`_general_cannot_read_reason`). Abilities without the `berserk_ok` flag, which no Trog ability has (`ability.cc` table l.525–531, check l.1817). Also wands (`evoke.cc:1000`), throwing (`throw.cc`), wear and remove (`item-use.cc:901, 969`), and **autoexplore** ("Calm down first, please.", `travel.cc` `do_explore_cmd`). Resting is allowed | confirmed |
| B2 | A rage lasts 10–19 turns | WS 3 | `player-act.cc` `player::go_berserk`: `(20 + random2avg(19,2)) / 2` = 10–19. Doubled for a potion with Efficient Metabolism | confirmed |
| B3 | As few as 3 turns if they go on anything but attacking | WS 3 | `main.cc` `_do_berserk_no_combat_penalty`: each action without an attack costs 1, 2, 3... extra turns on top of the normal one (2, 5, 9, 14, 20 cumulative). A 10-turn rage ends after 4 such actions, a 19-turn rage after 5. A swing at empty air counts as attacking (`fight.cc` `player_attempted_attack`) | confirmed (3–5) |
| B4 | Each kill may extend it under Trog | WS 3 | `mon-death.cc` ~l.2367: chance `min(piety, 160) / 800` per kill (12.5% at 100 piety, 20% at most), +1 to 6 turns | confirmed |
| B5 | Afterwards slowed for 14–36 turns | WS 3 | `player.cc` `player_end_berserk`: `12 + roll_dice(2,12)` | confirmed |
| B6 | Unable to rage again for twice that | WS 3 | same: `DUR_BERSERK_COOLDOWN` = 2 × that (28–72). It runs down 1.5× faster while hasted (`dec_berserk_recovery_player`) | confirmed |
| B7 | "Berserking at 50% HP is likely to be fatal" | WS 1 | Advice. Mechanism: a rage adds 50% to current and max HP in proportion and takes it back in proportion at the end (`go_berserk`, `player_end_berserk` → `calc_hp(true)`), so it heals nothing | not checkable (advice) |
| B8 | Trog's Hand: regeneration and +80 willpower, at 2 stars | WS 2.4 | `religion.cc` god powers: Hand at rank 2. `player.cc` `player_regen`: +100 regen, i.e. +1 HP per turn, even when sick. Willpower +2 pips × 40 = 80. Lasts `5 + 2d(piety/6 + 1)` turns (`god-abil.cc` `trog_do_trogs_hand`, power = piety/2) | confirmed |
| B9 | Brothers in Arms at 4 stars | WS 2.4 | `religion.cc`: rank 4 (100 piety) | confirmed |
| B10 | Their failure chance falls as piety rises | WS 2.4 | `ability.cc` table: raw failure Berserk 45 − piety/2, Hand 75 − piety, Brothers 160 − piety; Invocations skill plays no part for Trog | confirmed |
| B11 | Brothers' allies don't follow on stairs | WS 2.4 | `mon-util.cc` `mons_can_use_stairs`: summons can't; the berserkers are summons. Summoned allies are expired on leaving the floor (`files.cc`) | confirmed |
| B12 | "The piety figures beside each ability are not labelled as costs" | WS 2.4 | They are costs (`ability.cc` `ability_def.piety_cost`, plus `random2((cost+1)/2 + 1)`): Berserk 1–2, Hand 2–3, Brothers 5–8 piety | confirmed: they are costs |
| B13 | Trog's Hand can outlast lethal poison | WS 2.4 | Hand adds 1 HP per turn; poison takes at least 1 HP per turn and a fifth of what remains per turn above that (`player.cc` `handle_player_poison`). It outlasts small doses, not large ones *(inferred)* | confirmed, for small doses |
| B14 | Trog loses 1 piety per 340 turns of inactivity on average | WS 4 | `religion.cc` `handle_god_time`: 1 in 17, run every 100–300 aut (`timed-effects.cc`): 340 turns on average. It runs all the time, not only when idle; kills add piety | confirmed |
| B15 | Trog punishes training any magic skill | WS 4 | `god-conduct.cc` Trog's peeves: memorise spells, cast spells (penance), train magic skills, use wizardly items. Also `skills.cc` `is_harmful_skill` | confirmed |
| B16 | Trog dislikes magical staves | WS 4 | `god-item.cc` `is_wizardly_item`: staves, armour of energy, six unrands | confirmed |
| B17 | Trog dislikes pain-branded weapons | WS 4 | Changelog 0.31: "Trog now disables pain brand instead of becoming angry at it." `attack.cc` ~l.1264 skips the brand for Trog worshippers | **changed** (no penalty; the brand is inert) |
| B18 | Silence stops Trog's abilities too | WS 5 | `ability.cc` ~l.1837: no invocation while silenced. Nor any scroll (`_general_cannot_read_reason`) | confirmed |
| B19 | A potion of berserk rage is Trog's rage with the same aftermath and blocks items | WS 5; BC 1 | `potion.cc` `PotionBerserk` → `go_berserk(…, potion)`: same formula. Does nothing on `-Berserk`, known or not | confirmed |
| B20 | A rage reaches stairs 3–4 steps away | WS 3 | Not in the official sources | not checkable |

### Poison, healing, haste

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| P1 | Curing: a few HP, ends poison and confusion | WS 5 | `potion.cc` `PotionCuring`: 5–11 HP, clears poison and confusion, nothing else. Drinkable at full HP only if poisoned or confused. The manual's "cures many ailments" is vaguer than the code and the item text ("cures poison and confusion") | confirmed |
| P2 | Adders are fast and poison; keep a curing | WS 3 | `dat/mons/adder.yaml`: speed 13, poison bite, D:2–6 | confirmed |
| P3 | Heal wounds: about 25 HP, at least 10 | WS 5 | `potion.cc` `PotionHealWounds`: `10 + random2avg(28,3)` = 10–37, mean about 23.5. Refused at full HP | confirmed |
| P4 | `poison_survival` is something the brain can use | BC 2 | `player.cc` `poison_survival` (the lowest HP the current poison will leave, counting regeneration); Lua `you.poison_survival()`; already a brain input (`features.py`) | confirmed |
| H1 | Haste can stand in for berserk's speed | BC 2 | Both make actions take 2/3 the time (`defines.h` `haste_div`, `berserk_div`). They don't stack: a rage ignores haste (`player.cc` `player_speed`). Slow cancels either one: slowed in a rage is normal speed. Haste lasts 26–40 turns (`potion.cc`) | confirmed |
| H2 | Might adds damage | WS 5 | `potion.cc` `PotionMight`: 35–74 turns | confirmed |
| H3 | Berserk potion "never as a substitute for speed" | WS 5 | Advice; same speed as haste, but with the aftermath | not checkable (advice) |

### Teleportation and the other escapes

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| T1 | Teleportation takes 3–5 turns | WS 1, 5 | `spl-transloc.cc` `you_teleport`: `3 + random2(3)`. Abyss +5–14 (also in both FAQs), with the Orb +5–9 | confirmed |
| T2 | A second read cancels it | WS 5 | same function ("You feel strangely stable."); `items.txt` says so | confirmed |
| T3 | Don't teleport on an unexplored level | WS 3, 5 | Advice. Mechanism: the destination is a uniform random square with no monster or cloud on it (`_teleport_player`), not biased away from monsters | not checkable (advice) |
| T4 | Use escape items early | WS 1, 5 | `quickstart.md`: consumables "are more effective when used at the start of a tough fight than when you're near death" | confirmed |
| T5 | Blinking opens a target prompt | BC 2 | `item-use.cc` `controlled_blink`; 0.34: up to 2 squares of fuzz in Zot | confirmed |
| T6 | Fear checks willpower; nothing against undead or the nonliving | WS 5 | `beam.cc` `_monster_resists_mass_enchantment`, `monster.cc` `can_feel_fear`: natural, demonic and holy only, not berserk or frenzied monsters; willpower check at power 200 | confirmed |
| T7 | Butterflies push enemies back | WS 5 | Changelog 0.30 ("blow back nearby creatures"); knockback radius in `_get_scroll_targeter` | confirmed |
| T8 | Fog cuts off ranged attackers | WS 5 | `SCR_FOG` makes a random smoke cloud; whether it blocks a given attacker wasn't traced | not checkable |
| T9 | Ambrosia confuses and restores HP while it lasts | WS 5 | `potion.cc` `PotionAmbrosia`: 3–10 turns; `player.cc` `dec_ambrosia_player`: 3–5 HP and MP per turn; ends when the confusion does (so curing ends it) | confirmed |
| T10 | Silence is "very risky" | WS 5 | It blocks your own scrolls and invocations (B18) | confirmed |

### Stairs and resting

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| S1 | Only adjacent monsters follow up stairs | WS 1, 2.2 | Manual D: "most monsters adjacent to you will follow… Notable exceptions are zombies and other mindless undead." `mon-transit.cc` `_mons_can_follow_player_from`: a hostile must be adjacent, hunting you, able to act now, not incapacitated, constricted or dazed. `files.cc` checks again when you leave: still adjacent. Allies follow from 3 squares | confirmed |
| S2 | The stairs take about 2.5 turns | WS 1 | `main.cc` `_take_stairs`: followers are tagged at the key press ("Only those beside us right now can follow"), then a one-turn delay (`DescendingStairsDelay(1)`) that no default interrupt cancels (`initfile.cc` `set_default_activity_interrupts`) | **wrong** (one action and a one-turn delay) |
| S3 | Go up, rest, come back down for what followed | WS 1 | Changelog 0.34: monsters left behind "approach and encircle the last staircase they saw the player use"; monsters lured more than three floors from home return to it | **changed** |
| S4 | A normal level has three stairs down and three up | WS 3 | Both FAQs ("not counting any escape hatches") | confirmed |
| S5 | Explore only at full HP | WS 1 | `options_guide.txt`: `explore_auto_rest = true` (the ladder's rc keeps it) makes `o` wait for full HP and MP and, new in 0.34, for every negative status and cooldown (`explore_auto_rest_status` defaults `all_negative, all_cooldown, contam`: Slow, Conf, poison, `-Berserk`). `travel.cc` ~l.1096 | **changed** (built into explore) |
| S6 | Resting costs piety and lets wandering monsters arrive | WS 1 | B14; `timed-effects.cc` `handle_time` rolls for a new monster every 5 turns | confirmed |
| S7 | Pillar dancing was ended by attacks of opportunity | WS 2 | Changelog 0.31: a following monster now gets a chance to attack as it closes on a player who just stepped away | confirmed *(inferred that this ends it)* |

### Items

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| I1 | Potions: curing 18.4%, heal wounds 10.0%, eight uncommon 6.4% each, six rare 3.3% each, experience 0.2% | WS 5; BC 1 | `item-prop.cc` `_potion_rarity` × `makeitem.cc` `_potion_weight` (192, 105, 67, 35, 2; total 1045): 18.37, 10.05, 6.41, 3.35, 0.19%. Both lists match | confirmed |
| I2 | Scrolls: identify 26.1%, teleportation 13.1%, most others 4.7% | WS 5; BC 1 | `_scroll_rarity` × `_scroll_weight` (200, 100, 36, 15, 9). Total 765 in a game, since one of summoning and butterflies is excluded: 26.1, 13.1, 4.7% | confirmed |
| I3 | Rare scrolls (2.0%): brand weapon, poison, silence, torment | WS 5 | Poison is uncommon (36, 4.7%). Rare (15, 1.96%): brand weapon, silence, torment, and summoning or butterflies | **wrong** |
| I4 | Acquirement 1.2% | WS 5 | 9/765 = 1.18% | confirmed |
| I5 | Summoning and butterflies never both exist in a game | WS 5; BC 1 | `item-prop.cc` `item_sets` "ally scroll". The same holds for wands of paralysis or charming, of iceblast, roots or warping, and of acid, light or quicksilver | confirmed |
| I6 | The game identifies the last unknown kind itself | WS 5; BC 1 | `items.cc` `maybe_identify_base_type`; the excluded half of an item set counts as known | confirmed |
| I7 | Identify is useless once everything is known | WS 5; BC risks | `item-name.cc`: a known identify can't even be read ("There is nothing left to identify.") | confirmed |
| I8 | Identify names one potion or scroll kind, in the pack or on the floor | WS 5 | `item-use.cc` `_identify`, `OSEL_UNIDENT`: any one unidentified item but a book, in the pack or on your square, so unidentified gear and jewellery too | confirmed, wider |
| I9 | A known scroll's prompt can be cancelled with Esc at no cost | WS 5; BC risks | `item-use.cc` `_choose_target_item_for_scroll`: no "waste" question when known; `read`: `cancel_scroll` → the turn isn't used and the scroll stays. Unknown: "Really abort (and waste the scroll)?"; answering **n** reopens the prompt | confirmed |
| I10 | Unknown scrolls that open a prompt: identify, enchant armour, enchant weapon, blinking, brand weapon | BC "what the games say" | `item-use.cc` `run_uncancel(UNC_…)`; also amnesia and acquirement | confirmed |
| I11 | `scroll:fear` has no prompt | BC 1 | Changelog 0.34; `options_guide.txt` `force_scroll_targeter = fear, silence, vulnerability, immolation, torment`: a known one shows a targeter that must be confirmed. With no enemy in view a known fear asks "You can't see any enemies this would affect, really read…?" (`read`) | **changed** |
| I12 | Mutation is the only lasting harm from a trial | WS 5; BC 2 | `potion.cc` `PotionMutation`: removes 2–3 mutations, adds 1–3, and half the time one good one. The other bad trials are temporary: lignification 15–58 turns of uncancellable tree form, moonshine 10–25 turns of vertigo, attraction, and the hurt from torment, immolation or poison | confirmed |
| I13 | Several stacks found apart are likelier a common kind | WS 1, 5 | Follows from I1–I2: kind doesn't depend on depth, and a stack is 1 item (potions: +1 at 1/18, +1 at 1/25; scrolls 46/48 single) (`makeitem.cc`) *(inferred)* | not checkable (statistics) |
| I14 | Enchant body armour first, or small pieces first (try both) | WS 5; BC 2 | Manual G and `item-prop.cc` `armour_max_enchant`: body armour up to its base AC, shields +3/+5/+8, everything else +2. Small pieces fill after two scrolls each | not checkable (advice); cap added |
| I15 | Immolation and poison help only with nothing adjacent | WS 5 | `spl-clouds.cc` `scroll_of_poison`: poison clouds (10–20 turns) on every empty square in view, none under a creature, so adjacent monsters are untouched until they move | confirmed |
| I16 | Moonshine is one of the uncommon potions | WS 5 | Changelog 0.33: degeneration became moonshine (vertigo only) | confirmed |

### Weapons, skills, character

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| C1 | Delay is base delay less half the weapon skill | WS 3 | `player-act.cc` `attack_delay_with`: base − skill/2 (in tenths), down to `weapon_min_delay` (`fight.cc`: base/2, at most 0.7). A shield adds its penalty on top | confirmed |
| C2 | Skill for 1.0: mace and flail 8, morningstar and eveningstar 10, great mace 14 | WS 3 | `item-prop.cc`: 1.4, 1.4, 1.5, 1.5, 1.7. (Dire flail 1.3: skill 6; giant club 1.6: 12) | confirmed |
| C3 | Above 1.0 a normal-speed monster gets double turns | WS 3 | Delay is in aut and a speed-10 monster acts every 10 aut, so at 1.4 it acts 1.4 times per swing; double only at 2.0 *(inferred)* | **wrong** as stated |
| C4 | Javelins reach 1.0 delay at 10 Throwing | WS 2.5 | `attack_delay_with`: thrown delay = 1.0 + damage/20 − skill/20; javelin 1.5 → 1.0 at 10 | confirmed |
| C5 | Heavy armour doesn't slow throwing | WS 2.5 | Same function: body armour slows launchers only; a shield slows every attack | confirmed |
| C6 | Shields about 10 for a kite shield, 15 for a tower shield | WS 4 | `player.cc` `adjusted_shield_penalty`: falls linearly with skill to zero at 27 and with Strength; no step at 10 or 15 | not checkable (rule of thumb) |
| C7 | Axes hit every adjacent enemy for 70% | WS 4 | `melee-attack.cc` `cleave_damage_mod`: 70% | confirmed |
| C8 | Maces don't multiply hydra heads | WS 4 | `melee-attack.cc` `attack_chops_heads`: slicing, chopping or large claws only | confirmed |
| C9 | About 2 Throwing is enough early | WS 2.5 | A stone is 1.1 delay, 1.0 at Throwing 2 *(inferred from C4's formula)* | confirmed |
| X1 | Stat points at level 3 and every 6 after | WS 4 | `player.cc` `level_change`: XL 3, 9, 15, 21, 27. The Minotaur also gains a random Str or Dex every 4 levels (`minotaur.yaml`) | confirmed |
| X2 | Horns rule out helmets, not hats | WS 4 | `player-equip.cc`: helmets refused with any horns, all headgear only at horns 3; Minotaurs have 2 | confirmed |
| X3 | Lair entrance D:8–11, Mines D:9–12 | WS 4 | `branch-data.h` | confirmed |
| X4 | Refuse artefacts with *Slow, *Rage or *Silence | WS 4 | Not traced | not checkable |

### Threats

| # | claim | where | 0.34 says | verdict |
| --- | --- | --- | --- | --- |
| M1 | Orc priest smites for up to 17, from D:3 | WS 3 | `mon-cast.cc` `_cast_smiting`: 7–17. Alone from D:4 (`mon-pick-data.h`); earlier in orc bands, orcs being D:3–8 (`mon-place.cc` `BAND_ORCS`). Smiting is divine: silence stops it, antimagic doesn't (manual F) | confirmed |
| M2 | Centaur from D:5, outruns you | WS 3 | `centaur.yaml` speed 15, D:5–13 | confirmed |
| M3 | Ogre up to 39 a hit, D:4, slow to swing | WS 3 | `ogre.yaml`: hit 20, attack energy 15; `attack.cc` `calc_damage` adds the weapon roll: giant club (2 in 3) up to 39, giant spiked club up to 41, before AC. D:4–7 | confirmed |
| M4 | Fast: jackal, quokka, adder | WS 2.6, 3 | Speeds 14, 12, 13 (normal 10) | confirmed |
| M5 | Bats can't be escaped | WS 2.6 | `bat.yaml` speed 30 | confirmed |
| M6 | Grinder paralyses | WS 3 | `mon-spell.h` `MST_GRINDER`: Pain, Paralyse, Blink. D:3–6 | confirmed |
| M7 | Floating eyes paralyse | WS 3 | `floating-eye.yaml`: `cant_spawn`, speed 0, no attacks: kept for old saves only | **changed** (not generated) |
| M8 | Sigmund on D:2 | WS 2.7, 3 | `uniques.des`: D:2–6 | confirmed |
| M9 | Ijyb carries a wand | WS 3 | `ijyb.yaml` `always_wand`. D:3–5 | confirmed |
| M10 | A wand of paralysis works on D:3 with no Evocations | WS 2.8 | Only half of games have it (I5); its power wasn't traced | not checkable |
| M11 | Iceblast, roots and the lightning rod can't miss | WS 2.8 | Not traced | not checkable |
| M12 | Red or purple threat colour means stop and think | WS 3 | FAQ: "treat each new monster you meet with utmost caution". Changelog 0.34: the Trivial threshold "is now a little higher" | not checkable |

## 2. What the official sources add

### Rules the brain or qw can follow today

1. **Answer item prompts from the crawlrc, not from Python.** 0.34 calls Lua hooks before opening the
   menu: `c_choose_identify`, `c_choose_enchant_weapon`, `c_choose_enchant_armour`,
   `c_choose_brand_weapon` (each returns an inventory letter) and `c_choose_acquirement` (an index)
   (`item-use.cc` l.2278–2487, `acquire.cc` l.1773). They run on both paths, a known scroll and an
   unknown one being identified by reading. `c_answer_prompt` already answers yes/no prompts for qw
   (`tools/qw/ladder.lua`). This is step 1 of `brain-consumables.md` with no new menu handling, and
   it settles "acquirement stays as it is". Identify's hook only searches consumable letters
   (`_identify` loops from `MAX_GEAR`).
2. **Never answer yes to "Really abort (and waste the scroll)?"** Answering no reopens the prompt
   (`uncancel.cc`, `_choose_target_item_for_scroll`); with rule 1 in place the prompt never opens.
   Together they remove the 400 wasted reads *(inferred)*.
3. **Or switch the new scroll prompts off.** `force_scroll_targeter` in the rc controls which known
   scrolls show a targeter (I11); the alternative is to confirm it with Enter.
4. **Don't go berserk with poison you can't outlast.** For the brain's rules and for qw's rune-branch
   wall. Poison is a fixed number of HP still to come (`player.cc` `poison_player`,
   `handle_player_poison`), and the end of a rage scales current HP down by a third (`calc_hp(true)`).
   So 30 HP shown *during a rage* with 25 poison to come is lethal at 20 HP after it, and nothing can
   be drunk in between *(inferred from the two functions)*. The game says "You are lethally poisoned!"
   when it crosses over. *Correction, 2026-11-12:* starting a rage adds the same 50% (`go_berserk` →
   `calc_hp(true)`), so the round trip is neutral: poison held before a rage is lethal after it exactly
   when it is lethal now (`poison_survival <= 0`). The two-thirds comparison applies only to the HP
   shown while already berserk, which is where poison that lands during the rage is measured. What
   raging with poison costs is the potion you cannot drink until it ends.
5. **Poison runs on game time, not on actions.** It ticks per aut, so in a rage (2/3 time per action)
   each action costs less poison, and slowed (1.5×) each costs more. Slowed after a rage with poison
   left is the worst case: the fixed HP loss arrives over fewer of your actions *(inferred)*.
6. **Haste after a rage.** Haste and the post-rage Slow cancel to normal speed, and both Slow and
   `-Berserk` run down 1.5× faster while hasted (`dec_slow_player`, `dec_berserk_recovery_player`).
   A potion of haste is the cure for the aftermath, not only an alternative to berserk.
7. **After a fight still in a rage, `rest`, don't `explore`.** Explore is refused while berserk; resting
   isn't, and the no-attack penalty ends the rage in 4 or 5 actions (B3).
8. **`explore` already rests.** Pressing `o` rests to full and waits out Slow, `-Berserk`, confusion and
   poison before moving (S5). The difference `--style wiki=1` made to resting must come from elsewhere,
   most likely resting before `descend`, which doesn't wait *(inferred)*.
9. **Stairs: adjacency at the key press is what counts, and on arrival you act first.** Manual D: "you
   are guaranteed a chance to act before any monsters on the other side that you have not previously
   encountered" (0.34 changelog: they skip their first turn). The monsters that followed you, and
   ones met there before, get no such pause *(inferred from the wording)*.
10. **Read silence against an orc priest only when not counting on Trog.** It stops the priest's smiting
   (divine) and also your own invocations and scrolls.
11. **Resistance (rare, 3.3%) gives rPois** as well as rF, rC and rElec for 35–74 turns (`potion.cc`,
    `player.cc` `player_res_poison`). For qw's poison deaths it is the item to drink before the rage.
    Note that rPois only blocks two poisonings in three from attacks (`poison_player`); poison clouds
    and forced poison go through *(the clouds part inferred)*.
12. **Lignification is tree form**: immune to poison and mephitic clouds, uncancellable, 15–58 turns
    (`PotionLignify`). Bad as a trial next to monsters; a niche cure for standing in poison clouds.
13. **Enchant armour has caps** (I14): two scrolls per small piece, body armour up to its base AC.
    The rule "body first" never wastes a scroll; "small pieces first" stops after +2 each.

### Needs an action

- **Throwing.** Stones reach 1.0 at Throwing 2, javelins at 10 (C4, C9), and body armour doesn't slow
  them. But 0.34 made stones "much less common", so the action depends on picking up what there is.
- **Resting on the stairs and coming back by different stairs.** The 0.34 stair change (S3) means the
  old "fight on the stairs, up and down" pattern now meets a crowd at the bottom. Coming back down by
  one of the other two staircases avoids it *(inferred)*.
- **Haste as the post-rage action** (rule 6) needs `quaff:haste` from the consumables design.
- **Trog's Hand before a rage when poisoned** (B13) needs the Hand action.

### Needs an input

- **Rage time left and `-Berserk` time left.** The status lights exist (`Berserk`, `-Berserk`, `Slow`),
  the turns don't. With B2–B6 the brain could estimate them from the turn the rage began.
- **Poison as HP to come**, beside `poison_survival` (which the brain has). Rule 4 needs both.
- **Doom** (0.34): a percentage in the sidebar; at 100% a random Bane. Not observed today.
- **Status names** for the consumables catalog, from `duration-data.h`: `Resist`, `Attr`, `Ambros`,
  `Might`, `Will+`, `Vertigo`, `Tele`, `Conf`.

### Facts

- Uniques are placed by depth range: Sigmund D:2–6, Jessica and Terence D:2–3, Natasha and Robin
  D:2–4, Ijyb D:3–5, Grinder D:3–6, Blorkula D:5–8 (`uniques.des`). All uniques force a `--More--`
  on first sight in 0.34 (the rc's `show_more = false` covers it).
- The in-game FAQ (0.34): altars to almost every god in the first **ten** levels (the website says nine);
  a weapon's delay and damage rating show on its description or with `@`.
- Quickstart's tactics, the official version of the wiki's: rest between encounters, never fight more
  than one, back into a corridor, use consumables at the start of a fight, use projectiles first, skip
  a dangerous level ("but don't overdo this"). It recommends a minotaur Fighter with an axe.
- The manual still says "You can carry at most 52 items" (G); the 0.34 changelog says consumables are
  unlimited. The manual is stale there.
- The ladder's rc picks up helmets (`crawlrc.txt` `ladder_gear`), which a Minotaur can't wear (X2)
  *(inferred that it is wasted)*.

## 3. What 0.34 (and 0.31–0.33) changed under the wiki's advice

The wiki pages behind the digest are marked 0.30 to 0.34. From `/docs/changelog.txt`, the changes that
touch what the digest or the brain relies on:

**0.34**

- **Resting and explore wait for statuses.** Rest and autoexplore now wait out "all negative effects
  and transformations, all time-based cooldowns, and all magical contamination" (S5, rule 8).
- **Monsters at stairs.** Unseen monsters skip their first turn after you take stairs; monsters left
  behind gather at the last staircase you used; monsters more than three floors from home go back. The
  digest's stair advice (S3) predates all three.
- **Scroll targeters.** Known fear, silence, vulnerability, immolation and torment open a targeter
  (I11). Of the catalog's fight scrolls, fear joins blinking as one with a prompt; teleportation, fog,
  summoning and butterflies have none by default (`item-use.cc` `read`, `_scroll_has_forced_targeter`).
  The rc can remove the new ones with `force_scroll_targeter` (`options_guide.txt`; an empty value
  should clear the list, not tested).
- **Inventory.** Four inventories, unlimited potions, scrolls and evocables, separate letters per
  inventory, default letters for identified consumables (`consumable_shortcut`). Anything that reads
  letters off the inventory needs the 0.34 layout.
- **Messages.** "You encounter an X" replaces "An X comes into view" (the repo's tests already use the
  new form).
- **Threat colours.** The Trivial threshold is a little higher, so the `threat` input shifts.
- **Doom and Banes**, a new medium-term harm from some monsters (the digest has nothing on them).
- **Wandering monsters** no longer notice you just because you attack, but notice more often per turn.
- Stones are much less common; Teleportitis is now cancellable; the "unsafe potion/scroll" mutations
  are out of the bad mutation pool; monster miniparalysis is a fixed 15 aut.

**0.33**: berserk makes you immune to fear (also clears it on starting, `go_berserk`); potions of
degeneration became moonshine; Trog's wrath simplified.

**0.31**: Trog disables pain brand instead of angering (B17); monsters no longer use potions or scrolls;
potions of flight became enlightenment and scrolls of magic mapping became revelation; attacks of
opportunity reworked (S7).

**0.30**: scrolls of butterflies knock back and alternate with summoning (I5, T7).

**Not dated**: floating eyes are no longer generated (M7); I couldn't find the version in the changelog.

## 4. Not checked

Fog's effect on line of sight (T8); wand power at Evocations 0 and which wands can miss (M10, M11);
artefact properties to refuse (X4); the early portals' timers; anything in `docs/develop`. The digest's
own thresholds (50%, 30%, four steps) are its author's and have no official counterpart.
