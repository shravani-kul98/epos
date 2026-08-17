# Scoring Methodology

All scores are **deterministic** and **explainable**. GPT-4o never calculates any score.

The weight families and band cut-offs live in `src/config.py`. All Phase 3 penalty values,
thresholds, freshness bands, canonical status vocabulary and severity ordering live in a single
auditable module, `src/scoring_rules.py`, which re-exports the weights/bands from `config.py`
without duplicating them. `scoring_rules.validate_scoring_config()` runs at import and fails fast
if a weight family does not sum to 1.0 or factor keys are inconsistent.

Every factor returns a value in **0–100**, a **human-readable explanation**, and is resilient to
missing data. Where a factor has no evidence at all, it returns a documented neutral default and
the **Confidence** score (not Health) captures the data gap.

## Determinism policy
- Every public engine function takes a **required** `as_of_date: date`; scoring, confidence and
  alert logic never read the system clock.
- `calculated_at` / `detected_at` are derived deterministically as **midnight UTC on `as_of_date`**
  (`utils.reference_timestamp`). They represent the calculation reference timestamp, not a live
  wall-clock execution time.
- Schedule variance uses **calendar days** in Version 1 (documented limitation).

## Delivery health vs data confidence vs early-warning alerts
- **Delivery health** answers "how is the project performing?" (schedule, milestones, tasks, risk,
  dependencies, resources, actions).
- **Data confidence** answers "can we trust the data behind the health score?" (freshness,
  completeness, ownership, source reliability). Missing/adverse data lowers Confidence, never
  silently inflates Health.
- **Early-warning alerts** are discrete, deduplicated, evidence-cited signals for human action.
  They do not compute the scores; they highlight specific conditions.

## Controlled status vocabulary
Upstream systems use inconsistent labels. `scoring_rules` defines canonical values per domain and
normalises known aliases internally (source CSVs are never modified). Examples: `Completed` →
`Complete`; ` completed ` → `Complete` (case/whitespace tolerant). Unknown values are **not** treated
as healthy — they are recorded as `PortfolioData.status_anomalies` and surfaced via Data Confidence.
Terminal-status checks (`Complete`/`Closed`/`Cancelled`) always use canonical values. See
[data-dictionary.md](data-dictionary.md) for the full canonical list and accepted aliases.

## Freshness bands (`scoring_rules`)
| Band | Age vs `as_of_date` |
|------|---------------------|
| fresh | 0–7 days |
| stale | 8–14 days |
| significantly_stale | 15–21 days |
| critically_stale | > 21 days |

## Health Score (0–100)

```
Health = 0.25·SchedulePerformance
       + 0.20·MilestoneReadiness
       + 0.15·TaskExecution
       + 0.15·RiskExposure
       + 0.10·DependencyStatus
       + 0.10·ResourceCapacity
       + 0.05·ActionClosure
```

**Bands:** Green 80–100 · Amber 60–79.99 · Red 0–59.99.

The authoritative Version 1 penalty values are defined in `src/scoring_rules.py`. Each factor
starts at 100 (unless stated) and applies the documented penalties, clamped to 0–100. Terminal
records (`Complete`/`Closed`/`Cancelled`) are excluded from delivery penalties.

| Factor | Version 1 rules |
|--------|-----------------|
| Schedule Performance | Calendar-day slip = `forecast_end − baseline_end`. Score: ≤0 → 100; 1–5 → 85; 6–10 → 70; 11–20 → 50; 21–120 → 25; 121–240 → 12; >240 → 5, so a longer slip never scores better than a shorter one. Missing baseline/forecast → 50 (limitation). |
| Milestone Readiness | Per active milestone with `forecast_date > baseline_date`: −5/−10/−18/−25 for Low/Medium/High/Critical criticality; plus status penalty At Risk −8, Delayed −15, Blocked −20. No milestones → 50 (limitation). |
| Task Execution | Per active task: blocked −8 (−15 if on High/Critical milestone); overdue (`forecast_end < as_of_date`, not terminal) −6 (extra −6 on High/Critical milestone); `completion_percent < 50` when `planned_end ≤ as_of_date` −5. No tasks → 50 (limitation). |
| Risk Exposure | exposure = `probability × impact` (1–25) for Open/Mitigating risks. 20–25: −20 (+10 if no owner, +5 if mitigation Not Started); 12–19: −10 (+5 if no owner); 6–11: −4; 1–5: none (kept for transparency). |
| Dependency Status | Per delayed dependency (`delay_days > 0`): −5/−10/−15/−20 by criticality; Blocked +extra −10; Delayed +extra −8; At Risk +extra −5; long delays add −5 above 60 days, −10 above 90 days and −15 above 180 days. No dependency data → 70 (limitation). |
| Resource Capacity | Per allocation utilisation `allocated/capacity·100`: ≤90 → 0; ≤100 → −3; ≤110 → −10; ≤125 → −18; >125 → −25. No resources → 70 (limitation). |
| Action Closure | Per overdue active action (`due_date < as_of_date`): −2/−4/−7/−10 by priority; no owner +extra −5. No actions → 70 (limitation). |

**Needs attention** means an Amber or Red health band, or at least one Critical alert. Every
dashboard and Ask EPOS use this one rule (`src/scoring_rules.needs_attention`).

**Completeness caps:** a project with no tasks or no milestones has data completeness capped at
20; one with no risks is capped at 60, so an empty register cannot look complete.

`HealthResult` returns: `project_id`, `overall_score`, `health_band`, `factor_scores`,
`factor_weights`, `factor_explanations`, `critical_drivers` (structured), `source_ids`,
`as_of_date`, `calculated_at`, `assumptions_or_limitations`.

### Health engine behaviour (implemented)
- Public API: `calculate_project_health(project_id, portfolio, as_of_date) -> HealthResult`
  (in `src/health_engine.py`). An unknown `project_id` raises `DataValidationError`; the engine
  never returns a fabricated neutral score for a missing project.
- The engine reads `PortfolioData` as read-only and never mutates any project, milestone, task,
  risk, dependency, resource or action.
- **Missing data vs adverse condition:** a missing schedule date or absent optional table yields a
  documented fallback score plus an entry in `assumptions_or_limitations` — it is not counted as a
  delivery penalty. Optional-table fallback (dependencies/resources/actions = 70) applies only when
  the dataset contains no records of that type at all; a project that legitimately has none scores
  100.
- **Green Health with incomplete data can occur** (for example, a project with sparse but on-track
  records). Data Confidence (implemented in the next step) is what surfaces those data gaps; Health
  and Confidence must be read together.
- Health is configurable prototype project-controls logic, not a validated organisational
  forecasting model.

## Confidence Score (0–100)

```
Confidence = 0.40·DataFreshness
           + 0.30·DataCompleteness
           + 0.20·OwnershipCoverage
           + 0.10·SourceReliability
```

**Bands:** High 80–100 · Medium 60–79.99 · Low 0–59.99.

| Factor | Version 1 rules |
|--------|-----------------|
| Data Freshness | Start 100. Project `status_update_date` age: 8–14 −10, 15–21 −20, >21 −35, missing −40. For active task/requirement/test records, the percentage older than 7 days: ≤10% 0, ≤25% −10, ≤50% −25, >50% −40. Terminal records are not counted as stale. |
| Data Completeness | Missing-field percentage over required fields (per entity, active records only): ≤5% → 100, ≤15% → 80, ≤30% → 60, ≤50% → 35, >50% → 10. Missing owner is counted primarily under Ownership Coverage. |
| Ownership Coverage | Start 100. Active tasks without owner −5 (cap −25); Open/Mitigating risks without mitigation owner −10 (cap −35); active actions without owner −8 (cap −25); active requirements without owner −5 (cap −15); change requests without `requested_by` −5 (cap −10). |
| Source Reliability | "Prototype data-source availability assessment": all tables load/validate → 100; a non-critical optional table missing → 70; a critical table missing but system continues → 40. If project-level data cannot load/validate, no score is produced — a `DataValidationError` is raised. Critical tables: projects, milestones, tasks, risks. |

`ConfidenceResult` returns: `project_id`, `overall_score`, `confidence_band`, `factor_scores`,
`factor_weights`, `factor_explanations`, `data_quality_issues` (structured), `source_ids`,
`as_of_date`, `calculated_at`, `assumptions_or_limitations`.

### Confidence engine behaviour (implemented)
- Public API: `calculate_project_confidence(project_id, portfolio, as_of_date) -> ConfidenceResult`
  and `calculate_portfolio_confidence(portfolio, as_of_date) -> list[ConfidenceResult]`
  (in `src/confidence_engine.py`). An unknown `project_id` raises `DataValidationError`;
  `calculated_at` is midnight UTC on `as_of_date`.
- The engine reads `PortfolioData` as read-only and mutates nothing.
- **Ownership fields (`owner`, `mitigation_owner`, `requested_by`) are scored only by Ownership
  Coverage**, never double-counted under Completeness.
- **Freshness** excludes terminal records (`Complete/Closed/Cancelled/Superseded/Retired`); a
  missing `last_updated_date` on an active record counts as stale and raises a data-quality issue.
- **Source Reliability** is a *Prototype data-source availability assessment*. "Unavailable" means a
  table holds no records at all; a table that is present but simply has none for this project is
  **not** penalised. If the `projects` table is unavailable / the project is absent, no score is
  produced (`DataValidationError`).
- `data_quality_issues` are deduplicated and sorted by severity desc, then `issue_type`, first
  `source_id`, `message`.
- **Health vs Confidence distinction:** Health measures delivery performance; Confidence measures
  whether the data behind it can be trusted. A project can be **Green Health with Low Confidence**
  (healthy signals but stale/missing reporting data). The two are always read together.
- Future GPT-4o will **explain** these confidence results but will never calculate them.

## Worked interpretation examples
- **Green Health, Low Confidence:** delivery signals look healthy, but the project status is >21
  days old and several owners are blank — trust the health score with caution and refresh data.
- **Amber Health, High Confidence:** a High-criticality milestone has slipped 8 days and one
  resource is at 115% utilisation; the data is fresh, complete and owned, so the Amber status is
  trustworthy and actionable.
- **Red Health (schedule/risk/dependency):** forecast end is >20 days past baseline, an Open
  impact-5 risk has no mitigation owner, and a Critical milestone has a delayed supplier
  dependency — multiple factors push the weighted score below 60.

## Limitations
- Formulas are intentionally simple and transparent for a prototype; they are **not** an
  industry-calibrated EVM/PERT model.
- Schedule variance uses calendar days in Version 1.
- Source reliability is a prototype data-source availability assessment, not real integration
  monitoring.
- Rules are configurable prototype logic centralised in `src/scoring_rules.py`.
- No autonomous decisions are made; future AI can explain these scores but never calculate them.
- Neutral defaults on empty factors mean Health should always be read **together with**
  Confidence, which surfaces the underlying data gaps.

## Early-Warning Alerts
While Health and Confidence produce aggregate scores, the Early-Warning engine
(`src/risk_engine.py`) produces specific, individually actionable `EarlyWarningAlert` objects. An
alert is **deterministic and rule-based**, never AI-generated, and always cites the real source
record IDs behind it. Alerts are independent of the aggregate scores.

Public API: `generate_early_warnings(project_id, portfolio, as_of_date)` (project-scoped) and
`generate_portfolio_early_warnings(portfolio, as_of_date)` (all projects). An unknown `project_id`
raises `DataValidationError`. `detected_at` is midnight UTC on `as_of_date` (the same deterministic
policy as `calculated_at`).

**Determinism, dedup and ordering:** each `alert_id` is derived from the alert type and the sorted
source IDs, so unchanged data always yields the same id; alerts are deduplicated by `alert_id` and
sorted by severity (Critical→Low), then `project_id`, `alert_type`, `alert_id`. Each alert's
`source_ids` are unique, sorted and project-scoped.

| # | Rule | Condition | Severity |
|---|------|-----------|----------|
| 1 | Unowned high-exposure risk | status Open/Mitigating, exposure ≥ 20, no mitigation owner | Critical if impact = 5, else High |
| 2 | Critical milestone slip | criticality High/Critical, forecast > baseline | Critical (Critical, > 10d); High (Critical 1–10d, or High > 10d); Medium (High 1–10d) |
| 3 | Milestone delayed dependency | dependency Delayed/Blocked or delay_days > 0, linked to a High/Critical milestone | Critical if milestone Critical and (Blocked or delay > 10d), else High |
| 4 | Blocked task on critical milestone | active task blocked, linked milestone High/Critical | Critical if Critical, else High |
| 5 | Overdue high-priority action | active, due_date < as_of, priority High/Critical | Critical (Critical, > 7d); High (Critical ≤ 7d, or High > 7d); Medium (High ≤ 7d) |
| 6 | Resource over-allocation | allocated_hours > capacity_hours | Critical > 125%, High > 110%, Medium > 100% |
| 7 | Stale project status | status_update_date older than 14d, or missing | Critical if missing; High if > 21d; Medium if 15–21d |
| 8 | Requirement missing verification | active High/Critical requirement; via `trace_links` `verified_by` link to a test case | Critical (Critical, no verification path); Medium (linked test Not Run); High (High, linked test not passed / no evidence) |

**Rule 8 scope:** this uses only the existing simple requirement-to-test relationship in
`trace_links.csv` (`link_type = verified_by`) and `test_cases.csv`. It is **not** a full
traceability or change-impact engine. A `verified_by` link whose target test case does not exist is
treated as no verification path.

**Alert limitations:** thresholds are prototype values in `src/scoring_rules.py`; data is synthetic;
alerts are decision-support only and take no autonomous action.
