"""Choosing: which actions are possible now, what the rules of thumb would do, what the network prefers.

`BrainTiers` takes `StubTiers`' place inside Reflex. Where the stub raised an escalation (low HP
with monsters in view, an action that makes no progress) the brain picks another action instead,
so a game goes on until the character dies, the limits run out, or nothing at all is possible.

The network predicts outcome components per action; `Style` weighs them into one value at decision
time, so changing the style needs no retraining (the same split as s1-battle's trained brain).
"""

from __future__ import annotations

import random
import re
from dataclasses import asdict, dataclass

import numpy as np

from ..conn import ActResult, cancel_prompt
from ..interrupts import Before, Interrupt
from ..reflex import EXCLUDED_PROMPT, Escalation, StubTiers
from ..state import MF_DOOR, MF_FEATURE, MF_STAIR_UP, MF_TRAP, MF_WATER, NOT_WALKABLE, GameState, strip_tags
from ..travel import DIRECTIONS, step_toward

from . import gear, monsters
from .features import ACTIONS, COMPONENTS, MDAM_LEFT, POTIONS, encode, inventory, observe, path
from .net import Ensemble, TrainedNet
from .route import LAIR_KEY, LAIR_NO_WAY, LairRoute, where

# What a scroll can stop on (conn.classify_error's names). Anything else that comes up after using an
# item, such as the level-up stat prompt when the potion's turn killed something, is Reflex's to answer.
ITEM_PROMPTS = {"blink", "identify", "enchant_weapon", "enchant_item", "brand_weapon", "acquirement", "menu"}
ENCHANT_PROMPTS = {"enchant_weapon", "enchant_item", "brand_weapon"}   # what `Style.kit` answers instead of cancelling
REPLAY_DIVERGED, FORK_DONE = "replay diverged", "fork horizon reached"
LEVEL_STEP_LIMIT = 1500   # choices on one level before the brain calls itself stuck
IDLE_LIMIT = 60           # waits in a row, with nothing else possible, before it does the same
BLOCK_TURNS = 50         # an action that went nowhere is left alone for this many game turns
THROW_RETRY = 2          # ...but a throw with no clear shot (`Style.throw`) only for this many
FENCE_KEY = chr(9350)      # the rc's ladder_fence_shops macro (crawlrc.txt)
UNTIL_LEVEL = 10 ** 9     # ...or until the next level, for scrolls and potions that wouldn't go down
COMMITS = {"descend": "explore", "explore": "descend"}   # a committed fork's action, and the one it replaces


@dataclass
class Style:
    """How the predicted outcomes are weighed. value = sum(weight x component) + prior nudge.

    The default counts what the evaluation counts: depths gained by the end of the game, less a
    penalty for dying in the next few turns. The discounted components are there to be tried
    (`--style depth_go=1`), but on their own they taught every early model to dive.
    """
    died_soon: float = -1.0
    hp_lost: float = 0.0
    xp_soon: float = 0.0
    depth_go: float = 0.0
    xp_go: float = 0.0
    died_go: float = 0.0
    depth_end: float = 1.0
    human: float = 0.0        # weight of log P(the recorded player would do this)
    margin: float = 0.25      # leave the rules of thumb only for an action predicted this much better
    min_count: float = 40     # ...and only for actions the model saw at least this often in training
    wiki: float = 0.0         # 1 = the rules of thumb follow the DCSS wiki's guides (docs/wiki-strategy.md)
    teleport: float = 3.0     # 1 = the rules of thumb read teleportation when spent after a rage (`teleport_rule`),
                              # 2 = also when outnumbered by something dangerous, 3 = only when exhausted after a
                              # rage and outmatched (the hostiles' HP left at 1.5x the character's), 0 = off.
                              # 3 by default since 2026-11-15 (+0.24 [+0.16, +0.34] on 600 fresh dungeons).
    recover: float = 1.0      # 1 = with nothing in view, rest out a rage and its exhaustion (`recovering`) before
                              # taking the stairs, 2 = before exploring on as well, 0 = off. 1 by default since
                              # 2026-11-15 (with retreat=2: +0.45 [+0.24, +0.65] on 996 fresh dungeons).
    calm: float = 0.0         # 1 = with nothing in view, wait out a rage instead of trying to explore (DCSS
                              # refuses: "Calm down first, please."), and don't count that refusal as the
                              # level being done (`raging`). Off by default.
                              # 2 = as 1, and when explore is refused for an unseen monster close by ("There is a
                              # strange disturbance nearby!"), step to a free adjacent square and try again, as qw's
                              # `plan_disturbance_random_step` does, instead of setting explore aside and taking the
                              # stairs; at most DISTURB_MAX such steps per level visit (an automatic step,
                              # `BrainTiers.auto_step`).
    retreat: float = 2.0      # 1 = when a rage runs out with RETREAT_LEFT or more hostiles in view and stairs up
                              # known, go up them (kept to on that level while `recovering`), then rest the
                              # exhaustion out before anything else; 2 = the same, only with the stairs up within
                              # STAIRS_NEAR steps; 3 = as 2, and also whenever RETREAT_LEFT or more hostiles are in
                              # view while exhausted (`-Berserk`, not raging), not only as the rage runs out;
                              # 0 = off. 2 by default since 2026-11-15 (with recover=1).
    stairs: float = 0.0       # 1 = before a fight bigger than one rage (`big_fight`), nothing adjacent and no rage
                              # on, walk to stairs up within STAIRS_NEAR steps first, once per fight. Off by default.
    unseen: float = 2.0       # hurt with nothing in view (`BrainTiers.assailed`): 1 = when burning (DCSS's sticky
                              # flame, `Fire`), walk toward the stairs, since every step shakes some of it off and
                              # waiting only burns; 2 = also when something unseen keeps hurting (UNSEEN_HITS falls in
                              # HP, not poison), read teleportation, else go up the stairs. 0 = off. 2 by default
                              # since 2026-11-15 (+0.17 [+0.04, +0.31] on 598 fresh dungeons).
    avoid: float = 0.0        # k > 0 = before a fight, read teleportation instead of starting a rage when the hostiles
                              # in view have k times the character's maximum HP or more left between them (`foe_hp`),
                              # neither raging nor exhausted, no teleport coming (`avoid_rule`); 0 = off. Off by default.
    escape: float = 0.0       # h > 0 = in a fight, exhausted after a rage (`-Berserk`, not raging) with HP at h times the
                              # maximum or under, read teleportation, whatever the hostiles' HP (`escape_rule`); 0 = off.
                              # Off by default.
    unique: float = 0.0       # 1 = a unique the game rates extremely dangerous (threat 3) in view and not adjacent, the
                              # character not raging: read teleportation, hold the rage while it is coming, and leave the
                              # level once it has worked (`unique_rule`); 0 = off. Off by default.
    calmfor: float = 0.0      # T > 0 = `calm` holds only for the first T turns of each visit to a level; after that a
                              # rage ends the exploring there as it does without `calm`; 0 = no limit. Off by default.
    rage: float = 0.0         # h > 0 = start a rage later, as qw does (`late_rage`): with a hostile within two squares,
                              # only at h times the maximum HP or under, or when the hostiles within two have the
                              # character's maximum HP or more left between them, or one of them is threat 3; not at
                              # the first threat-2 monster or three small ones within two. 0 = off. Off by default.
    hold: float = 0.0         # k > 0 = with hostiles in view and none within two squares, none known to attack from range or with
                              # reach, and one of them awake and coming (`hold_ground`): wait for them, up to k waits
                              # in a row, as qw's `plan_melee_wait_for_enemy` does, instead of walking to them.
                              # 0 = off. Off by default.
    kit: float = 2.0          # (2 by default: both levels passed their tests on fresh dungeons.) 1 = with nothing in view and no rage on, put on the rings and amulets worth wearing (by qw's
                              # valuation, `gear.JEWEL_VALUES`), read known enchant armour, enchant weapon and brand weapon
                              # scrolls, answer those scrolls' prompts with the armour or weapon in use instead of cancelling
                              # them, and rank and pick up the tower shield (`gear.KIT_ARMOURS`). Automatic steps taken
                              # before the brain's choice (`BrainTiers.auto_step`), not actions. 0 = off. On by default
                              # since it passed its test on fresh dungeons (docs/trained-brain.md).
                              # 2 = all of 1, plus the parts `kitpart` picks (`kit_parts`), also automatic steps:
                              # "gear" (item names read right: ego armour and artefacts ranked by their properties, weapon
                              # brands, `gear.weapon2`/`armour2`/`jewel2`; wear and wield by that ranking; enchant armour in
                              # qw's order; pick up a better piece of a kind already carried, `gear.KIT2_RC`), "acquire"
                              # (answer acquirement with the best offer, `gear.acquire_choice`, and read a known one) and
                              # "shop" (walk into the shops on the level and buy, `gear.shop_choice`). Off by default.
    kitpart: float = 0.0      # with kit=2: which parts, as a sum of 1 ("gear"), 2 ("acquire") and 4 ("shop"); 0 = all.
    hand: float = 0.0         # 1 = invoke Trog's Hand when a monster on qw's `hand_monsters` list is in view (`hand_wanted`),
                              # as an automatic step before the brain's choice. 0 = off. Off by default.
    throw: float = 0.0        # 1 = pick up javelins, boomerangs and large rocks (`gear.THROW_RC`) and throw them at a hostile in
                              # view with a clear shot when qw would (`throw_wanted`) and the rules of thumb would walk up to
                              # it or wait for it; never while raging. An automatic step (`BrainTiers.auto_step`). 0 = off.
                              # Off by default.
    step: float = 0.0         # k > 0 = with two or more hostiles adjacent and not raging, step to the free adjacent square that
                              # cuts the hostiles able to hit next turn by k or more (`step_square`; 2 is qw's "outnumbered"),
                              # where the rules of thumb would fight, wait or rage; at most STEP_MAX steps per fight. An
                              # automatic step (`BrainTiers.auto_step`). 0 = off. Off by default.
    save: float = 0.0         # 1 = keep potions as qw does: in a fight, drink a healing potion at SAVE_HEAL (a quarter) of the
                              # maximum HP or under, not at half (qw's `want_to_heal_wounds`: `hp_is_low(25)`), and drink an
                              # unknown potion to identify it only from a stack of two or more (qw's `plan_quaff_unided_potions`:
                              # `quaff_unided_potion(2)`), nothing in view as before; at that HP in a fight with no healing
                              # potion known, drink an unknown one (qw's `heal_general`). Rules only: no action, no
                              # observation changes. 0 = off. Off by default.
    # The three parts of qw's way with potions and scrolls, one at a time (none lowers the healing threshold, which
    # is `save`'s alone). Each is off by default; none adds an action or changes the observation.
    ident: float = 0.0        # 1 = with nothing in view, no rage, able to read: read a known scroll of identify while an
                              # unknown potion or scroll is held (qw's `plan_use_identify_scrolls`), an automatic step
                              # ("read_ident", `BrainTiers.auto_step`); and answer the identify prompt, from that read or
                              # from an unknown scroll that turns out to be identify, with the item qw's
                              # `get_unidentified_item` picks (`ident_choice`: a potion before a scroll, the smallest
                              # stack first) instead of cancelling it. 0 = off. Off by default.
    stack: float = 0.0        # 1 = with nothing in view, drink an unknown potion to identify it only from a stack of two or
                              # more, the largest (qw's `plan_quaff_unided_potions`: `quaff_unided_potion(2)`); `save`'s
                              # `unknown_pair` part alone. 0 = off. Off by default.
    cure: float = 0.0         # 1 = drink curing when confused (qw's `plan_cure_confusion`) or badly poisoned as qw counts it
                              # (`cure_wanted`: lethal poison, or 60 HP or more of it with hostiles in view, `plan_cure_bad_poison`;
                              # with nothing in view, poison that leaves 1 HP or less, `plan_cure_poison`), besides the
                              # rules' own serious-poison cure; and never drink curing to heal: a healing potion for HP is
                              # heal wounds only (qw's `plan_heal_wounds`). 0 = off. Off by default.
    lair: float = 0.0         # k > 0 = the Lair detour (`route.LairRoute`, as qw's goal list goes): once the Lair's entrance is
                              # known (the rc's `ladder_find_lair`, `route.LAIR_RC`), where the rules of thumb would take the
                              # stairs down, go to the entrance and in; explore Lair:1 down to Lair:4 (k = 1) or Lair:5 (k = 2)
                              # with the rules as they are; then walk back up through the Lair and go on down the Dungeon from
                              # the entrance's level. Automatic steps ("lair_scan", "lair"), no action, no observation change.
                              # 0 = off. Off by default.

    def weights(self) -> np.ndarray:
        return np.asarray([getattr(self, c) for c in COMPONENTS], dtype=np.float32)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def saved(cls, saved: dict | None) -> Style:
        """The style a saved run (results.json, a step log's header) was played with.

        A key missing from it was played with the value the key had when it was added
        (`STYLE_ADDED_AS`), not with today's default: `recover` and `retreat` were added at 0 and are
        on by default only since. Every other key's default has never changed."""
        known = cls().to_dict()
        return cls(**{**known, **STYLE_ADDED_AS, **{k: v for k, v in (saved or {}).items() if k in known}})


# Style keys whose default has changed since they were added, with the value they were added at: a run
# saved before the key existed was played with this value.
STYLE_ADDED_AS = {"recover": 0.0, "retreat": 0.0, "teleport": 0.0, "unseen": 0.0, "kit": 0.0}


SERIOUS_POISON = 65       # % of current HP the poison will take: the game's "seriously poisoned" (status.cc)


def _has(obs: dict, *prefixes: str) -> bool:
    return any(x.startswith(prefixes) for x in obs.get("status") or [])


def poison_share(obs: dict) -> int:
    """How much of the current HP the poison will have taken once it has run its course, in percent,
    counted as the game's status line does (`_describe_poison`): 100 or more is lethal."""
    hp = obs["hp"]
    if hp <= 0:
        return 100
    return (hp - max(0, obs.get("poison_survival", hp))) * 100 // hp


def poison_lethal_after_rage(obs: dict) -> bool:
    """Whether the poison now in the character would kill it after a rage, if the rage ended at once.

    A rage multiplies current HP by 3/2 when it starts (`player::go_berserk`) and by 2/3 when it ends
    (`player_end_berserk`), both through `calc_hp(true)`, which keeps the fraction, so the round trip
    loses under 1/100 HP. Poison still to come is a fixed amount and is not scaled.
    - Raging now: HP at the end is 2/3 of what is shown, so with P = hp - poison_survival still to come,
      it is lethal once 2*hp/3 <= P, that is poison_survival <= hp/3.
    - Not raging yet: the HP held now comes back at the end, so the poison is lethal afterwards exactly
      when it is lethal now (poison_survival <= 0, `poison_is_lethal`). What the rage adds is that no
      potion can be drunk until it is over, so a cure has to come first.
    """
    hp, survival = obs["hp"], max(0, obs.get("poison_survival", obs["hp"]))
    if survival >= hp:
        return False                                    # not poisoned, or regeneration outpaces it
    if _has(obs, "Berserk"):
        return 3 * survival <= hp
    return survival <= 0


def heal_potion(obs: dict) -> str | None:
    """Which healing potion `quaff_heal` drinks: "curing", "heal_wounds", or None with neither.

    Curing when the poison is serious (it ends the poison; heal wounds cures nothing) or when HP is full
    (heal wounds is refused then, curing isn't while poisoned or confused). Heal wounds otherwise: it
    heals 10-37 against curing's 5-11. Either way the other one when only the other is held.
    """
    inv = obs["inv"]
    held = {"curing": inv.get("curing", 0) > 0, "heal_wounds": inv.get("heal_wounds", 0) > 0}
    want = "curing" if poison_share(obs) > SERIOUS_POISON or obs["hp"] >= obs["hp_max"] else "heal_wounds"
    other = "heal_wounds" if want == "curing" else "curing"
    return want if held[want] else other if held[other] else None


def needs_cure(obs: dict) -> bool:
    """Seriously poisoned, with curing in the pack: drink it before anything else, a rage above all."""
    return poison_share(obs) > SERIOUS_POISON and obs["inv"].get("curing", 0) > 0


QW_BAD_POISON = 60        # `Style.cure`: poison still to come, in HP, that qw cures with danger in view


def cure_wanted(obs: dict) -> bool:
    """`Style.cure`: curing held, and qw would drink it now (runs/qw/build-zk/qw.lua).
    - Confused (`plan_cure_confusion` 12430-12455: whenever confused, in effect, since its other conditions include
      "autopickup on"). qw skips this standing in noxious fumes; nothing in the observation says so, so this doesn't.
    - Poison that would kill (`plan_cure_bad_poison` 11768-11786: `poison_survival() <= 0`), or with hostiles in view
      poison that will take QW_BAD_POISON HP or more (`survival <= hp - 60`); with nothing in view, poison that leaves
      1 HP or less (`plan_cure_poison` 14288-14300)."""
    if obs["inv"].get("curing", 0) <= 0:
        return False
    if _has(obs, "Conf"):
        return True
    hp, survival = obs["hp"], obs.get("poison_survival", obs["hp"])
    if survival >= hp:
        return False                                    # not poisoned, or regeneration outpaces it
    if survival <= 0:
        return True
    return survival <= hp - QW_BAD_POISON if obs["n_hostiles"] else survival <= 1


RECOVERING = ("Berserk", "-Berserk", "Slow")     # a rage, the exhaustion after it, the slowness it leaves


def recovering(obs: dict) -> bool:
    """In a rage or just out of one: `Berserk`, `-Berserk` (exhausted: no second rage) or `Slow` showing.

    The end of a rage leaves the character slowed for 14-36 turns and unable to rage again for twice that
    (`player_end_berserk`). Resting (`5`) passes that time even at full HP ("You start waiting."), and a rage
    with nothing to hit wears off sooner (`_do_berserk_no_combat_penalty`).
    """
    return any(x in RECOVERING for x in obs.get("status") or [])


CALM_DOWN = "Calm down first, please."     # DCSS's answer to autoexplore (and travel) during a rage
DISTURBANCE = "There is a strange disturbance nearby!"   # ...and with an unseen monster close by (`Style.calm` 2)
DISTURB_MAX = 10          # `Style.calm` 2: steps away from a disturbance per level visit, at most


def raging(obs: dict) -> bool:
    """In a rage now (`Berserk`, not the `-Berserk` exhaustion after it): autoexplore is refused."""
    return "Berserk" in (obs.get("status") or [])


RETREAT_LEFT = 2          # hostiles still in view when a rage runs out that `Style.retreat` goes upstairs from
STAIRS_NEAR = 8           # steps to the stairs up that `Style.stairs` walks before a big fight, and `Style.retreat`
                          # 2 walks after a rage


def foe_hp(obs: dict, mons: list[dict] | None = None) -> float:
    """The HP the hostiles in view (or just `mons`) have left between them, estimated: each one's average HP (the
    game's `avghp`, else the monster table's) times the share its damage level leaves (`features.MDAM_LEFT`)."""
    total = 0.0
    for m in obs["mons"] if mons is None else mons:
        avg = m.get("avghp")
        if not avg:
            k = monsters.lookup(m["name"])
            avg = k["hp"] if k else 0
        total += avg * MDAM_LEFT.get(m.get("mdam", 0), 1.0)
    return total


def big_fight(obs: dict) -> bool:
    """More than one rage is likely to finish: the hostiles in view have more HP left between them (`foe_hp`)
    than the character has at most. In the saved games (`{A,C}-fix-rec1`), 40% of the rages begun in one ran
    out with the fight still on or ended in death, against 10% of the others."""
    return obs["n_hostiles"] > 0 and foe_hp(obs) >= max(obs["hp_max"], 1)


BURNING, UNSEEN = "burning", "unseen"     # what `BrainTiers.assailed` reports
UNSEEN_HITS = 2           # falls in HP with nothing in view, in a row, that count as something unseen attacking


def available(obs: dict, level_explored: bool, blocked: set[str], rest_stalled: bool, recover: bool = False,
              calm: bool = False, assailed: str | None = None) -> list[str]:
    """The actions that can be carried out right now, in ACTIONS order.

    `recover` (`Style.recover`): `rest` is also possible at full HP while `recovering`, and a rest that left HP
    where it was doesn't rule it out then (HP is full; the rest was for the time).
    `calm` (`Style.calm`): while `raging`, `explore` is not possible (DCSS would refuse it) and `rest` is, in
    the same way as for `recover`, so the rage can be waited out.
    `assailed` (`Style.unseen`, from `BrainTiers.assailed`): hurt with nothing in view. `flee_up` is then possible
    without a hostile in view (a step toward the stairs up, or up them), and when UNSEEN, `read_teleport` too.
    """
    inv, hostiles = obs["inv"], obs["n_hostiles"] > 0
    adjacent = any(max(abs(m["dx"]), abs(m["dy"])) <= 1 for m in obs["mons"])
    hurt = obs["hp"] < obs["hp_max"]
    status = obs.get("status") or []
    waiting_calm = calm and raging(obs)
    waiting_out = (recover and recovering(obs)) or waiting_calm
    calm = not any(x.startswith("Berserk") for x in status)             # no potions or scrolls in a rage
    can_read = calm and not any(x.startswith(("silenced", "Conf")) for x in status)
    # curing can be drunk at full HP while poisoned or confused; heal wounds can't
    ailing = inv.get("curing", 0) > 0 and _has(obs, "Pois", "Conf")
    unseen = not hostiles and assailed in (BURNING, UNSEEN)
    can = {
        "explore": not hostiles and not level_explored and not waiting_calm,
        "fight": hostiles,
        "rest": not hostiles and (hurt or obs["mp"] < obs["mp_max"] or waiting_out) and (not rest_stalled or waiting_out),
        "descend": obs["on_down"] or obs["dist_down"] >= 0,
        # the stairs up from D:1 leave the dungeon
        "flee_up": (hostiles or unseen) and (obs["on_up"] or obs["dist_up"] >= 0)
                   and not (obs["place"] in ("", "Dungeon") and obs["depth"] <= 1),
        "quaff_heal": inv["heal"] > 0 and (hurt or ailing) and calm,
        "quaff_unknown": inv["unknown_potions"] > 0 and calm,
        "read_unknown": inv["unknown_scrolls"] > 0 and can_read,
        # not while a teleport is already coming (`Tele`): a second scroll cancels it ("You feel strangely stable")
        "read_teleport": inv["teleport"] > 0 and (hostiles or (unseen and assailed == UNSEEN)) and can_read
                         and "Tele" not in status,
        "wait": hostiles and not adjacent,
        # Trog's Berserk: refused while berserk or exhausted, which the no-progress block then handles.
        # Never with poison that would kill once the rage is over: the rage would block the cure.
        "berserk": hostiles and obs.get("god") == "Trog" and not any(x.startswith(("Berserk", "-Berserk")) for x in status)
                   and not poison_lethal_after_rage(obs),
        # changing equipment takes several turns: never with something watching
        "wield": bool(inv.get("wield")) and not hostiles and calm,
        "wear": bool(inv.get("wear")) and not hostiles and calm,
    }
    return [a for a in ACTIONS if can[a] and a not in blocked]


CROWD = 3                 # hostiles in view that count as outnumbered for `teleport_rule` 2
OUTMATCHED = 1.5          # the hostiles' HP left (`foe_hp`) against the character's own HP now, for `teleport_rule` 3


def teleport_rule(obs: dict, level: int) -> tuple[bool, bool]:
    """When the opt-in teleport rules (`Style.teleport`) would read teleportation: (now, crowded).

    `now` is read first in a fight (after a cure and a retreat), `crowded` after a rage and the healing potion.
    - level 1 and 2, `now` when spent: just out of a rage, exhausted and slowed (`-Berserk` with `Slow`), with
      monsters in view. Another rage is refused and every action takes twice as long.
    - level 2, `crowded`: at least CROWD hostiles in view, one of them dangerous (webtiles threat 2 or 3).
      `baseline` puts it after a rage, so it covers a fight the rules wouldn't rage at, or can't.
    - level 3, `now` when outmatched: exhausted after a rage (`-Berserk`, slowed or not) and the hostiles in
      view have OUTMATCHED times the character's current HP or more left between them (`foe_hp`). This is
      the condition that best reproduces `v6-clean3`'s reads at `margin=0.6` (in the spells of exhaustion of
      the saved runs, 83% of the spells it fires in are ones the model read in, and it fires in 82% of
      those). Not the level 1 and 2 rules: those read at every spent moment.
    Neither while a teleport is already coming (`Tele`): a second scroll would cancel it. That the scroll can
    be read at all is `available`'s part.
    """
    status = obs.get("status") or []
    if level < 1 or not obs["n_hostiles"] or "Tele" in status:
        return False, False
    if level >= 3:
        return "-Berserk" in status and foe_hp(obs) >= OUTMATCHED * max(obs["hp"], 1), False
    spent = "-Berserk" in status and "Slow" in status
    crowded = level >= 2 and obs["n_hostiles"] >= CROWD and any(m["threat"] >= 2 for m in obs["mons"])
    return spent, crowded


def avoid_rule(obs: dict, k: float) -> bool:
    """`Style.avoid`: whether to read teleportation instead of starting the fight (and the rage) in view.

    With k > 0: hostiles in view with k times the character's maximum HP or more left between them (`foe_hp`, the
    measure `big_fight` uses at k = 1), the character neither raging nor exhausted after a rage (`Berserk`,
    `-Berserk`; exhausted is `teleport_rule`'s part), and no teleport already coming (`Tele`). In the current rules'
    saved games, rages begun at 1.5 times the maximum or more were followed by death within 50 turns 32% of the time
    (all rages: 6%). The scroll takes some turns to work, and a rage is still possible after reading, so the rules
    rage on the next choice if they would have (a teleport isn't cancelled by a rage). That the scroll can be read is
    `available`'s part."""
    status = obs.get("status") or []
    if k <= 0 or not obs["n_hostiles"] or "Tele" in status or any(x.startswith(("Berserk", "-Berserk")) for x in status):
        return False
    return foe_hp(obs) >= k * max(obs["hp_max"], 1)


def escape_rule(obs: dict, h: float) -> bool:
    """`Style.escape`: whether to read teleportation in a fight that is being lost while exhausted.

    With h > 0: hostiles in view, exhausted after a rage (`-Berserk`, not raging: no second rage is possible), HP at
    h times the maximum or under, and no teleport already coming (`Tele`). `teleport_rule` 3 reads in the same state
    only when the hostiles' HP left is 1.5 times the character's HP now; in the `calm=1` games of 2026-11-16 the
    character died with a known scroll unread in 14 of the 88 deaths on D:4-6 where the defaults got deeper, at 10-35%
    HP against hostiles with (mostly) 0.8-1.3 times that left, and read it, if at all, a turn before dying. That the scroll can
    be read is `available`'s part."""
    status = obs.get("status") or []
    if h <= 0 or not obs["n_hostiles"] or "Tele" in status or "Berserk" in status or "-Berserk" not in status:
        return False
    return obs["hp"] <= h * obs["hp_max"]


UNIQUE_THREAT = 3         # webtiles' threat level (3: "extremely dangerous" for this character) that `Style.unique` heeds


def dangerous_unique(obs: dict) -> bool:
    """A unique the game rates extremely dangerous for this character (threat UNIQUE_THREAT) in view, not adjacent."""
    return any(m.get("unique") and m["threat"] >= UNIQUE_THREAT and max(abs(m["dx"]), abs(m["dy"])) > 1
               for m in obs["mons"])


def unique_rule(obs: dict, on: float) -> bool:
    """`Style.unique`: whether to read teleportation at the sight of a dangerous unique (`dangerous_unique`).

    Not while raging (no scroll can be read) and not with a teleport already coming (`Tele`). In the `calm=1` games of
    2026-11-16 a unique was in the fatal fight in 27 of the 88 deaths on D:4-6 where the defaults got deeper (13 of 61
    the other way round), and after first sight of a threat-3 unique 22% of those characters died within 100 turns.
    `baseline` holds the rage while the teleport is coming; `BrainTiers` leaves the level once the scroll is read."""
    status = obs.get("status") or []
    if not on or not obs["n_hostiles"] or "Tele" in status or "Berserk" in status:
        return False
    return dangerous_unique(obs)


def late_rage(obs: dict, near: list[dict], h: float) -> bool:
    """`Style.rage`: whether to start a rage now, the hostiles within two squares being `near` (not empty).

    qw's rule as this project's qw plays it (`want_to_berserk` with the tuned `zerk_hp70`, runs/qw/combo1-lua/
    MiBe_mace.lua): at 70% HP or under with an enemy within two that can reach it, or when the threat within two is
    high. Here: HP at h times the maximum or under (and always at half, as the rules have it); or the hostiles within
    two have the character's maximum HP or more left between them (`foe_hp` of those alone: on block A qw raged at
    11-18% of its choices above 70% HP in that state, against 0.2-1% otherwise); or one of them is threat 3
    (qw's "scary" enemy). On block A's levels D:3-7 qw raged in 14% of its fights, at a median 67% HP, the rules in
    56%, at a median 100% HP, and 4.2% of the rules' fights began exhausted (qw: 0.6%)."""
    frac = obs["hp"] / max(obs["hp_max"], 1)
    return frac <= max(h, 0.5) or any(m["threat"] >= 3 for m in near) or \
        foe_hp(obs, near) >= max(obs["hp_max"], 1)


AWAKE = 0                 # `beh` of a monster that is awake and neither unaware, fleeing nor helpless (features.BEHAVIOUR)
HOLD_FROM = 3             # `hold_ground` waits only while every hostile is this many squares away or more: a monster
                          # with a polearm hits from two, and nothing in view says which ones carry one (the first
                          # `hold=10` on block A, waiting at two, had 68 deaths with "hits you from afar" in the last
                          # messages against the defaults' 16)


def hold_ground(obs: dict) -> bool:
    """`Style.hold`: whether waiting would let the hostiles in view come to the character, as qw's
    `plan_melee_wait_for_enemy` waits for an enemy that can reach it but not yet hit it (`player_can_wait_for_melee`).

    Hostiles in view, none within HOLD_FROM - 1 squares; none that the monster table (`monsters.lookup`) says attacks from range or with
    reach (qw moves in on a ranged enemy rather than be shot while waiting); and at least one awake (`beh` AWAKE: not
    asleep, unaware, fleeing or helpless) and able to move (table speed above 0), since nothing else will come.
    `BrainTiers` caps the waits in a row."""
    if not obs["n_hostiles"] or any(max(abs(m["dx"]), abs(m["dy"])) < HOLD_FROM for m in obs["mons"]):
        return False
    coming = False
    for m in obs["mons"]:
        k = monsters.lookup(m["name"])
        if k and ({"ranged", "reach"} & set(k["kinds"])):
            return False
        coming = coming or (m.get("beh", AWAKE) == AWAKE and (k is None or k["speed"] > 0))
    return coming


# qw's `hand_monsters` (runs/qw/build-zk/qw.lua 8064-8095): Trog's Hand while one of these is in view and the
# character's XL is under the number (`monster_in_list`). Names as the game gives them, compared without case.
HAND_MONSTERS = {
    "grinder": 10, "orc sorcerer": 17, "wizard": 17,
    **dict.fromkeys(("ogre mage", "rupert", "xtahua", "aizul", "erolcha", "louise", "lich", "ancient lich",
                     "dread lich", "kirke", "golden eye", "deep elf sorcerer", "deep elf demonologist", "sphinx",
                     "great orb of eyes", "vault sentinel", "the enchantress", "satyr", "fenstrider witch",
                     "vampire knight", "siren", "merfolk avatar"), 100),
}
HAND_PIETY = 2            # piety rank (stars) Trog's Hand needs (qw's `can_trogs_hand`)


def hand_wanted(god: str, piety: int, xl: int, status: list[str], names: list[str], hp_frac: float,
                heal_held: bool) -> bool:
    """`Style.hand`: whether to invoke Trog's Hand now, as qw's `want_to_trogs_hand` with `can_trogs_hand` does.

    Trog, piety rank HAND_PIETY or more, able to invoke (not raging, confused or silenced: qw's `can_invoke`), not
    already regenerating from it (the status line's "Regen Will++") and no teleport coming (`Tele`), and a monster on
    HAND_MONSTERS in view while the character's XL is under its number. qw drinks heal wounds before the Hand when hurt
    (`plan_heal_wounds` comes first in its emergency cascade), so not at half HP or under with a healing potion held."""
    if god != "Trog" or piety < HAND_PIETY:
        return False
    if any(x == "Berserk" or x.startswith(("Conf", "silenced", "Regen", "Tele")) for x in status):
        return False
    if hp_frac <= 0.5 and heal_held:
        return False
    return any(xl < HAND_MONSTERS.get(n.lower(), 0) for n in names)


def moderate_threat(xl: int) -> int:
    """qw's `moderate_threat_level` (qw.lua 7921-7923): 2 up to XL 7, then one more per level to 5 at XL 10."""
    return 5 - max(0, min(3, 10 - xl))


def throw_wanted(obs: dict, missiles: int) -> bool:
    """`Style.throw`: whether qw would throw now (`plan_throw` with `get_throwing_target`, runs/qw/build-zk/qw.lua
    11189-11201, `get_throwing_target_func` 587-605), given `missiles` held. Where the shot goes is the rc's `ladder_throw` (`gear.THROW_RC`).

    - Not raging, confused or held (`unable_to_throw`, 15846-15856): the game refuses a throw in a rage.
    - Hostiles in view and none adjacent: with one to hit in melee, qw's throw "prefers melee" (`prefer_melee`) and
      doesn't throw (`get_ranged_attack_target`, 490-536).
    - A threat-3 hostile in view (qw's "scary" enemy): out of reach of the mace, the throw is its best attack
      (`get_high_threat_target` 558-585, `monster_best_player_attack` 935-955).
    - Otherwise only while the threat in view (the hostiles' webtiles threat summed, as qw's `assess_enemies` sums
      `minfo:threat()`) is under qw's moderate level for the XL (`have_moderate_threat` 8366-8369): against more, qw closes in
      or waits; and not with a hostile in view that attacks from range or with reach (by the monster table), which qw
      walks up to instead (`get_ranged_attack_target`'s `is_ranged` check).
    Whether the rules of thumb would walk up or wait at all (not drink, read, retreat or rage first) is `BrainTiers`'."""
    status = obs.get("status") or []
    if missiles <= 0 or not obs["n_hostiles"] or any(x == "Berserk" or x.startswith(("Conf", "Held")) for x in status):
        return False
    mons = obs["mons"]
    if any(max(abs(m["dx"]), abs(m["dy"])) <= 1 for m in mons):
        return False
    if any(m["threat"] >= 3 for m in mons):
        return True
    if sum(m["threat"] for m in mons) >= moderate_threat(obs["xl"]):
        return False
    for m in mons:
        k = monsters.lookup(m["name"])
        if k and {"ranged", "reach"} & set(k["kinds"]):
            return False
    return True


KIT_PARTS = {1: "gear", 2: "acquire", 4: "shop"}
SHOP_GOLD = 20            # `Style.kit` 2 "shop": gold below this isn't worth a walk to a shop
SHOP_STEPS = 80           # ...and a shop more steps away than this is given up for this visit to the level
SAVE_HEAL = 0.25          # `Style.save`: the HP fraction a healing potion waits for in a fight (qw's hp_is_low(25))
ACQUIRE_GOLD = (0.5, 3.0)  # what the acquirement's gold is worth (armour plus points) without and with "shop"


def kit_parts(style: Style) -> set[str]:
    """The parts of `Style.kit` 2 that are on (none below 2)."""
    if style.kit < 2:
        return set()
    bits = int(style.kitpart) or sum(KIT_PARTS)
    return {name for bit, name in KIT_PARTS.items() if bits & bit}


STEP_MAX = 3              # `Style.step`: steps per fight at most (the count starts again once nothing is in view)
STEP_INTO = {MF_DOOR, MF_WATER, MF_TRAP}   # not stepped into: a door may be shut (opening it is no step), shallow
                                           # water slows (qw's `a.slow`), a trap isn't safe (qw's `is_safe_at`)
OPEN_DOOR = "'"


def step_square(state: GameState, hostiles: list, need: float) -> tuple[int, int] | None:
    """`Style.step`: the direction (dx, dy) of a step out of a surround, as qw's `choose_tactical_step` with reason
    "outnumbered" (runs/qw/build-zk/qw.lua: `choose_tactical_step` 9941-10005, `step_reason` 9798-9875 with the
    "outnumbered" case at 9862-9870, `assess_square_enemies` 9686-9735),
    or None.

    Only with two or more of `hostiles` adjacent. A square counts the hostiles that could hit there next turn: those
    adjacent to it, and those two away that the monster table says are faster than the character (qw's `a.ranged`; a
    ranged attacker in view counts the same from every square, so it is left out). A step is taken to the free
    adjacent square (walkable, no monster, no cloud, not a shut door, shallow water or a trap) whose count is `need`
    or more below the count here; among those, the lowest count, then the one nearest a hostile (qw's
    `step_improvement`: stay in the fight), then the first in `DIRECTIONS` order."""
    px, py = state.pos
    if sum(1 for m in hostiles if state.distance(m.pos) <= 1) < 2:
        return None
    speeds = {m.id: (monsters.lookup(m.name) or {}).get("speed", 10) for m in hostiles}

    def count(sq: tuple[int, int]) -> int:
        n = 0
        for m in hostiles:
            d = max(abs(m.pos[0] - sq[0]), abs(m.pos[1] - sq[1]))
            n += d <= 1 or (d == 2 and speeds[m.id] > 10)
        return n

    here = count(state.pos)
    taken = {m.pos for m in state.monsters()}
    best = None
    for dx, dy in DIRECTIONS:
        sq = (px + dx, py + dy)
        cell = state.cells.get(sq)
        if cell is None or sq in taken or (cell.get("t") or {}).get("cloud"):
            continue
        mf = cell.get("mf", 0)
        if mf in NOT_WALKABLE or (mf in STEP_INTO and not (mf == MF_DOOR and cell.get("g") == OPEN_DOOR)):
            continue
        n = count(sq)
        if n > here - need:
            continue
        near = min(max(abs(m.pos[0] - sq[0]), abs(m.pos[1] - sq[1])) for m in hostiles)
        if best is None or (n, near) < best[0]:
            best = ((n, near), (dx, dy))
    return best[1] if best else None


def disturb_square(state: GameState, k: int) -> tuple[int, int] | None:
    """`Style.calm` 2: the direction of a step to a free adjacent square (walkable, no monster, no cloud, not a shut
    door, shallow water, a trap or a shop), the k-th such in `DIRECTIONS` order, going round. qw's
    `random_step` picks one at random; a fixed turn of the list keeps a replay the same game."""
    px, py = state.pos
    taken = {m.pos for m in state.monsters()}
    shops = state.shops()
    free = []
    for dx, dy in DIRECTIONS:
        sq = (px + dx, py + dy)
        cell = state.cells.get(sq)
        if cell is None or sq in taken or sq in shops or (cell.get("t") or {}).get("cloud"):
            continue
        mf = cell.get("mf", 0)
        if mf in NOT_WALKABLE or (mf in STEP_INTO and not (mf == MF_DOOR and cell.get("g") == OPEN_DOOR)):
            continue
        free.append((dx, dy))
    return free[k % len(free)] if free else None


def unknown_pair(state: GameState) -> str | None:
    """`Style.save`: the letter of the largest unknown potion stack holding two or more, else None."""
    best = None
    for item in (state.player.get("inv") or {}).values():
        name, qty = item.get("name", ""), item.get("quantity", 1) or 0
        if item.get("base_type") != POTIONS or qty < 2 or (" of " in name and "{unknown}" not in name):
            continue
        if best is None or qty > best[0]:
            best = (qty, chr(item.get("letter", ord("a"))))
    return best[1] if best else None


def _unknown(item: dict) -> bool:
    """An unidentified potion or scroll, as `features.inventory` tells one."""
    name = item.get("name", "")
    return item.get("base_type") in (POTIONS, gear.SCROLLS) and (item.get("quantity", 1) or 0) > 0 and \
        bool(name) and not (" of " in name and "{unknown}" not in name)


def ident_scroll(state: GameState) -> str | None:
    """`Style.ident`: the letter of a known scroll of identify, when an unknown potion or scroll is held (qw's
    `plan_use_identify_scrolls` with `get_unidentified_item`, qw.lua 13796-13812, 13983-14003), else None."""
    inv = (state.player.get("inv") or {}).values()
    if not any(_unknown(item) for item in inv):
        return None
    for item in inv:
        name = item.get("name", "")
        if item.get("base_type") == gear.SCROLLS and (item.get("quantity", 1) or 0) > 0 and \
                "identify" in name and not _unknown(item):
            return chr(item.get("letter", ord("a")))
    return None


IDENT_QTY = re.compile(r"^\s*\w - (\d+) ")


def ident_choice(menu: list[tuple[str, str, bool]]) -> str | None:
    """`Style.ident`: the line of the identify prompt ("Identify which item?", which lists only unknown items) that qw's
    `get_unidentified_item` (qw.lua 13983-14003, the later of its two definitions; `c_choose_identify` 14005) would pick: a potion before a scroll, the smallest stack first, the
    first of equal stacks; nothing else (qw identifies only potions and scrolls). None: nothing fits."""
    best = None
    for letter, text, _ in menu:
        kind = 0 if "potion" in text else 1 if "scroll" in text else None
        if kind is None:
            continue
        m = IDENT_QTY.match(text)
        key = (kind, int(m.group(1)) if m else 1)
        if best is None or key < best[0]:
            best = (key, letter)
    return best[1] if best else None


RENAMED = re.compile(r"^(?:\w -> )?(\w) - (.+)$")


def rename_identified(state: GameState, messages: list[dict]) -> None:
    """`Style.ident`: after an identify, write the item's new name into the pack as the game's message gives it
    ("d -> b - a potion of brilliance"). Webtiles sends the moved item's new letter and flags but not its new name (seen
    in `v6l/A-ident`: the pack kept "cyan potion" at `b`, and the rules tried to drink it to identify it, 808 times
    with no game time passing), so without this an identified potion stays unknown to the rules."""
    inv = state.player.get("inv") or {}
    for batch in messages:
        if batch.get("msg") != "msgs":
            continue
        for m in batch.get("messages", []):
            for part in strip_tags(m.get("text", "")).split("; "):
                hit = RENAMED.match(part.strip())
                if not hit:
                    continue
                letter, name = ord(hit.group(1)), re.sub(r"^(a|an) ", "", hit.group(2).strip())
                for item in inv.values():
                    if item.get("letter") == letter and item.get("base_type") in (POTIONS, gear.SCROLLS):
                        item["name"] = name


KIT_SCROLLS = ("enchant armour", "enchant weapon", "brand weapon")


def kit_scroll(state: GameState, parts: set[str] = frozenset()) -> str | None:
    """`Style.kit`: the letter of a known enchant armour, enchant weapon or brand weapon scroll worth reading now, else
    None. A weapon scroll only with a ranked weapon in hand (`gear.weapon`), and brand weapon only onto one without a
    brand (a new brand replaces the old at random). With kit 2's "gear" part the weapon is ranked and its brand read as
    the pack names them (`gear.weapon2`, `gear.brand_of`); with "acquire", a known acquirement scroll is read too."""
    inv = state.player.get("inv") or {}
    wielded = inv.get(str(state.player.get("weapon_index", -1)))
    if "gear" in parts:
        ranked = bool(wielded and gear.weapon2(wielded))
        branded = bool(wielded and gear.brand_of(wielded.get("name", "")))
    else:
        ranked = bool(wielded and gear.weapon(wielded))
        branded = bool(wielded and " of " in wielded.get("name", ""))
    for item in inv.values():
        name = item.get("name", "")
        if item.get("base_type") != gear.SCROLLS or (item.get("quantity", 1) or 0) <= 0 or "{unknown}" in name:
            continue
        if "enchant armour" in name or (ranked and "enchant weapon" in name) or \
                (ranked and "brand weapon" in name and not branded) or ("acquire" in parts and "acquirement" in name):
            return chr(item.get("letter", ord("a")))
    return None


def baseline(obs: dict, avail: list[str], level_explored: bool, wiki: bool = False, teleport: int = 0,
             recover: int = 0, calm: bool = False, retreat: bool = False, rest_out: bool = False,
             to_stairs: bool = False, assailed: str | None = None, avoid: float = 0.0, escape: float = 0.0,
             unique: float = 0.0, rage: float = 0.0, hold: bool = False, heal_at: float = 0.5,
             gamble: bool = False, cure: bool = False) -> str:
    """Rules of thumb: the stub's behaviour, plus drinking a healing potion instead of giving up.

    `wiki` plays the variant that follows the DCSS wiki's strategy guides instead (`Style.wiki`).
    `teleport` 1, 2 or 3 adds the opt-in teleport rules (`teleport_rule`, `Style.teleport`); 0 leaves them out.
    `recover` 1 rests out a rage and its exhaustion (`recovering`) with nothing in view before taking the
    stairs, 2 before exploring on as well (`Style.recover`); 0 leaves it out. `avail` must then come from
    `available(..., recover=True)`, or `rest` is seldom there at full HP.
    `calm` waits out a rage (`raging`) with nothing in view before exploring on (`Style.calm`); `avail` must
    then come from `available(..., calm=True)`.
    The next three are `BrainTiers`' to set, since they depend on what came before (`Style.retreat`, `Style.stairs`):
    `retreat` heads up the stairs with hostiles in view (after a healing potion at half HP); `rest_out` rests
    with nothing in view before going on, as `recover` 2 does (`avail` then from `available(..., recover=True)`);
    `to_stairs` walks toward the stairs up before a fight.
    `assailed` (`BrainTiers.assailed`, `Style.unseen`) with nothing in view: BURNING walks toward the stairs up (or
    down), UNSEEN reads teleportation, else goes up the stairs; `avail` then from `available(..., assailed=...)`.
    `avoid` (`Style.avoid`) reads teleportation before a rage when `avoid_rule` holds, `escape` (`Style.escape`) when
    `escape_rule` does, `unique` (`Style.unique`) when `unique_rule` does; with `unique`, while that teleport is coming
    and the unique is still in view and not adjacent, the rules keep away (toward the stairs up, else wait) instead of
    raging.
    `rage` (`Style.rage`) starts a rage only when `late_rage` holds, not at the first threat-2 monster within two.
    `hold` (`BrainTiers` from `Style.hold` and `hold_ground`) waits for the hostiles in view to come instead of
    walking to them.
    `heal_at`: in a fight, a healing potion is drunk at this fraction of the maximum HP or under (`Style.save`
    lowers it to SAVE_HEAL); the cure for serious poison is drunk whatever the HP. `gamble` (`Style.save`): at that
    HP with no healing potion known, drink an unknown potion (qw's `heal_general`: `quaff_unided_potion()` when heal
    wounds is not identified); a fifth of the unknown potions the rules drank were curing or heal wounds.
    `cure` (`Style.cure`): curing also when `cure_wanted` holds (confusion, poison as qw counts it), first as the
    serious-poison cure is; and a potion for HP only with heal wounds held (`BrainTiers.perform` then drinks that).
    """
    if wiki:
        return baseline_wiki(obs, avail, level_explored)
    frac = obs["hp"] / max(obs["hp_max"], 1)
    sick = needs_cure(obs) or (cure and cure_wanted(obs))
    gamble_at = heal_at
    if cure:
        # Style.cure: curing is never drunk for HP, so a potion for HP waits for heal wounds
        heal_at = heal_at if obs["inv"].get("heal_wounds", 0) > 0 else -1.0
    cure = ["quaff_heal"] if sick else []                 # serious poison: curing first, before any rage
    if obs["n_hostiles"]:
        near = [m for m in obs["mons"] if max(abs(m["dx"]), abs(m["dy"])) <= 2]
        if rage > 0:
            go = bool(near) and late_rage(obs, near, rage)
        else:
            go = frac <= 0.5 or any(m["threat"] >= 2 for m in near) or len(near) >= 3
        now, crowded = teleport_rule(obs, teleport)
        if retreat:
            away = (["quaff_heal"] if frac <= heal_at else []) + ["flee_up"]
        else:
            away = ["flee_up"] if to_stairs else []
        now = now or avoid_rule(obs, avoid) or escape_rule(obs, escape) or unique_rule(obs, unique)
        if unique and "Tele" in (obs.get("status") or []) and dangerous_unique(obs):
            # the scroll is working: keep the unique at a distance until it does (a healing potion first at half HP)
            away = away + (["quaff_heal"] if frac <= heal_at else []) + ["flee_up", "wait"]
        order = cure + away + (["read_teleport"] if now else []) + (["berserk"] if go and near else []) + \
                (["quaff_heal"] if frac <= heal_at else []) + \
                (["quaff_unknown"] if gamble and frac <= gamble_at and not obs["inv"]["heal"] else []) + \
                (["read_teleport"] if crowded else []) + \
                (["wait"] if hold else []) + ["fight", "descend", "flee_up", "wait"]
    else:
        onward = ["descend"] if level_explored else ["explore"]
        if rest_out and recovering(obs):
            onward = ["rest"] + onward              # gone up from a fight: rest it off before going on
        elif recover and recovering(obs) and (level_explored or recover >= 2):
            onward = ["rest"] + onward              # arrive, or explore on, able to rage and at full speed
        elif calm and raging(obs) and not level_explored:
            onward = ["rest"] + onward              # explore is refused until the rage is over
        # hurt by what can't be seen: rest and explore are refused ("You are on fire!"), and waiting only burns
        away = {BURNING: ["flee_up", "descend"], UNSEEN: ["read_teleport", "flee_up"]}.get(assailed, [])
        order = cure + away + ["wield", "wear"] + (["rest"] if frac < 0.8 else ["read_unknown", "quaff_unknown"]) + \
                onward + ["rest", "descend", "explore"]
    return next((a for a in order if a in avail), avail[0])


STAIRS_IN_REACH = 4       # steps to the stairs up that a hurt character walks before anything is adjacent


def baseline_wiki(obs: dict, avail: list[str], level_explored: bool) -> str:
    """The rules of thumb with the DCSS wiki's advice worked in (docs/wiki-strategy.md has the sources).

    What differs from `baseline`:
    - Explore only at full HP: rest whenever hurt, not only below 80%.
    - A rage blocks potions and scrolls, so a healing potion is drunk before going berserk, not after.
    - Hurt, with stairs up close and nothing adjacent yet: go up. Only adjacent monsters follow.
    - Berserk exhausted or refused and HP at 30%: teleport, then try unknown potions, then unknown scrolls.
    Both drink curing first when seriously poisoned (`needs_cure`).
    """
    frac = obs["hp"] / max(obs["hp_max"], 1)
    cure = ["quaff_heal"] if needs_cure(obs) else []
    if obs["n_hostiles"]:
        dists = [max(abs(m["dx"]), abs(m["dy"])) for m in obs["mons"]]
        near = [m for m, d in zip(obs["mons"], dists) if d <= 2]
        adjacent = any(d <= 1 for d in dists)
        tough = any(m["threat"] >= 2 for m in near) or len(near) >= 3
        order = list(cure)
        if frac <= 0.5:
            order.append("quaff_heal")
            if not adjacent and (obs["on_up"] or 0 <= obs["dist_up"] <= STAIRS_IN_REACH):
                order.append("flee_up")
        if near and (tough or frac <= 0.5):
            order.append("berserk")
        if frac <= 0.3:
            order += ["read_teleport", "quaff_unknown", "read_unknown"]
        order += ["fight", "descend", "flee_up", "wait"]
    else:
        order = cure + ["wield", "wear"] + (["rest"] if frac < 1.0 else ["read_unknown", "quaff_unknown"]) + \
                (["descend"] if level_explored else ["explore"]) + ["rest", "descend", "explore"]
    return next((a for a in order if a in avail), avail[0])


class BrainTiers(StubTiers):
    """Reflex's tiers object with the trained brain choosing. Without a net it plays the baseline."""

    def __init__(self, net: TrainedNet | Ensemble | None = None, style: Style | None = None, epsilon: float = 0.0,
                 rng: random.Random | None = None, script: list[str] | None = None, horizon: int = 0,
                 commit: bool = False):
        super().__init__()
        # A fork (forks.py): replay `script`'s choices, whose last one is the alternative being tried,
        # then play on as usual for `horizon` game turns (0 = to the end). With `commit`, a fork to
        # `descend` (or `explore`) keeps taking it on that level wherever the rules would take the other.
        self.script, self.horizon, self.commit = script or [], horizon, commit
        self.choices = 0
        self.fork_turn: int | None = None
        self.committed: tuple[str, str, int] | None = None     # (action, the one it replaces, level_seq)
        self.net, self.style, self.epsilon = net, style or Style(), epsilon
        self.rng = rng or random.Random()
        self.blocked: dict[str, int] = {}      # action -> the turn it may be tried again
        self.stalls: dict[str, int] = {}       # action -> times in a row it used no game time
        self.idle = 0                          # waits in a row for want of anything else
        self.last: dict | None = None          # the choice just made
        self.sink = None                       # called with each choice (steplog.StepLog.attach)
        self.choice: str | None = None
        self.level_steps = 0
        self.level_turn = 0
        self.prev_frac: float | None = None
        self.last_action: str | None = None
        self.fenced: set = set()               # (level, shop square) already excluded from explore
        self.worn: dict[str, str] | None = None   # armour kind -> inventory slot (gear.py)
        self.was_raging = False                # `raging` at the choice before (Style.retreat)
        self.retreat_from: int | None = None   # level_seq of the level being left after a rage ran out
        self.stairs_done = False               # this fight has had its walk to the stairs (Style.stairs)
        self.unseen_hits = 0                   # falls in HP in a row with nothing in view (Style.unseen)
        self.prev_status: list[str] = []       # the status line at the choice before
        self.calm_now = bool(self.style.calm)  # Style.calm holds at this choice (Style.calmfor can end it on a level)
        self.holds = 0                         # waits in a row for the hostiles to come (Style.hold)
        self.auto: str | None = None           # the automatic step just taken (Style.kit, Style.hand), if any
        self.auto_blocked: dict[str, int] = {}  # automatic step -> the turn it may be tried again after going nowhere
        self.jewels: set[str] = set()          # letters of the rings and amulets on (Style.kit), as the P menu shows
        self.kit_counts: dict[str, int] = {}   # what the automatic steps did, for the end of game record
        self.steps_taken = 0                   # Style.step: steps out of a surround in this fight (STEP_MAX)
        self.step_way: tuple[int, int] = (0, 0)   # Style.step: the direction `auto_step` chose
        self.parts = kit_parts(self.style)     # Style.kit 2's parts that are on
        self.rank_kit = 2 if "gear" in self.parts else bool(self.style.kit)   # the ranking wield and wear use
        self.shops_done: set = set()           # Style.kit 2 "shop": (level_seq, shop square) visited or given up
        self.shop_steps = 0                    # ...steps walked toward the shop being visited
        self.shop_goal: tuple | None = None    # ...(level_seq, shop square) being walked to
        self.shop_back: tuple[int, int] | None = None   # ...the direction of the last step taken toward it
        self.shop_leave: tuple | None = None   # ...(level_seq, square) of the shop just visited, to step off once
        self.shop_opened = False               # ...the step just taken opened a shop (it takes no game time)
        self.disturbed = False                 # Style.calm 2: explore was just refused for a disturbance
        self.disturb_steps = 0                 # ...steps taken away from one on this level visit (DISTURB_MAX)
        self.cure_now = False                  # Style.cure: `cure_wanted` held at the last choice (curing, not heal wounds)
        self.route = LairRoute(int(self.style.lair)) if self.style.lair else None   # Style.lair

    # --- choosing ------------------------------------------------------

    def next_action(self, state: GameState) -> str:
        self.last = self.choice = self.auto = None
        hostiles = self.active_hostiles(state)
        if not hostiles:
            self.approach = False
            self.steps_taken = 0
        if state.caught:
            return "struggle"
        shops = {(state.level_seq, s) for s in state.shops()}
        if shops - self.fenced:
            self.fenced |= shops
            # Before explore can walk into one (see crawlrc.txt). The brain has no action that buys,
            # so unlike StubTiers it never visits a shop: stepping onto a fenced square asks "really?".
            return "fence_shops"
        if self.worn is None:                  # joining a game part-way: found out by trying
            self.worn = gear.initial_worn(state) if state.turn <= 1 else {}
        if (auto := self.auto_step(state, hostiles)):
            self.auto = auto                   # not a choice: no step log line, nothing the model sees
            return auto
        frac = state.hp / state.hp_max
        obs = observe(state, hostiles, {
            "worn": self.worn, "kit": bool(self.style.kit),
            "level_explored": self.level_explored, "level_steps": self.level_steps, "level_turn": self.level_turn,
            "hp_delta": 0.0 if self.prev_frac is None else frac - self.prev_frac, "last_action": self.last_action})
        self.prev_frac = frac
        blocked = {a for a, until in self.blocked.items() if state.turn < until} | self.save_blocked(state, hostiles)
        retreat, rest_out, to_stairs = self.fight_moves(state.level_seq, obs)
        assailed = self.assailed(obs)
        # Style.calmfor: calm only for the first T turns of this visit to the level
        self.calm_now = bool(self.style.calm) and (not self.style.calmfor or obs["level_turns"] < self.style.calmfor)
        avail = available(obs, self.level_explored, blocked, self.rest_stalled_at == (state.turn, state.hp),
                          recover=bool(self.style.recover) or rest_out, calm=self.calm_now, assailed=assailed)
        if not avail and "wait" not in blocked and self.idle < IDLE_LIMIT:
            # Everything else went nowhere: let a turn pass. Now and then look again, since "partly
            # explored, can't reach some places" stops being true once a cloud of gas has cleared.
            avail = ["wait"]
            self.idle += 1
            if self.idle % 10 == 0:
                self.level_explored = False
                self.blocked.pop("explore", None)
        if self.level_steps > LEVEL_STEP_LIMIT:
            raise Escalation(f"{self.level_steps} choices on this level without leaving it")
        if not avail:
            raise Escalation("nothing the brain can do here" + (f" (tried: {', '.join(sorted(blocked))})" if blocked else ""))
        # Style.hold: up to k waits in a row for the hostiles to come; any other choice starts the count again, so
        # after k waits the rules take one step toward them and may wait again, as qw's wait_count does
        hold = bool(self.style.hold) and self.holds < self.style.hold and hold_ground(obs)
        base = baseline(obs, avail, self.level_explored, wiki=bool(self.style.wiki), teleport=int(self.style.teleport),
                        recover=int(self.style.recover), calm=self.calm_now, retreat=retreat,
                        rest_out=rest_out, to_stairs=to_stairs, assailed=assailed, avoid=self.style.avoid,
                        escape=self.style.escape, unique=self.style.unique, rage=self.style.rage, hold=hold,
                        heal_at=SAVE_HEAL if self.style.save else 0.5, gamble=bool(self.style.save),
                        cure=bool(self.style.cure))
        self.cure_now = bool(self.style.cure) and cure_wanted(obs)
        choice, source, extra = base, "baseline", {}
        if self.fork_turn is not None and self.horizon and state.turn > self.fork_turn + self.horizon:
            raise Escalation(FORK_DONE)
        if self.choices < len(self.script):
            choice = self.script[self.choices]
            source = "fork" if self.choices == len(self.script) - 1 else "replay"
            if choice not in avail:
                raise Escalation(f"{REPLAY_DIVERGED} at choice {self.choices + 1}: {choice} not in {avail}")
            if source == "fork":
                self.fork_turn = state.turn
                if self.commit and choice in COMMITS:
                    self.committed = (choice, COMMITS[choice], state.level_seq)
        elif self.committed and self.committed[2] == state.level_seq and base == self.committed[1] \
                and self.committed[0] in avail:
            # a descend fork is one step toward the stairs; the rules would turn back to exploring
            choice, source = self.committed[0], "commit"
        elif len(avail) > 1 and self.rng.random() < self.epsilon:
            choice, source = self.rng.choice(avail), "random"
        elif self.net and len(avail) > 1:
            choice, extra = self.prefer(obs, avail, base)
            source = "net"
        self.last = {"obs": obs, "avail": avail, "baseline": base, "action": choice, "source": source, **extra}
        self.choice = self.last_action = choice
        self.holds = self.holds + 1 if hold and choice == "wait" else 0
        if choice == "read_teleport" and unique_rule(obs, self.style.unique):
            self.level_explored = True          # Style.unique: once away from it, leave rather than explore back into it
        self.choices += 1
        self.level_steps += 1
        if self.sink:
            self.sink(self.last)
        if choice == "fight":
            return "approach" if self.approach else "fight"
        if choice == "descend":
            return "descend" if obs["on_down"] else "travel"
        return choice

    def auto_step(self, state: GameState, hostiles: list) -> str | None:
        """An automatic step to take before the brain chooses, as `fence_shops` is, or None. Only with `Style.hand` or
        `Style.kit` on; none changes the observation, the actions or the step log, so a saved model plays as before.
        - "trogs_hand" (`hand`): when `hand_wanted` holds.
        - "read_kit" (`kit`): nothing in view, no rage, able to read: a known enchant or brand scroll (`kit_scroll`).
        - "put_on" (`kit`): nothing in view, no rage: a ring or amulet to put on or take off (`gear.jewellery_choice`).
        - "step" (`step`): out of a surround (`step_square`), not raging or confused, at most STEP_MAX per fight, where
          the rules of thumb would fight, wait or rage (qw takes its tactical step after its heal, teleport and flight
          and before its rage: `set_plan_emergency`, qw.lua 12594-12644).
        - "throw" (`throw`): when `throw_wanted` holds and the rules of thumb would walk up to the hostiles or wait for
          them (qw's `plan_throw` is in its attack plans, after all of the emergency ones).
        - "read_ident" (`ident`): nothing in view, no rage, able to read: a known identify scroll while something is
          unknown (`ident_scroll`), after the kit's steps (qw's `plan_use_identify_scrolls`).
        - kit 2, nothing in view and no rage: "equip" ("gear": a better weapon or armour by `gear.upgrades` at kit 2,
          before any scroll so an enchantment lands on the piece kept), "read_kit" as above (with "acquire", a known
          acquirement scroll too), "put_on" by `gear.jewel2`, and "kit_shop" ("shop": a step toward, or into, a shop on
          this level not yet visited, with SHOP_GOLD or more and half HP or more).
        - `lair`, nothing in view, after all of the above: "lair_scan" (a branch staircase not yet looked at is on the map
          and the Lair's entrance isn't known: the rc's `ladder_find_lair`, no game time), then "lair" where the rules of
          thumb would take the stairs down (`rules_now` gives "descend", or nothing at all) and the route wants other
          stairs (`route.LairRoute.wants`): toward the Lair's entrance or the stairs up, or through them (`lair_step`).
        A step that used no game time is not tried again for BLOCK_TURNS turns (`observe`); a throw that found no clear
        shot, for THROW_RETRY."""
        if self.disturbed:
            self.disturbed = False
            if not hostiles and self.style.calm >= 2 and disturb_square(state, self.disturb_steps):
                return "disturb_step"
        if not (self.style.kit or self.style.hand or self.style.throw or self.style.step or self.style.ident or
                self.route):
            return None
        status = state.statuses

        def ok(step: str) -> bool:
            return state.turn >= self.auto_blocked.get(step, 0)

        if self.style.hand and hostiles and ok("trogs_hand"):
            if hand_wanted(state.player.get("god") or "", state.player.get("piety_rank", 0) or 0,
                           state.player.get("xl", 1) or 1, status, [m.name for m in hostiles],
                           state.hp / max(state.hp_max, 1), inventory(state)["heal"] > 0):
                return "trogs_hand"
        if hostiles and "Berserk" not in status and not any(x.startswith("Conf") for x in status):
            if self.style.step and self.steps_taken < STEP_MAX and ok("step"):
                way = step_square(state, hostiles, self.style.step)
                if way and self.rules_now(state, hostiles)[1] in ("fight", "wait", "berserk"):
                    self.step_way = way
                    return "step"
            if self.style.throw and ok("throw"):
                held = sum(gear.missiles(state).values())
                if held:
                    obs, rules = self.rules_now(state, hostiles)
                    if rules in ("fight", "wait") and throw_wanted(obs, held):
                        return "throw"
        if self.style.kit and not hostiles and "Berserk" not in status:
            if "gear" in self.parts and ok("equip"):
                up = gear.upgrades(state, self.worn or {}, kit=2)
                if up["wield"] or up["wear"]:
                    return "equip"
            readable = not any(x.startswith(("silenced", "Conf")) for x in status)
            if readable and ok("read_kit") and kit_scroll(state, self.parts):
                return "read_kit"
            if ok("put_on") and gear.jewellery_choice(self.jewel_pieces(state), kit=self.rank_kit or 1):
                return "put_on"
            if "shop" in self.parts and ok("kit_shop") and (self.on_visited_shop(state) or self.shop_target(state)):
                return "kit_shop"             # not "shop": that name is Reflex's own walk into a shop
        if self.style.ident and not hostiles and "Berserk" not in status and ok("read_ident") and \
                not any(x.startswith(("silenced", "Conf")) for x in status) and ident_scroll(state):
            return "read_ident"
        if self.route and not hostiles:
            if self.route.needs_scan(state):
                return "lair_scan"
            # where the rules of thumb would take the stairs down (or, on a level without any, have nothing left to do),
            # the route's stairs instead
            if ok("lair") and self.route.target(state) and self.rules_now(state, hostiles)[1] in ("descend", "") and \
                    self.route.wants(state):
                return "lair"
        return None

    @staticmethod
    def still_a_shop(state: GameState, pos: tuple[int, int]) -> bool:
        """The square is still a shop's: a feature on the map (the glyph hides under the character's), and no "The shop
        is a mimic!" among the latest messages. `<` anywhere else opens no menu, and the read for it would never end."""
        if state.cells.get(pos, {}).get("mf") != MF_FEATURE:
            return False
        return not any("is a mimic" in m for m in state.recent_messages(5))

    def on_visited_shop(self, state: GameState) -> bool:
        """`Style.kit` 2 "shop": standing on the shop just visited. Its square is travel-excluded (the fence), and
        explore refuses to start from one ("You're in a travel-excluded area, stopping explore."), so step off first,
        once: a later walk across a visited shop (to another shop, or to the stairs) is not stepped back from."""
        return self.shop_leave == (state.level_seq, state.pos)

    def shop_target(self, state: GameState) -> tuple[int, int] | None:
        """`Style.kit` 2 "shop": the nearest shop on this level not yet visited (nor given up), when there is gold to
        spend (SHOP_GOLD), HP is at half or more, and a known way leads there. Once picked it stays the goal until it
        is visited or given up: standing on a shop hides its glyph under the character's."""
        if (state.player.get("gold", 0) or 0) < SHOP_GOLD or state.hp * 2 < state.hp_max:
            return None
        goal = self.shop_goal if self.shop_goal and self.shop_goal[0] == state.level_seq else None
        if goal and not self.still_a_shop(state, goal[1]):
            self.shops_done.add(goal)                   # a shop mimic, gone in a puff of smoke
            goal = None
        if goal and goal not in self.shops_done and (state.pos == goal[1] or step_toward(state, goal[1])):
            return goal[1]
        for shop in sorted(state.shops(), key=state.distance):
            if (state.level_seq, shop) in self.shops_done:
                continue
            if state.pos == shop or step_toward(state, shop):
                self.shop_goal = (state.level_seq, shop)
                return shop
        return None

    def rules_now(self, state: GameState, hostiles: list) -> tuple[dict, str]:
        """(observation, the rules of thumb's choice) for this moment, as `next_action` would make them, changing
        nothing: no counter, no remembered rage, no step log. `Style.retreat`'s state is read as `fight_moves` would
        update it; the opt-in walk to the stairs (`Style.stairs`) and the unseen-attacker rules (nothing is unseen
        with hostiles in view) are left out."""
        frac = state.hp / state.hp_max
        obs = observe(state, hostiles, {
            "worn": self.worn or {}, "kit": bool(self.style.kit),
            "level_explored": self.level_explored, "level_steps": self.level_steps, "level_turn": self.level_turn,
            "hp_delta": 0.0 if self.prev_frac is None else frac - self.prev_frac, "last_action": self.last_action})
        blocked = {a for a, until in self.blocked.items() if state.turn < until} | self.save_blocked(state, hostiles)
        retreat = False
        if self.style.retreat and obs["n_hostiles"]:
            reach = STAIRS_NEAR if self.style.retreat >= 2 else 10 ** 9
            now = raging(obs)
            spent = self.style.retreat >= 3 and not now and "-Berserk" in (obs.get("status") or [])
            starts = ((self.was_raging and not now) or spent) and obs["n_hostiles"] >= RETREAT_LEFT and \
                (obs["on_up"] or 0 <= obs["dist_up"] <= reach)
            retreat = starts or (self.retreat_from == state.level_seq and recovering(obs))
        calm = bool(self.style.calm) and (not self.style.calmfor or obs["level_turns"] < self.style.calmfor)
        avail = available(obs, self.level_explored, blocked, self.rest_stalled_at == (state.turn, state.hp),
                          recover=bool(self.style.recover) or retreat, calm=calm)
        if not avail:
            return obs, ""
        choice = baseline(obs, avail, self.level_explored, wiki=bool(self.style.wiki), teleport=int(self.style.teleport),
                          recover=int(self.style.recover), calm=calm, retreat=retreat, assailed=None,
                          avoid=self.style.avoid, escape=self.style.escape, unique=self.style.unique,
                          rage=self.style.rage, hold=bool(self.style.hold) and hold_ground(obs),
                          heal_at=SAVE_HEAL if self.style.save else 0.5, gamble=bool(self.style.save),
                          cure=bool(self.style.cure))
        return obs, choice

    def save_blocked(self, state: GameState, hostiles: list) -> set[str]:
        """`Style.save` or `Style.stack`: {"quaff_unknown"} with nothing in view and no unknown potion stack of two or
        more (qw drinks one to identify it only from such a stack, so a kind costs at most half of what was found), else
        nothing. With hostiles in view the rules drink one only as a last healing potion (`baseline`'s `heal_at`)."""
        if not (self.style.save or self.style.stack) or hostiles or unknown_pair(state):
            return set()
        return {"quaff_unknown"}

    def jewel_pieces(self, state: GameState) -> list[tuple[str, dict, bool]]:
        """(letter, item, worn) for each ring or amulet in the pack, worn as last seen (`self.jewels`)."""
        return [(chr(it.get("letter", 0)), it, chr(it.get("letter", 0)) in self.jewels)
                for it in (state.player.get("inv") or {}).values() if it.get("base_type") == gear.JEWELLERY]

    def count(self, what: str) -> None:
        self.kit_counts[what] = self.kit_counts.get(what, 0) + 1

    @staticmethod
    def note(conn, **what) -> None:
        """A line of ours in the game's protocol recording (`Connection._note`), to find a throw or a step afterwards:
        they write no step log line."""
        if (write := getattr(conn, "_note", None)):
            write(**what)

    def fight_moves(self, level_seq: int, obs: dict) -> tuple[bool, bool, bool]:
        """What the opt-in fight rules want now, for `baseline`: (retreat, rest_out, to_stairs).

        `Style.retreat`: a rage that has just run out (raging at the last choice, not now) with RETREAT_LEFT or
        more hostiles in view and stairs up known (at level 2, within STAIRS_NEAR steps: a slowed walk further
        than that lost more than it saved on block A) marks this level as one to leave; at level 3 so does any
        choice with RETREAT_LEFT or more in view while exhausted (`-Berserk`), with the stairs as close. While still `recovering`,
        head up the stairs there whenever something is in view (`retreat`), and with nothing in view, on any
        level, rest before going on (`rest_out`).
        `Style.stairs`: with a `big_fight` in view, no rage or exhaustion on and nothing adjacent, walk toward
        stairs up within STAIRS_NEAR steps (`to_stairs`), until on them or something is adjacent; once per fight.
        """
        was, self.was_raging = self.was_raging, raging(obs)
        retreat = to_stairs = False
        if self.style.retreat:
            reach = STAIRS_NEAR if self.style.retreat >= 2 else 10 ** 9
            ran_out = was and not self.was_raging
            # level 3: met while exhausted, too (a fight that finds the character resting off a rage)
            spent = self.style.retreat >= 3 and not self.was_raging and "-Berserk" in (obs.get("status") or [])
            if (ran_out or spent) and obs["n_hostiles"] >= RETREAT_LEFT and \
                    (obs["on_up"] or 0 <= obs["dist_up"] <= reach):
                self.retreat_from = level_seq
            if self.retreat_from is not None and not recovering(obs):
                self.retreat_from = None
            retreat = self.retreat_from == level_seq and obs["n_hostiles"] > 0
        if self.style.stairs:
            adjacent = any(max(abs(m["dx"]), abs(m["dy"])) <= 1 for m in obs["mons"])
            if not obs["n_hostiles"]:
                self.stairs_done = False
            elif obs["on_up"] or adjacent or recovering(obs):
                self.stairs_done = True
            to_stairs = not self.stairs_done and big_fight(obs) and 0 < obs["dist_up"] <= STAIRS_NEAR
        return retreat, self.retreat_from is not None, to_stairs

    def assailed(self, obs: dict) -> str | None:
        """`Style.unseen`: BURNING or UNSEEN when hurt with nothing in view, else None.

        BURNING (level 1 and up): DCSS's sticky flame (`Fire`) is on, nothing in view. It burns every turn until it
        runs out, each step taken shakes six turns of it off (`shake_off_sticky_flame`), and while it burns the game
        refuses to rest or explore ("You are on fire!"), so the rules were left to wait in it.
        UNSEEN (level 2): the HP fraction has fallen at UNSEEN_HITS choices in a row with nothing in view (a choice
        where it stayed put doesn't break the run, one where it rose does), not poisoned, not burning (a choice while
        burning ends the run) and not the choice a rage ended at (the HP lost there is the rage's). Something invisible, or a hostile out of reach that `active_hostiles`
        leaves out, is hitting the character; rest and explore are refused, and the rules waited.
        """
        status = obs.get("status") or []
        prev, self.prev_status = self.prev_status, list(status)
        if not self.style.unseen or obs["n_hostiles"]:
            self.unseen_hits = 0
            return None
        if "Fire" in status:
            self.unseen_hits = 0                # the fire's own damage is not something unseen
            return BURNING
        rage_end = "Berserk" in prev and "Berserk" not in status
        if obs["hp_delta"] < 0 and not _has(obs, "Pois") and not rage_end:
            self.unseen_hits += 1
        elif obs["hp_delta"] > 0:
            self.unseen_hits = 0
        return UNSEEN if self.style.unseen >= 2 and self.unseen_hits >= UNSEEN_HITS else None

    def prefer(self, obs: dict, avail: list[str], base: str) -> tuple[str, dict]:
        """The network's pick among `avail`, kept to the baseline unless it is `margin` better."""
        q, danger, prior = self.net.forward(*encode(obs, avail))
        value = q @ self.style.weights()
        if self.style.human:
            idx = [ACTIONS.index(a) for a in avail]
            logp = prior[idx] - np.log(np.exp(prior[idx] - prior[idx].max()).sum()) - prior[idx].max()
            value = value.copy()
            value[idx] += self.style.human * logp
        vals = {a: float(value[ACTIONS.index(a)]) for a in avail}
        # an action the model has barely seen has no predictions worth acting on
        known = [a for a in avail if a == base or self.net.counts.get(a, 0) >= self.style.min_count]
        best = max(known, key=lambda a: vals[a])
        choice = best if vals[best] - vals[base] > self.style.margin else base
        return choice, {"values": {a: round(v, 3) for a, v in vals.items()}, "danger": round(danger, 3)}

    # --- carrying out the actions Reflex has no key for -----------------

    def perform(self, reflex, action: str) -> ActResult | None:
        state, conn = reflex.state, reflex.conn
        inv = inventory(state, largest=bool(self.style.wiki))
        letters = inv["letters"]
        item = {"quaff_heal": ("q", "heal"), "quaff_unknown": ("q", "unknown_potions"),
                "read_unknown": ("r", "unknown_scrolls"), "read_teleport": ("r", "teleport")}
        if action in item:
            verb, kind = item[action]
            if action == "quaff_unknown" and (self.style.save or self.style.stack) and unknown_pair(state):
                letters = {**letters, kind: unknown_pair(state)}
            if action == "quaff_heal":
                # which of the two, by what is needed now (heal_potion)
                now = {"hp": state.hp, "hp_max": state.hp_max, "status": state.statuses, "inv": inv,
                       "poison_survival": state.player.get("poison_survival", state.hp)}
                kind = heal_potion(now) or kind
                if self.style.cure:
                    # Style.cure: curing for confusion and poison, heal wounds for HP, never curing for HP
                    cures = (self.cure_now or needs_cure(now)) and inv.get("curing", 0) > 0
                    kind = "curing" if cures else "heal_wounds" if inv.get("heal_wounds", 0) > 0 else kind
                    self.count("cure" if cures else "heal_wounds")
            if kind not in letters:
                return ActResult()
            result = self.through_menu(conn, verb, letters[kind])
            if self.style.kit and result.blocking in ENCHANT_PROMPTS:
                return self.answer_enchant(conn, result)
            if "acquire" in self.parts and result.blocking == "acquirement":
                return self.answer_acquire(conn, state, result)
            if self.style.ident and result.blocking == "identify":
                return self.answer_identify(conn, state, result)
            if result.blocking in ITEM_PROMPTS:
                # The scroll wants a target or an item (blinking, identify, enchant...). There is no
                # action for that yet: cancel, and say yes to "really abort and waste the scroll?",
                # one key at a time (a Y typed ahead put every later reply a key behind).
                after = cancel_prompt(conn)
                after.messages = result.messages + after.messages
                return after
            return result
        if action == "fence_shops":
            return conn.act(FENCE_KEY)
        if action == "read_kit":
            letter = kit_scroll(state, self.parts)
            if not letter:
                return ActResult()
            result = self.through_menu(conn, "r", letter)
            if result.blocking in ENCHANT_PROMPTS:
                return self.answer_enchant(conn, result)
            if "acquire" in self.parts and result.blocking == "acquirement":
                return self.answer_acquire(conn, state, result)
            if result.blocking in ITEM_PROMPTS:
                after = cancel_prompt(conn)
                after.messages = result.messages + after.messages
                return after
            return result
        if action == "read_ident":
            letter = ident_scroll(state)
            if not letter:
                return ActResult()
            result = self.through_menu(conn, "r", letter)
            if result.blocking == "identify":
                return self.answer_identify(conn, state, result)
            if result.blocking in ITEM_PROMPTS:
                after = cancel_prompt(conn)
                after.messages = result.messages + after.messages
                return after
            return result
        if action == "put_on":
            return self.put_on(conn, state)
        if action == "trogs_hand":
            return self.trogs_hand(conn)
        if action == "step":
            self.steps_taken += 1
            self.count("step")
            self.note(conn, auto="step", turn=state.turn, hp=state.hp, way=list(self.step_way),
                      adjacent=sum(1 for m in self.active_hostiles(state) if state.distance(m.pos) <= 1))
            return conn.act(DIRECTIONS[self.step_way])
        if action == "throw":
            return self.throw(conn, state)
        if action == "kit_shop":
            return self.shop(conn, state)
        if action == "lair_scan":
            result = conn.act(LAIR_KEY)
            texts = [strip_tags(m.get("text", "")) for batch in result.messages if batch.get("msg") == "msgs"
                     for m in batch.get("messages", [])]
            self.route.scanned_now(state, texts)
            return result
        if action == "lair":
            return self.lair_step(conn, state)
        if action == "disturb_step":
            way = disturb_square(state, self.disturb_steps)
            self.disturb_steps += 1
            if way is None:
                return ActResult()
            self.count("disturb_step")
            self.note(conn, auto="disturb_step", turn=state.turn, way=list(way))
            return conn.act(DIRECTIONS[way])
        if action == "equip":
            up = gear.upgrades(state, self.worn or {}, kit=2)
            action = "wield" if up["wield"] else "wear"
            self.count("equip_" + action)
        if action in ("wield", "wear"):
            kit = self.rank_kit
            letter = gear.upgrades(state, self.worn or {}, kit=kit)[action]
            if not letter:
                return ActResult()
            piece = gear.kind_of(state, letter, kit=kit)
            result = self.through_menu(conn, "w" if action == "wield" else "W", letter)
            if result.blocking:
                # Something came into view part-way ("Keep equipping yourself?", a yes/no menu that
                # ignores Esc), or the game wants to be sure. No, either way.
                after = conn.act("N", through_menu=True)
                after.messages = result.messages + after.messages
                result = after
            if action == "wear" and piece and self.worn is not None:
                text = " ".join(strip_tags(m.get("text", "")) for batch in result.messages
                                if batch.get("msg") == "msgs" for m in batch.get("messages", []))
                if "You finish putting on" in text or "You are now wearing" in text:
                    self.worn[piece[0]] = piece[1]
                elif "You finish taking off" in text or "You take off" in text:
                    self.worn.pop(piece[0], None)   # it was on already, and the key took it off
            return result
        if action == "wait":
            return conn.act("s")
        if action == "berserk":
            return self.through_menu(conn, "a", "a")
        if action == "flee_up":
            if state.cells.get(state.pos, {}).get("mf") == MF_STAIR_UP:
                return conn.act("<")
            key, _ = path(state, MF_STAIR_UP)
            return conn.act(key) if key else ActResult()
        return None

    def answer_enchant(self, conn, result: ActResult) -> ActResult:
        """`Style.kit`: answer an enchant armour, enchant weapon or brand weapon scroll's item menu with the armour or
        weapon in use (`gear.enchant_target`) instead of cancelling it; cancel when nothing in it fits."""
        target = gear.enchant_target(result.blocking, gear.worn_from_menu(result.messages), kit=self.rank_kit or 1)
        if target is None:
            after = cancel_prompt(conn)
        else:
            after = conn.act(target, through_menu=True)
            if after.blocking in ITEM_PROMPTS | {"yesno"}:
                more = cancel_prompt(conn)                   # anything more it asks: no
                more.messages = after.messages + more.messages
                after = more
            else:
                self.count("enchant_" + result.blocking)
        after.messages = result.messages + after.messages
        return after

    def answer_identify(self, conn, state: GameState, result: ActResult) -> ActResult:
        """`Style.ident`: answer the identify prompt ("Identify which item?", tag `use_item`; seen in the real game, job
        `brain-v6l/probe5.py`) with the line `ident_choice` picks; cancel when nothing in it fits. The letter closes the
        menu and the item is named at once ("f -> w - 2 potions of heal wounds"); a known scroll's read takes a turn."""
        menu = gear.worn_from_menu(result.messages)
        letter = ident_choice(menu)
        if letter is None:
            after = cancel_prompt(conn)
        else:
            after = conn.act(letter, through_menu=True)
            if after.blocking in ITEM_PROMPTS | {"yesno", "menu"}:
                more = cancel_prompt(conn)                   # anything more it asks: no
                more.messages = after.messages + more.messages
                after = more
            else:
                self.count("identify")
                self.note(conn, auto="identify", chosen=next((t for k, t, _ in menu if k == letter), ""),
                          turn=state.turn)
                rename_identified(state, after.messages)
        after.messages = result.messages + after.messages
        return after

    def put_on(self, conn, state: GameState) -> ActResult:
        """`Style.kit`: open the `P` menu, take what is worn from it (its "(worn)" marks), and press the letter
        `gear.jewellery_choice` gives for that: a piece put on, or a worn one taken off for a better one next time.
        A multi-turn change that something interrupts ("Spend multiple turns changing equipment while enemies are
        nearby?") is answered no, as `wear` does; Esc when the menu shows nothing to change."""
        behind = conn.catch_up()
        if behind.blocking:
            return behind
        opened = conn.act("P")
        opened.messages = behind.messages + opened.messages
        if opened.blocking != "menu":
            return opened
        self.jewels = {letter for letter, _, on in gear.worn_from_menu(opened.messages) if on}
        letter = gear.jewellery_choice(self.jewel_pieces(state), kit=self.rank_kit or 1)
        if letter is None:
            after = conn.act("key_esc", through_menu=True)
            after.messages = opened.messages + after.messages
            return after
        result = conn.act(letter, through_menu=True)
        if result.blocking:
            after = conn.act("key_esc" if result.blocking == "text_input" else "N", through_menu=True)
            after.messages = result.messages + after.messages
            result = after
        text = " ".join(strip_tags(m.get("text", "")) for batch in result.messages
                        if batch.get("msg") == "msgs" for m in batch.get("messages", []))
        if "You remove" in text:
            self.jewels.discard(letter)
            self.count("jewel_off")
        elif f"{letter} - " in text and "(worn)" in text:
            self.jewels.add(letter)
            self.count("jewel_on")
        result.messages = opened.messages + result.messages
        return result

    def answer_acquire(self, conn, state: GameState, result: ActResult) -> ActResult:
        """`Style.kit` 2 "acquire": answer the acquirement menu ("Choose an item to acquire.") with the offer that adds
        most (`gear.acquire_choice`; the gold when nothing does), say yes, and pick up what appears at the character's
        feet ("Something appears at your feet!"). A pick-up menu (other things lie there too) is answered with the line
        naming it. Cancelled as before if the menu can't be read."""
        menu = gear.worn_from_menu(result.messages)
        letter = gear.acquire_choice(menu, state, self.worn or {}, self.jewels, ACQUIRE_GOLD["shop" in self.parts])
        if letter is None:
            after = cancel_prompt(conn)
            after.messages = result.messages + after.messages
            return after
        chosen = next((text for k, text, _ in menu if k == letter), "")
        picked = conn.act(letter, through_menu=True)
        if picked.blocking != "yesno":
            more = cancel_prompt(conn) if picked.blocking else ActResult()
            more.messages = result.messages + picked.messages + more.messages
            return more
        made = conn.act("y", through_menu=True)
        self.count("acquire")
        self.note(conn, auto="acquire", chosen=chosen, turn=state.turn)
        got = conn.act("g", through_menu=True)
        if got.blocking == "menu":
            name = re.sub(r"^\s*\w - (an?|the) ", "", chosen)[:24]
            pick = next((k for k, text, _ in gear.worn_from_menu(got.messages) if name and name in text), None)
            more = conn.act(*([pick, "key_enter"] if pick else ["key_esc"]), through_menu=True)
            got.messages += more.messages
            got.blocking = more.blocking
        got.messages = result.messages + picked.messages + made.messages + got.messages
        return got

    def shop(self, conn, state: GameState) -> ActResult:
        """`Style.kit` 2 "shop": one step toward the shop `shop_target` picks (answering yes to "Really walk into a
        travel-excluded area?": the bot fences shops off from explore), or, on it, open it (`<`), mark what
        `gear.shop_choice` picks, buy (Enter, then yes) and leave (Esc). Buying takes no game time. A shop is visited
        once per level visit; one SHOP_STEPS or more steps away is given up. Standing on the shop just visited, with
        no other to walk to, step off it (`leave_shop`)."""
        shop = self.shop_target(state)
        if shop is None and self.on_visited_shop(state):
            return self.leave_shop(conn, state)
        if shop is None:
            return ActResult()
        key = (state.level_seq, shop)
        if state.pos != shop:
            self.shop_steps += 1
            step = step_toward(state, shop)
            if step is None or self.shop_steps > SHOP_STEPS:
                self.shops_done.add(key)
                self.shop_steps = 0
                return ActResult()
            self.shop_back = next((k for k, v in DIRECTIONS.items() if v == step), None)
            result = conn.act(step)
            if result.blocking in ("menu", "yesno"):          # the question comes as a menu, read with it or not
                after = conn.act("Y", through_menu=True)
                after.messages = result.messages + after.messages
                result = after
            return result
        self.shops_done.add(key)
        self.shop_steps = 0
        behind = conn.catch_up()
        if behind.blocking or not self.still_a_shop(state, shop) or not any(
                "entrance to" in m for m in state.recent_messages(8)):
            return behind                          # nothing to open here (a mimic): never press `<` blind
        opened = conn.open_menu("<")
        opened.messages = behind.messages + opened.messages
        self.shop_leave, self.shop_opened = key, True      # no game time: the step off it isn't to be held back
        menu = gear.worn_from_menu(opened.messages)
        letters = gear.shop_choice(menu, state, self.worn or {}, self.jewels)
        self.count("shop_visit")
        if not letters:
            done = conn.act("key_esc", through_menu=True)
        else:
            asked = conn.act(*letters, "key_enter", through_menu=True)
            done = conn.act("y" if asked.blocking == "yesno" else "N", "key_esc", through_menu=True)
            done.messages = asked.messages + done.messages
            bought = [text for k, text, _ in menu if k in letters]
            self.count("bought")
            self.kit_counts["bought_items"] = self.kit_counts.get("bought_items", 0) + len(letters)
            self.note(conn, auto="shop", bought=bought, gold=state.player.get("gold", 0), turn=state.turn)
        done.messages = opened.messages + done.messages
        return done

    def leave_shop(self, conn, state: GameState) -> ActResult:
        """One step off a visited shop's square: back the way the character came if that square is free, else to the
        first free walkable neighbour (no monster, no trap, not a shop). Tried once per visit."""
        self.shop_leave = None
        taken = {m.pos for m in state.monsters()}
        px, py = state.pos
        ways = ([(-self.shop_back[0], -self.shop_back[1])] if self.shop_back else []) + list(DIRECTIONS)
        for dx, dy in ways:
            sq = (px + dx, py + dy)
            cell = state.cells.get(sq)
            if cell is None or sq in taken or cell.get("mf", 0) in NOT_WALKABLE | {MF_TRAP} or sq in state.shops():
                continue
            self.count("shop_leave")
            result = conn.act(DIRECTIONS[(dx, dy)])
            if result.blocking in ("menu", "yesno"):
                after = conn.act("Y", through_menu=True)
                after.messages = result.messages + after.messages
                result = after
            return result
        return ActResult()

    def lair_step(self, conn, state: GameState) -> ActResult:
        """`Style.lair`: one step of the route (`LairRoute.target`). Toward the entrance, or `>` on it; toward the stairs
        up, or `<` on them. A step onto a fenced shop square is asked about ("Really walk into a travel-excluded
        area?") and answered yes, as the walk to the stairs down does. No known way to the entrance gives the route up;
        no known way up counts as a step that failed (`LairRoute.failed`)."""
        route = self.route
        aim = route.target(state)
        if aim is None:
            return ActResult()
        if aim == "up" and where(state)[0] == "Lair":
            route.start_back(state)
        if aim == "entrance":
            goal = route.entrance[1]
            if state.pos == goal:
                self.count("lair_in")
                return conn.act(">")
            key = step_toward(state, goal)
            if key is None:
                # seen, but not yet reached on foot (across water, past a part left unexplored after a rage): let explore
                # go on, LAIR_NO_WAY times, before giving the route up. Not a step that failed: nothing was sent.
                route.no_way += 1
                self.auto = None
                if route.no_way > LAIR_NO_WAY:
                    route.give_up("no known way to the entrance", state)
                else:
                    route.event("no_way", state)
                    self.level_explored = False
                    self.blocked.pop("explore", None)
                return ActResult()
        else:
            if state.cells.get(state.pos, {}).get("mf") == MF_STAIR_UP:
                self.count("lair_up")
                return conn.act("<")
            key, _ = path(state, MF_STAIR_UP)
            if key is None:
                route.failed(state, "no known way up")
                return ActResult()
        result = conn.act(key)
        if result.blocking == "menu" and any(EXCLUDED_PROMPT in strip_tags((m.get("title") or {}).get("text", ""))
                                             for m in result.messages if m.get("msg") == "menu"):
            after = conn.act("Y", through_menu=True)
            after.messages = result.messages + after.messages
            result = after
        return result

    def trogs_hand(self, conn) -> ActResult:
        """`Style.hand`: `a`, then the letter the ability menu shows for Trog's Hand; Esc if it isn't there."""
        behind = conn.catch_up()
        if behind.blocking:
            return behind
        opened = conn.act("a")
        opened.messages = behind.messages + opened.messages
        if opened.blocking != "menu":
            return opened
        letter = next((k for k, text, _ in gear.worn_from_menu(opened.messages) if "Trog's Hand" in text), None)
        result = conn.act(letter or "key_esc", through_menu=True)
        if letter:
            self.count("hand")
        result.messages = opened.messages + result.messages
        return result

    def throw(self, conn, state: GameState) -> ActResult:
        """`Style.throw`: quiver a missile if none is (the `Q` menu, `gear.quiver_line`), then press the rc's
        `ladder_throw` key (`gear.THROW_KEY`), which throws at the hostile with a clear shot or does nothing."""
        held = gear.missiles(state)
        result = ActResult()
        self.note(conn, auto="throw", turn=state.turn, hp=state.hp, held=sum(held.values()))
        if str(state.player.get("quiver_item", -1)) not in held:
            behind = conn.catch_up()
            if behind.blocking:
                return behind
            opened = conn.act("Q")
            opened.messages = behind.messages + opened.messages
            if opened.blocking != "menu":
                return opened
            letter = gear.quiver_line(gear.worn_from_menu(opened.messages))
            result = conn.act(letter or "key_esc", through_menu=True)
            result.messages = opened.messages + result.messages
            if letter is None or result.blocking:
                return result
            self.count("quiver")
        fired = conn.act(gear.THROW_KEY)
        fired.messages = result.messages + fired.messages
        text = " ".join(strip_tags(m.get("text", "")) for batch in fired.messages
                        if batch.get("msg") == "msgs" for m in batch.get("messages", []))
        if "You throw" in text:
            self.count("throw")
        return fired

    @staticmethod
    def through_menu(conn, verb: str, letter: str) -> ActResult:
        """Press `verb`, and `letter` only once its menu is up. A refused verb (reading while silenced)
        opens no menu, and the letter would then be taken as a command of its own."""
        behind = conn.catch_up()
        if behind.blocking:
            return behind                       # a prompt was already waiting: that first
        opened = conn.act(verb)
        opened.messages = behind.messages + opened.messages
        if opened.blocking != "menu":
            return opened
        result = conn.act(letter, through_menu=True)
        result.messages = opened.messages + result.messages
        return result

    # --- bookkeeping ---------------------------------------------------

    def observe(self, action: str, before: Before, state: GameState, interrupts: list[Interrupt]) -> None:
        opened, self.shop_opened = self.shop_opened, False
        if self.auto and state.turn == before.turn and state.level_seq == before.level_seq and not opened:
            # went nowhere: leave it a while (a throw only briefly: the shot may be clear after the next move). A
            # shop's menu takes no game time either, but went somewhere: held back, the step off the shop's square
            # waited BLOCK_TURNS, with explore refused there all the while
            self.auto_blocked[self.auto] = state.turn + (THROW_RETRY if self.auto == "throw" else BLOCK_TURNS)
            if self.auto == "lair":
                self.route.failed(state, "a step that went nowhere")
        if self.route and any(i.kind == "level_change" for i in interrupts):
            self.route.arrived(state, before.place)
        if any(i.kind == "level_change" for i in interrupts):
            self.blocked.clear()
            self.stalls.clear()
            self.idle = 0
            self.unseen_hits = 0
            self.disturb_steps = 0
            self.level_steps, self.level_turn = 0, state.turn
        try:
            super().observe(action, before, state, interrupts)
        except Escalation:
            if self.choice is None:
                raise                           # not the brain's choice (struggling in a net): nothing else to pick
        if self.choice is None or state.dead:
            return
        # An action that used no game time went nowhere, whatever the reason (a refusal, a cancelled
        # prompt such as "really walk into that poison gas?"). Twice in a row and it is left alone.
        if state.turn != before.turn or state.level_seq != before.level_seq:
            self.stalls.pop(self.choice, None)
            if self.choice != "wait":
                self.idle = 0
            return
        if self.calm_now and self.choice == "explore" and \
                any(m["text"] == CALM_DOWN for m in state.messages[before.msg_index:]):
            return                              # refused for the rage, not for want of anywhere to go
        if self.style.calm >= 2 and self.choice == "explore" and self.disturb_steps < DISTURB_MAX and \
                any(m["text"] == DISTURBANCE for m in state.messages[before.msg_index:]):
            self.disturbed = True               # an unseen monster close by: step aside and try again (`auto_step`)
            return
        self.stalls[self.choice] = self.stalls.get(self.choice, 0) + 1
        if self.stalls[self.choice] < 2:
            return
        self.stalls.pop(self.choice)
        item = self.choice in ("read_unknown", "quaff_unknown", "quaff_heal", "read_teleport", "wield", "wear")
        self.blocked[self.choice] = UNTIL_LEVEL if item else state.turn + BLOCK_TURNS
        if self.choice == "fight":
            # out of reach (behind glass, across water). Explore won't run with it in view, so stop
            # exploring this level and head for the stairs rather than pacing between the two.
            self.ignored |= {m.id for m in state.hostiles()}
            self.level_explored = True

    def describe(self) -> dict:
        out = {"model": self.net.name if self.net else None, "epsilon": self.epsilon, "style": asdict(self.style)}
        if self.style.kit or self.style.hand or self.style.throw or self.style.step or self.style.calm >= 2 or \
                self.style.ident or self.style.cure:
            out["kit"] = dict(self.kit_counts)
        if self.route:
            out["lair"] = self.route.record()
        return out
