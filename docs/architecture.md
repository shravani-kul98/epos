# Architecture

EPOS Lite is an **integration / intelligence prototype**, not a replacement for any enterprise
system. It consolidates selected structured signals into one explainable management view.

## Layered design

```
+-------------------------------------------------------------+
|  Presentation (Streamlit)                                   |
|  app.py + pages/*.py  — UI only, no business logic          |
+----------------------------┬--------------------------------+
                             | imports & calls
+----------------------------▼--------------------------------+
|  Deterministic domain layer (src/)                          |
|  health_engine, confidence_engine, risk_engine,             |
|  change_impact_engine, scenario_engine                      |
|  -> calculate ALL facts, scores and impacts                 |
+----------------------------┬--------------------------------+
                             | typed models
+--------------------┬-------┴---------┬-----------------------+
|  Data access       |   Validation   |  Config                |
|  data_loader.py    |   validators.py|  config.py (weights,    |
|  (CSV now, DB later)|  schemas.py   |  thresholds, env)       |
+--------------------┴----------------┴-----------------------+
                             |
+----------------------------▼--------------------------------+
|  AI explanation layer (src/ai_assistant.py)                 |
|  GPT-4o EXPLAINS validated evidence only. No calculation.   |
|  Strict CopilotResponse validation + source-ID grounding    |
+-------------------------------------------------------------+
```

## Core principle
**Deterministic Python calculates facts. GPT-4o explains facts. Humans approve.**

The AI layer is strictly downstream of the deterministic layer. It receives a small,
validated evidence package and returns an explanation. It never calculates scores, forecasts
dates, invents IDs/risks/owners, or modifies data.

## Data flow
1. `data_loader` reads CSVs from `data/` and parses each row into a Pydantic model.
2. `validators` checks columns, duplicate IDs and referential integrity.
3. Deterministic engines compute Health, Confidence, alerts, traceability and change impact.
4. Pages render typed results and expose evidence (source IDs) for every conclusion.
5. On demand, `ai_assistant` builds an evidence package, calls Azure OpenAI, validates the
   response into `CopilotResponse`, and shows it as a human-review draft.

## Components (`src/`)
| Module | Responsibility |
|--------|----------------|
| `config.py` | Env loading (`API_KEY`/`ENDPOINT`), score weights, thresholds, paths. |
| `schemas.py` | Pydantic v2 entity and result models. |
| `data_loader.py` | Load CSVs into typed models via a repository abstraction. |
| `validators.py` | Column/ID/referential-integrity validation. |
| `utils.py` | Dates, working-day maths, safe division, banding. |
| `health_engine.py` | Deterministic 0–100 Health score + explanations. |
| `confidence_engine.py` | Deterministic 0–100 Confidence score + issues. |
| `risk_engine.py` | Rule-based early-warning alerts. |
| `dependency_engine.py` | Intentionally out of scope for Version 1 and removed. Dependency traversal is implemented inside the health, risk, change-impact and scenario engines, where it is actually used. |
| `traceability_engine.py` | Intentionally out of scope for Version 1 and removed. Single-hop requirement-to-test traceability is implemented by Risk Rule 8 and the Requirements Traceability page. |
| `change_impact_engine.py` | Change-request impact analysis. Implemented: traverses change request to requirement to tasks/tests/milestones via trace links, then dependencies referencing affected tasks. Produces a `ChangeImpactResult` with a coarse schedule estimate and risk level. See [change-impact-methodology.md](change-impact-methodology.md). |
| `scenario_engine.py` | Non-mutating what-if simulation. Implemented: deep-copies the portfolio, delays one dependency, and re-runs Health/Confidence/Risk for comparison. See [scenario-methodology.md](scenario-methodology.md). |
| `ai_assistant.py` | Implemented: evidence packaging for seven supported questions, Azure Chat Completions request/response handling with a strict JSON schema, injectable transport, and source-ID grounding checks. See [ai-governance.md](ai-governance.md). |
| `approval_log.py` | Intentionally out of scope for Version 1 and removed. Ask EPOS presents AI drafts for human review but does not persist an approval decision; a persisted approval log is Version 2 scope. |

## Future-proofing
The data-access layer returns typed models behind a repository interface, so a future
SQLite/PostgreSQL implementation can replace CSV loading without changing the engines.

## UI layer (Streamlit)
- Streamlit pages are **presentation-only**: layout, widgets, charts, formatting, and calls into
  `src/` functions. All business logic (scoring, banding, alert rules, aggregation of facts) stays
  in `src/`. Pages never recalculate anything an engine already computes.
- `app.py` is the shell: it loads the portfolio once per session (cached) into session state and
  defines navigation with `st.navigation` / `st.Page`. UI-only formatting and presentation tallies
  live in `src/ui_formatting.py`, which imports no engine and contains no scoring/alert logic.
- **Current pages:** Portfolio Dashboard (`pages/1_Portfolio_Dashboard.py`) and Project
  Intelligence (`pages/2_Project_Intelligence.py`). Requirements Traceability, Change Impact,
  Scenario Planner and Ask EPOS are added to the same navigation list in later steps. Pages reuse
  the shared "evidence-panel" convention documented in the UI design guide.
- **Version 1 limitation (not a defect):** the analysis reference date is fixed at
  `date(2026, 8, 25)` and shown in the UI, matching the Phase 3 tests. A user-selectable date is a
  documented future enhancement.

## Caching and performance
The shell caches the portfolio load, and the Portfolio Dashboard, Project Intelligence and Change
Impact pages cache their engine results with `@st.cache_data`. Measured across one shell render
plus six page renders on the two-project portfolio: `load_portfolio` runs **once**,
`calculate_project_health` and `calculate_project_confidence` five times each, and
`generate_early_warnings` six times. Revisiting a page or moving a widget triggers **no**
recomputation. These counts are locked in by `tests/test_caching.py`.

**Known constraint: cache keys do not hash portfolio contents.** The cached helpers take the
portfolio as an underscore-prefixed argument, so Streamlit does not hash it. The effective keys are
`as_of` for the dashboard, and `as_of` plus the selected id for the other two. Because Version 1
loads exactly one dataset per process and uses a fixed reference date, this is safe today: the key
always maps to the one and only portfolio. It would need a **portfolio fingerprint added to the
cache key** before supporting a reload control, more than one dataset, or a multi-user deployment,
since two portfolios sharing a reference date would otherwise share a cache entry. This is recorded
as a named Version 2 requirement in [roadmap.md](roadmap.md).
