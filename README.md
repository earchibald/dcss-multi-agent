# dcss-multi-agent

A decision-ladder player for Dungeon Crawl Stone Soup. Concept and open questions:
[DCSS Decision Ladder](https://claude.ai/artifact/Ya5MnWtmtUYGAQGQV9tATv).

This repo currently holds the **Reflex tier prototype**: a loop that walks, stops on
every interrupt, and logs it. No models yet. A small deterministic stub stands in for
Jev, Tactics and Strategy so games keep moving; when it has no safe answer it ends the
game and logs an `escalation`, which marks where the higher tiers will take over.

## Setup

Requires Homebrew, Docker via Colima (no Docker Desktop), and uv.

```bash
brew install colima docker docker-compose docker-buildx uv
brew services start colima          # or: colima start --cpu 6 --memory 8
docker compose up -d --build        # builds DCSS 0.34.0 natively (~5 min the first time)
uv sync
```

The server listens on `localhost:8080` only. Open it in a browser to watch a game:
log in as the bot and spectate, or use your own account.

### Secrets

Account passwords live in macOS Keychain, service `dcss-ladder`, account
`dcss-account/<username>`. The first run creates a random password and registers the
account. If the server volume is reset (`docker compose down -v`), the next run
re-registers with the same Keychain password.

## Run

```bash
uv run ladder spike --games 3 --seed 1 --max-steps 500
uv run ladder spike --record ...    # also saves raw protocol messages per game
```

Each run writes `runs/<timestamp>/`:
- `interrupts.jsonl`: one line per interrupt, with kind, source (`dcss` = DCSS's own stop,
  `ladder` = our detector), decision type, details, a state snapshot and the last messages
- `summary.json`: games, and counts by kind, source and place

## Jev routing (offline)

`profiles.toml` maps tiers to model profiles; each profile names a Keychain item, never a key.
Jev uses `dcss-ladder / typesafe`. Add your TypeSafe key once (prompts for the value):

```bash
security add-generic-password -s dcss-ladder -a typesafe -w
```

Then run Jev over a logged run and see where the routing policy sends each interrupt:

```bash
uv run ladder jev-eval runs/<dir> --dry-run      # plan only: requests built, rule 1 applied, no calls
uv run ladder jev-eval runs/<dir> --limit 40     # ask Jev; answers saved to runs/<dir>/jev.jsonl
uv run ladder retune runs/<dir> --threat 1.5     # re-route stored answers, no new calls, plus a threshold sweep
```

## Test

```bash
uv run pytest                       # unit tests + recorded-game replay, no server needed
uv run pytest -m integration        # live: scenario room + a seeded run (needs the server)
```

Integration tests use their own account (`laddertest`) and dcss-api's scenario builder
(wizard mode) for the reproducible test room in `tests/scenarios/`.

## Layout

| Path | What |
|---|---|
| `server/` | Webtiles image: DCSS 0.34.0 built without DGAMELAUNCH so wizard mode works. Adapted from nkhoit/dcss-webtiles (MIT) |
| `src/ladder/conn.py` | dcss-api wrapper: login via Keychain, game start, `act()` that never waits on a prompt that can't come |
| `src/ladder/state.py` | Folds webtiles' partial `player`/`map`/`msgs` updates into a game state and snapshot |
| `src/ladder/interrupts.py` | Native-stop classification and our detectors: HP slope, status change, no progress, prompts, junctions |
| `src/ladder/travel.py` | Stepwise BFS travel, so every step passes through the detectors |
| `src/ladder/reflex.py` | The loop, plus `StubTiers` (placeholder decisions) |
| `src/ladder/crawlrc.txt` | The rc file we ship: part of Reflex is DCSS configuration |

## Notes from building it

- dcss-api's `read_until` blocks with no timeout and holds the GIL. `act()` waits for any
  `input_mode` and treats a menu as a prompt; waiting for command mode alone hangs on menus
  such as `G` (interlevel travel).
- A new game's first prompt arrives with the start messages; a resumed game's arrives
  later. `Connection._settle` handles both.
- Webtiles keeps remembered monsters on cells that left view; visibility comes from the
  `UNSEEN`/`MM_UNSEEN` bits of the cell's tile background.
- nkhoit/dcss-ai has no license, so it is a design reference only; no code is copied.
