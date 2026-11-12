# ladder-fleet

Plays the trained brain's games on other Macs. One binary, two roles:

- **server**, on the driving Mac: takes requests (`selfplay`, `eval`, `forks`), cuts them into batches,
  hands each batch to a run host, collects the games into `runs/brain/<name>/` and merges them.
- **agent**, on each run host: pairs once, offers some number of games at once, installs what it needs,
  plays batches and sends the games back. Installed as a LaunchAgent, so it survives logout and reboot.

## How a run goes

1. `ladder-fleet selfplay --games 200` asks the server. The server runs `ladder brain fleet-jobs` (Python)
   to turn the request into named runs of jobs: seeds, or fork jobs. An evaluation skips seeds it
   already has.
2. The server snapshots the repo's code: tracked and new files, not ignored ones, so uncommitted work
   goes too. The snapshot is named by its content. Every batch of the run plays that code.
3. Every 10 s each agent reports its **offer**: performance cores + half the efficiency cores − 2,
   capped by memory (1 GB per game after 4 GB), by its owner's `maxWorkers`, by another Docker's CPUs;
   0 on battery, when too hot, when the disk is nearly full or, with `idleOnlyMinutes`, while someone
   is using the Mac. A run can cap it further (`--max-per-host`, `--hosts`).
4. The server gives a ready host a batch of `offer × --per-worker` games (3 by default). The host
   fetches the code and image if it doesn't have them, plays the batch with
   `ladder brain fleet-shard` against its own DCSS server, and sends back a tarball of the games.
5. The server unpacks them into `<out>/<name>/` and runs `ladder brain fleet-merge`, which writes
   `results.json` in selfplay's own format. `ladder brain eval` reuses a finished fleet evaluation.
   `ladder brain corpus` reads the step logs.

If a host drops out, its batch goes back in the queue. A game that hung or crashed is retried once on
any host; after that it counts as lost. A batch finished while the server was unreachable waits on
the host and is sent when it reconnects. Run state survives a server restart (`scheduler.json`).

## Setting up: this M5 plus the M4 and the M1

On the M5, from a checkout that has `src/ladder/brain/fleet.py`:

```bash
mac/Fleet/build.sh --install                 # ~/.local/bin/ladder-fleet, signed with your Developer ID
docker compose build                         # the DCSS image, if it isn't built yet
ladder-fleet server install --out ~/Code/dcss-multi-agent/runs/brain   # LaunchAgent; or `ladder-fleet server` in a terminal
ladder-fleet invite
```

`invite` prints a code (good for 30 minutes and any number of hosts) and one command. Run that command
in Terminal on the M4 and on the M1. It downloads the binary from the M5, pairs, and installs the
agent. The agent then sets itself up:

- **uv**: the one on the PATH, or the latest release, into the fleet folder.
- **Docker**: the Mac's own if `docker info` works. Otherwise colima, lima and the docker CLI are
  downloaded into the fleet folder and a colima VM (profile `ladder-fleet`, vz) is started, sized to
  the offer. No Homebrew and no sudo.
- **The DCSS image**: streamed from the server (about 185 MB) and `docker load`ed. A container
  `ladder-fleet-dcss` runs it on 127.0.0.1:8180, so a DCSS on 8080 isn't disturbed.
- **The code**: per run, unpacked into the fleet folder's `checkout/`, then `uv sync --frozen --no-dev`.
  The first time, that downloads Python 3.12.

**Over SSH.** The agent keeps the fleet key in the login keychain and runs as a LaunchAgent, and both
need the host's user logged in on its screen. Over SSH the login keychain is locked and macOS can't
show its prompt (`Keychain add failed: -25308`). So before pairing, `join` explains this and asks for
the login password on the terminal, with echo off (`readpassphrase`), and unlocks the keychain with it
in-process (`SecKeychainUnlock`); the password is never on a command line, in a file or sent to the
server. An empty line skips it with nothing changed. Plain `ssh host 'cmd'` has no terminal to ask on:
use `ssh -t`. If nobody is logged in on the host's screen, the key is
saved but the LaunchAgent can't start: log in on it once (for a headless Mac, turn on automatic login,
which needs FileVault off), then run `~/ladder-fleet install`. After a reboot the agent comes back only
once someone, or automatic login, has logged in.

**Local Network permission.** macOS's Local Network privacy keeps a LaunchAgent off the LAN until
someone allows it (anything run in Terminal or over SSH is exempt, which is why `join` itself gets
through). The agent spots this (`unsatisfiedReason == .localNetworkDenied`, or on macOS 26 ENETDOWN on a
path that says it's satisfied), says so once, and holds each attempt open for 15 s so macOS can ask, on
the host's screen, whether "ladder-fleet" may find and connect to devices on the local network. Click
Allow there (Screen Sharing works), or turn ladder-fleet on in System Settings > Privacy & Security >
Local Network. A refused connection doesn't go ahead by itself once allowed, so the agent keeps making
fresh ones and connects within about 15 s. macOS tracks the
permission by code signature, so a Developer ID self-update shouldn't ask again. After installing, `join`
(and `install`) waits to see the agent reach the server and prints this if it's blocked.

On a host, `ladder-fleet check` says whether the agent is running and can reach the server (from
`link.json`, which the agent keeps up to date) and shows the end of its log; on the server, a host that
has paired but never connected says so. Once connected, `ladder-fleet hosts` shows each host with its
offer and why, power, heat, idle time, disk, and what it has installed so far.

## Commands

```bash
ladder-fleet hosts
ladder-fleet runs
ladder-fleet selfplay --games 300 --seed 20001 --model models/brain.json --epsilon 0.2 --wait
ladder-fleet eval baseline models/brain.json models/iter4.json --games 200 --wait   # alias: versus
ladder-fleet forks ~/Code/dcss-multi-agent/runs/brain/iter4 --points 200 --model models/brain.json --wait
ladder-fleet cancel <run>
ladder-fleet forget <host>          # it can't connect until it joins again
```

Every run takes `--style KEY=VALUE...`, `--hosts m4,m1-mini`, `--max-per-host N` and `--per-worker N`.

## A run host's limits

Each host's `~/Library/Application Support/LadderFleet/agent.json` has a `policy`. Any field may be left out:

```json
{ "policy": { "maxWorkers": 6, "reserveCores": 2, "allowOnBattery": false,
              "idleOnlyMinutes": 10, "gbPerWorker": 1.0, "minFreeDiskGB": 10 } }
```

The agent reads it at start: `launchctl kickstart -k gui/$(id -u)/com.dcss-ladder.fleet-agent`.
The agent holds a no-idle-sleep assertion while it plays. A laptop with its lid closed on battery
sleeps anyway, and by default it offers nothing on battery.

## Security

- The channel is X25519 combined with a pre-shared key, then ChaCha20-Poly1305 frames numbered by a
  counter. A frame can't be read, forged, replayed or reordered without the key.
- The fleet key is 32 random bytes in each Mac's Keychain (`dcss-ladder` / `fleet-key`). Nothing
  secret is written to a file, a log or a command line.
- Pairing uses the invite code as the pre-shared key. A recorded pairing can't be brute-forced
  offline, because the session key also needs the X25519 secret. Five wrong codes close the invite.
- The binary download is plain HTTP. The invite prints its SHA-256. Self-updates check the hash the
  server sent over the authenticated channel.
- An agent runs only allow-listed `ladder brain` commands, on code from the server it paired with.
  Pairing with a server means trusting it to run code on that Mac.
- To revoke every host, delete the server's `fleet-key` Keychain item and restart the server; hosts
  must then join again. `forget` drops one host by name, which is a courtesy rather than a lock,
  since the key is shared.

## Updating

Rebuild on the server (`build.sh --install`) and restart it. On connecting, each agent compares its
binary with the server's. An installed agent downloads the new one between batches, checks its
SHA-256, replaces itself and lets launchd restart it.

Sign with a Developer ID (`build.sh` does). The Keychain trusts a Developer ID binary by identifier
and team, so a new build reads the fleet key without asking. An ad-hoc signature is a hash of the
binary: every new build raises a Keychain prompt, and a run host with nobody at it waits on that
prompt forever.

## Files

| Where | What |
|---|---|
| `Sources/FleetCore/Wire.swift` | Messages between agents and server, and the control socket's |
| `Sources/FleetCore/Crypto.swift`, `Channel.swift` | Handshake, sealed frames, byte streams (Network.framework, in-memory for tests), file transfer |
| `Sources/FleetCore/Scheduler.swift` | Batches by offer, retries, hosts dropping out, restart; the offer policy |
| `Sources/FleetCore/System.swift`, `Shell.swift` | Fleet folder, Keychain, what this Mac is and how it's doing, sleep assertion; running tools |
| `Sources/ladder-fleet/Server.swift` | The server: listeners (Bonjour, control socket, binary download), artifacts, ingest and merge |
| `Sources/ladder-fleet/Agent.swift`, `Provision.swift` | The agent: session, offers, batches, self-update, pairing, LaunchAgent; installing uv, Docker, image, code |
| `../../src/ladder/brain/fleet.py` | The Python side: `fleet-jobs`, `fleet-shard`, `fleet-merge` |

Tests: `swift test` here and `uv run pytest tests/test_fleet.py`.

The fleet folder is `~/Library/Application Support/LadderFleet`; `$LADDER_FLEET_HOME` overrides it,
and gives that fleet its own Keychain account, which is how one Mac can run a test server and agent.
Logs are in its `logs/`: `agent.log`, `server.log`, and `games.log` for the games' own output.

## Checked so far

On one Mac, a server and an agent with separate fleet folders went through pairing (a wrong code was
refused), downloading the binary, setting up with an existing Docker, two self-play runs and an
evaluation in batches, killing the agent mid-batch (the batch was requeued and replayed), `ladder brain
eval` reusing the fleet's evaluation, self-update with a Developer ID signature and no Keychain
prompt, and the code going out once for two runs. Not yet run on a second Mac: setting up colima from
scratch and loading the streamed image (the export itself was checked: 185 MB in 3 s).
