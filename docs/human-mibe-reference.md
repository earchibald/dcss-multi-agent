# Human Minotaur Berserkers on 0.34, beside the bot

How people do with the bot's character, measured the way `tools/qw/run.py` measures the bot, so
that the bot's numbers have a human scale. Built 2026-11-13 (UTC) from two public servers' 0.34
logfiles (10,838 MiBe games) and 232 morgues. Tool: `tools/humangames/mibe.py`; test:
`tests/test_humangames.py`. Background on the servers, their files and the etiquette:
`docs/human-games.md`.

**In short.** Up to the Lair, the tuned qw bot plays this character as well as the humans who have
won a game, and better than the average human: it is a level deeper, 1.5 XL higher and enters the
Lair twice as often. After the Lair it converts like a human who has never won: 14% of its Lair
games take a rune, against 36% for the winners' games, and 1.7% take three, against 13%. Humans
who have won something win 2.1% of their MiBe games (6.6% of those that reach the Lair); the bot
has won none of 400, which is significantly below them (expected 8.4 wins) but not below the human
average (0.36%, expected 1.4).

## Headline

Bot: all 400 training games (`runs/qw/zk-train-400`). Humans: band (b), games of 1,000+ turns that
did not end by quitting; (c) the same, for players with a win of any character; (d) each player's
first such MiBe game. "Estimated" human values come from the logfile corrected by the morgue sample
(see below).

| | Bot | Humans (b) | (c) players with a win | (c) players with none | (d) first game |
|---|---|---|---|---|---|
| Games (players) | 400 | 9,193 (861) | 1,577 (89) | 7,616 (772) | 861 (861) |
| XL at end, mean | 10.18 | 8.68 | 10.53 | 8.29 | 8.07 |
| Deepest D, mean | **8.34** exact (SE 0.24) | 7.33 est. | 8.56 est. | 7.08 est. | 6.88 est. |
| Deepest D, logfile rule, mean (SE) | 6.87 (0.18) | 6.32 (0.03) | 7.18 (0.09) | 6.15 (0.03) | 5.93 (0.10) |
| Entered the Lair | **45%** exact (181) | 21% est. | 32% est. | 19% est. | 21% est. |
| Runes per game | 0.095 | 0.079 | 0.262 | 0.041 | 0.074 |
| Games with 3+ runes | 0.75% (3) | 1.1% (103) | 4.2% (67) | 0.5% (36) | 1.5% (13) |
| Wins | **0** | 33 (0.36%) | 33 (2.1%) | 0 | 7 (0.8%) |
| Of games that entered the Lair: took a rune | 14% (26/181) | 18% est. | 36% est. | 11% est. | 16% est. |
| … took 3 runes | 1.7% | 5.4% est. | 13.4% est. | 2.5% est. | 7.3% est. |
| … won | 0% | 1.7% est. | 6.6% est. | 0% | 3.9% est. |

All human MiBe games, band (a), 10,838 from 979 players: 33 wins (0.30%), mean XL 7.69, deepest D
5.63 by the rule and 6.50 estimated, 18% estimated to enter the Lair.

## Sources

| What | URL | Bytes | Fetched (UTC) |
|---|---|---|---|
| CDI 0.34 logfile | `https://crawl.dcss.io/crawl/meta/crawl-0.34/logfile` | 75,736,311 | 2026-11-13 05:58 |
| CBR2 0.34 logfile | `https://cbro.berotato.org/meta/0.34/logfile` | 66,172,421 | 2026-11-13 05:59 |
| Bot account list (50 names) | [dcss-stats `apps/api/prisma/seedData.ts`](https://github.com/O4epegb/dcss-stats/blob/HEAD/apps/api/prisma/seedData.ts), `bots: [...]` | 14,085 | 2026-11-13 06:00 |
| 232 morgues: all 33 MiBe wins, and 200 random band-(b) non-winning games (100 per server; 1 timed out) | `https://crawl.dcss.io/crawl/morgue/<name>/morgue-<name>-<end>.txt`, `https://cbro.berotato.org/morgue/<name>/morgue-<name>-<end>.txt` | 4,798,162 | 2026-11-13 06:03–06:11 |
| The bot | `runs/qw/zk-train-400`: `results.json` and each game's `logfile.txt` and `morgue.txt`; qw `zk` build, tuned settings (`zerk_hp70+zerk_early+bia7`), training seeds 100000–100399, 3600 s limit | local | |

- Both servers are among those `docs/human-games.md` lists with no robots.txt. Each logfile was fetched
  once, whole (no compression offered; HEAD first). The morgues were fetched one at a time,
  alternating servers, 1.5 s apart, each once. Generic User-Agent, no login.
- **Milestones were not fetched.** The 0.34 milestone files are 381 MB (CDI) and 380 MB (CBR2) and
  cannot be filtered by character on the server. The morgues' notes give the same events (each branch
  entered, each rune, each XL gained) with turn and place for the games that matter here, at under 1% of
  the bytes. The pacing below comes from them.
- The two logfiles hold 231,122 games; 10,838 are MiBe (4.7%), ended 2026-01-31 to 2026-11-13:
  0.34-b1 150, 0.34.0 2,278, 0.34.1 8,410 (the container builds 0.34.0). No MiBe game is on the bot
  list. 99.5% worshipped Trog.
- Everything fetched is kept under `runs/humangames/` (git-ignored). Player names appear nowhere in
  this page and in no committed file; the JSON reports in `runs/` keep them.

## How it is measured

**Bands of human games.** Server logs are dominated by quick deaths and by a few heavy players (979
players, median 2 MiBe games each; the ten busiest played 26% of the games, one of them 485):

- (a) every 0.34 MiBe game.
- (b) "played": 1,000 turns or more, not ended by quitting or leaving the dungeon.
- (c) band (b) split by players with at least one win of **any** character in the two files (329
  players; 89 of them played MiBe) and players with none. Names are matched across the two servers.
- (d) band (b), each player's first 3 MiBe games, or only the first (by start time).

The bot is shown for all 400 games (its own summary: 398 finished, 2 timed out; the timed-out two
count with their last XL) and through the band (b) filter (366 games: 10 quits and 24 deaths before
turn 1,000 out).

**Deepest floor.** For the bot, `tools/qw/run.py` takes the deepest **Dungeon** level visited: the
morgue's `Branches:` overview (`Dungeon (n/15)`) or qw's own place log, whichever is deeper. A logfile
line only says where the game ended, so from a logfile the tool takes a lower bound:

| Ended in | Deepest D (rule) | Why |
|---|---|---|
| D:n | n | |
| Temple | 4 | entrance on D:4–7 |
| Lair, Swamp, Shoals, Snake, Spider, Slime | 8 | Lair entrance on D:8–11 |
| Orc, Elf | 9 | Orc entrance on D:9–12 |
| Vaults, Crypt, Tomb | 13 | Vaults entrance on D:13–14 |
| Depths, Zot, Hells, Pandemonium, Ziggurat | 15 | Depths from D:15 |
| Sewer 3, Ossuary 4, Bailey 7, Ice cave, Volcano, Gauntlet 8, Wizlab, Desolation 9 | as listed | entry depths in `dat/des/portals/*.des` |
| Necropolis | its `absdepth` if 10 or less (the D level it was entered from), else 8 | `place.cc`: a necropolis takes its origin's depth |
| Abyss, Labyrinth, Bazaar, Trove | 1 | unknown |
| any game with a rune | at least 8 | |
| a win | 15 | |

Branch entrances are from 0.34.0's `branch-data.h` in the container. The same rule runs on the bot's
own logfile lines, so the "logfile rule" rows compare like with like.

The **exact** value for humans comes from the morgues, computed as for the bot: the deeper of the
overview, any D level in the notes, and the place of death (the overview lags after a shaft: 2 of 199
sampled games died on a D level the overview did not show). Run on the bot's 398 morgues, this gives
the same deepest D as `results.json` in all 398. The band estimates then add, to each non-winning
game's rule value, the sample's mean (exact − rule) for games that ended in the same zone, and take
the sample's share that entered the Lair for that zone; a win counts 15 and Lair.

"Entered the Lair" from a logfile alone is also a lower bound (ended in the Lair or one of its
branches, holds a rune, or won).

## Exact deepest floor, from the morgues

| | Games | Exact deepest D (SE) | Logfile rule | Exact − rule (SE) | Rule = exact | Entered Lair: exact / rule |
|---|---|---|---|---|---|---|
| Human sample, band (b), not won | 199 | 7.65 (0.28) | 6.43 | 1.23 (0.17) | 140 | 52 / 39 |
| … players with a win | 39 | 8.18 | 6.69 | 1.49 | | 12 |
| … players with none | 160 | 7.53 | 6.36 | 1.17 | | 40 |
| Human wins | 33 | 15 | 15 | 0 | 33 | 33 / 33 |
| Bot, all | 400 | 8.34 (0.24) | 6.87 | 1.43 (0.13) | 267 | 181 / 136 |
| Bot, band (b) | 366 | 8.70 (0.24) | 7.18 | | | 173 |

Exact − rule by where the game ended (mean, games):

| Ended in | Human sample | Bot |
|---|---|---|
| D:1-4 | 0.10 (61) | 0.03 (118) |
| D:5-10 | 0.10 (70) | 0.10 (98) |
| D:11-15 | 0.00 (8) | 0.19 (27) |
| Lair | 2.58 (19) | 1.17 (66) |
| Orc, Elf | 3.83 (6) | 6.00 (10) |
| Lair rune branches | 5.71 (14) | 7.00 (45) |
| Vaults and later | 1.33 (6) | 1.25 (24) |
| Abyss | 11.25 (4) | 10.67 (6) |
| portals, Temple | 2.36 (11) | 1.50 (4) |

- The rule is nearly exact for games that end in the Dungeon (two thirds of human deaths).
- **Deepest D rewards the bot's route.** qw goes down to D:15 before the rune branches and Orc: every
  one of its 45 rune-branch deaths and 10 Orc deaths had seen D:15. Humans who die in a rune branch
  have seen D:13.7 on average. So deepest D flatters the bot by up to a level against humans at the
  same stage; XL and "entered the Lair" are fairer yardsticks across routes.
- The correction is estimated on band (b) non-wins of both kinds of player and applied to every
  band; players with a win gain a little more from it (1.49 against 1.17), so their 8.56 is if
  anything low.

## Bot against humans, every measure

Logfile rule throughout (the same instrument for both).

| | Bot, all | Bot, (b) | (a) all | (b) played | (c) winners | (c) never won | (d) first 3 | (d) first 1 |
|---|---|---|---|---|---|---|---|---|
| Games | 400 | 366 | 10,838 | 9,193 | 1,577 | 7,616 | 1,779 | 861 |
| Players | 1 | 1 | 979 | 861 | 89 | 772 | 861 | 861 |
| Wins | 0 (0.0%) | 0 (0.0%) | 33 (0.3%) | 33 (0.4%) | 33 (2.1%) | 0 (0.0%) | 13 (0.7%) | 7 (0.8%) |
| Quit or left | 10 | 0 | 266 | 0 | 0 | 0 | 0 | 0 |
| Deepest D, logfile rule, mean (SE) | 6.87 (0.18) | 7.18 (0.18) | 5.63 (0.03) | 6.32 (0.03) | 7.18 (0.09) | 6.15 (0.03) | 6.13 (0.07) | 5.93 (0.10) |
| Deepest D ≥ 5 (rule) | 68.6% | 72.4% | 55.6% | 65.3% | 73.9% | 63.5% | 62.1% | 59.9% |
| Deepest D ≥ 8 (rule) | 57.3% | 60.4% | 33.3% | 39.2% | 51.4% | 36.7% | 36.8% | 34.0% |
| Deepest D ≥ 10 (rule) | 15.3% | 16.1% | 9.9% | 11.7% | 17.3% | 10.5% | 10.5% | 8.7% |
| Deepest D ≥ 15 (rule) | 3.5% | 3.8% | 1.7% | 1.9% | 5.4% | 1.2% | 1.7% | 1.7% |
| XL at end, mean / median | 10.18 / 10 | 10.61 / 11 | 7.69 / 7 | 8.68 / 8 | 10.53 / 10 | 8.29 / 8 | 8.33 / 8 | 8.07 / 7 |
| XL at death, mean / median | 10.13 / 10 | 10.61 / 11 | 7.76 / 7 | 8.61 / 8 | 10.19 / 10 | 8.29 / 8 | 8.20 / 8 | 7.93 / 7 |
| Ended in the Lair or below, or with a rune (rule) | 34.0% | 36.1% | 11.7% | 13.7% | 24.4% | 11.5% | 14.3% | 14.6% |
| Runes, total (per game) | 38 (0.095) | 37 (0.101) | 729 (0.067) | 723 (0.079) | 413 (0.262) | 310 (0.041) | 144 (0.081) | 64 (0.074) |
| Games with a rune / with 3+ | 26 / 3 | 25 / 3 | 343 / 103 | 340 / 103 | 181 / 67 | 159 / 36 | 63 / 25 | 29 / 13 |
| Death turn, quartiles | 2,597 / 8,177 / 18,622 | 3,126 / 8,636 / 19,827 | 1,792 / 4,118 / 9,033 | 2,517 / 5,212 / 10,092 | 3,364 / 7,337 / 16,151 | 2,432 / 4,853 / 9,392 | 2,301 / 4,659 / 9,485 | 2,250 / 4,243 / 8,888 |

Where deaths happen, share of deaths (wins, quits and unfinished games left out):

| End place | Bot, all | Bot, (b) | (a) all | (b) played | (c) winners | (c) never won | (d) first 3 | (d) first 1 |
|---|---|---|---|---|---|---|---|---|
| D:1-4 | 29.9% | 25.7% | 41.1% | 32.4% | 23.9% | 34.2% | 36.3% | 38.4% |
| D:5-10 | 24.2% | 25.7% | 31.7% | 36.3% | 33.7% | 36.9% | 34.3% | 33.1% |
| D:11-15 | 6.7% | 7.1% | 5.8% | 6.7% | 6.7% | 6.6% | 6.1% | 5.0% |
| Lair | 16.2% | 17.2% | 5.0% | 5.8% | 6.8% | 5.6% | 6.6% | 7.4% |
| Orc, Elf | 2.6% | 2.7% | 3.3% | 3.8% | 5.3% | 3.5% | 4.0% | 4.0% |
| Lair rune branches | 11.6% | 12.3% | 4.6% | 5.2% | 8.6% | 4.6% | 5.0% | 5.2% |
| Vaults, Crypt, Depths, Zot and later | 6.2% | 6.6% | 1.6% | 1.8% | 5.3% | 1.1% | 1.4% | 0.9% |
| Abyss | 1.5% | 1.6% | 1.4% | 1.6% | 2.1% | 1.4% | 1.1% | 1.1% |
| portals, Temple | 1.0% | 1.1% | 5.5% | 6.3% | 7.6% | 6.1% | 5.3% | 4.9% |

Death turn, share of deaths:

| Turns | Bot, all | Bot, (b) | (a) all | (b) played | (c) winners | (c) never won | (d) first 3 | (d) first 1 |
|---|---|---|---|---|---|---|---|---|
| 0–1000 | 5.7% | 0.0% | 13.1% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| 1000–3000 | 22.2% | 23.5% | 27.3% | 31.4% | 22.3% | 33.2% | 35.9% | 37.9% |
| 3000–10000 | 29.6% | 31.4% | 37.6% | 43.3% | 39.8% | 44.0% | 40.6% | 41.1% |
| 10000–30000 | 31.7% | 33.6% | 17.8% | 20.4% | 25.8% | 19.3% | 20.0% | 17.9% |
| 30000–100000 | 10.8% | 11.5% | 4.2% | 4.9% | 12.0% | 3.4% | 3.4% | 3.0% |
| 100000+ | 0.0% | 0.0% | 0.0% | 0.0% | 0.1% | 0.0% | 0.1% | 0.0% |

Killers, share of deaths (the union of the bot's and human band (b)'s top 12). The logfile's
`killer`; every `<name>'s ghost` counts as "a player ghost"; deaths with no killer show by kind.

| Killer | Bot, all | (a) all | (b) played | (c) winners |
|---|---|---|---|---|
| a gnoll | 9.8% | 10.2% | 8.1% | 7.0% |
| an orc priest | 3.9% | 3.5% | 3.7% | 3.4% |
| an ogre | 1.5% | 2.9% | 3.2% | 2.6% |
| an orc warrior | 0.3% | 2.6% | 3.0% | 2.8% |
| an orc wizard | 3.9% | 2.7% | 2.9% | 2.1% |
| a wight | 1.0% | 1.9% | 2.2% | 2.2% |
| a bombardier beetle | 0.8% | 1.7% | 1.8% | 1.4% |
| an orc | 1.3% | 1.9% | 1.8% | 1.5% |
| a gnoll sergeant | 0.3% | 1.6% | 1.8% | 1.7% |
| Grinder | 0.8% | 1.5% | 1.7% | 1.3% |
| a two-headed ogre | 0.5% | 1.4% | 1.6% | 0.9% |
| a yak | 2.1% | 1.2% | 1.4% | 0.8% |
| Sigmund | 5.9% | 1.7% | 1.2% | 0.9% |
| a goblin | 2.6% | 1.8% | 0.7% | 0.3% |
| a death yak | 2.1% | 0.5% | 0.6% | 0.6% |
| a cane toad | 1.3% | 0.5% | 0.6% | 0.6% |
| a ribbon worm | 1.3% | 0.9% | 0.5% | 0.4% |
| Erica | 1.3% | 0.7% | 0.9% | 0.7% |

How the games that entered the Lair ended (exact, from morgues for humans):

| | Entered | Died in the Lair | Died in a rune branch | Took a rune | Took 3 | Won |
|---|---|---|---|---|---|---|
| Bot | 181 | 66 (36%) | 45 (25%) | 26 (14%) | 3 | 0 |
| Human sample, band (b), not won | 52 | 19 (37%) | 14 (27%) | 8 (15%) | 2 | 0 |

## Pacing: when humans get there

Turn and XL at the first note on each floor or branch (the XL is the one held on arrival), median
and interquartile range. Winners: all 33 MiBe wins in the two files (24 with 3 runes, 6 with 4, 3
with 5; median 69,030 turns to win, XL 27 in 18). The bot: every game that got there.

| Event | Human winners (33): turn | XL | Humans in band (b) who entered the Lair, not won (52): turn | XL | Bot: games, turn | XL |
|---|---|---|---|---|---|---|
| D:5 | 3,212 (2,965–3,752) | 6 (6–7) | 3,572 (3,221–4,000) | 6.5 | 281, 3,691 (3,268–4,011) | 7 |
| D:8 | 6,967 (6,309–7,629) | 9 (9–10) | 6,681 (6,210–7,880) | 9 | 234, 6,756 (6,250–7,212) | 9 |
| Lair | **11,703** (10,537–13,095) | **12** (11–12) | 11,678 (10,213–13,549) | 11 (11–12) | 179, **9,053** (8,188–10,387) | **11** (10–11) |
| Orc | 20,316 (18,172–23,500) | 15 (14–15) | 20,636 (16,622–28,308), 26 games | 14 | 80, 21,954 (20,599–23,077) | 15 |
| First rune | 31,434 (28,088–33,678) | 17 (17–17) | 28,227, 8 games | 17 | 26, 30,944 (29,500–32,545) | 17.5 |
| Vaults | 39,300 (35,295–45,087), 32 games | 19 (18–20) | 36,219, 6 games | 19.5 | 25, **31,614** (30,010–32,501) | **18** |
| Depths | 44,855 (39,990–54,489) | 21 (19–22) | 43,661, 5 games | 18 | 9, 40,494 | 20 |
| Third rune | 55,651 (45,150–64,142) | 24 (23–24) | 2 games | | 3, 48,605 | 23 |
| Zot | 61,966 (54,215–67,972) | 24 (24–25) | 2 games | | 3, 49,218 | 23 |

Targets for the bot, from the winners:

- **Lair at XL 12, around turn 11,700.** The bot enters at XL 11 around turn 9,000: 2,600 turns
  sooner and a level lower. Humans who reach the Lair and do not win enter it at XL 11, as the bot does.
- **Orc at XL 15 around turn 20,000; first rune at XL 17 around turn 31,000.** The bot matches both.
- **Vaults at XL 19 around turn 39,000, and only after a rune.** The bot goes to the Vaults right after
  its first rune: 8,000 turns sooner and at XL 18.
- **Depths at XL 21, third rune and Zot at XL 24** (around turns 45,000, 56,000 and 62,000). The bot's
  three 3-rune games reached the Depths at XL 20 and the third rune and Zot at XL 23, 5,000–13,000
  turns sooner.
- Winners' order: Lair, Orc, a rune, Vaults, Depths, the third rune, Zot. All 33 entered Orc.

## Where the bot stands

- **Early game: about the human average, short of the winners.** The bot dies in D:1–4 in 29% of its
  games; humans in band (b) 32%, players with a win 23% (deaths there per game). Gnolls are the first
  killer for both (about 10% of deaths). Two killers are the bot's own: **Sigmund** (5.9% of its
  deaths, against 1.2% of humans' in band (b)) and **goblins** (2.6% against 0.7%).
- **Getting to the Lair: better than any human band.** 45% of the bot's games enter it, against an
  estimated 32% of the winners' games and 21% of band (b). Its mean XL (10.2) is the winners' (10.5).
- **After the Lair: like a human who has never won.** Of the bot's Lair games, 36% die in the Lair and
  25% in a rune branch, as for sampled humans who did not win (37%, 27%). 14% take a rune (humans:
  never-won players 11%, band (b) 18%, winners 36%) and 1.7% three (2.5%, 5.4%, 13.4%). Players with a
  win turn a Lair game into a win 6.6% of the time.
- **Wins.** 0 in 400. At the winners' rate of 2.1% that has a probability of about 0.0002; at band
  (b)'s 0.36%, about 0.24. The bot is not yet distinguishable from the average human player on wins,
  and clearly below the players who win.
- So the gap is in the Lair and below, and the pacing points the same way: the bot enters the Lair,
  the Vaults, the Depths and Zot about one XL short of the winners and thousands of turns sooner. It
  matches them only at Orc and the first rune. Winners enter the Lair at XL 12 and the Vaults at XL 19,
  only after a rune. Whether the bot gains from arriving later and stronger (when it takes the Lair
  stairs, and the Vaults before or after a second rune) is the obvious experiment.

## Caveats

- **Two servers, not ten.** CDI and CBR2 hold about a third of all 0.34 games. Players differ between
  servers: CBR2's MiBes won 21 of 5,590, CDI's 12 of 5,248.
- **Bots.** Only the 50 names on dcss-stats' list are excluded; none played MiBe here. The fastest
  human MiBe players run at 20–27 game turns per real second (median over their games of 1,000+
  turns), against 6.4 for the median game; the busiest player (485 games, 2 wins) runs at 15. That
  neither proves nor excludes an unlisted bot. Band (d) caps any one account's weight.
- **Human deepest D and Lair entry are estimates** outside the 199 sampled games and the 33 wins: the
  logfile rule plus a correction by end zone from a 199-game sample (SE about 0.17 levels on the mean
  correction). Bands (c) and (d) borrow the correction from the whole sample.
- **The human-sample pacing beyond the Lair rests on few games** (8 first runes, 6 Vaults). The
  winners' pacing (33 games) and the bot's are the solid columns.
- **Different players, different conditions.** The bot plays fresh seeds of one build to the end; it
  never quits a bad start or abandons a character. Humans played over ten months, on 0.34-b1 to
  0.34.1 (0.34.1 is a bug-fix release; not checked line by line for balance changes). Bands (b) and
  (d) take out the quits and the heavy players.
- **Turns are game turns** (`turn`) for both. qw rests and explores in its own way, so equal turns do
  not mean equal play.
- **"Players with a win" is within these two files**: a win on another server or version counts as none.
- Portal and Abyss deaths (7% of human deaths) have only coarse bounds in the rule; the morgues
  correct them in the estimates.
- The bot's XL row includes its 2 unfinished games at their last XL (10.18, against 10.15 for the
  398 finished games in its own summary).

## Rerun

```sh
D=runs/humangames                                      # git-ignored; the files are already there
# Logfiles grow: fetch only the new bytes (curl -C - -o $D/cdi-logfile URL), never the whole file again.
uv run python -I tools/humangames/mibe.py report --logfile CDI=$D/cdi-logfile --logfile CBR2=$D/cbr2-logfile \
    --bots $D/seedData.ts --bot-run runs/qw/zk-train-400 --out $D/report.json
uv run python -I tools/humangames/mibe.py tables --report $D/report.json        # the tables above
uv run python -I tools/humangames/mibe.py pick-morgues --logfile CDI=$D/cdi-logfile --logfile CBR2=$D/cbr2-logfile \
    --bots $D/seedData.ts --sample 100 --out $D/morgues.json
uv run python -I tools/humangames/mibe.py fetch --list $D/morgues.json --dir $D/morgues   # 1.5 s apart, never twice
uv run python -I tools/humangames/mibe.py morgues --list $D/morgues.json --dir $D/morgues \
    --bot-run runs/qw/zk-train-400 --logfile CDI=$D/cdi-logfile --logfile CBR2=$D/cbr2-logfile \
    --bots $D/seedData.ts --out $D/morgue-report.json
```

`report.json` holds every band's full measures (histograms, killers, gods); `morgue-report.json`
the exact-depth calibration, the band estimates and the pacing tables.
