"""Stepwise travel over the known map.

Reflex walks one square per action so the detectors look at every step.
DCSS's own interlevel travel (G) opens a menu, which is a prompt, not a walk.
"""

from __future__ import annotations

from collections import deque

from .state import MF_TRAP, NOT_WALKABLE, GameState

DIRECTIONS = {
    (0, -1): "key_dir_n", (1, -1): "key_dir_ne", (1, 0): "key_dir_e", (1, 1): "key_dir_se",
    (0, 1): "key_dir_s", (-1, 1): "key_dir_sw", (-1, 0): "key_dir_w", (-1, -1): "key_dir_nw",
}
AVOID = NOT_WALKABLE | {MF_TRAP}


def first_step(state: GameState, goal_mf: int) -> str | None:
    """Direction key for the first step of a shortest known path to the nearest cell with `goal_mf`.

    Returns None when no such cell is reachable over explored, walkable ground.
    """
    start = state.pos
    cells = state.cells
    prev: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    queue = deque([start])
    while queue:
        cur = queue.popleft()
        if cur != start and cells.get(cur, {}).get("mf") == goal_mf:
            while prev[cur] != start:
                cur = prev[cur]
            return DIRECTIONS[(cur[0] - start[0], cur[1] - start[1])]
        for dx, dy in DIRECTIONS:
            nxt = (cur[0] + dx, cur[1] + dy)
            if nxt in prev:
                continue
            cell = cells.get(nxt)
            if cell is None or cell.get("mf", 0) in AVOID:
                continue
            prev[nxt] = cur
            queue.append(nxt)
    return None
