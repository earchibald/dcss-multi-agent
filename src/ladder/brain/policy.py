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

from ..conn import ActResult
from ..interrupts import Before, Interrupt
from ..reflex import Escalation, StubTiers
from ..state import MF_STAIR_UP, GameState
from .features import ACTIONS, COMPONENTS, encode, inventory, observe, path
from .net import TrainedNet

# What a scroll can stop on (conn.classify_error's names). Anything else that comes up after using an
# item, such as the level-up stat prompt when the potion's turn killed something, is Reflex's to answer.
ITEM_PROMPTS = {"blink", "identify", "enchant_weapon", "enchant_item", "brand_weapon", "acquirement", "menu"}
REPLAY_DIVERGED, FORK_DONE = "replay diverged", "fork horizon reached"
LEVEL_STEP_LIMIT = 1500   # choices on one level before the brain calls itself stuck
IDLE_LIMIT = 60           # waits in a row, with nothing else possible, before it does the same
BLOCK_TURNS = 50         # an action that went nowhere is left alone for this many game turns
UNTIL_LEVEL = 10 ** 9     # ...or until the next level, for scrolls and potions that wouldn't go down


@dataclass
class Style:
    """How the predicted outcomes are weighed. value = sum(weight x component) + prior nudge."""
    died_soon: float = -2.0
    hp_lost: float = -0.5
    xp_soon: float = 0.5
    depth_go: float = 1.0
    xp_go: float = 0.5
    died_go: float = -2.0
    human: float = 0.0        # weight of log P(the recorded player would do this)
    margin: float = 0.05      # leave the rules of thumb only for an action predicted this much better
    min_count: float = 40     # ...and only for actions the model saw at least this often in training

    def weights(self) -> np.ndarray:
        return np.asarray([getattr(self, c) for c in COMPONENTS], dtype=np.float32)

    def to_dict(self) -> dict:
        return asdict(self)


def available(obs: dict, level_explored: bool, blocked: set[str], rest_stalled: bool) -> list[str]:
    """The actions that can be carried out right now, in ACTIONS order."""
    inv, hostiles = obs["inv"], obs["n_hostiles"] > 0
    adjacent = any(max(abs(m["dx"]), abs(m["dy"])) <= 1 for m in obs["mons"])
    hurt = obs["hp"] < obs["hp_max"]
    status = obs.get("status") or []
    calm = not any(x.startswith("Berserk") for x in status)             # no potions or scrolls in a rage
    can_read = calm and not any(x.startswith(("silenced", "Conf")) for x in status)
    can = {
        "explore": not hostiles and not level_explored,
        "fight": hostiles,
        "rest": not hostiles and (hurt or obs["mp"] < obs["mp_max"]) and not rest_stalled,
        "descend": obs["on_down"] or obs["dist_down"] >= 0,
        # the stairs up from D:1 leave the dungeon
        "flee_up": hostiles and (obs["on_up"] or obs["dist_up"] >= 0)
                   and not (obs["place"] in ("", "Dungeon") and obs["depth"] <= 1),
        "quaff_heal": inv["heal"] > 0 and hurt and calm,
        "quaff_unknown": inv["unknown_potions"] > 0 and calm,
        "read_unknown": inv["unknown_scrolls"] > 0 and can_read,
        "read_teleport": inv["teleport"] > 0 and hostiles and can_read,
        "wait": hostiles and not adjacent,
        # Trog's Berserk: refused while berserk or exhausted, which the no-progress block then handles
        "berserk": hostiles and obs.get("god") == "Trog" and not any(x.startswith(("Berserk", "-Berserk")) for x in status),
    }
    return [a for a in ACTIONS if can[a] and a not in blocked]


def baseline(obs: dict, avail: list[str], level_explored: bool) -> str:
    """Rules of thumb: the stub's behaviour, plus drinking a healing potion instead of giving up."""
    frac = obs["hp"] / max(obs["hp_max"], 1)
    if obs["n_hostiles"]:
        near = [m for m in obs["mons"] if max(abs(m["dx"]), abs(m["dy"])) <= 2]
        rage = frac <= 0.5 or any(m["threat"] >= 2 for m in near) or len(near) >= 3
        order = (["berserk"] if rage and near else []) + (["quaff_heal"] if frac <= 0.5 else []) + \
                ["fight", "descend", "flee_up", "wait"]
    else:
        order = (["rest"] if frac < 0.8 else ["read_unknown", "quaff_unknown"]) + \
                (["descend"] if level_explored else ["explore"]) + ["rest", "descend", "explore"]
    return next((a for a in order if a in avail), avail[0])


class BrainTiers(StubTiers):
    """Reflex's tiers object with the trained brain choosing. Without a net it plays the baseline."""

    def __init__(self, net: TrainedNet | None = None, style: Style | None = None, epsilon: float = 0.0,
                 rng: random.Random | None = None, script: list[str] | None = None, horizon: int = 0):
        super().__init__()
        # A fork (forks.py): replay `script`'s choices, whose last one is the alternative being tried,
        # then play on as usual for `horizon` game turns (0 = to the end).
        self.script, self.horizon = script or [], horizon
        self.choices = 0
        self.fork_turn: int | None = None
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

    # --- choosing ------------------------------------------------------

    def next_action(self, state: GameState) -> str:
        self.last = self.choice = None
        hostiles = self.active_hostiles(state)
        if not hostiles:
            self.approach = False
        if state.caught:
            return "struggle"
        if not hostiles and not self.level_explored and self.unvisited_shop(state):
            # see StubTiers: explore would wedge on the shop menu. A berserker can't shop, and Reflex
            # would wait forever for the menu, so let the rage pass first.
            return "wait" if any(x.startswith("Berserk") for x in state.statuses) else "shop"
        frac = state.hp / state.hp_max
        obs = observe(state, hostiles, {
            "level_explored": self.level_explored, "level_steps": self.level_steps, "level_turn": self.level_turn,
            "hp_delta": 0.0 if self.prev_frac is None else frac - self.prev_frac, "last_action": self.last_action})
        self.prev_frac = frac
        blocked = {a for a, until in self.blocked.items() if state.turn < until}
        avail = available(obs, self.level_explored, blocked, self.rest_stalled_at == (state.turn, state.hp))
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
        base = baseline(obs, avail, self.level_explored)
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
        letters = inventory(state)["letters"]
        item = {"quaff_heal": ("q", "heal"), "quaff_unknown": ("q", "unknown_potions"),
                "read_unknown": ("r", "unknown_scrolls"), "read_teleport": ("r", "teleport")}
        if action in item:
            verb, kind = item[action]
            if kind not in letters:
                return ActResult()
            result = self.through_menu(conn, verb, letters[kind])
            if result.blocking in ITEM_PROMPTS:
                # The scroll wants a target or an item (blinking, identify, enchant...). There is no
                # action for that yet: cancel, and say yes to "really abort and waste the scroll?".
                # Sent together, because act() would wait forever between the two.
                after = conn.act("key_esc", "Y", through_menu=True)
                after.messages = result.messages + after.messages
                return after
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
        opened = conn.act(verb)
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
        self.stalls[self.choice] = self.stalls.get(self.choice, 0) + 1
        if self.stalls[self.choice] < 2:
            return
        self.stalls.pop(self.choice)
        item = self.choice in ("read_unknown", "quaff_unknown", "quaff_heal", "read_teleport")
        self.blocked[self.choice] = UNTIL_LEVEL if item else state.turn + BLOCK_TURNS
        if self.choice == "fight":
            # out of reach (behind glass, across water). Explore won't run with it in view, so stop
            # exploring this level and head for the stairs rather than pacing between the two.
            self.ignored |= {m.id for m in state.hostiles()}
            self.level_explored = True

    def describe(self) -> dict:
        return {"model": self.net.name if self.net else None, "epsilon": self.epsilon, "style": asdict(self.style)}
