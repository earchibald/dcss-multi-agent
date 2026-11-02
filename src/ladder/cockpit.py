"""The cockpit: a local web app beside webtiles.

Two processes. The game runs in a child process, because dcss-api's
`read_until` blocks with no timeout and holds the GIL: a web server sharing its
process would freeze whenever the game waits. The parent serves the page and a
server-sent event stream on 127.0.0.1, holds `Authority`, and answers the
child's decision requests over a pipe: Strategy (still the stub's
recommendation) or the player, with the idle switch ticking in between.

`ladder channel` (a Claude Code channel, see channel.py) subscribes to the same
stream as `/events?client=channel`: the page shows whether a coding session is
listening, and notes go both ways through `/api/note`.

With `--jev`, every interrupt that needs Jev is also sent to it in the
background and routed by the policy, so the stream shows which tier would take
it. That routing is shadow only for now: Reflex and the stub still act.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import multiprocessing as mp
import queue
import signal
import threading
import time
import traceback
import uuid
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from . import keychain
from .authority import ASSISTED, AUTONOMOUS, Authority, Pending
from .decisions import TAKE_OVER, Answer, DecisionRequest
from .games import run_games
from .jev import Jev, build_state
from .jeveval import SeenBefore
from .pace import pace_ms
from .reflex import Hooks
from .routing import Thresholds, needs_jev, route

STRATEGY_STUB = "stub recommendation; Strategy isn't built yet"
GAME_GONE = "the run is over, so there is no game to send that to; start the cockpit again for a new run"
MAX_DELAY = 60           # seconds between actions
MAX_STEPS = 1000         # actions per Step
MAX_NOTE = 4000          # characters in a note to or from Claude
NO_CHANNEL = ("no Claude Code session is listening; start one in this repo with "
              "`claude --dangerously-load-development-channels server:cockpit`")


# --- child process: the game ------------------------------------------------

class ChildHooks(Hooks):
    """Reflex's hooks in the game process: report everything, wait on the parent for decisions."""

    def __init__(self, pipe, delay: float = 0.0):
        self.pipe = pipe
        self.held = False
        self.stopping = False
        self.delay = delay              # seconds between actions, so a person can follow the game
        self.steps_left = 0             # actions to run before holding again
        self.last_action = 0.0

    def send(self, ev: str, **data) -> None:
        self.pipe.send({"ev": ev, **data})

    def _handle(self, msg: dict) -> dict | None:
        cmd = msg.get("cmd")
        if cmd == "hold":
            self.held, self.steps_left = True, 0
        elif cmd == "resume":
            self.held, self.steps_left = False, 0
        elif cmd == "step":
            self.held, self.steps_left = True, msg["n"]
        elif cmd == "speed":
            self.delay = msg["delay"]
        elif cmd == "stop":
            self.stopping = True
        elif cmd == "answer":
            return msg
        return None

    def _holding(self) -> bool:
        return self.held and not self.steps_left and not self.stopping

    def _pace(self) -> None:
        """Wait out the pause since the last action, still taking commands: a new speed applies at once."""
        while not self.stopping and not self._holding():
            left = self.last_action + self.delay - time.monotonic()
            if left <= 0:
                return
            if self.pipe.poll(left):
                self._handle(self.pipe.recv())

    def checkpoint(self) -> bool:
        while self.pipe.poll():
            self._handle(self.pipe.recv())
        self._pace()
        if self._holding():
            self.send("paused", paused=True)
            while self._holding():
                self._handle(self.pipe.recv())
            self.send("paused", paused=False)
        if self.steps_left:
            self.steps_left -= 1
        return not self.stopping

    def decide(self, request: DecisionRequest) -> Answer:
        self.send("decision", request=request.to_dict())
        while True:
            msg = self._handle(self.pipe.recv())
            if msg and msg.get("id") == request.id:
                return Answer(msg["choice"], msg["decider"], msg.get("reason", ""))

    def on_record(self, record: dict) -> None:
        self.send("record", record=record)

    def pace_ms(self) -> int:
        return pace_ms(self.delay)

    def on_step(self, reflex, action: str) -> None:
        self.last_action = time.monotonic()
        self.send("step", game=reflex.game_no, step=reflex.steps, action=action,
                  snapshot=reflex.state.snapshot(), messages=reflex.state.recent_messages(5))


def child_main(pipe, args: argparse.Namespace) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)     # Ctrl-C goes to the parent, which stops us cleanly
    faulthandler.register(signal.SIGUSR1)            # `kill -USR1 <pid>` prints stacks, even inside read_until
    hooks = ChildHooks(pipe, args.delay)
    try:
        run_games(args, hooks, on_event=hooks.send)
    except Exception:
        hooks.send("error", message=traceback.format_exc(limit=8))
    finally:
        pipe.close()


# --- parent process: the hub ------------------------------------------------

class Hub:
    """Cockpit state shared by the pipe reader, the idle ticker and the HTTP handlers."""

    def __init__(self, authority: Authority, send: Callable[[dict], None], jev: Jev | None = None,
                 thresholds: Thresholds = Thresholds(), clock: Callable[[], float] = time.time,
                 backlog: int = 500, links: dict | None = None, stall_after: float = 45.0, delay: float = 0.0):
        self.authority = authority
        self._send = send
        self.jev = jev
        self.thresholds = thresholds
        self.clock = clock
        self.links = links or {}
        self.lock = threading.RLock()
        self.events: deque[dict] = deque(maxlen=backlog)
        self.subscribers: set[queue.Queue] = set()
        self.seq = 0
        self.status: dict = {}
        self.run: dict = {"state": "starting", "games": []}
        self.pending: dict | None = None
        self.held = False
        self.paused = False
        self.delay = delay
        self.tiers: Counter[str] = Counter()
        self.deciders: Counter[str] = Counter()
        self.seen = SeenBefore()
        self.pool = ThreadPoolExecutor(2, thread_name_prefix="jev") if jev else None
        self.stall_after = stall_after
        self.last_heard = clock()
        self.stalled = False
        self.gone = False                   # the game process has exited and its pipe is closed
        self.boot = uuid.uuid4().hex        # tells a reconnecting channel whether this is the cockpit it knew
        self.channels = 0                   # Claude Code channels subscribed to the stream

    # -- publishing --

    def publish(self, ev: str, keep: bool = True, **data) -> dict:
        with self.lock:
            self.seq += 1
            event = {"ev": ev, "seq": self.seq, "t": round(self.clock(), 3), **data}
            if keep:
                self.events.append(event)
            for q in list(self.subscribers):
                q.put(event)
            return event

    def subscribe(self, channel: bool = False) -> tuple[queue.Queue, dict]:
        with self.lock:
            q: queue.Queue = queue.Queue()
            self.subscribers.add(q)
            snapshot = self.snapshot()
            if channel:
                self.channels += 1
                self.publish("settings", keep=False, settings=self.settings())
            return q, snapshot

    def unsubscribe(self, q: queue.Queue, channel: bool = False) -> None:
        with self.lock:
            self.subscribers.discard(q)
            if channel:
                self.channels -= 1
                self.publish("settings", keep=False, settings=self.settings())

    def settings(self) -> dict:
        a = self.authority
        return {"mode": a.mode, "idle_minutes": a.idle_minutes, "switched_by_idle": a.switched_by_idle,
                "held": self.held, "paused": self.paused, "delay": self.delay, "jev": self.jev is not None,
                "channel": self.channels > 0}

    def pending_view(self) -> dict | None:
        if not self.pending:
            return None
        waited = self.clock() - self.pending["posted_at"]
        idle = self.authority.idle_minutes
        takeover = max(0.0, idle * 60 - waited) if idle and self.authority.mode == ASSISTED else None
        return {**self.pending["request"], "why_asked": self.pending["why"], "waited_s": round(waited, 1),
                "takeover_in_s": None if takeover is None else round(takeover, 1)}

    def snapshot(self) -> dict:
        with self.lock:
            return {"boot": self.boot, "settings": self.settings(), "status": self.status, "run": self.run,
                    "links": self.links, "pending": self.pending_view(), "events": list(self.events),
                    "tiers": dict(self.tiers), "deciders": dict(self.deciders)}

    def _publish_settings(self) -> None:
        self.publish("settings", keep=False, settings=self.settings())
        self.publish("pending", keep=False, pending=self.pending_view())

    # -- from the game process --

    def handle(self, msg: dict) -> None:
        msg = dict(msg)
        ev = msg.pop("ev")
        with self.lock:
            self.last_heard = self.clock()
            if self.stalled:
                self.stalled = False
                self.publish("stall", stalled=False)
            if ev == "step":
                self.status = msg
                self.publish("status", keep=False, status=msg)
            elif ev == "record":
                self._record(msg["record"])
            elif ev == "decision":
                self._decision(msg["request"])
            elif ev == "paused":
                self.paused = msg["paused"]
                self.publish("settings", keep=False, settings=self.settings())
            else:
                if ev == "run_start":
                    self.run.update(state="running", dir=msg["dir"], user=msg["user"])
                elif ev == "game_start":
                    self.status = {"game": msg["game"], "step": 0, "action": None,
                                   "snapshot": msg["snapshot"], "messages": []}
                    self.publish("status", keep=False, status=self.status)
                elif ev == "game_end":
                    self.run["games"].append(msg)
                elif ev == "run_end":
                    self.run["state"] = "finished"
                elif ev == "error":
                    self.run["state"] = "error"
                self.publish(ev, **msg)
                self.publish("run", keep=False, run=self.run)

    def child_gone(self) -> None:
        with self.lock:
            self.gone = True
            if self.pending:
                self.pending = None
                self.publish("pending", keep=False, pending=None)
            if self.run["state"] in ("starting", "running", "stopping"):
                self.run["state"] = "error"
                self.publish("error", message="the game process exited")
                self.publish("run", keep=False, run=self.run)

    def _record(self, record: dict) -> None:
        jev_state = None
        if needs_jev(record):
            r = None
            if self.jev is not None:
                jev_state = build_state(record, self.seen.before(record))
        else:
            r = route(record, None, self.thresholds)
        self.seen.add(record)
        view = asdict(r) if r else ({"tier": "asking", "reason": "asking Jev"} if jev_state else
                                     {"tier": "reflex", "reason": "Jev off"})
        if r and r.tier != "none":
            self.tiers[r.tier] += 1
        event = self.publish("record", record=record, route=view)
        if jev_state is not None:
            self.pool.submit(self._ask_jev, event, record, jev_state)

    def _ask_jev(self, event: dict, record: dict, state: dict) -> None:
        try:
            result = self.jev.ask(state)
            r = route(record, result.answers, self.thresholds)
            view = {**asdict(r), "answers": result.answers.to_dict(), "latency_ms": round(result.latency_ms)}
        except Exception as e:                     # shadow routing: report and carry on
            view = {"tier": "error", "rule": 0, "reason": f"Jev: {e}"[:200]}
        with self.lock:
            event["route"] = view
            self.tiers[view["tier"]] += 1
            self.publish("route", keep=False, ref=event["seq"], route=view)

    def _decision(self, request: dict) -> None:
        verdict = self.authority.decide(request["decision_type"], request["context"])
        if verdict.decider == "strategy":
            self._answer(request, request["recommended"], "strategy", f"{verdict.reason}; {STRATEGY_STUB}")
        else:
            self.pending = {"request": request, "posted_at": self.clock(), "why": verdict.reason}
            self.publish("pending", keep=False, pending=self.pending_view())

    def _to_game(self, cmd: dict) -> str | None:
        """Send to the game process. Once it has exited the pipe is closed, so say that instead of raising."""
        if self.gone:
            return GAME_GONE
        try:
            self._send(cmd)
        except OSError:                     # BrokenPipeError, or the handle is closed
            self.gone = True
            return GAME_GONE
        return None

    def _answer(self, request: dict, choice: str, decider: str, reason: str) -> str | None:
        err = self._to_game({"cmd": "answer", "id": request["id"], "choice": choice, "decider": decider,
                             "reason": reason})
        if err:
            return err
        self.deciders[decider] += 1
        label = next(o["label"] for o in request["options"] if o["key"] == choice)
        self.publish("decided", id=request["id"], decision_type=request["decision_type"],
                     question=request["question"], choice=choice, label=label, decider=decider, reason=reason,
                     recommended=request["recommended"], turn=request["snapshot"].get("turn"))
        if self.pending and self.pending["request"]["id"] == request["id"]:
            self.pending = None
            self.publish("pending", keep=False, pending=None)
        return None

    # -- from the player --

    def decide(self, decision_id: str, choice: str) -> str | None:
        """The player's answer. Returns an error message, or None when it was accepted."""
        with self.lock:
            if not self.pending or self.pending["request"]["id"] != decision_id:
                return "that decision isn't waiting any more"
            request = self.pending["request"]
            if choice not in {o["key"] for o in request["options"]}:
                return f"'{choice}' isn't an option"
            return self._answer(request, choice, "player", "your call")

    def set_mode(self, mode: str) -> str | None:
        if mode not in (ASSISTED, AUTONOMOUS):
            return f"mode is '{ASSISTED}' or '{AUTONOMOUS}'"
        with self.lock:
            self.authority.set_mode(mode)
            self.publish("mode", mode=mode, by="player")
            if mode == AUTONOMOUS and self.pending:
                self._answer(self.pending["request"], self.pending["request"]["recommended"], "strategy",
                             f"autonomous mode; {STRATEGY_STUB}")
            self._publish_settings()
        return None

    def set_idle(self, minutes) -> str | None:
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 0:
            return "idle minutes is a whole number, 0 for never"
        with self.lock:
            self.authority.idle_minutes = minutes
            self._publish_settings()
        return None

    def tick(self, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        with self.lock:
            self._check_stall(now)
            if not self.pending or self.gone:
                return
            request = self.pending["request"]
            verdict = self.authority.check_idle(Pending(request["decision_type"], self.pending["posted_at"]), now)
            if verdict:
                self.publish("mode", mode=AUTONOMOUS, by="idle")
                self._answer(request, request["recommended"], "strategy", f"{verdict.reason}; {STRATEGY_STUB}")
                self._publish_settings()

    def _check_stall(self, now: float) -> None:
        """dcss-api's read_until has no timeout, so a game can hang mid-action. Say so instead of looking idle."""
        waiting_on_us = self.pending or self.paused
        if self.run["state"] != "running" or waiting_on_us or self.stalled:
            return
        if now - self.last_heard >= self.stall_after + self.delay:
            self.stalled = True
            self.publish("stall", stalled=True, seconds=round(now - self.last_heard))

    def hold(self, on: bool) -> str | None:
        with self.lock:
            err = self._to_game({"cmd": "hold" if on else "resume"})
            if err:
                return err
            self.held = bool(on)
            self.publish("settings", keep=False, settings=self.settings())
            return None

    def step(self, n) -> str | None:
        """Run `n` more actions, then hold. From a running game it holds after the next `n`."""
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= MAX_STEPS:
            return f"step is a whole number of actions, 1 to {MAX_STEPS}"
        with self.lock:
            err = self._to_game({"cmd": "step", "n": n})
            if err:
                return err
            self.held = True
            self.publish("settings", keep=False, settings=self.settings())
            return None

    def set_speed(self, delay) -> str | None:
        """Seconds to wait between actions, so a person watching webtiles can keep up. 0 is full speed."""
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not 0 <= delay <= MAX_DELAY:
            return f"the pause between actions is 0 to {MAX_DELAY} seconds"
        with self.lock:
            err = self._to_game({"cmd": "speed", "delay": float(delay)})
            if err:
                return err
            self.delay = float(delay)
            self.publish("settings", keep=False, settings=self.settings())
            return None

    def note(self, text, by: str) -> str | None:
        """A note between the player and Claude Code. It goes on the stream, where the channel picks it up."""
        if by not in ("player", "claude"):
            return "a note is from 'player' or 'claude'"
        if not isinstance(text, str) or not text.strip():
            return "a note needs some text"
        if len(text) > MAX_NOTE:
            return f"a note is at most {MAX_NOTE} characters"
        with self.lock:
            if by == "player" and not self.channels:
                return NO_CHANNEL
            status = self.status or {}
            self.publish("note", by=by, text=text.strip(), game=status.get("game"), step=status.get("step"),
                         turn=(status.get("snapshot") or {}).get("turn"))
            return None

    def stop(self) -> str | None:
        """Stop after the current action and leave the game saved, so the player can take the wheel."""
        with self.lock:
            if self.gone:
                return GAME_GONE
            if self.pending:
                request = self.pending["request"]
                keys = {o["key"] for o in request["options"]}
                choice = TAKE_OVER if TAKE_OVER in keys else request["recommended"]
                self._answer(request, choice, "player", "stopped from the cockpit")
            err = self._to_game({"cmd": "stop"})
            if err:
                return err
            self.held = False
            self.run["state"] = "stopping" if self.run["state"] == "running" else self.run["state"]
            self.publish("run", keep=False, run=self.run)
            return None


# --- HTTP ---------------------------------------------------------------------

STATIC = {"/": ("cockpit.html", "text/html; charset=utf-8"),
          "/cockpit.css": ("cockpit.css", "text/css; charset=utf-8"),
          "/cockpit.js": ("cockpit.js", "text/javascript; charset=utf-8")}
CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


def make_handler(hub: Hub, port: int) -> type[BaseHTTPRequestHandler]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    static = resources.files("ladder").joinpath("static")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):
            pass

        def _allowed(self) -> bool:
            # Host and Origin checks keep other sites (and DNS rebinding) out of a localhost server.
            if self.headers.get("Host") not in hosts:
                return False
            origin = self.headers.get("Origin")
            return origin is None or urlsplit(origin).netloc in hosts

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", CSP)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: dict) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def do_GET(self):
            if not self._allowed():
                return self._json(403, {"error": "forbidden"})
            path = urlsplit(self.path).path
            if path == "/events":
                return self._events(parse_qs(urlsplit(self.path).query).get("client") == ["channel"])
            if path == "/api/state":
                return self._json(200, hub.snapshot())
            if path in STATIC:
                name, ctype = STATIC[path]
                return self._send(200, static.joinpath(name).read_bytes(), ctype)
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._allowed():
                return self._json(403, {"error": "forbidden"})
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self._json(415, {"error": "send application/json"})
            path = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            if length > (4 * MAX_NOTE + 1024 if path == "/api/note" else 4096):
                return self._json(413, {"error": "too large"})
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._json(400, {"error": "bad json"})
            if path == "/api/mode":
                err = hub.set_mode(body.get("mode"))
            elif path == "/api/idle":
                err = hub.set_idle(body.get("minutes"))
            elif path == "/api/decide":
                err = hub.decide(str(body.get("id")), str(body.get("choice")))
            elif path == "/api/hold":
                err = hub.hold(bool(body.get("hold")))
            elif path == "/api/step":
                err = hub.step(body.get("n"))
            elif path == "/api/speed":
                err = hub.set_speed(body.get("delay"))
            elif path == "/api/stop":
                err = hub.stop()
            elif path == "/api/note":
                err = hub.note(body.get("text"), str(body.get("from", "player")))
            else:
                return self._json(404, {"error": "not found"})
            self._json(409 if err else 200, {"error": err} if err else {"ok": True})

        def _events(self, channel: bool = False) -> None:
            q, snapshot = hub.subscribe(channel)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                self._event({"ev": "hello", **snapshot})
                while True:
                    try:
                        self._event(q.get(timeout=15))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                hub.unsubscribe(q, channel)

        def _event(self, data: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(data).encode() + b"\n\n")
            self.wfile.flush()

    return Handler


# --- wiring -------------------------------------------------------------------

def lobby_url(server: str) -> str:
    parts = urlsplit(server)
    scheme = "https" if parts.scheme == "wss" else "http"
    return f"{scheme}://{parts.netloc}/"


def watch_url(server: str, user: str) -> str:
    return f"{lobby_url(server)}#watch-{user}"


def game_links(server: str, user: str) -> dict:
    """Where to watch, and what the player needs to pick up a game the cockpit left saved."""
    return {"webtiles": watch_url(server, user), "lobby": lobby_url(server), "user": user,
            "password_cmd": f"security find-generic-password -s {keychain.SERVICE} "
                            f"-a {keychain.dcss_account(user)} -w | pbcopy"}


def handover_text(links: dict, game: dict) -> str:
    return (f"Game {game['game']} is saved for you at {game['final_place']}, turn {game['turns']}.\n"
            f"  1. Copy the password:  {links['password_cmd']}\n"
            f"  2. Open {links['lobby']} and log in as {links['user']}.\n"
            f"  3. Click Play: DCSS resumes the saved game.\n"
            f"To hand it back, save with Ctrl-S in DCSS and start the cockpit again; it resumes the save.")


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def serve(args: argparse.Namespace, thresholds: Thresholds = Thresholds()) -> None:
    from . import profiles

    faulthandler.register(signal.SIGUSR1)            # `kill -USR1 <pid>` prints every thread's stack
    # Ctrl-C and SIGTERM both stop cleanly, even when launched with SIGINT ignored (e.g. `cmd &` from a script).
    signal.signal(signal.SIGINT, signal.default_int_handler)
    signal.signal(signal.SIGTERM, _interrupt)
    authority = Authority(mode=args.mode, idle_minutes=args.idle_minutes)
    jev = Jev(profiles.for_tier("jev")) if args.jev else None
    parent_end, child_end = mp.Pipe()
    hub = Hub(authority, parent_end.send, jev=jev, thresholds=thresholds,
              links=game_links(args.server, args.user), delay=args.delay)
    proc = mp.get_context("spawn").Process(target=child_main, args=(child_end, args), name="ladder-game",
                                           daemon=True)
    proc.start()
    child_end.close()

    def pump() -> None:
        try:
            while True:
                msg = parent_end.recv()
                hub.handle(msg)
                if msg.get("ev") == "game_end" and msg.get("ended_by") in ("take_over", "stopped"):
                    print(handover_text(hub.links, msg), flush=True)
        except (EOFError, OSError):
            hub.child_gone()

    def ticker() -> None:
        while True:
            time.sleep(1)
            hub.tick()

    threading.Thread(target=pump, name="pump", daemon=True).start()
    threading.Thread(target=ticker, name="idle", daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(hub, args.port))
    server.daemon_threads = True
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Cockpit: {url}\nWatch the game: {hub.links['webtiles']}\nCtrl-C to stop (the game stays saved).")
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.stop()
        proc.join(timeout=20)
        if proc.is_alive():
            proc.terminate()
        server.server_close()
