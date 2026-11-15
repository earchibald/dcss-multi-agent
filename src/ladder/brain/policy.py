"""Choosing: which actions are possible now, what the rules of thumb would do, what the network prefers.

`BrainTiers` takes `StubTiers`' place inside Reflex. Where the stub raised an escalation (low HP
with monsters in view, an action that makes no progress) the brain picks another action instead,
so a game goes on until the character dies, the limits run out, or nothing at all is possible.

The network predicts outcome components per action; `Style` weighs them into one value at decision
time, so changing the style needs no retraining (the same split as s1-battle's trained brain).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

import numpy as np

from ..conn import ActResult, cancel_prompt
from ..interrupts import Before, Interrupt
from ..reflex import Escalation, StubTiers
from ..state import MF_STAIR_UP, GameState, strip_tags

from . import gear, monsters
from .features import ACTIONS, COMPONENTS, MDAM_LEFT, encode, inventory, observe, path
from .net import Ensemble, TrainedNet

# What a scroll can stop on (conn.classify_error's names). Anything else that comes up after using an
# item, such as the level-up stat prompt when the potion's turn killed something, is Reflex's to answer.
ITEM_PROMPTS = {"blink", "identify", "enchant_weapon", "enchant_item", "brand_weapon", "acquirement", "menu"}
REPLAY_DIVERGED, FORK_DONE = "replay diverged", "fork horizon reached"
LEVEL_STEP_LIMIT = 1500   # choices on one level before the brain calls itself stuck
IDLE_LIMIT = 60           # waits in a row, with nothing else possible, before it does the same
BLOCK_TURNS = 50         # an action that went nowhere is left alone for this many game turns
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
    teleport: float = 0.0     # 1 = the rules of thumb read teleportation when spent after a rage (`teleport_rule`),
                              # 2 = also when outnumbered by something dangerous. Off by default.
    recover: float = 1.0      # 1 = with nothing in view, rest out a rage and its exhaustion (`recovering`) before
                              # taking the stairs, 2 = before exploring on as well, 0 = off. 1 by default since
                              # 2026-11-15 (with retreat=2: +0.45 [+0.24, +0.65] on 996 fresh dungeons).
    calm: float = 0.0         # 1 = with nothing in view, wait out a rage instead of trying to explore (DCSS
                              # refuses: "Calm down first, please."), and don't count that refusal as the
                              # level being done (`raging`). Off by default.
    retreat: float = 2.0      # 1 = when a rage runs out with RETREAT_LEFT or more hostiles in view and stairs up
                              # known, go up them (kept to on that level while `recovering`), then rest the
                              # exhaustion out before anything else; 2 = the same, only with the stairs up within
                              # STAIRS_NEAR steps; 0 = off. 2 by default since 2026-11-15 (with recover=1).
    stairs: float = 0.0       # 1 = before a fight bigger than one rage (`big_fight`), nothing adjacent and no rage
                              # on, walk to stairs up within STAIRS_NEAR steps first, once per fight. Off by default.

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
STYLE_ADDED_AS = {"recover": 0.0, "retreat": 0.0}


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


RECOVERING = ("Berserk", "-Berserk", "Slow")     # a rage, the exhaustion after it, the slowness it leaves


def recovering(obs: dict) -> bool:
    """In a rage or just out of one: `Berserk`, `-Berserk` (exhausted: no second rage) or `Slow` showing.

    The end of a rage leaves the character slowed for 14-36 turns and unable to rage again for twice that
    (`player_end_berserk`). Resting (`5`) passes that time even at full HP ("You start waiting."), and a rage
    with nothing to hit wears off sooner (`_do_berserk_no_combat_penalty`).
    """
    return any(x in RECOVERING for x in obs.get("status") or [])


CALM_DOWN = "Calm down first, please."     # DCSS's answer to autoexplore (and travel) during a rage


def raging(obs: dict) -> bool:
    """In a rage now (`Berserk`, not the `-Berserk` exhaustion after it): autoexplore is refused."""
    return "Berserk" in (obs.get("status") or [])


RETREAT_LEFT = 2          # hostiles still in view when a rage runs out that `Style.retreat` goes upstairs from
STAIRS_NEAR = 8           # steps to the stairs up that `Style.stairs` walks before a big fight, and `Style.retreat`
                          # 2 walks after a rage


def foe_hp(obs: dict) -> float:
    """The HP the hostiles in view have left between them, estimated: each one's average HP (the game's
    `avghp`, else the monster table's) times the share its damage level leaves (`features.MDAM_LEFT`)."""
    total = 0.0
    for m in obs["mons"]:
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


def available(obs: dict, level_explored: bool, blocked: set[str], rest_stalled: bool, recover: bool = False,
              calm: bool = False) -> list[str]:
    """The actions that can be carried out right now, in ACTIONS order.

    `recover` (`Style.recover`): `rest` is also possible at full HP while `recovering`, and a rest that left HP
    where it was doesn't rule it out then (HP is full; the rest was for the time).
    `calm` (`Style.calm`): while `raging`, `explore` is not possible (DCSS would refuse it) and `rest` is, in
    the same way as for `recover`, so the rage can be waited out.
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
    can = {
        "explore": not hostiles and not level_explored and not waiting_calm,
        "fight": hostiles,
        "rest": not hostiles and (hurt or obs["mp"] < obs["mp_max"] or waiting_out) and (not rest_stalled or waiting_out),
        "descend": obs["on_down"] or obs["dist_down"] >= 0,
        # the stairs up from D:1 leave the dungeon
        "flee_up": hostiles and (obs["on_up"] or obs["dist_up"] >= 0)
                   and not (obs["place"] in ("", "Dungeon") and obs["depth"] <= 1),
        "quaff_heal": inv["heal"] > 0 and (hurt or ailing) and calm,
        "quaff_unknown": inv["unknown_potions"] > 0 and calm,
        "read_unknown": inv["unknown_scrolls"] > 0 and can_read,
        # not while a teleport is already coming (`Tele`): a second scroll cancels it ("You feel strangely stable")
        "read_teleport": inv["teleport"] > 0 and hostiles and can_read and "Tele" not in status,
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


def teleport_rule(obs: dict, level: int) -> tuple[bool, bool]:
    """When the opt-in teleport rules (`Style.teleport`) would read teleportation: (spent, crowded).

    - spent (level 1 and up): just out of a rage, exhausted and slowed (`-Berserk` with `Slow`), with
      monsters in view. Another rage is refused and every action takes twice as long.
    - crowded (level 2): at least CROWD hostiles in view, one of them dangerous (webtiles threat 2 or 3).
      `baseline` puts it after a rage, so it covers a fight the rules wouldn't rage at, or can't.
    Neither while a teleport is already coming (`Tele`): a second scroll would cancel it. That the scroll can
    be read at all is `available`'s part.
    """
    status = obs.get("status") or []
    if level < 1 or not obs["n_hostiles"] or "Tele" in status:
        return False, False
    spent = "-Berserk" in status and "Slow" in status
    crowded = level >= 2 and obs["n_hostiles"] >= CROWD and any(m["threat"] >= 2 for m in obs["mons"])
    return spent, crowded


def baseline(obs: dict, avail: list[str], level_explored: bool, wiki: bool = False, teleport: int = 0,
             recover: int = 0, calm: bool = False, retreat: bool = False, rest_out: bool = False,
             to_stairs: bool = False) -> str:
    """Rules of thumb: the stub's behaviour, plus drinking a healing potion instead of giving up.

    `wiki` plays the variant that follows the DCSS wiki's strategy guides instead (`Style.wiki`).
    `teleport` 1 or 2 adds the opt-in teleport rules (`teleport_rule`, `Style.teleport`); 0 leaves them out.
    `recover` 1 rests out a rage and its exhaustion (`recovering`) with nothing in view before taking the
    stairs, 2 before exploring on as well (`Style.recover`); 0 leaves it out. `avail` must then come from
    `available(..., recover=True)`, or `rest` is seldom there at full HP.
    `calm` waits out a rage (`raging`) with nothing in view before exploring on (`Style.calm`); `avail` must
    then come from `available(..., calm=True)`.
    The next three are `BrainTiers`' to set, since they depend on what came before (`Style.retreat`, `Style.stairs`):
    `retreat` heads up the stairs with hostiles in view (after a healing potion at half HP); `rest_out` rests
    with nothing in view before going on, as `recover` 2 does (`avail` then from `available(..., recover=True)`);
    `to_stairs` walks toward the stairs up before a fight.
    """
    if wiki:
        return baseline_wiki(obs, avail, level_explored)
    frac = obs["hp"] / max(obs["hp_max"], 1)
    cure = ["quaff_heal"] if needs_cure(obs) else []      # serious poison: curing first, before any rage
    if obs["n_hostiles"]:
        near = [m for m in obs["mons"] if max(abs(m["dx"]), abs(m["dy"])) <= 2]
        rage = frac <= 0.5 or any(m["threat"] >= 2 for m in near) or len(near) >= 3
        spent, crowded = teleport_rule(obs, teleport)
        if retreat:
            away = (["quaff_heal"] if frac <= 0.5 else []) + ["flee_up"]
        else:
            away = ["flee_up"] if to_stairs else []
        order = cure + away + (["read_teleport"] if spent else []) + (["berserk"] if rage and near else []) + \
                (["quaff_heal"] if frac <= 0.5 else []) + (["read_teleport"] if crowded else []) + \
                ["fight", "descend", "flee_up", "wait"]
    else:
        onward = ["descend"] if level_explored else ["explore"]
        if rest_out and recovering(obs):
            onward = ["rest"] + onward              # gone up from a fight: rest it off before going on
        elif recover and recovering(obs) and (level_explored or recover >= 2):
            onward = ["rest"] + onward              # arrive, or explore on, able to rage and at full speed
        elif calm and raging(obs) and not level_explored:
            onward = ["rest"] + onward              # explore is refused until the rage is over
        order = cure + ["wield", "wear"] + (["rest"] if frac < 0.8 else ["read_unknown", "quaff_unknown"]) + \
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

    # --- choosing ------------------------------------------------------

    def next_action(self, state: GameState) -> str:
        self.last = self.choice = None
        hostiles = self.active_hostiles(state)
        if not hostiles:
            self.approach = False
        if state.caught:
            return "struggle"
        shops = {(state.level_seq, s) for s in state.shops()}
        if shops - self.fenced:
            self.fenced |= shops
            # Before explore can walk into one (see crawlrc.txt). The brain has no action that buys,
            # so unlike StubTiers it never visits a shop: stepping onto a fenced square asks "really?".
            return "fence_shops"
        frac = state.hp / state.hp_max
        if self.worn is None:                  # joining a game part-way: found out by trying
            self.worn = gear.initial_worn(state) if state.turn <= 1 else {}
        obs = observe(state, hostiles, {
            "worn": self.worn,
            "level_explored": self.level_explored, "level_steps": self.level_steps, "level_turn": self.level_turn,
            "hp_delta": 0.0 if self.prev_frac is None else frac - self.prev_frac, "last_action": self.last_action})
        self.prev_frac = frac
        blocked = {a for a, until in self.blocked.items() if state.turn < until}
        retreat, rest_out, to_stairs = self.fight_moves(state.level_seq, obs)
        avail = available(obs, self.level_explored, blocked, self.rest_stalled_at == (state.turn, state.hp),
                          recover=bool(self.style.recover) or rest_out, calm=bool(self.style.calm))
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
        base = baseline(obs, avail, self.level_explored, wiki=bool(self.style.wiki), teleport=int(self.style.teleport),
                        recover=int(self.style.recover), calm=bool(self.style.calm), retreat=retreat,
                        rest_out=rest_out, to_stairs=to_stairs)
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
        self.choices += 1
        self.level_steps += 1
        if self.sink:
            self.sink(self.last)
        if choice == "fight":
            return "approach" if self.approach else "fight"
        if choice == "descend":
            return "descend" if obs["on_down"] else "travel"
        return choice

    def fight_moves(self, level_seq: int, obs: dict) -> tuple[bool, bool, bool]:
        """What the opt-in fight rules want now, for `baseline`: (retreat, rest_out, to_stairs).

        `Style.retreat`: a rage that has just run out (raging at the last choice, not now) with RETREAT_LEFT or
        more hostiles in view and stairs up known (at level 2, within STAIRS_NEAR steps: a slowed walk further
        than that lost more than it saved on block A) marks this level as one to leave. While still `recovering`,
        head up the stairs there whenever something is in view (`retreat`), and with nothing in view, on any
        level, rest before going on (`rest_out`).
        `Style.stairs`: with a `big_fight` in view, no rage or exhaustion on and nothing adjacent, walk toward
        stairs up within STAIRS_NEAR steps (`to_stairs`), until on them or something is adjacent; once per fight.
        """
        was, self.was_raging = self.was_raging, raging(obs)
        retreat = to_stairs = False
        if self.style.retreat:
            reach = STAIRS_NEAR if self.style.retreat >= 2 else 10 ** 9
            if was and not self.was_raging and obs["n_hostiles"] >= RETREAT_LEFT and \
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
            if action == "quaff_heal":
                # which of the two, by what is needed now (heal_potion)
                kind = heal_potion({"hp": state.hp, "hp_max": state.hp_max, "status": state.statuses, "inv": inv,
                                    "poison_survival": state.player.get("poison_survival", state.hp)}) or kind
            if kind not in letters:
                return ActResult()
            result = self.through_menu(conn, verb, letters[kind])
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
        if action in ("wield", "wear"):
            letter = gear.upgrades(state, self.worn or {})[action]
            if not letter:
                return ActResult()
            piece = gear.kind_of(state, letter)
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
        if any(i.kind == "level_change" for i in interrupts):
            self.blocked.clear()
            self.stalls.clear()
            self.idle = 0
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
        if self.style.calm and self.choice == "explore" and \
                any(m["text"] == CALM_DOWN for m in state.messages[before.msg_index:]):
            return                              # refused for the rage, not for want of anywhere to go
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
        return {"model": self.net.name if self.net else None, "epsilon": self.epsilon, "style": asdict(self.style)}
