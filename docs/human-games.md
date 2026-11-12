# Human games on the public servers, and what each tier could learn from them

Read 2026-11-12: the **Playing Online** section of the
[DCSS site's sidebar](https://crawl.develz.org/wordpress/) (the how-to page, the scoring overview, the ten
WebTiles servers) and what those lead to. Two indexes list every server's data: the scoring scripts'
[`sources.yml`](https://github.com/crawl/scoring/blob/master/sources.yml) (has 0.34 for all ten servers;
last change 2026-04-27) and Sequell's [`config/sources.yml`](https://github.com/crawl/sequell/blob/master/config/sources.yml)
(stops at 0.33, has no CRG or CBRG, last change 2025-05). This page keeps what bears on the ladder:
a Minotaur Berserker of Trog on 0.34 that dies around D:5–6.

Checked by a handful of HEAD requests per server (sizes, dates), `robots.txt`, and four small samples
from CDI: the last 150 KB of the 0.34 logfile, the last 60 KB of the 0.34 milestones, one MiBe morgue
with its `.lst`, and one 37 KB ttyrec. No directory trees were crawled, nothing was spectated, no
websocket was opened. Where something below is inferred rather than read, it says so.

## Sources

| source | what it is | used for |
| --- | --- | --- |
| [How to play online](https://crawl.develz.org/wordpress/howto) | server list, locations, SSH ports | which servers exist; it has no data or bot policy |
| [CAO scoring overview](http://crawl.akrasiac.org/scoring/overview.html), [ToC](http://crawl.akrasiac.org/scoring/index.html) | recent wins, top scores, fastest wins, streaks, combo high scores, across CAO CBR2 CDI CKO CNC CPO CUE CXC (and CRG, CBRG per its config) | the 0.34 top players; "current stable" is 0.34 |
| [0.34 tournament combo scoreboard](https://crawl.develz.org/tournament/0.34/combo-scoreboard.html) | best game per combo; games dated 2026-02-07 to 02-22 | the best tournament MiBe |
| [crawl/scoring `sources.yml`](https://github.com/crawl/scoring/blob/master/sources.yml) | logfile, milestone and morgue URLs per server and version | the URL patterns below |
| [crawl/sequell `sources.yml`](https://github.com/crawl/sequell/blob/master/config/sources.yml) | the same, plus ttyrec URLs | ttyrec locations; out of date for 0.34 |
| [dcss-stats](https://github.com/O4epegb/dcss-stats) (MIT) | stats site that ingests every server's logfiles; its seed data lists every logfile path and 50 known **bot accounts** (qw and others) | bot names to exclude; dcss-stats.com itself answered 429, not read |
| the ten servers | below | |

## The ten servers

All ten publish 0.34 data, all updated within the last hours (HEAD, 2026-11-12 ~22:50 UTC). Sizes in MB.

| server | WebTiles | 0.34 logfile | MB | 0.34 milestones MB | trunk logfile MB | morgues | ttyrecs | robots.txt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CAO | crawl.akrasiac.org:8443 | `http://crawl.akrasiac.org/logfile34` | 103.8 | 600.0 (`milestones34`) | 1,204 (`logfile-git`) | `/rawdata/<name>/` (listing 403) | `/rawdata/<name>/` | **disallows** `/rawdata`, `/rcfiles`, `/scoring-data`, `/scoring/players` for every agent |
| CBR2 | cbro.berotato.org:8443 | `https://cbro.berotato.org/meta/0.34/logfile` | 66.1 | 379.8 | 644.6 (`meta/git/`) | `/morgue/` | `/ttyrec/` | none |
| CBRG | crawl-br.roguelikes.gg | `https://crawl-br.roguelikes.gg/meta/crawl-0.34/logfile` | 9.6 | 47.8 | not checked | `/morgue/<name>/…` (the directory is a JS browse page) | `/ttyrec/` (inferred) | none |
| CDI | crawl.dcss.io | `https://crawl.dcss.io/crawl/meta/crawl-0.34/logfile` | 75.7 | 381.0 | 123.7 (`crawl-git/`) | `/crawl/morgue/<name>/` (.txt and .lst read) | `/crawl/ttyrec/<name>/` (read) | none |
| CNC | crawl.nemelex.cards | `https://archive.nemelex.cards/meta/crawl-0.34/logfile` | 36.7 | 209.8 | 388.7 (`crawl-git/`) | `archive.nemelex.cards/morgue/` | `archive.nemelex.cards/ttyrec/` | **archive.nemelex.cards: `Disallow: /`** |
| CPO | crawl.project357.org | `https://crawl.project357.org/dcss-logfile-0.34` | 16.8 | 93.8 (`dcss-milestones-0.34`) | 255.5 (`dcss-logfile-trunk`) | `/morgue/` | `/ttyrec/` | none |
| CRG | crawl.roguelikes.gg | `https://crawl.roguelikes.gg/meta/crawl-0.34/logfile` | 10.7 | 48.7 | 6.9 (`crawl-git/`) | `/morgue/<name>/…` (JS browse page); rc files `/rcfiles/crawl-0.34/` | `/ttyrec/` (JS browse page) | none; [code of conduct](https://crawl.roguelikes.gg/code_of_conduct.txt) |
| CUE | underhound.eu:8080 | `https://underhound.eu/crawl/meta/0.34/logfile` | 49.1 | 295.0 | 684.8 (`meta/git/`) | `/crawl/morgue/` (listing 401) | `/crawl/ttyrec/` (Sequell; not checked) | 502, unreadable |
| CXC | crawl.xtahua.com | `https://crawl.xtahua.com/crawl/meta/0.34/logfile` | 44.2 | 266.8 | 581.9 (`meta/git/`) | `/crawl/morgue/` (listing off: a 191-byte page from 2019) | `/crawl/ttyrec/` | none |
| LLD | lazy-life.ddo.jp:8080 | `http://lazy-life.ddo.jp/mirror/meta/0.34/logfile` | 7.3 | 50.4 | stale (2022) | **not found**: `:8080/morgue/` and `:8080/morgue-0.34/` are 404 | `/mirror/ttyrecs-0.34/` (one directory per version) | none |
| **total** | | | **420** | **2,373** | | | | |

- Milestones are always the logfile's path with `milestones` for `logfile`.
- The scoring config writes CRG and CBRG as `meta/0.34/` and CPO as `dcss-logfiles-0.34`; the paths above
  are the ones that answered 200. The other spelling may also work (not checked).
- All files are append-only and served with byte ranges (206 on CDI), which is how Sequell, the scoring
  scripts and dcss-stats keep up: `wget --continue` (read in dcss-stats' `fetchLogfile.ts`).
- 0.34 began 2026-01-31 (first CDI line, `v=0.34-b1`); servers now run 0.34.1 (`0.34.1-5-gfd259fce64` on
  CDI). The project builds **0.34.0** (`docker-compose.yml`). Trunk (`git`) logfiles hold 0.35-a0 now.
- CDO (crawl.develz.org) is console-only and not one of the ten. Its `robots.txt` disallows `/morgues/`
  and `/ttyrecs/`. It hosts the tournament pages.
- Count: ~420 MB of 0.34 logfile at ~600 bytes a line is **about 700,000 finished 0.34 games** (inferred
  from the CDI tail's line length; CDI alone is ~126,000, ~440 a day).
- Ttyrecs are by far the largest form. One 48-minute game on CDI is 7.5 MiB raw while in progress;
  finished sessions are bz2, 37–720 KiB each in the one directory listed. Across 700k games that is
  terabytes: not something to mirror.

## What each form contains

### Logfile (one line per finished game)

`xlog`: `key=value` fields joined by `:`, a literal colon written `::`. **Months are 0-based**:
`end=20261012212600S` is 12 November. 61 fields in 0.34. A real line (CDI, 0.34.1, name redacted):

```
v=0.34.1:vlong=0.34.1-5-gfd259fce64:lv=0.1:vsav=34.316:tiles=1:name=<player>:race=Minotaur:cls=Berserker:
char=MiBe:xl=11:sk=Axes:sklev=12:title=Cleaver:place=Necropolis:br=Necropolis:lvl=1:absdepth=9:hp=-6:
mhp=95:mmhp=95:mp=10:mmp=10:bmmp=10:str=25:int=4:dex=11:ac=19:ev=7:sh=0:god=Trog:start=20261012203836S:
dur=1692:turn=7465:aut=74886:kills=223:status=confused,on berserk cooldown,slowed,studying Short Blades:
gold=431:goldfound=633:goldspent=202:scrollsused=11:potionsused=7:sc=9095:ktyp=mon:killer=<player>'s ghost:
dam=18:sdam=32:tdam=32:piety=125:end=20261012212600S:map=regret_index_necropolis_purge, ...:
seed=2468790573574272766:tmsg=slain by <player>'s ghost:vmsg=mangled by <player>'s ghost
```

(Wrapped here; one line in the file.) What it gives: combo, god and piety, where and how the game
ended (`ktyp`: `mon`, `beam`, `pois`, `quitting`, `leaving`, `winning`, …; `killer`, `dam`, `kaux` the
weapon), XL, highest skill, AC/EV/SH, stats, turns and real time, runes (`nrune`, `urune`), potions
and scrolls used, statuses at death, the vault the killer came from (`killermap`), `tiles=1` for a
WebTiles game, and the **dungeon seed**. Not the path through the game, and nothing between start and end.

### Milestones (in-game events)

The same format, one line per event, with the character's state at that moment and `type=`/`milestone=`.
Join to the logfile by `name` + `start`. Types seen in a 113-line tail: `uniq` (killed or banished a
unique), `br.enter`, `br.exit`, `br.end` (reached a branch's bottom), `shaft`, `god.worship`,
`god.mollify`, `rune`, `zotorb`, `abyss.enter`, `begin`. A real line (MiBe, name redacted):

```
v=0.34.1:...:name=<player>:race=Minotaur:cls=Berserker:char=MiBe:xl=12:sk=Fighting:sklev=13:place=Lair::1:
br=Lair:lvl=1:absdepth=11:hp=116:mhp=116:...:ac=21:ev=7:sh=18:god=Trog:start=20261010154016S:dur=4809:
turn=12277:...:scrollsused=23:potionsused=4:oplace=D::9:time=20261012215944S:type=br.enter:
milestone=entered the Lair of Beasts.
```

This is the branch order with turn, XL, HP and AC at each entry: the outline of a game. Not every
level change is a milestone (only branch entries and ends, shafts); the morgue's notes fill in the rest.

### Morgue dumps (`morgue-<name>-<YYYYMMDD-HHMMSS>.txt`, plus `.lst`)

Written at the end of every game, under `<morgue base>/<name>/`; the time is the logfile's `end` with
the month made 1-based. 16 KB for the XL 11 sample. Sections, in order (real, abridged):

```
 Dungeon Crawl Stone Soup version 0.34.1-5-gfd259fce64 (webtiles) character file.
Game seed: 2468790573574272766
9095 <player> the Cleaver (level 11, -6/95 HPs)
             Began as a Minotaur Berserker on Nov 12, 2026.
...
a - +1 broad axe (flame)          k - +3 plate armour       l - +0 kite shield
a: Renounce Religion (0%), Berserk (0%), Trog's Hand (0%), Brothers in Arms (19%)
Inventory: ... Wands  e - a wand of paralysis (7) ... Scrolls  t - 4 scrolls of teleportation ...
   Skills:  + Level 8.6 Fighting  + Level 12.2(12.6) Axes  + Level 8.7 Armour  + Level 8.8 Shields ...
Message History           (the last ~40 messages, verbatim)
The deep elf archer casts a spell at you.
You are confused.
...You die...
<the map around the player at death, as console glyphs>
Vanquished Creatures      (kill list, with the level where only a few were killed)
Notes
Turn   | Place    | Note
  2807 | D:5      | Entered Level 5 of the Dungeon
  4496 | D:6      | Encountered Edmund
  6882 | D:9      | Identified the +6 tower shield of the Depths {*Slow +Blink Str+3 SInv}
  7464 | Necropol | HP: 1/95 [deep elf archer/arrow (13)]
Levels and vault maps discovered:   D:6: nicolae_cairo_tiling_large_dashed, layout_basic, ...
Skill      XL: |  1  2  3  4  5  6  7  8  9 10 11 |
Axes           |  4           5     6  7  9 11 12 | 12.2
Action                     |  1- 3 |  4- 6 |  7- 9 | 10-12 || total
 Attack: Normal            |    72 |   126 |   237 |   168 ||   603
 Invoke: Berserk           |       |       |       |     1 ||     1
  Drink: Heal wounds       |       |       |     1 |     3 ||     4
   Read: Teleportation     |       |       |     1 |       ||     1
```

What it adds over the logfile: the final kit and the whole pack (known and unknown items), skills now
and **skill level by XL**, the **action counts by XL band** (attacks per weapon, each potion drunk,
each scroll read, each invocation, blocks and dodges), the notes (each new floor, unique met, XL
gained, near-death HP lines with the attacker and damage), the last ~40 messages before death, the
map at death, and the vaults per level. In 0.34 consumables have their own inventory letters, so a
letter repeats across sections (`e - 3 javelins`, `e - a wand of paralysis`): parse by section.

The `.lst` (11 KB) lists the items left on each floor, by level and coordinates (inferred from content:
`(17, -14, D:1)  a +0 animal skin`): what the player chose not to carry. No `.map` file on CDI (404).

### Ttyrecs (`<YYYY-MM-DD.HH:MM:SS>.ttyrec[.bz2]`, one per session)

A recording of the terminal: frames of `sec, usec, length` (three little-endian uint32) and then that
many bytes of VT100 output. **WebTiles games are recorded too**, as the console view the server
renders alongside: the CDI player whose WebTiles (`tiles=1`) game is the morgue above has a ttyrec
whose start time matches the game's. The 37 KiB sample: 469 KB raw, 2,268 frames, 110 s of a short
game from the species menu to the death screen:

```
Please select your species. ... Minotaur Berserker ... Welcome, <player>
The kobold barely misses you.        The rat closely misses you.
You puncture Terence!       Terence is heavily wounded. ...  You die...
Slain by a kobold ... wielding a ... short sword.
```

So it holds every screen: map, sidebar (HP, MP, AC, XL, place), the monster list, messages, and any
menu the player opened. **It does not hold the keys.** What the player did must be inferred from what
changed between screens, and a screen shows only what the console view shows (no cell feature flags,
no hidden inventory, no monster info beyond the list). A game spans several files when the player
saves and comes back; the logfile's `start` and `end` bracket them by time.

Ttyrec directories on CAO are under `/rawdata`, which `robots.txt` disallows. Old ttyrecs are mirrored
at `termcast.shalott.org` (per Sequell's config; not checked).

### WebTiles spectating

Every server's lobby is public: the lobby websocket lists each live game (`lobby_entry`: name, combo,
XL, place, god, milestone, spectators), and anyone can watch. dcss-stats uses the lobby for its "live
games" page (read in its source). A spectator receives the same JSON our `spectate.py` already folds
into a `GameState` (map cells, player, monsters, messages), so it would record a public game in exactly
our `player<n>.protocol.jsonl` format: **the richest form there is, but not recorded anywhere** found here
(no server publishes the WebTiles stream; the ttyrec is the only recording). Not tried: no websocket was opened.

### Other

- **rc files** (`/rcfiles/crawl-0.34/<name>.rc` on CRG; `/rcfiles` on CAO, disallowed): the player's
  options, autopickup, macros. Useful only to interpret a ttyrec (which key does what).
- **Scoring pages**: the CAO overview (the stable sections are 0.34), per-player pages
  (`/scoring/players/<name>.html`, disallowed by CAO's robots), combo standings, top combo scores.
- **Tournament**: per-version pages at `crawl.develz.org/tournament/0.34/`.
- **Sequell** (`!lg`, `!lm` in the DCSS IRC channel and Discord) answers ad-hoc questions over every
  logfile. Its public config stops at 0.33, so whether it has 0.34 is not known from here.

## MiBe on 0.34

Not counted: that needs the full logfiles (420 MB). What could be said from what was read:

- **The CDI tail** (251 games ending 12 Nov 07:20–22:46 UTC, all 0.34.1): 3 MiBe (1.2%), all Trog, dead
  on D:2 and D:3 to gnolls at XL 4, and at XL 11 in a Necropolis portal off D:9 to a player ghost.
  No wins among the 251 games. The most played combos in it: OpSh 24, MiFi 17, CoHu 12, DsEn 12.
- **Rough total**: ~1% of ~700,000 is several thousand 0.34 MiBe games. Three in 251 is too few to put a
  tight number on it (anything from ~0.3% to ~3.5% fits). Wins are rarer still: CRG's own page counts
  179 wins in 29,012 games (0.6%, all versions).
- **Best MiBe in the 0.34 tournament**: a 5-rune win with Trog, XL 27, 56,602 turns, 2026-02-07 (player
  BubbleThief). All-time best MiBe on the CAO combo page is a 15-rune win of 0.18-a0 (2015, CXC).
- **Strongest 0.34 players overall** (CAO overview, current stable): EnegeticOcto (top score, AtCj,
  Jiyva); sentinel (fastest win by turns, 12,904); p0werm0de (fastest by real time, 23:30); sergey
  (109-win streak, still active on 9 Nov).

How to count properly, in order of cost:

1. Ask Sequell: `!lg * MiBe cv=0.34 s=ktyp` (games by how they ended) and `!lg * MiBe cv=0.34 won s=name`
   (winners by player). Syntax from memory: check `!help lg`. Zero load on the servers.
2. dcss-stats.com has a combo filter ("suggest") for the latest version (read in its source; the site
   answered 429 here).
3. Download the ten 0.34 logfiles once (420 MB; CNC's archive is robots-disallowed, see below), keep them
   current with ranged requests, and filter `char=MiBe`, `ktyp=winning`. Drop the bot accounts in
   dcss-stats' list (qw, gw, jw, autorobin and 46 more), or MiBe numbers will include bots.

## Rules and etiquette

What the sources say:

- **robots.txt**: CAO disallows `/rawdata` (all morgues and ttyrecs), `/rcfiles`, `/scoring-data` and
  `/scoring/players` for every user agent; its logfiles at the root are not disallowed.
  archive.nemelex.cards (all of CNC's logfiles, morgues and ttyrecs) disallows everything. CDO
  disallows `/morgues/` and `/ttyrecs/`. The other servers have no robots.txt (404); CUE's answered 502.
- **CRG's code of conduct**: no chat bots without an admin's consent; nothing that degrades the server;
  no repetitive actions to reach huge turn counts; abusers are banned without warning. It says nothing
  about downloading or spectating.
- **The how-to page** has no policy on bots, automation or downloads. No server page read here states a
  licence for game records. DCSS itself is GPL v2 or later; dcss-stats is MIT; Sequell and the scoring
  scripts carry no licence on GitHub.
- **Established practice** (read in dcss-stats' and the scoring scripts' code): whole logfiles fetched
  once and then resumed by range; morgues linked one by one, not mirrored.
  Bot accounts are known by name and excluded from human statistics.

So, for us:

- **Do not** crawl morgue or ttyrec directories, or mirror them. Fetch single files whose names come
  from the logfile, slowly (one at a time, a second or more apart), and cache them forever.
- **Do not** fetch anything under a disallowed path (CAO `/rawdata`, `/rcfiles`, `/scoring/players`;
  anything on archive.nemelex.cards; CDO `/morgues/`, `/ttyrecs/`) without the operator's say-so. For
  CNC and CAO morgues, ask first or leave them out.
- **Do not** re-download whole logfiles or milestones: one full fetch, then `Range` from the local size.
  Milestones (2.4 GB) only from the servers that are needed.
- **Do not** run the bot on a public server, under any account, and **do not** spectate public games
  automatically, without asking the server's admin first (CRG requires consent for bots; the others
  say nothing, which is not permission). Spectating is cheap for a server, but a recorder that follows
  many games is a bot.
- **Do not** republish what is downloaded. Records carry player names; keep the corpus local (`runs/`
  is git-ignored), and redact names in anything committed, as here.
- Use a generic User-Agent with no names in it, and never log in.

## Which tier could learn what

| form | Strategy ✦ | Tactics ⚔ | Jev J | Reflex * | trained brain |
| --- | --- | --- | --- | --- | --- |
| logfile | god choice; where MiBe games end, by XL (the tail: gnolls on D:2–3; the rest is to count); win and survival rates by depth reached | which killers matter at each depth | the prior for "deadly": what actually kills this character at this XL and depth | thresholds: potions and scrolls used per game | an outside yardstick: human MiBe median death depth against the bot's 5.86 |
| milestones | branch order and timing: turn, XL, HP and AC at Lair, Orc, Temple entry; when winners leave the Dungeon | uniques met and killed, and at what XL | `needs_plan` for branch entries | | depth-by-turn curves to calibrate `depth_go` |
| morgue | skills by XL (weapon to the 1.0 breakpoint?), armour and shield choices, what is carried | the last ~40 messages and the map at each death: post-mortems | labelled examples: the situation before a death | consumable use by XL band: how often humans drink, read, berserk, throw | features worth adding (skills, wielded, worn), as `docs/wiki-strategy.md` asks |
| ttyrec | the route through every floor | every fight, every retreat, with the screens before and after | many labelled moments | rule thresholds measured on real play | step logs with inferred actions (below) |
| spectated WebTiles | the same as ttyrec, as exact JSON | | | | step logs from `GameState`, as for our own games |

What the existing code would need:

- **Logfile, milestones, morgue**: none of it touches `humanplay.py`. A small parser (xlog is a few
  lines; the morgue is sectioned plain text) and an offline report, like `tools/knowledge/`. The
  morgue's action table already gives what the brain's action mix should be compared with.
- **Spectated WebTiles JSON** (public games, or Reflex's own turns in a shared game, Next 8 in
  `trained-brain.md`): `spectate.py` records it already. `humanplay.Converter` reads keys to know the
  action; without keys it needs an **action inferrer**: from two consecutive `GameState`s, say what was
  done (moved toward a hostile or hit it: `fight`; HP up with turns passing and nothing moved: `rest`;
  a new level below: `descend`; a stack shrank: which potion or scroll; many squares walked toward
  unexplored floor: `explore`). It can be built and **measured on our own `play<n>.jsonl`**, where the
  keys give the right answer.
- **Ttyrec**: that inferrer, plus a screen reader in front of it: a VT100 emulator (e.g. `pyte`) to turn
  frames into 80×24 screens (size inferred), and a parser from the console layout to a `GameState`
  (sidebar numbers, map glyphs and colours to cells and monsters, the message lines). The console shows
  less than the WebTiles JSON: no `mf` cell flags (the stairs are glyphs `<` `>`), no monster list beyond
  the sidebar's, no pack unless the player opens it. `features.observe` would need a reduced
  observation, or the missing parts reconstructed (the pack from pickups and use messages). Large: weeks,
  not a day. Join each ttyrec to its logfile line by name and time to label the outcome (`corpus.py`
  wants `died`, depth reached, turns).
- **Seeds**: every 0.34 game records its dungeon seed. If 0.34.0 and 0.34.1 generate the same levels
  for a seed (not checked; vault changes between point releases would break it), the bot could play the
  very dungeon a human won or died in, and the morgue's vault list per level would confirm the match.

## First step, sized for a day

**A MiBe 0.34 reference from logfiles and morgues, no ttyrecs.**

1. Count first, download nothing big: ask Sequell (or dcss-stats' combo page) for 0.34 MiBe games by
   outcome and the winners by name. If that answers it, skip to 3.
2. Otherwise fetch the 0.34 logfiles of the servers that allow it (CDI, CBR2, CXC, CPO, CUE, CRG, CBRG,
   LLD, CAO's root logfile: ~385 MB, one request each, under `runs/humangames/`), with a resumable
   ranged fetch. Write `tools/humangames/xlog.py` (parse, filter `char=MiBe`, drop bot accounts).
3. Report, into this page or a sibling: MiBe games and wins; death place and killer by XL for games
   that ended at D:1–D:10; the share that reach D:6, D:10, Lair; god (Trog or not). Compare with the
   bot's evaluation games: does it die where humans die, to the same things?
4. Fetch morgues for every 0.34 MiBe win (expected tens to low hundreds, ~20–60 KB each) and for ~100
   deaths on D:4–D:8, one file at a time, a second apart, from servers not disallowed. From them: skill
   levels at each XL, the action table per XL band (berserks, potions, teleports, throws per game), when
   the Lair was entered and at what XL. These answer `wiki-strategy.md`'s open questions with numbers
   instead of advice: when to rest, when to berserk, what to train.

That gives Strategy and Reflex measured thresholds, Jev a ground truth for "deadly", and the brain a
human yardstick, for about 400 MB of one-time download and a few hundred small files. Ttyrecs and
spectating come after, starting with the action inferrer built against our own recordings.

## Not verified

- **CUE**: `robots.txt` answered 502; the morgue directory 401; ttyrec path taken from Sequell's config.
- **LLD morgues**: not found at the configured `:8080/morgue/` or `:8080/morgue-0.34/` (both 404); the
  directory may simply not list, or they live elsewhere.
- **CRG and CBRG** morgue and ttyrec files: the directories are JavaScript pages; file paths come from the
  scoring page's links and dcss-stats' config, not from a fetch. CBRG's trunk logfile not checked.
- The MiBe 0.34 game and win counts, and the strongest MiBe players (see above for how to get them).
- dcss-stats.com (429), and whether the deployed Sequell has 0.34.
- That other servers record WebTiles games as ttyrecs as CDI does (likely: the same server software).
- The ttyrec terminal size, and whether a WebTiles spectator on a public server sees exactly what our
  local one does (same 0.34 protocol, so very likely, but not tried by rule).
- Whether a 0.34.1 seed reproduces the same dungeon on 0.34.0.
