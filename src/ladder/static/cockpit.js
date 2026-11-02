"use strict";
// Ladder cockpit: one EventSource for everything the game process reports, small POSTs back.

const $ = (id) => document.getElementById(id);

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid);
  return el;
}

const TIER = {
  reflex: "* Reflex", asking: "J asking", jev: "J Jev", tactics: "⚔ Tactics", strategy: "✦ Strategy",
  reflex_goal: "* goal", player: "@ Player", none: "log", error: "J error", stub: "* stub",
};
const ROUTINE = new Set(["level_change", "xl_up"]);
const rows = new Map();       // record seq → stream row, for late Jev routes
let settings = {}, links = {}, pending = null, clockTimer = null, deadline = null;
let tiers = {}, deciders = {};

// ---- describing interrupts -------------------------------------------------

function monsters(list) {
  return (list || []).map((m) => `${m.name}${m.unique ? " (unique)" : ""} · ${m.threat} · ${m.dist} sq`).join(", ");
}

function describe(r) {
  const d = r.detail || {};
  switch (r.kind) {
    case "hostile_in_view": return (d.explore_refused ? "explore refused: " : "in view: ") + monsters(d.monsters);
    case "item_in_view": return `${d.count} new item${d.count === 1 ? "" : "s"}`;
    case "feature_in_view": return `${d.feature} ${d.glyph ? `'${d.glyph}' ` : ""}at ${d.dist} sq`;
    case "hp_loss": return `lost ${d.lost} HP`;
    case "hp_slope": return `HP fell ${d.dropped} in ${d.turns} turns (now ${d.hp}/${d.hp_max})`;
    case "level_change": return `${d.from} → ${d.to}`;
    case "status_change": return [...(d.added || []).map((s) => "+" + s), ...(d.removed || []).map((s) => "−" + s)].join(" ");
    case "junction": return `junction: ${d.frontier_groups} unexplored directions`;
    case "no_progress": return `no progress on ${d.action} (${d.repeats}×)`;
    case "escalation": return d.reason;
    case "xl_up": return `reached XL ${d.xl}`;
    case "prompt": return `prompt: ${d.reason}`;
    case "died": return (d.last_messages || []).slice(-1)[0] || "died";
    default: return d.message || d.reason || Object.entries(d).map(([k, v]) => `${k}=${typeof v === "object" ? JSON.stringify(v) : v}`).join(" ");
  }
}

function routeText(route) {
  if (!route) return "";
  if (route.tier === "none" || route.tier === "reflex") return "";
  const a = route.answers;
  const jev = a ? ` · threat ${a.threat.toFixed(2)}, plan ${a.needs_plan.toFixed(2)}, worthy ${a.player_worthy.toFixed(2)}, goal ${a.next_goal} (${a.next_goal_confidence.toFixed(2)}) · ${route.latency_ms} ms` : "";
  return (route.rule ? `rule ${route.rule}: ` : "") + (route.reason || "") + jev;
}

// ---- stream ------------------------------------------------------------------

function chip(tier, label) {
  return h("span", { class: "chip", dataset: { t: tier === "reflex_goal" ? "reflex" : tier } }, label || TIER[tier] || tier);
}

function push(li) {
  const list = $("stream");
  list.prepend(li);
  while (list.children.length > 600) list.lastChild.remove();
}

function addRecord(e) {
  const r = e.record;
  const sub = h("span", { class: "sub" });
  const li = h("li", { dataset: ROUTINE.has(r.kind) || e.route?.tier === "none" ? { routine: "1" } : {} },
    h("span", { class: "turn", title: `game ${r.game} · step ${r.step}` }, String(r.snapshot?.turn ?? "")),
    chip(e.route?.tier || "reflex"),
    h("span", { class: "what" },
      h("b", null, r.kind.replaceAll("_", " ")), " ", describe(r),
      r.decision_type ? h("span", { class: "dt" }, ` → ${r.decision_type}`) : null,
      sub));
  sub.textContent = [r.snapshot?.place, routeText(e.route)].filter(Boolean).join(" · ");
  li._sub = sub;
  li._place = r.snapshot?.place;
  rows.set(e.seq, li);
  push(li);
}

function updateRoute(e) {
  const li = rows.get(e.ref);
  if (!li) return;
  li.children[1].replaceWith(chip(e.route.tier));
  li._sub.textContent = [li._place, routeText(e.route)].filter(Boolean).join(" · ");
}

function addNote(text, cls = "sep") {
  push(h("li", { class: cls }, text));
}

function addEvent(e) {
  switch (e.ev) {
    case "record": return addRecord(e);
    case "decided": addDecision(e); return push(h("li", null,
      h("span", { class: "turn" }, String(e.turn ?? "")), chip(e.decider),
      h("span", { class: "what" }, h("b", null, e.decision_type.replaceAll("_", " ")), " ", e.label,
        h("span", { class: "sub" }, e.reason))));
    case "mode": return addNote(`mode → ${e.mode}${e.by === "idle" ? " (idle switch)" : ""}`);
    case "run_start": return addNote(`run started · ${e.dir}`);
    case "game_start": return addNote(`game ${e.game} started${e.seed != null ? ` · seed ${e.seed}` : ""}`);
    case "game_end": return addNote(`game ${e.game} ended · ${e.ended_by} · ${e.final_place}, turn ${e.turns}, XL ${e.xl}` +
      (e.escalation ? ` · ${e.escalation}` : ""));
    case "run_end": return addNote("run finished");
    case "stall": return e.stalled
      ? addNote(`No word from the game for ${e.seconds} s. It may be stuck waiting on the server (dcss-api's read_until ` +
          "has no timeout). Ctrl-C the cockpit: the game stays saved, and the next start resumes it.", "err")
      : addNote("game responding again");
    case "error": return addNote(e.message, "err");
  }
}

// ---- decisions ---------------------------------------------------------------

function addDecision(e) {
  deciders[e.decider] = (deciders[e.decider] || 0) + 1;
  renderCounts();
  const list = $("decisions");
  list.prepend(h("li", null, chip(e.decider),
    h("span", null, h("b", null, e.label), " ", h("span", { class: "muted" }, `· ${e.decision_type}`),
      e.choice !== e.recommended ? h("span", { class: "dt" }, " · not the recommendation") : null,
      h("span", { class: "sub small muted", style: "display:block" }, e.reason))));
  while (list.children.length > 40) list.lastChild.remove();
}

function renderCounts() {
  const fmt = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${(TIER[k] || k).replace(/^\S+ /, "")} ${v}`).join(" · ");
  $("tier-counts").textContent = Object.keys(tiers).length ? "Routed: " + fmt(tiers) : (settings.jev ? "" : "Jev is off: start with --jev to see routes.");
  $("decider-counts").textContent = Object.keys(deciders).length ? "Decided by: " + fmt(deciders) : "No decisions yet.";
}

function renderPending(p) {
  pending = p;
  clearInterval(clockTimer);
  $("card").hidden = !p;
  if (!p) return;
  $("card-type").textContent = p.decision_type;
  $("card-q").textContent = p.question;
  const s = p.snapshot || {};
  $("card-ctx").textContent = `${s.place} · turn ${s.turn} · HP ${s.hp}/${s.hp_max}` +
    (s.hostiles?.length ? ` · ${monsters(s.hostiles)}` : "");
  const choices = p.options.filter((o) => !o.exit), exits = p.options.filter((o) => o.exit);
  $("card-opts").replaceChildren(...choices.map((o, i) => h("button", {
    type: "button", class: o.key === p.recommended ? "rec" : null, onclick: () => decide(o.key),
  }, h("span", null, h("span", { class: "n" }, String(i + 1)), o.label),
    o.key === p.recommended ? h("span", { class: "rec-tag" }, "✦ recommended (stub)") : null)));
  $("card-exits").replaceChildren(...exits.map((o) => h("button", { type: "button", onclick: () => decide(o.key) },
    o.label + (o.key === p.recommended ? " · recommended" : ""))));
  const why = p.why_asked === "pinned" ? `${p.decision_type} is pinned: in assisted mode it always asks you`
    : `${p.decision_type} isn't deferred to Strategy`;
  $("card-why").textContent = `${why}. Keys 1–${choices.length} answer.`;
  deadline = p.takeover_in_s == null ? null : performance.now() / 1000 + p.takeover_in_s;
  const start = performance.now() / 1000 - p.waited_s;
  const tickClock = () => {
    const now = performance.now() / 1000;
    if (deadline == null) $("card-clock").textContent = `waiting ${fmtSecs(now - start)} · idle switch off`;
    else $("card-clock").textContent = `Strategy takes over in ${fmtSecs(Math.max(0, deadline - now))}`;
  };
  tickClock();
  clockTimer = setInterval(tickClock, 1000);
  $("card").querySelector(".opts button")?.focus({ preventScroll: true });
}

function fmtSecs(s) {
  s = Math.round(s);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ---- status and settings -----------------------------------------------------

function renderStatus(st) {
  const s = st?.snapshot;
  if (!s) return;
  $("s-place").textContent = s.place || "–";
  $("s-turn").textContent = s.turn;
  $("s-xl").textContent = s.xl;
  $("s-step").textContent = st.step ?? "–";
  $("s-hp").textContent = `${s.hp}/${s.hp_max}`;
  const frac = s.hp_max ? s.hp / s.hp_max : 0;
  $("s-hpbar").style.width = `${Math.round(frac * 100)}%`;
  $("s-hpbar").classList.toggle("low", frac < 0.5);
  $("s-action").textContent = st.action || "–";
  $("s-hostiles").textContent = s.hostiles?.length ? monsters(s.hostiles) : "none in view";
  $("s-msgs").replaceChildren(...(st.messages || []).map((m) => h("li", null, m)));
}

function renderSettings(s) {
  settings = s;
  const auto = s.mode === "autonomous";
  $("mode-assisted").setAttribute("aria-pressed", String(!auto));
  $("mode-autonomous").setAttribute("aria-pressed", String(auto));
  $("idle-badge").hidden = !s.switched_by_idle;
  $("mode-note").textContent = auto
    ? "Strategy decides everything, pinned types included. (Strategy is still the stub's recommendation.)"
    : "You decide every decision type that isn't deferred. Deferred ones go to Strategy.";
  if (document.activeElement !== $("idle")) $("idle").value = s.idle_minutes;
  $("hold").setAttribute("aria-pressed", String(s.held));
  $("hold").textContent = s.held ? (s.paused ? "▶ Resume (holding)" : "▶ Resume (will hold)") : "❚❚ Hold at next event";
  renderCounts();
}

function renderRun(run) {
  $("run-state").textContent = run.state;
  $("run-state").dataset.s = run.state;
  $("run-dir").textContent = run.dir || "";
  const ended = run.games?.slice(-1)[0];
  const saved = ended && (ended.ended_by === "take_over" || ended.ended_by === "stopped");
  $("stop").disabled = run.state !== "running";
  $("hold").disabled = !["starting", "running"].includes(run.state);
  $("handover").hidden = !(saved && run.state !== "running");
  if ($("handover").hidden) return;
  $("h-handover").textContent = `Saved for you at ${ended.final_place}, turn ${ended.turns}`;
  $("ho-cmd").textContent = links.password_cmd;
  $("ho-lobby").href = links.lobby;
  $("ho-user").textContent = links.user;
}

// ---- talking to the server ---------------------------------------------------

function toast(text, info = false) {
  $("toast").textContent = text;
  $("toast").style.color = info ? "var(--muted)" : "";
}

async function post(path, body) {
  try {
    const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (data.error) toast(data.error);
    else if (!$("toast").style.color) toast("");
    return !data.error;
  } catch (err) {
    toast(`cockpit server unreachable: ${err.message}`);
    return false;
  }
}

function decide(choice) {
  if (pending) post("/api/decide", { id: pending.id, choice });
}

$("mode-assisted").addEventListener("click", () => post("/api/mode", { mode: "assisted" }));
$("mode-autonomous").addEventListener("click", () => post("/api/mode", { mode: "autonomous" }));
$("idle-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const n = Number($("idle").value);
  if (!Number.isInteger(n) || n < 0) return toast("idle minutes is a whole number, 0 for never");
  post("/api/idle", { minutes: n });
});
$("hold").addEventListener("click", () => post("/api/hold", { hold: !settings.held }));
$("stop").addEventListener("click", () => post("/api/stop", {}));
$("ho-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(links.password_cmd);
    $("ho-copy").textContent = "Copied: paste it in a terminal";
  } catch {
    $("ho-copy").textContent = "Select the command and copy it";
  }
});
$("hide-routine").addEventListener("change", (ev) => $("stream").classList.toggle("hidden-routine", ev.target.checked));
document.addEventListener("keydown", (ev) => {
  if (!pending || ev.target.closest("input, textarea") || ev.metaKey || ev.ctrlKey || ev.altKey) return;
  const choices = pending.options.filter((o) => !o.exit);
  const i = Number(ev.key) - 1;
  if (i >= 0 && i < choices.length) decide(choices[i].key);
});

function connect() {
  const es = new EventSource("/events");
  es.onmessage = (msg) => {
    const e = JSON.parse(msg.data);
    switch (e.ev) {
      case "hello":
        links = e.links; tiers = { ...e.tiers }; deciders = {};
        $("watch").href = links.webtiles;
        $("stream").replaceChildren(); $("decisions").replaceChildren(); rows.clear();
        renderSettings(e.settings); renderRun(e.run); renderStatus(e.status);
        e.events.forEach(addEvent);
        renderPending(e.pending); renderCounts();
        break;
      case "status": return renderStatus(e.status);
      case "settings": return renderSettings(e.settings);
      case "pending": return renderPending(e.pending);
      case "run": return renderRun(e.run);
      case "route":
        tiers[e.route.tier] = (tiers[e.route.tier] || 0) + 1; renderCounts();
        return updateRoute(e);
      case "record":
        if (e.route.tier !== "none" && e.route.tier !== "asking" && e.route.tier !== "reflex") {
          tiers[e.route.tier] = (tiers[e.route.tier] || 0) + 1; renderCounts();
        }
        return addEvent(e);
      default: return addEvent(e);
    }
  };
  es.onerror = () => { $("run-state").textContent = "reconnecting…"; $("run-state").dataset.s = "error"; };
}
connect();
