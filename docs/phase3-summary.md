# Phase 3 Summary — Deterministic Core

Phase 3 delivers the deterministic project-controls core of EPOS Lite: three independent,
explainable engines that calculate facts from validated synthetic portfolio data. No AI, network,
database, UI or system-clock access is involved. Every public function takes an explicit
`as_of_date` and treats `PortfolioData` as read-only.

## Engines

### Health Score Engine (`src/health_engine.py`)
`calculate_project_health(project_id, portfolio, as_of_date) -> HealthResult`

```
Health = 0.25 Schedule Performance
       + 0.20 Milestone Readiness
       + 0.15 Task Execution
       + 0.15 Risk Exposure
       + 0.10 Dependency Status
       + 0.10 Resource Capacity
       + 0.05 Action Closure
```
Bands: Green >= 80, Amber 60-79.99, Red < 60. Full factor rules and fallbacks are in
[scoring-methodology.md](scoring-methodology.md).

### Data Confidence Score Engine (`src/confidence_engine.py`)
`calculate_project_confidence(project_id, portfolio, as_of_date) -> ConfidenceResult`
and `calculate_portfolio_confidence(portfolio, as_of_date) -> list[ConfidenceResult]`

```
Confidence = 0.40 Data Freshness
           + 0.30 Data Completeness
           + 0.20 Ownership Coverage
           + 0.10 Source Reliability
```
Bands: High >= 80, Medium 60-79.99, Low < 60. Factor 4 is a "Prototype data-source availability
assessment", not real integration monitoring.

### Risk Early-Warning Engine (`src/risk_engine.py`)
`generate_early_warnings(project_id, portfolio, as_of_date) -> list[EarlyWarningAlert]`
and `generate_portfolio_early_warnings(portfolio, as_of_date) -> list[EarlyWarningAlert]`

Eight deterministic, evidence-cited rules:
1. Unowned high-exposure risk (exposure >= 20, no mitigation owner).
2. Critical/High milestone forecast slip.
3. Delayed dependency affecting a High/Critical milestone.
4. Blocked task on a High/Critical milestone.
5. Overdue High/Critical action.
6. Resource over-allocation (> 100/110/125% utilisation).
7. Stale project status (> 14 days, or missing).
8. High/Critical requirement lacking verification evidence (via the existing `verified_by` trace
   link only; not a full traceability engine).

## Integration test results (real data, as of 2026-08-25)

Run against the real synthetic CSVs for P-002 and P-007 via the production loader with
`as_of_date = date(2026, 8, 25)`:

| Project | Health | Health band | Confidence | Confidence band | Alerts (Critical/High/Medium) |
|---------|--------|-------------|------------|-----------------|-------------------------------|
| P-002 | 50.7 | Red | 82.0 | High | 7 (5 / 2 / 0) |
| P-007 | 51.95 | Red | 68.0 | Medium | 9 (4 / 4 / 1) |

Both projects are Red on Health, but their Confidence differs (High vs Medium), which demonstrates
that Health and Confidence are derived independently. P-002's known supplier delayed-dependency
alert and P-007's stale-status and missing-verification alerts each appear only in their own
project.

The integration suite (`tests/test_phase3_integration.py`) verifies: successful real-data load;
all three engines return fully populated results for both projects; project-scoped `source_ids`
that reference only real records of that project; known adverse signals appearing in the correct
project only; distinct, non-perfect outcomes; Health/Confidence independence; no mutation across a
full multi-engine run; Critical alerts never coinciding with a Green Health band; byte-identical
results on repeated execution; portfolio-level functions matching project-level results; and a
consistent `DataValidationError` for an unknown project across all three engines.

## What this proves
For a technical reviewer, Phase 3 establishes that the three engines are:
- **Independently correct** — each has its own unit suite and a real-data regression snapshot.
- **Mutually consistent** — Critical alerts align directionally with adverse Health, and scope
  never crosses between projects.
- **Project-scoped** — every emitted `source_id` belongs to the project being scored.
- **Side-effect-free** — a full multi-engine run leaves `PortfolioData` field-for-field unchanged.
- **Fully deterministic** — identical inputs and `as_of_date` always produce identical scores,
  bands and alert lists (including alert IDs and ordering).

## Scope of this document
This summary covers the **Phase 3 deterministic core only** (Health, Confidence, Risk and their
integration tests), as it stood at the end of Phase 3. Capabilities delivered in later phases are
documented separately: Change Impact
([change-impact-methodology.md](change-impact-methodology.md)), Scenario simulation
([scenario-methodology.md](scenario-methodology.md)), the six Streamlit pages, and the GPT-4o
explanation layer ([ai-governance.md](ai-governance.md)). See [roadmap.md](roadmap.md) for the
authoritative list of what is implemented.

Still not implemented in Version 1: a full multi-hop requirements-traceability graph, a
milestone-to-milestone dependency simulation, an AI approval log, and any deployment.
