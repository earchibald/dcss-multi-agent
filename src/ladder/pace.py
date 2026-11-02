"""DCSS's own step delay during explore and travel, matched to the cockpit's speed.

One explore or travel action can cover a whole hallway. With the rc's
`travel_delay = -1` the game draws only where it ends, so at any speed but
full a viewer sees the player jump. The delay is a game option, read when the
game starts, but Lua can change it mid-game: the rc defines one Lua function
per level, each bound to a key no command uses, and Reflex sends the key when
the speed changes.
"""

from __future__ import annotations

import math

PACE_MS = (-1, 100, 125, 150, 200, 250, 300, 400, 500, 700, 1000)   # -1: draw only where a run ends
KEY_BASE = 0x2460        # ① ② ③…: never typed at DCSS, and webtiles passes them through as keycodes


def pace_ms(delay: float) -> int:
    """Per-step delay for a pause of `delay` seconds between actions: none at full speed, else 0.1s and up."""
    if delay <= 0:
        return -1
    want = 100 * math.sqrt(1 + delay)
    return min(PACE_MS[1:], key=lambda ms: abs(ms - want))


def pace_key(ms: int) -> str:
    return chr(KEY_BASE + PACE_MS.index(ms))


def pace_rc() -> str:
    """rc lines defining the Lua setters and binding their keys."""
    lines = ["{"]
    for i, ms in enumerate(PACE_MS):
        lines.append(f'function ladder_pace_{i}() crawl.setopt("travel_delay = {ms}") '
                     f'crawl.setopt("explore_delay = {ms}") end')
    lines.append("}")
    lines += [f"macros += M \\{{{KEY_BASE + i}}} ===ladder_pace_{i}" for i in range(len(PACE_MS))]
    return "\n".join(lines) + "\n"
