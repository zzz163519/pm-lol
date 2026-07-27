# BFX-DK deterministic visual extractor V0 replay

## Result

`PARTIAL_LOW_CONFIDENCE` — engineering feasibility passed for the numeric
scoreboard path, but this replay does not pass V0 exact-BP acceptance and does
not count toward the two-match V1 gate.

The runtime path is pure code:

```text
saved HLS frame
  -> versioned KeSPA ROI layout
  -> RapidOCR numeric recognition
  -> Data Dragon template features + SIFT/RANSAC geometric verification
  -> clock/counter monotonicity and cross-frame consensus
  -> accepted value or unknown
```

No LLM, wallet, private key, strategy, signal or order path is present.

## Replay evidence

The extractor replayed all 12 checked-in BFX-DK gameplay frames in chronological
order. All 12 were retained after the live-screen rule was corrected to accept
either an explicit `LIVE` glyph or a complete high-confidence core scoreboard.
This matters because the broadcast replaces the top-right `LIVE` glyph with
dragon/Baron timers during normal gameplay.

| Field | Automated result | Ground truth visible in saved frames | Status |
|---|---:|---:|---|
| Clock | `06:49` -> `44:15`, 12 advancing samples | `06:49` -> `44:15` | pass |
| Gold | `10.6K-11.5K` -> `87.3K-91.5K` | same | pass |
| Kills | final `21-32` | `21-32` | pass |
| Towers | repeated state `3-2`; final raw frame `4-10` | `3-2`, later `4-10` | pass conservatively; latest transition needs another frame |
| Dragons | repeated `0-3` | `0-3` | pass |
| Baron | top-right timer is observable but not normalized yet | active timer `4:26` then `3:08` | pending |
| Inhibitors | no accepted direct event | no direct event frame | pending |

The objective aggregator intentionally reports the latest value with at least
two agreeing samples. It therefore keeps towers at `3-2` instead of promoting
the single final `4-10` observation. OCR `30` from the dragon icon/counter crop
is constrained by the legal dragon-counter range and normalized to `3`.

## Draft result

The in-game side portraits are only 44x40 pixels, team-tinted, compressed and
partly covered by level/UI elements. RANSAC geometric verification removed the
known false Zoe acceptance in the Ryze slot: ambiguous candidates are now
`unknown`. Across the 12 frames, cross-frame consensus produced candidates for
5/10 picks and 2/10 bans; the remaining slots stayed unknown. No gameplay-icon
candidate is accepted without an exact draft-screen confirmation, so this is
not a V1 pass.

The next live run must capture the draft screen, where champion portraits and
ban icons are larger and unobstructed. Draft-screen extraction becomes the
authoritative exact-BP path; the in-game sidebar remains a continuous
cross-check only. A mismatch remains rejected even when the gameplay candidate
has a high template score. Thresholds will not be lowered merely to fill missing
slots.

## Safety and asset handling

- Data Dragon version is pinned to `16.14.1` in the layout.
- 173 Riot champion icons are downloaded only to the ignored local cache.
- Riot images are not committed and must not be displayed by the monitoring UI
  without a separate compliance decision.
- No signed HLS URL or embedded token is written to this artifact.

## Remaining V0/V1 work

1. Capture and calibrate a draft-screen layout on the next Polymarket-backed
   match, then require exact 10 picks and 10 bans.
2. Normalize Baron timer/event state and capture a direct inhibitor event when
   one occurs.
3. Persist `observedAt`, source-frame freshness and recovery/interruption
   metrics in the continuous runner.
4. Reconcile against postgame ground truth and run two consecutive unattended
   Polymarket-backed matches with >=95% usable normal-game samples and zero
   known-wrong accepted snapshots.
