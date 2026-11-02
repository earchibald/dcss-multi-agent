# dcss-multi-agent

A decision-ladder player for Dungeon Crawl Stone Soup. Concept and open questions:
[DCSS Decision Ladder](https://claude.ai/artifact/Ya5MnWtmtUYGAQGQV9tATv).

This repo currently holds the **Reflex tier prototype** and a first **web cockpit**.
Reflex walks, stops on every interrupt, and logs it. A small deterministic stub stands
in for Tactics and Strategy so games keep moving; when it has no safe answer it raises
an `escalation`, which marks where the higher tiers will take over. Jev runs live in the
cockpit as shadow routing (it shows where each interrupt would go; Reflex still acts).

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
- `decisions.jsonl`: one line per decision point: options, recommendation, choice, who decided
- `summary.json`: games, and counts by kind, source, place and decider

## Cockpit

```bash
uv run ladder cockpit --seed 1 --max-steps 300 --open
uv run ladder cockpit --mode autonomous --idle-minutes 10 --jev
```

A local web app on `http://127.0.0.1:8090/`, beside webtiles (its "Watch in webtiles"
link spectates the bot). It shows:
- **Escalation stream**: every interrupt as it happens, with the tier the routing policy
  sends it to. With `--jev`, Jev is asked about each one in the background and the row
  shows its answers and latency; without it, only decision types and bookkeeping are routed.
- **Your call**: decision points (stairs, altars, uniques, the level-up stat prompt,
  escalations) wait for you when `Authority` says the player decides. Each card offers
  only what Reflex can carry out, marks the stub's recommendation, and has two ways out:
  *Take the wheel* (stop, game left saved) and *End game*. Number keys answer.
- **Control**: Assisted / Autonomous, the idle switch (whole minutes, `0` = never, with a
  countdown on the card), *Hold at next event*, and *Take the wheel*.
- **Speed**: *Pause between actions* (0–5 s on the slider; `--delay` sets it at start, up
  to 60 s) slows Reflex down so you can follow it in webtiles. *Step ▸* runs N Reflex
  actions (default 1) and holds again; from a running game it holds after the next N.
  One action can cover many turns: an autoexplore runs until something interrupts it.
  At any pause above 0, DCSS's own explore and travel also walk at 0.1 s per square or
  slower, rising with the pause, so the player doesn't jump down a hallway. At 0 they run
  at full speed. The rc can't change that delay mid-game, so the shipped rc binds a Lua
  setter for each step to a key no command uses (`ladder/pace.py`), and Reflex sends the
  key when the speed changes.

To take the wheel, log in to webtiles as the bot with the password from Keychain
(`security find-generic-password -s dcss-ladder -a dcss-account/ladderbot -w`). The
next `ladder cockpit` or `ladder spike` resumes the saved game.

The game runs in a child process: dcss-api's `read_until` blocks with no timeout and
holds the GIL, so a server in the same process would freeze with it. If the game goes
quiet for 45 s while nothing is waiting on you, the stream says so; Ctrl-C leaves the
game saved and the next start resumes it. Decisions are logged to `runs/<dir>/decisions.jsonl`.

## Claude Code channel

The running game can talk to a Claude Code session in this repo, and Claude can answer. `.mcp.json`
registers `ladder channel`, a [channel](https://code.claude.com/docs/en/channels-reference) MCP server that
Claude Code spawns over stdio. It subscribes to the cockpit's event stream on 127.0.0.1:8090 and pushes
these into the session as `<channel source="cockpit" kind="...">` events:

- **notes** you write in the cockpit's *Claude Code* panel (⌘/Ctrl-Enter sends)
- **errors** from the game process, with the traceback, and **stalls**
- **escalations**, **deaths** and **no-progress** loops, with place, turn, HP and the last game messages
- **run start** (with the log directory), **game end**, **run end**, and the cockpit going away mid-run

Everything else (routine interrupts, status, settings) stays in the cockpit. Claude has two tools: `reply`
(its text shows in the cockpit's stream) and `cockpit_state` (run, game, settings, the waiting decision,
recent events).

```bash
bin/claude-cockpit                # = claude --dangerously-load-development-channels server:cockpit; approve the warning
uv run ladder cockpit --seed 1    # in another terminal, any time
```

Channels are a research preview: custom channels aren't on the allowlist, so they need the development flag,
which works in interactive sessions only (not `-p`, the Agent SDK or background sessions), and no setting
replaces it. On a Team or Enterprise plan an admin has to enable channels. The channel reconnects by itself,
so the cockpit can be stopped and started under one coding session.

`.claude/settings.json` enables the server and allows its two tools, so every session in the repo can call
`reply` and `cockpit_state`. Only a session started with the flag hears the cockpit, though: `ladder channel`
looks at the `claude` process above it and stays off the event stream otherwise, so the panel's *listening*
means a session that will get your notes. Notes are refused when nobody is listening. One listener is
enough. `ladder channel --listen always|never` overrides the check; point it at another port with
`--cockpit http://127.0.0.1:<port>`, both in `.mcp.json`.

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

## Models

`profiles.toml` puts Strategy on `claude-opus-5` through the Anthropic adapter (official
SDK, server-side refusal fallbacks on) and Tactics on DeepSeek V4.1 Flash (`deepseek-flash`)
through the OpenAI-compatible adapter (official OpenAI SDK, any base URL; JSON via
`json_object` with the schema in the prompt). The `deepseek-anth` spare reaches the same model
through DeepSeek's Anthropic-style endpoint. Keys go in Keychain the same way:

```bash
security add-generic-password -s dcss-ladder -a anthropic -w
security add-generic-password -s dcss-ladder -a deepseek -w
```

## Who decides

`src/ladder/authority.py`: in assisted mode the player decides every decision type that
isn't deferred; in autonomous mode Strategy decides everything, pinned types included.
The idle switch hands a waiting decision to Strategy after a whole number of minutes
(`0` = never) and flips the session to autonomous.

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
| `src/ladder/reflex.py` | The loop, `Hooks` (how it reaches the tiers and the cockpit), and `StubTiers` (placeholder decisions) |
| `src/ladder/decisions.py` | Decision requests: the options Reflex can carry out, the stub's recommendation, Authority's context |
| `src/ladder/games.py` | Plays a run of games; shared by `spike` and the cockpit |
| `src/ladder/cockpit.py`, `static/` | The cockpit: game process, hub, HTTP + server-sent events on 127.0.0.1 |
| `src/ladder/channel.py`, `.mcp.json` | Claude Code channel: cockpit events into a coding session, `reply` and `cockpit_state` back |
| `bin/claude-cockpit`, `.claude/settings.json`, `CLAUDE.md` | Start the listening session; the server and its tools enabled for every session; notes for Claude |
| `src/ladder/crawlrc.txt` | The rc file we ship: part of Reflex is DCSS configuration |
| `src/ladder/jev.py`, `routing.py`, `jeveval.py` | Jev questions, the routing rules, and the offline evaluator |
| `src/ladder/llm.py`, `profiles.py` | Anthropic and OpenAI-compatible adapters; profiles with capability flags |
| `src/ladder/authority.py` | Assisted vs autonomous decisions and the idle switch |

## Notes from building it

- dcss-api's `read_until` blocks with no timeout and holds the GIL. `act()` waits for any
  `input_mode` and treats a menu as a prompt; waiting for command mode alone hangs on menus
  such as `G` (interlevel travel).
- Greedy explore walks into every unvisited shop and opens its menu. A menu sends no
  `input_mode`, and here it came in a later frame than explore's busy `input_mode 0`, so
  `act()` waited forever (seed 777, turn 39). Reflex visits shops itself first and waits
  for the menu with `Connection.open_menu`.
- A new game's first prompt arrives with the start messages; a resumed game's arrives
  later. `Connection._settle` handles both.
- Webtiles keeps remembered monsters on cells that left view; visibility comes from the
  `UNSEEN`/`MM_UNSEEN` bits of the cell's tile background.
- dcss-api's `start_game_with_scenario` overwrites the account's rc with its own two-line
  example (`show_more = false`, `rest_delay = -1`), so scenario games don't run on
  `crawlrc.txt`. To test an rc option in a scenario, save by hanging up, `set_rc`, and resume.
- nkhoit/dcss-ai has no license, so it is a design reference only; no code is copied.
