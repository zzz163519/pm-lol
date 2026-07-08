# Cito / LoLEsports Draft Phase Probe

Date: 2026-07-08 UTC

## Scope

Read-only follow-up for CAL-54 after the match entered pick/early-game window.
No wallet, private key, order placement, strategy, prediction model, or trading
signal path was used.

## Raw Samples

- First probe: `docs/source-spike/cito-draft-phase-probe-20260708T031052Z.json`
- Short loop: `docs/source-spike/cito-draft-phase-loop-20260708T031242Z.json`

## Result

Cito draft endpoint is reachable but did not provide draft rows during the
sampled window:

```text
GET /api/v1/lol/analytics/drafts/115570934355614587
hasDraft: false
hasPicks: false
hasBans: false
bluePicks: []
redPicks: []
blueBans: []
redBans: []
message: Draft data is not populated for this match yet.
```

Cito visual-state alternated between `not_ready` and `on_break`; it did not
return usable visual `data`.

LoLEsports livestats became useful shortly after. At
`2026-07-08T03:14:51Z`, `GET
https://feed.lolesports.com/livestats/v1/window/115570934355614588` returned
champion metadata for all ten players:

| Side | Player | Role | Champion |
|---|---|---|---|
| Blue / LYON | LYON Dhokla | top | Renekton |
| Blue / LYON | LYON Inspired | jungle | Trundle |
| Blue / LYON | LYON Saint | mid | Taliyah |
| Blue / LYON | LYON Berserker | bottom | Ezreal |
| Blue / LYON | LYON Isles | support | Alistar |
| Red / TSW | TSW Pun | top | Volibear |
| Red / TSW | TSW Hizto | jungle | Lee Sin |
| Red / TSW | TSW Dire | mid | Sylas |
| Red / TSW | TSW Eddie | bottom | Kai'Sa |
| Red / TSW | TSW Bie | support | Nautilus |

Cito `/api/v1/lol/live/115570934355614588/stats` also began returning the same
champion/player rows by `2026-07-08T03:14:46Z`, but team totals were still zero
and coverage still reported `numeric_live_state=false`.

## Conclusion

```text
cito_analytics_drafts = reachable_but_empty
cito_visual_state = not_ready_or_on_break
cito_live_stats = champion_rows_present_after_early_game
lolesports_window = champion_rows_present
picks_available = yes_via_lolesports_window_and_cito_live_stats
bans_available = not_observed
```

For Phase 0, the practical pick source from this window is LoLEsports
`livestats/window` first, with Cito `live/{gameId}/stats` as a delayed secondary
source for champion rows. Cito `analytics/drafts` did not prove live draft
coverage in this sample.
