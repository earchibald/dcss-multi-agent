from helpers import make_state

from ladder.state import MF_STAIR_DOWN
from ladder.travel import first_step


def test_steps_toward_nearest_downstairs():
    state = make_state(["#####", "#@..#", "#..>#", "#####"])
    assert first_step(state, MF_STAIR_DOWN) in ("key_dir_e", "key_dir_se")


def test_routes_around_walls():
    state = make_state([
        "#######",
        "#@#..>#",
        "#.#.###",
        "#...###",
        "#######",
    ])
    assert first_step(state, MF_STAIR_DOWN) == "key_dir_s"


def test_avoids_known_traps():
    state = make_state(["#####", "#@^>#", "#...#", "#####"])
    assert first_step(state, MF_STAIR_DOWN) == "key_dir_se"


def test_none_when_unreachable():
    state = make_state(["#####", "#@#>#", "#####"])
    assert first_step(state, MF_STAIR_DOWN) is None
