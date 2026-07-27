# Strategy Model Semantics

Status: authoritative strategy clarification for future modeling work. This document does not authorize strategy implementation, signals, paper trading, wallet integration, or order execution while Phase 0 remains open.

## Core Thesis

PM-LOL is a value/mispricing system, not a speed-arbitrage system. The model estimates the conditional probability that one mapped team wins a specific Game Winner market. A delayed source can still be useful when its state is accurate enough and the executable Polymarket price still leaves positive net value.

```text
team_strength_prior
  + draft_power_curve(time)
  + conditional economy/objective/map state
  + calibrated interactions
  = conditional_fair_probability

conditional_fair_probability
  - executable_market_probability
  - spread_and_slippage
  = net_value_gap
```

Delay is therefore a freshness and remaining-edge constraint, not the alpha source and not an automatic disqualifier. A stale, rolled-back, ambiguous, or near-terminal state must still be blocked.

## Conditional Probability Model

`TeamStrengthBase` is the prior. Ranking, roster continuity, league strength and recent performance affect the starting probability, but a weak or low-ranked team is never an automatic buy.

Final picks define more than one fixed draft delta. They define a time-varying composition power curve:

- early-game pressure and lane stability;
- mid-game item, level and objective spikes;
- late-game scaling, engage, wave-clear and team-fight profile;
- the timing and reachability of remaining power spikes.

Live economy and objectives must be evaluated conditionally against that curve. The same gold deficit can be survivable for a scaling composition and close to terminal for an early composition. Gold, towers, dragons, soul state, Baron, Elder, inhibitors and nexus towers are state transitions whose value depends on time, draft and map state; they are not universal fixed probability points.

The intended future model is:

```text
P(win at t) = f(
  team_strength_prior,
  draft_power_curve(t),
  gold_and_item_state(t),
  objective_and_map_state(t),
  side_and_patch,
  team_execution_context,
  interactions
)
```

Required interactions include at least `draft x time`, `draft x economy`, `draft x objectives`, and `team strength x draft`. Diagnostic logit deltas may remain visible, but the model must not mechanically add an independent fixed draft score to a generic live-state score.

## Strategy Families

- `S1 pregame strength mispricing`: the team-strength prior differs materially from the executable market probability.
- `S2 post-draft temporal mispricing`: final picks change the early/mid/late power curve more than the market price reflects.
- `S3 conditional resource mispricing`: the market overweights headline gold or underweights objectives, map state and composition timing.
- `S4 high-odds reversal`: a gated expression of S2/S3, not a standalone rule to buy weak teams or long odds.

The mainline remains pregame plus post-draft validation. S3/S4 stay frozen until their separate unlock criteria are met.

## High-Odds Reversal Gate

A high-odds entry is valid only when all of the following hold:

- the executable market probability plus costs is materially below the calibrated conditional win probability;
- the draft curve contains unrealized scaling or a reachable power spike;
- the current deficit is better than, or survivable relative to, the expected trajectory for that roster and composition;
- the game has not crossed an irreversible-state gate involving soul, Elder, Baron, inhibitors, nexus towers, alive-player state, or another near-terminal condition;
- the relevant low-probability bucket has enough chronological out-of-sample evidence and acceptable calibration.

High odds alone are not value. Low ranking alone is not value. Current gold deficit alone is not evidence of either value or terminal loss.

## Value Realization And Evaluation

Two outcomes must be evaluated separately:

1. `resolution EV`: buying below true conditional probability can be valid even if the market does not reprice before game end;
2. `price convergence`: repricing toward fair value can support an earlier exit, faster capital reuse and lower outcome variance, but is not required for the core value thesis.

Future validation must compare against both an Elo-only baseline and the timestamp-aligned Polymarket probability baseline. It must report tail calibration for model probabilities such as 0.05-0.10, 0.10-0.20 and 0.20-0.30 with sample counts and uncertainty. Aggregate accuracy or Brier score must not hide a poorly calibrated reversal tail.

Market comparison must use executable ask/VWAP plus spread, slippage and later applicable fees, not midpoint or last trade as if they were fill prices.

## Supersession

This clarification supersedes any earlier wording that can be read as:

- requiring a speed lead over Polymarket for the strategy to exist;
- treating draft as one time-invariant scalar adjustment;
- treating objectives as fixed context-free win-probability points;
- treating weak teams, current deficits or high odds as automatic buy signals;
- requiring short-horizon price convergence for a value position to be valid.
