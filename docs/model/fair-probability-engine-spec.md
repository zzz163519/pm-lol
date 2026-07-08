# FairProbabilityEngine Modeling Spec

Status: Phase 2 modeling design only. This document defines the probability
engine contract for future implementation cards. It does not implement model
code, connect live data, compare against Polymarket prices, generate strategy
signals, size positions, connect wallets, store private keys, or place orders.

This spec is based on CAL-57 methodology research, CAL-59 field-source-map
evidence, the project architecture note, `docs/schema-phase1.md`, and the CAL-61
dashboard interface direction.

## 1. Overall Architecture

`FairProbabilityEngine` estimates the fair win probability for one mapped
Polymarket LoL `Game N Winner` outcome. The module is a read-only probability
calculator. Its public seam is one input snapshot plus one output estimate; it
hides team rating, draft feature, side, patch, and live-state coefficient logic.
Callers do not know model internals and cannot ask the engine for trading
permission.

Use logit-space composition:

```text
base_probability = TeamStrengthBase(team_a, team_b, match_context)
logit_base = log(base_probability / (1 - base_probability))

logit_fair =
  logit_base
  + draft_delta
  + side_delta
  + patch_delta
  + live_state_delta

fair_probability = 1 / (1 + exp(-logit_fair))
```

Do not add probabilities directly. Every adjustment after
`TeamStrengthBase` is a logit delta. The engine must clamp the final
probability only for numerical safety, for example to `[0.01, 0.99]`; clamping
is not a substitute for calibration.

### Component Contract

| Component | Input fields | Output | Space | Initial behavior |
|---|---|---|---|---|
| `TeamStrengthBase` | teams, league, match date, roster ids, historical results | `base_probability`, `logit_base` | probability then logit | Required |
| `DraftAdjustment` | final blue/red picks, patch, side, champion ids, optional roles | `draft_delta` | logit delta | Required after `draft_complete=true` |
| `SideAdjustment` | league, patch, team side, game number | `side_delta` | logit delta | Required, may be `0.0` |
| `PatchMetaAdjustment` | patch, league, recency window, coefficient version | `patch_delta` | logit delta | Required, may be `0.0` |
| `InGameAdjustment` | game clock, gold, goldDiff, objectives, kills, gameState | `live_state_delta` | logit delta | Designed here; enable only after source freshness gates |

All component outputs must include `confidence`, `source`, `featureTimestamp`,
and `blockedReasons[]`. If a hard gate fails, the engine should emit a blocked
estimate with missing deltas set to `0.0` and must not silently substitute a
fallback that looks successful.

### Source And Dependency Classification

- Historical match data is local-substitutable once imported; Oracle's Elixir is
  historical-only input, not a live dependency.
- Cito visual-state, LoLEsports frontend API, Polymarket, PandaScore, and GRID
  are true external dependencies.
- The future dashboard API is an in-process or local HTTP caller of the engine
  output; it should consume a stable DTO, not model internals.
- Test adapters are local-substitutable fixtures built from stored source-spike
  samples.

The deletion test favors a single `FairProbabilityEngine` seam: without it,
rating, draft, side, patch, and live-state deltas would leak into dashboard,
backtest, and later signal callers. Keeping the interface small makes the module
deep enough to justify the abstraction.

## 2. TeamStrengthBase

`TeamStrengthBase` produces the pre-draft fair win probability for the target
game before side, patch, draft, and live-state deltas. Version 1 should use
roster-aware Elo as the primary implementation and optionally compute TrueSkill
or ProjektZero-style ensemble values as offline diagnostics.

### Inputs

Required fields:

- `match_id`, `game_id`, `game_number`
- `league`, `start_time`, `patch` when known
- `team_a_id`, `team_b_id`, `team_a_name`, `team_b_name`
- expected roster ids or player ids when available
- historical games with `match_date`, `league`, `patch`, `team_ids`, `roster_ids`,
  `side`, `game_number`, and `winner_team_id`

Candidate historical source: Oracle's Elixir downloads for professional LoL
match, team, player, champion, side, patch, and result data. It is suitable for
offline training and backtesting only. It must not be treated as live input.

### Elo Formula

Maintain one rating per roster-aware team key:

```text
team_key = team_id + roster_fingerprint
rating_default = 1500
scale = 400

expected_a = 1 / (1 + 10 ^ ((rating_b - rating_a) / scale))
expected_b = 1 - expected_a

score_a = 1 if team_a wins else 0
rating_a_next = rating_a + k * match_weight * (score_a - expected_a)
rating_b_next = rating_b + k * match_weight * ((1 - score_a) - expected_b)
```

Recommended initial parameters:

- `k = 24` for major-league professional matches.
- `match_weight = 1.0` for same-tier league matches.
- `match_weight = 0.75` for cross-league or lower-confidence historical rows.
- Use exponential decay on stale matches:

```text
age_days = prediction_date - match_date
decay_weight = exp(-age_days / 365)
effective_match_weight = match_weight * decay_weight
```

Roster-aware handling:

```text
roster_overlap = count(current_roster_ids intersect historical_roster_ids) / 5
if roster_overlap >= 0.8:
  use roster rating
elif roster_overlap >= 0.6:
  blend = 0.7 * roster_rating + 0.3 * organization_rating
else:
  blend = 0.4 * organization_rating + 0.6 * league_default_rating
```

For missing roster ids, fall back to organization-level Elo and lower
`componentConfidence`. Do not fabricate player-level continuity.

### Base Probability Output

The base model returns:

```text
base_probability_a = expected_a
logit_base_a = log(base_probability_a / (1 - base_probability_a))
team_strength_delta = rating_a - rating_b
team_strength_confidence
rating_version
rating_snapshot_date
```

The engine should compute the probability from the viewpoint of the mapped
Polymarket outcome team. If the mapped team is on red side, `base_probability`
still means the mapped team's chance to win, not blue-side chance.

### TrueSkill / ProjektZero Use

TrueSkill can be used as a second base signal when enough historical data is
available. The initial design should not expose TrueSkill to callers. It can
produce an internal diagnostic:

```text
trueskill_probability
elo_probability
base_probability = 0.8 * elo_probability + 0.2 * trueskill_probability
```

Use this blend only after backtest calibration proves improvement. Before that,
report TrueSkill as a shadow metric. ProjektZero's Elo + TrueSkill + performance
feature idea is useful as a design reference, but its repository data and model
weights must not be copied as production truth for this project.

## 3. DraftAdjustment

`DraftAdjustment` starts after final picks are known. It outputs a bounded
logit delta for the mapped team. It is not a standalone win probability model.
DraftGap or any hero-composition tool can provide draft features, but DraftGap
scores must never be used directly as `fair_probability`.

### Inputs

From CAL-59 field-source-map:

- primary source: LoLEsports livestats
- endpoint: `GET https://feed.lolesports.com/livestats/v1/window/{gameId}`
- response paths:
  - `gameMetadata.blueTeamMetadata.participantMetadata[].championId`
  - `gameMetadata.redTeamMetadata.participantMetadata[].championId`

Required normalized fields:

```text
draft_complete
patch
blue_team_id
red_team_id
blue_champions[5]
red_champions[5]
champion_id standardization status
role assignments when available
source_latency_sec when available
```

Hard gates:

- `draft_complete=false` blocks `DraftAdjustment`.
- Any missing or unstandardized champion id blocks the component.
- Ambiguous side mapping blocks the component.
- Bans may be nullable because current LoLEsports samples do not expose them.

### Feature Design

Initial features should be simple and auditable:

```text
blue_champion_strength_sum
red_champion_strength_sum
blue_role_fit_score
red_role_fit_score
blue_synergy_score
red_synergy_score
blue_counter_score
red_counter_score
patch_pickban_popularity_delta
scaling_profile_delta
```

Candidate feature providers:

- DraftGap-style champion matchup, ally duo, synergy, and counter features.
- Historical professional match data by champion, role, patch, and region.
- Project-local coefficient tables generated offline.

Do not use raw champion win rate as direct probability. Convert draft features
to a delta through a calibrated model:

```text
draft_feature_delta =
  beta_strength * (mapped_strength_sum - opponent_strength_sum)
  + beta_synergy * (mapped_synergy_score - opponent_synergy_score)
  + beta_counter * (mapped_counter_score - opponent_counter_score)
  + beta_scaling * (mapped_scaling_profile - opponent_scaling_profile)

draft_delta = clamp(draft_feature_delta, -0.35, 0.35)
```

The initial clamp is intentionally conservative. A logit delta of `0.35` moves a
50 percent game to about 58.7 percent before other deltas, which keeps draft
from overwhelming team strength without evidence.

### Output

```text
draft_delta
draft_confidence
draft_model_version
draft_feature_values
draft_source = "lolesports_livestats"
draft_blocked_reasons[]
```

When draft data is blocked, return `draft_delta=0.0`,
`draft_confidence=0.0`, and a blocked reason. The caller must display this as
missing evidence, not as proof that draft has no impact.

## 4. SideAdjustment / PatchMetaAdjustment

`SideAdjustment` and `PatchMetaAdjustment` are small calibrated logit deltas.
They exist to keep known contextual effects out of `TeamStrengthBase` and
`DraftAdjustment`.

### SideAdjustment

Inputs:

- `league`
- `patch`
- `game_number`
- `team_side` for the mapped team
- historical games with blue/red side and winner

Estimate side advantage by league and patch window:

```text
blue_win_rate = blue_wins / blue_games
blue_side_delta = logit(shrink(blue_win_rate)) - logit(0.5)
mapped_side_delta = blue_side_delta if mapped_team_side == "blue" else -blue_side_delta
```

Use shrinkage toward 50 percent to avoid overfitting small samples:

```text
shrink(p) = (wins + prior_strength * 0.5) / (games + prior_strength)
prior_strength = 200 games
```

Fallback rules:

- League + patch window has at least 200 games: use that coefficient.
- League has at least 500 recent games across patches: use league coefficient.
- Otherwise use global professional coefficient.
- If no coefficient is available, use `side_delta=0.0` and
  `side_confidence=0.25`, not a blocked estimate.

### PatchMetaAdjustment

Patch/meta adjustment captures known patch-level shifts not already explained by
side or draft features. It should start conservative:

```text
patch_delta =
  beta_patch_volatility * patch_volatility_score
  + beta_meta_fit * mapped_team_meta_fit_delta
```

Initial version may set `patch_delta=0.0` with a valid model version until
offline calibration exists. That is acceptable if the output explicitly states
that patch coefficients are not yet active.

Coefficient re-estimation triggers:

- new major patch appears in source data;
- champion system changes or item system changes affect feature stability;
- calibration drift exceeds threshold, for example Brier score worsens by more
  than 10 percent versus the previous patch window;
- at least 50 new professional games on the patch are available for a shadow
  coefficient update.

Fallback rules:

- Unknown patch: `patch_delta=0.0`, low confidence, warning.
- Known patch but no league-specific fit: use global patch coefficient.
- Patch string missing: `patch_delta=0.0`, low confidence, warning.

Patch adjustment must not look ahead to future patch outcomes when backtesting.

## 5. InGameAdjustment

`InGameAdjustment` computes `live_state_delta` from current game state. This is
the highest-risk component because it can leak terminal information or react to
stale live frames. It must remain disabled until source freshness gates and
backtest replay semantics are accepted for the implementation card.

Riot/AWS Win Probability is the structural reference: use game time, gold share,
XP or level proxies, alive-player state when available, towers, dragons, soul,
Herald, inhibitors, Baron, Elder, and timers. The public Riot note says the
official model is XGBoost trained on professional games since patch 10.4 and
uses relative features such as Gold %. PM-LOL should reproduce the feature
principles, not copy a closed model.

### CAL-59 Source Mapping

Primary source for live-state fields:

- source: Cito visual-state
- endpoint: `GET /api/v1/lol/live/{gameId}/visual-state`
- game id discovery: use Cito `/api/v1/lol/matches/{matchId}/coverage`; do not
  treat `/lol/live` matchId as visual-state gameId directly

Field mapping:

| Model field | Source path | Notes |
|---|---|---|
| team identity | `blueTeam.tag`, `redTeam.tag` | Side mapping must join resolver output |
| gold | `blueTeam.gold`, `redTeam.gold` | Use raw totals |
| goldDiff | `blueTeam.gold - redTeam.gold` | Positive means blue leads |
| objectives | `blueTeam.dragons`, `redTeam.dragons`, `blueTeam.barons`, `redTeam.barons`, `blueTeam.towers`, `redTeam.towers` | Compact team totals |
| kills | `blueTeam.kills`, `redTeam.kills` | Auxiliary, not a primary economic proxy |
| gameClock | `gameTimeFormatted`, `gameTimeSeconds` | Prefer explicit Cito clock |
| gameState | `status` | Must pass freshness gate |
| winner | LoLEsports `getEventDetails` reconciliation | Winner is for labels and postgame reconciliation only |

`winner` is never a live prediction feature. It is a label for training,
backtest scoring, and terminal reconciliation.

### Feature Design

Use relative and time-aware features:

```text
total_gold = blue_gold + red_gold
blue_gold_share = blue_gold / total_gold
mapped_gold_share_delta =
  mapped_team_gold / total_gold - opponent_gold / total_gold

gold_diff_per_min = gold_diff_for_mapped_team / max(game_clock_min, 1)
tower_delta = mapped_towers - opponent_towers
dragon_delta = mapped_dragons - opponent_dragons
baron_delta = mapped_barons - opponent_barons
kill_delta = mapped_kills - opponent_kills
```

When source fields later expose XP, levels, alive players, inhibitors, Baron
timers, Elder timers, or dragon soul state, add them as explicit optional
features. Do not infer them from absent fields.

### Time-Weighted Delta

The first implementation should use a calibrated logistic feature model rather
than fixed public coefficients:

```text
time_bucket = bucket(game_clock_min)
live_state_delta =
  beta_gold_share[time_bucket] * mapped_gold_share_delta
  + beta_gold_per_min[time_bucket] * gold_diff_per_min
  + beta_tower[time_bucket] * tower_delta
  + beta_dragon[time_bucket] * dragon_delta
  + beta_baron[time_bucket] * baron_delta
  + beta_kill[time_bucket] * kill_delta
```

Initial buckets:

```text
0-10 min:   low gold weight, low objective weight, high uncertainty
10-15 min:  rising gold and first-objective weight
15-20 min:  primary midgame calibration bucket
20-25 min:  objectives and Baron setup gain weight
25-35 min:  Baron/Elder/tower/inhibitor features dominate when available
35+ min:    cap confidence and avoid overreacting to gold-only leads
```

The public EGR-style heuristic from the architecture note
(`15m ~320 gold ~= 4.0pp`, dragon ~= 7.5pp) can be used as a sanity-check prior,
not as the final coefficient. Convert any probability-point heuristic into
logit deltas during calibration.

### Freshness And Hard Gates

Block `live_state_delta` when:

- resolver `mapping_confidence < 0.90`;
- `market_type != game_winner`;
- side mapping is ambiguous;
- `gameState` is stale, unknown, or incompatible with live prediction;
- `source_latency_sec` or observed update age exceeds the accepted threshold for
  the current phase;
- source payload schema is missing required live fields;
- winner is already known and the row is not explicitly part of postgame label
  reconciliation.

When blocked, output `live_state_delta=0.0` with blocked reasons. Do not treat
stale Cito data as successful fallback.

## 6. Backtest Design

Backtesting must evaluate whether `fair_probability` is calibrated and useful
as a probability estimate. It must not evaluate trading PnL, edge, sizing, or
execution in this spec.

### Dataset Shape

Build time-indexed examples:

```text
prediction_time
match_id
game_id
game_number
league
patch
mapped_team_id
opponent_team_id
team_side
features_available_at_prediction_time
fair_probability
label_win_after_game_end
```

Prediction checkpoints:

- pregame before draft;
- post-draft after `draft_complete=true`;
- live buckets such as 10m, 15m, 20m, 25m, 30m, if live snapshots are available
  and fresh.

Candidate historical sources:

- Oracle's Elixir for historical match results, teams, players, champions, patch,
  and side where available.
- Stored Cito/LoLEsports snapshots for source-faithful replay when available.
- LoLEsports `getEventDetails` terminal state for winner labels.

### Leakage Rules

Hard no-leakage rules:

- Train/validation/test split must be chronological, not random by row.
- A prediction row may use only information known at or before
  `prediction_time`.
- Do not use future patch outcomes when estimating patch coefficients.
- Do not use postgame winner, final gold, final objectives, final scoreboard, or
  series result as features for an in-game checkpoint.
- If multiple checkpoints from one game are included, split by game date so that
  later checkpoints from a game cannot appear in training while earlier
  checkpoints appear in validation.
- Roster ratings for a date must be produced by walking forward through earlier
  games only.
- Draft features must use final picks only after draft completion; pre-draft
  examples must not include champion fields.
- Polymarket prices and orderbook fields are not model features for
  `FairProbabilityEngine`.

### Metrics

Primary metrics:

```text
Brier score = mean((probability - outcome)^2)
log loss = -mean(outcome * log(probability) + (1 - outcome) * log(1 - probability))
calibration curve by probability bucket
expected calibration error
```

Secondary diagnostics:

- reliability table by bucket: predicted mean vs realized win rate;
- calibration by league;
- calibration by patch;
- calibration by time bucket;
- delta ablation: base only, base+draft, base+draft+side+patch, full live;
- confidence coverage: performance when `confidence >= threshold`.

Accuracy is not sufficient and must not be the main model-selection metric. A
model that predicts calibrated 55 percent edges can have mediocre accuracy while
still being a useful probability model.

### Acceptance Thresholds For Future Implementation

An implementation card should define thresholds before training. Suggested
initial gates:

- no leakage test failures in fixture backtests;
- Brier and log loss improve over Elo-only baseline on chronological validation;
- calibration buckets from 0.35 to 0.65 are not systematically overconfident;
- adding `DraftAdjustment` or `InGameAdjustment` must improve validation metrics
  or remain shadow-only.

## 7. Phase 2 Boundary And Dashboard Interface

This spec ends at `fair_probability`. It does not compare
`fair_probability` with Polymarket market prices, does not calculate edge, does
not size orders, and does not emit signals. Those belong to later
`EdgeCapacityCalculator`, `NetEdgeCalculator`, `SignalEngine`, paper execution,
and live execution phases.

Phase boundaries:

- Phase 2: read-only `FairProbabilityEngine` output and offline calibration.
- Phase 3: optional `fair_probability vs market_price` and edge display after
  explicit approval.
- Phase 4/5: paper/live execution gates only after separate review; wallets,
  private keys, order signing, and real placement remain out of scope here.

### Dashboard Output Contract

The Dashboard should receive a read-only DTO that can fill the CAL-61 reserved
FairProbabilityEngine slot:

```json
{
  "adapter": "fair_probability",
  "matchId": "115570934355614581",
  "gameId": "115570934355614582",
  "conditionId": "0x...",
  "marketId": "polymarket-market-id",
  "marketType": "game_winner",
  "mappedTeamId": "team-id",
  "mappedTeamName": "T1",
  "teamSide": "red",
  "fairProbability": 0.542,
  "modelVersion": "fair-probability-engine/v0.1.0",
  "componentDeltas": {
    "logitBase": 0.08,
    "draftDelta": 0.03,
    "sideDelta": -0.01,
    "patchDelta": 0.0,
    "liveStateDelta": 0.05
  },
  "inputFreshness": {
    "ratingsSnapshotDate": "2026-07-01",
    "draftObservedAt": "2026-07-08T08:05:10Z",
    "gameStateObservedAt": "2026-07-08T08:15:20Z",
    "sourceLatencySec": 24.0,
    "stale": false
  },
  "confidence": 0.82,
  "calibrationBucket": "0.50-0.55",
  "blockedReasons": [],
  "warnings": ["patch_delta_shadow_only"],
  "inputsSnapshotIds": {
    "resolvedMarketId": "resolved-id",
    "draftSnapshotId": "draft-id",
    "gameStateSnapshotId": "state-id"
  },
  "observedAt": "2026-07-08T08:15:22Z"
}
```

Required fields:

- `fairProbability`
- `modelVersion`
- `componentDeltas`
- `inputFreshness`
- `confidence`
- `calibrationBucket`
- `blockedReasons`

When blocked, the DTO should still render:

```json
{
  "adapter": "fair_probability",
  "fairProbability": null,
  "modelVersion": "fair-probability-engine/v0.1.0",
  "componentDeltas": {
    "logitBase": 0.0,
    "draftDelta": 0.0,
    "sideDelta": 0.0,
    "patchDelta": 0.0,
    "liveStateDelta": 0.0
  },
  "inputFreshness": {
    "stale": true
  },
  "confidence": 0.0,
  "calibrationBucket": "blocked",
  "blockedReasons": ["mapping_confidence_below_threshold"]
}
```

Dashboard copy must not describe this as an entry, signal, edge, or trade. The
value is a model estimate only.

### Implementation-Card Acceptance Notes

Future implementation cards should test the public seam, not internals:

- valid mapped pregame fixture returns base probability and component deltas;
- incomplete draft blocks only `DraftAdjustment`;
- stale Cito snapshot blocks `InGameAdjustment`;
- low mapping confidence blocks the whole estimate;
- postgame winner is accepted as a label in backtests but rejected as a live
  feature;
- DTO matches the dashboard contract exactly.

Risk labels:

- blocker-now: do not implement signals, market-price comparison, wallets, or
  order placement from this spec.
- pre-next-card blocker: implementation must define the exact offline training
  dataset and no-leakage fixture tests before model code.
- deferred: TrueSkill blending, full XGBoost live-state model, GRID/PandaScore
  adapters, and Phase 3 edge display.

## References

- CAL-57 comments: Riot/AWS WP, ProjektZero, DraftGap, DNN robustness, and
  Kaggle/SHAP methodology summary.
- CAL-59 `docs/source-spike/field-source-map.md`: Cito + LoLEsports split and
  winner reconciliation.
- CAL-61 dashboard handoff: `DataSourceAdapter` and reserved FairProbability
  dashboard slot.
- `docs/schema-phase1.md`: `resolved_markets`, `matches`, `games`,
  `draft_snapshots`, `game_state_snapshots`, and `quotes` schema.
- Riot LoLEsports Dev Diary, "Win Probability Powered by AWS at Worlds": public
  description of XGBoost WP features including game time, Gold %, XP, alive
  players, towers, dragons, Herald, inhibitors, Baron, and Elder.
- GitHub references inspected through `gh repo view`:
  `MRittinghouse/ProjektZero-LoL-Model`, `vigovlugt/draftgap`, and
  `hubkrieb/lol-win-probabilities`.
