# BNK FEARX vs Dplus KIA KeSPA Cup live-source validation

## Scope

Read-only Phase 0 validation against a match with an active Polymarket Game
Winner market. No strategy, prediction, signal, wallet, private key, order, or
execution path was used.

Required fields were final picks, bans, game clock, gold, kills, towers,
inhibitors, dragons, and barons. A source was not counted as live merely because
it had a schedule row, score, or eventual postgame statistics.

## Target mapping

- Match: BNK FEARX vs Dplus KIA, KeSPA Cup Group Stage, BO1
- Scheduled start: `2026-07-21T07:00:00Z` (`15:00` Asia/Shanghai)
- Polymarket event: `lol-fox1-dk-2026-07-21`
- Riot match ID: `116929405026285764`
- BO3.gg match ID: `123998`
- OP.GG match ID: `32417`
- Broadcast channel: `https://www.twitch.tv/kespa2026lck`

At `2026-07-21T07:17:25.9771556Z`, Polymarket reported the event as
`active=true`, `closed=false`, and `acceptingOrders=true`. The moneyline was
BNK FEARX `0.505` and Dplus KIA `0.495`, with a `0.50 / 0.51` displayed best
bid/ask. The live source evidence therefore comes from an in-scope,
Polymarket-backed match.

## Validated source: public Twitch HLS broadcast

Streamlink 8.4.0 resolved the public channel without account credentials and
reported:

- live broadcast ID `320480616026`
- category `League of Legends`
- title `BNK FEARX DPLUS KIA on KeSPA 2026 KeSPA Cup 2026 KeSPA Cup`
- HLS variants including `1080p60`

`scripts/twitch_hls_frame_probe.py` then piped the HLS stream into ffmpeg and
saved consecutive raw frames. The probe completed with
`ffmpegReturnCode=0`, captured every requested frame, and required no Twitch or
Riot API key.

### Consecutive live evidence

| Raw frame | Game clock | DK gold | BFX gold | Kills DK-BFX | Other visible evidence |
|---|---:|---:|---:|---:|---|
| `twitch-bfx-dk-live-20260721T071529Z-01.jpg` | `06:49` | `10.6K` | `11.5K` | `0-1` | final champion portraits, both five-icon ban rows, tower counters, objective strip |
| `twitch-bfx-dk-live-20260721T071529Z-02.jpg` | `07:01` | `11.0K` | `11.8K` | `0-1` | Cloud Drake kill announcement plus the same stable draft and scoreboard layout |
| `twitch-bfx-dk-live-20260721T071529Z-03.jpg` | `07:13` | `11.4K` | `12.0K` | `0-1` | clock and gold continue advancing; draft and resource fields remain visible |
| `twitch-bfx-dk-live-20260721T072316Z-01.jpg` | `14:37` | `24.4K` | `25.7K` | `1-5` | tower counters `0-0`, objective counters and player KDA/CS/item panel |
| `twitch-bfx-dk-live-20260721T072316Z-02.jpg` | `14:48` | `24.6K` | `25.8K` | `1-5` | all required overlay regions remain stable across another sample |
| `twitch-bfx-dk-late-20260721T072930Z-01.jpg` | `20:54` | `39.2K` | `37.6K` | `6-8` | tower counters have advanced to `3-2`; resource strip remains readable |
| `twitch-bfx-dk-late-20260721T072930Z-02.jpg` | `21:03` | `39.6K` | `37.9K` | `6-8` | late-game state advances while all overlay regions remain stable |
| `twitch-bfx-dk-objectives-20260721T073227Z-02.jpg` | `24:00` | `44.8K` | `43.5K` | `7-9` | tower counters `3-2`; dragon counter/strip reads `0-3` |
| `twitch-bfx-dk-baron-20260721T073406Z-03.jpg` | `25:35` | `47.8K` | `46.0K` | `7-9` | tower `3-2` and dragon `0-3` states remain stable and readable |
| `twitch-bfx-dk-baron-result-20260721T074109Z-01.jpg` | `32:27` | `60.3K` | `61.8K` | `10-15` | tower `3-4`; BFX Baron timer is visibly active at `4:26` |
| `twitch-bfx-dk-inhibitor-20260721T074213Z-03.jpg` | `33:45` | `63.5K` | `66.0K` | `11-17` | tower `3-6`; BFX Baron timer remains active at `3:08` |
| `twitch-bfx-dk-ending-20260721T075238Z-05.jpg` | `44:15` | `87.3K` | `91.5K` | `21-32` | tower `4-10`; final picks, ban rows, objective counters and player panels remain readable |

The game clock advances by exactly 12 seconds across the first three selected
frames while gold changes on both teams. This rejects a paused or stale image.
The overlay preserves both teams' five final champion portraits and their
five-icon ban rows throughout the game. The center scoreboard exposes game
clock, team gold, kills, towers, and the objective strip; objective kill
announcements provide an additional observable event path. Later frames prove
that tower state advanced from `0-0` to `3-2` and dragon state advanced to
`0-3`. A Baron fight replay was captured, followed by normal-overlay frames
showing BFX's active Baron timer at `4:26` and `3:08`. Baron availability and a
nonzero Baron state therefore pass visual validation. The later `44:15` frame
shows BFX at ten destroyed towers, which implies that an inhibitor lane was
opened under League of Legends map rules, but no sampled frame contains a
direct inhibitor-destruction announcement or an independently readable
inhibitor counter. The inhibitor event therefore remains pending direct visual
validation rather than being inferred as a pass.

At `2026-07-21T07:31:11.0550875Z`, a direct read of the resolved media
playlist found two-second segments with the latest program-date-time starting
at `07:31:08.560Z`. The latest advertised segment therefore ended around
`07:31:10.560Z`, approximately `0.495s` behind the observation timestamp. This
proves that the HLS transport itself was at the live edge; it does not measure
any upstream spectator or broadcast-production delay.

The source therefore **passes live visual field availability and continuous
readability**. It is a raw visual source, not a structured JSON source. A
champion-template/OCR parser still needs its own accuracy, confidence, and
latency validation before this can become an automated normalized input.

## Structured-source cross-checks

### BO3.gg

- Public match, lineup, stats, snapshot, and WebSocket surfaces were found.
- The live WebSocket handshake succeeded with HTTP 101 and required no auth.
- During this game, the socket emitted only ping/pong in the sampled window.
- `last_snapshot` returned HTTP 404 while the broadcast was already live.
- `players_stats` remained `state=no_stats`, with empty team/player arrays.
- `lineup` remained empty.

BO3.gg is useful for schedule and identity mapping, and it had a timely final
kill/result snapshot for the preceding Gen.G-HLE game. It **failed** the
required live draft/gold/objective test for this match.

### OP.GG Esports

OP.GG mapped the match but marked the KeSPA series `liveSupported=false`.
The completed Gen.G-HLE detail page displayed “currently collecting match
data” and did not expose draft or game statistics. It **failed** as a KeSPA live
field source.

### Cito

An authenticated read-only probe from `2026-07-21T07:18:14Z` through
`2026-07-21T07:19:32Z` made one schedule request and eight `/lol/live`
attempts at a ten-second interval. All requests returned without HTTP 429, but
every live attempt returned `no_match`; final picks, clock, gold, objectives,
and winner fields were all `missing_no_live_match`. Cito's schedule still
marked both this game and the already-completed Gen.G-HLE game as `unstarted`.
It **failed** this active-match live test.

## Phase 0 judgment

- Polymarket-backed match mapping: **pass**.
- Public, continuously advancing live visual source: **pass**.
- Final picks and ban overlay availability: **pass visually**.
- Clock, gold, kills, towers, and objective visibility: **pass visually**.
- Nonzero dragon and Baron state: **pass visually**.
- Nonzero inhibitor transition: **pending; tower state implies one occurred, but no direct inhibitor event was captured**.
- Automated structured extraction: **not yet validated**.
- BO3.gg structured live fields for KeSPA: **fail in this window**.
- OP.GG structured live fields for KeSPA: **fail in this window**.
- Cito active-match row and numeric fields: **fail in this window**.

The practical Phase 0 candidate is now the official-event Twitch HLS broadcast
as a delayed visual fallback. The next gate is deterministic extraction:
template-match the ten picks and ten bans, OCR the numeric scoreboard, require
cross-frame agreement, and skip any sample below a configured confidence
threshold. Until that parser is measured, the project remains
`PHASE_0_NO_GO` for an automatic data-input closure.

## Artifacts

- `scripts/twitch_hls_frame_probe.py`
- `twitch-bfx-dk-live-20260721T071529Z-01.jpg`
- `twitch-bfx-dk-live-20260721T071529Z-02.jpg`
- `twitch-bfx-dk-live-20260721T071529Z-03.jpg`
- `twitch-bfx-dk-live-20260721T072316Z-stream.json`
- `twitch-bfx-dk-live-20260721T072316Z-probe.json`
- `twitch-bfx-dk-live-20260721T072316Z-01.jpg`
- `twitch-bfx-dk-live-20260721T072316Z-02.jpg`
- `twitch-bfx-dk-late-20260721T072930Z-stream.json`
- `twitch-bfx-dk-late-20260721T072930Z-probe.json`
- `twitch-bfx-dk-late-20260721T072930Z-01.jpg`
- `twitch-bfx-dk-late-20260721T072930Z-02.jpg`
- `twitch-bfx-dk-objectives-20260721T073227Z-stream.json`
- `twitch-bfx-dk-objectives-20260721T073227Z-probe.json`
- `twitch-bfx-dk-objectives-20260721T073227Z-02.jpg`
- `twitch-bfx-dk-baron-20260721T073406Z-stream.json`
- `twitch-bfx-dk-baron-20260721T073406Z-probe.json`
- `twitch-bfx-dk-baron-20260721T073406Z-03.jpg`
- `twitch-bfx-dk-baron-result-20260721T074109Z-stream.json`
- `twitch-bfx-dk-baron-result-20260721T074109Z-probe.json`
- `twitch-bfx-dk-baron-result-20260721T074109Z-01.jpg`
- `twitch-bfx-dk-inhibitor-20260721T074213Z-stream.json`
- `twitch-bfx-dk-inhibitor-20260721T074213Z-probe.json`
- `twitch-bfx-dk-inhibitor-20260721T074213Z-03.jpg`
- `twitch-bfx-dk-ending-20260721T075238Z-stream.json`
- `twitch-bfx-dk-ending-20260721T075238Z-probe.json`
- `twitch-bfx-dk-ending-20260721T075238Z-05.jpg`
- `twitch-kespa-hls-edge-20260721T073111Z.json`
