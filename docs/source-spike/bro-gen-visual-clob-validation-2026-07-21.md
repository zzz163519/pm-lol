# BRO vs GEN visual + CLOB validation — 2026-07-21

## Status

This is the first full-match Phase 0 validation of the Polymarket-backed
broadcast path. It is useful positive evidence, but it is not the second
required consecutive match and it does not close source feasibility.

The public KeSPA Twitch channel produced 480/480 five-second frames from
`2026-07-21T09:45:49Z` through `10:25:57Z`. The capture contains the final
draft, advancing gameplay from 0 through 24 minutes, postgame player cameras,
highlights, and the result board (`BRO 1-0 GEN`). No account, LLM, OCR service,
wallet, private key, or order endpoint was used. Signed HLS URLs were redacted
and are not present in the repository.

## Deterministic draft extraction

The draft graphic uses version-pinned CommunityDragon champion art. Large pick
panels match the exact centered `splashPath`; small ban panels match the exact
`tilePath`. Individual panels may be mirrored independently, so the extractor
evaluates both orientations and compares champion identities only after
collapsing their orientation variants.

The final pick result, normalized to top/jungle/mid/ADC/support order, is:

- GEN left: Ambessa, Jarvan IV, Taliyah, Syndra, Camille.
- BRO right: Vayne, Naafiri, Ryze, Ezreal, Shen.

All ten picks repeated across three frames. Correct pick candidates had 33–88
RANSAC inliers in the reference frame, while ordinary runner-up identities had
only 4–7. Cross-frame pick confidence ranged from 0.892 to 0.985.

Only five of ten small bans passed the strict per-frame and cross-frame gates:
Cassiopeia, Locke, Orianna, Galio, and Sivir. The left ban row is partly hidden
by a third-party stream overlay. Low-feature candidates remain unknown; the
code does not lower thresholds or convert visual guesses into accepted data.

CommunityDragon artwork remains an ignored local cache. The selected evidence
frames are committed, but the artwork is not. Production usage/compliance must
be reviewed before this source is promoted beyond the spike.

## Gameplay extraction

A dense 15-frame sample used three adjacent frames around five game times. The
monotonic clock gate retained 13 advancing frames. At 24:22, the accepted state
was:

| Field | GEN / left | BRO / right |
|---|---:|---:|
| Gold | 41.5k | 57.3k |
| Kills | 8 | 29 |
| Towers | 0 | 8 |
| Dragons | 3 | 0 |

The tower digit ROIs were narrowed after the original left crop allowed the
tower glyph to be read as the leading `1` in `10`. With digit-only ROIs, three
adjacent late frames consistently returned left `0` and right `8`; the values
match the visible scoreboard.

Seven of ten tiny gameplay portraits also matched the authoritative draft
after cross-frame agreement. The other three remain unknown. This does not
invalidate final picks because the complete draft screen is the authoritative
pick input; the gameplay sidebar is only a continuity check.

Baron/inhibitor normalization is not implemented in this evidence run.

## Polymarket CLOB REST continuity

The public orderbook probe requested both outcome books every 30 seconds from
`09:25:56Z` through `10:17:05Z`:

- 199/200 book requests succeeded.
- One HANJIN BRION request timed out after 20 seconds at sample 3; subsequent
  polls recovered without intervention.
- Median request latency was 326.822 ms; p95 was 685.123 ms.
- Median observed-minus-source-timestamp lag was 169.002 ms; p95 was
  1,117.417 ms.
- HANJIN BRION moved from 0.85/0.86 to 0.995/0.996 best bid/ask.
- Gen.G moved from 0.14/0.15 to 0.004/0.005.

The market remained readable through draft and gameplay. This is source
evidence only; no fair probability, signal, position, or execution decision was
calculated.

## Evidence

- `bro-gen-visual-clob-validation-20260721.json` — compact machine-readable
  capture, extraction, and orderbook summary.
- `twitch-bro-gen-draft-final-20260721T095544Z.jpg` — complete final draft.
- `twitch-bro-gen-gameplay-0559-20260721T100224Z.jpg` — early gameplay.
- `twitch-bro-gen-gameplay-1552-20260721T101224Z.jpg` — midgame.
- `twitch-bro-gen-gameplay-2412-20260721T102044Z.jpg` — late gameplay.
- `twitch-bro-gen-result-board-20260721T102544Z.jpg` — result board.

## Conclusion

First-match continuity passes for capture, final picks, game clock, gold,
kills, towers, dragons, result, and CLOB REST. Full bans, Baron/inhibitor
normalization, second-match repetition, and CommunityDragon production
compliance remain open. Therefore the honest Phase 0 status is still
`partial_low_confidence`, not source solved.
