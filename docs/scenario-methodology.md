# Scenario Methodology

The scenario engine (`src/scenario_engine.py`) answers "what happens if this dependency slips?"
It is deterministic, uses no AI, and **never modifies baseline data**.

Public API:
`simulate_dependency_delay(dependency_id, additional_delay_days, portfolio, as_of_date) -> ScenarioResult`

## How the simulation works
1. Validate `additional_delay_days` against `SCENARIO_MIN_DELAY_DAYS` (1) and
   `SCENARIO_MAX_DELAY_DAYS` (365). Out-of-range values are **rejected with a clear error**, never
   silently clamped. An unknown `dependency_id` raises `DataValidationError` naming the ID.
2. Build an **independent deep copy** of the portfolio (`copy.deepcopy`), so the copy shares no
   references with the baseline object the caller passed in.
3. On the copied dependency only, set `delay_days = delay_days + additional_delay_days` and set
   `status = "Delayed"` (unless it is already `Blocked`, which is more severe and is preserved).
4. Run the **existing** `calculate_project_health`, `calculate_project_confidence` and
   `generate_early_warnings` twice: once against the untouched baseline and once against the copy.
5. Structure the difference into a `ScenarioResult`.

The engine duplicates no scoring or alert logic. Its only original responsibilities are building
the copy, invoking the three engines, and structuring the comparison.

## Why both delay_days and status are changed
Health Factor E penalises a dependency when `delay_days > 0`, and Risk Rule 3 triggers when a
dependency is `Delayed`/`Blocked` **or** has `delay_days > 0`. Changing `delay_days` alone leaves an
already-delayed dependency unchanged, because it has already crossed every threshold. Setting the
status to `Delayed` reflects the reality that a dependency which gains delay is delayed, and is what
allows an On-Track dependency to cross the existing thresholds. Both changes are applied to the
copy only.

## Schedule propagation (Version 2)
A delay now moves the records it actually reaches. `src/scenario_network.py` walks the dependency
graph in topological order and shifts the forecast date of every downstream Task and Milestone.

Conventions, applied consistently and never mixed:

- **Calendar days**, matching the Health engine's slip thresholds.
- **Durations are preserved**: a delayed record shifts as a whole. Under that assumption all four
  relationship types transmit the same magnitude, so the relationship type governs which dates are
  compared for float, not how much delay travels.
- **Free float is absorbed first.** Slack between a predecessor's planned finish (plus recorded
  lag) and a successor's planned start absorbs delay before any movement propagates. Float that
  cannot be evidenced is treated as zero, which propagates the full delay rather than hiding it.
- **Convergence takes the controlling predecessor**, never the sum, so delay is never double
  counted.
- **Cycles are rejected**, reusing `ensure_acyclic_dependency_network`.
- A project finishes no earlier than its latest scheduled endpoint, which is the only rule that
  converts endpoint movement into project movement. It introduces no constant.

Every movement records its original date, scenario date, shift, controlling dependency, controlling
predecessor and propagation hop.

## Why delay magnitude now matters
Health grades project slip on an existing ladder: 0 days scores 100, 5 scores 85, 10 scores 70, 20
scores 50, and anything beyond scores 25. Because propagation moves real dates, that ladder responds
to the size of the delay. **No new penalty curve was introduced.**

## Saturation is reported, not hidden
A bounded score stops responding once it reaches a bound. When a factor cannot move the result says
so explicitly, naming the bound, and directs the reader to the forecast date movement, which is
continuous and unbounded.

One artefact is reported rather than silently corrected: `task_execution` penalises work whose
forecast is behind today, so pushing a late forecast into the future can *raise* that factor. The
result states that the movement came from crossing a date threshold rather than from delivery
improving. Correcting the underlying rule would re-baseline health across the whole product and is
tracked separately.

## Critical Path Method status
CPM is **not supported** on this data. It requires an activity duration for every node, and a Task's
planned start date is optional and absent from the CSV dataset. `critical_path_data_is_complete`
reports this, and the product uses accurate terminology instead: controlling dependencies, recorded
free float per link, and downstream exposure counts. Nothing is labelled a critical path.

## Sensitivity analysis
`analyse_sensitivity` re-runs the same engine at each tested value: 1, 5, 10, 30, 90, 180 and 365
days. Each point is a full deterministic run; nothing between tested points is interpolated. A
reported threshold is therefore the smallest **tested** value at which an outcome first occurs, and
the true threshold lies between it and the previous tested point. An input that changes nothing is
declared unresponsive rather than presented as a flat curve.

## What the score numbers mean
Health and every health factor use a 0–100 index where higher is healthier. Health is Green from
80, Amber from 60 and Red below 60. A factor moving from 51 to 63 is a 12-point improvement in that
factor, not twelve recovered days and not twelve points of overall project health. Its effect on
overall health is the factor movement multiplied by its configured weight. For example, a 12-point
movement in a factor weighted at 15% contributes `12 × 0.15 = 1.8` points to overall health. The
Scenario page shows both values and a weighted-contribution waterfall.

Completion-date movement is presented before score movement. A bounded score may stay flat after
reaching its floor while the forecast continues to move by months; in that case the forecast delta
is the decision-relevant output and the saturation is stated explicitly.

## AI explanation and predictive-model boundary
The Scenario page offers an explicit AI explanation after deterministic execution. Azure OpenAI
receives only the calculated result and selected evidence records. It may translate those facts
into management language and propose reviewer questions; it cannot execute the scenario, calculate
or change figures, or mutate records. Every factual claim must cite a supplied evidence ID. A
malformed response or fabricated citation rejects all model-authored content, while preserving the
deterministic result. The narrative is always labelled:

> AI-generated decision-support draft; human review required.

No predictive machine-learning model is used for scenario figures. The repository has no
historical outcome labels, calibrated predictive target, duration distributions or correlation
assumptions from which a defensible model could be trained or validated. Adding an unvalidated
model would make the result less repeatable and less auditable, so deterministic graph propagation
and sensitivity analysis remain authoritative.

## Not supported, and deliberately not fabricated
- **Cost and budget scenarios.** No cost field exists on any entity.
- **Supplier scenarios.** `Supplier` is a dependency endpoint type only; there is no supplier
  entity carrying dates or capacity.
- **Monte Carlo.** No duration distributions, probability assumptions or correlation assumptions
  exist. Adding them would mean inventing inputs.

## Observed effect on the real synthetic data (as of 2026-08-25)
| Dependency | Project | Effect |
|---|---|---|
| `D-2001` (Supplier to Milestone, Critical, already Delayed) | P-002 | Forecast end moves 0 days at 30, 59 days at 90, 334 days at 365 |
| `D-1101` (Supplier to Milestone, Critical) | P-011 | Forecast end moves 0 / 20 / 295 days at 30 / 90 / 365 |
| `D-1901` (Supplier to Milestone, Critical) | P-019 | Forecast end moves 0 / 48 / 323 days at 30 / 90 / 365 |

Health scores on these projects do not move because `schedule_performance` already sits at its
floor of 25 and `milestone_readiness` at 0: every one of these projects is already deeply late. The
result explains that saturation and points to the date movement.

## Known limitations
- Scenario results are simulated and do not modify baseline project data or any other page.
- Scenarios are transient; they are not persisted, versioned or shareable yet.
- All data is synthetic.
