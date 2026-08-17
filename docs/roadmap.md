# Roadmap & Implementation Plan

This is the delivery plan and forward-looking roadmap. The sections on Version 1 describe the
original Streamlit prototype, which remains runnable. The current product is **EPOS Next**.

## EPOS Next (implemented)

- FastAPI service over SQLModel with Alembic migrations (SQLite locally, PostgreSQL hosted),
  authentication, role-based and project-scoped authorisation, and an append-only audit trail.
- React interface built with Vite and tested with Vitest and Testing Library.
- Delivery workflows: account-based task and action assignment, progress and completion notes,
  optional manager review of completed work (reported and accepted completion kept separate),
  and an in-app notification inbox.
- Requirements, trace links and test results maintained in the interface with evidence rules.
- Ask EPOS with deterministic routing, validated model classification, structured and shown-back
  project filters, grounded explanations and conversation memory.
- Server-side sessions in HttpOnly cookies with CSRF protection, per-session sign-out,
  invitation-based onboarding and request limits shared across instances.

Still future work: a backend CI job, email delivery (verification,
reset and notification digests), multi-factor sign-in, directory integration, attachments, and
enterprise connectors.

## Version 1 complete (implemented and tested)

### Deterministic engines (`src/`)
| Engine | Status | What it does |
|--------|--------|--------------|
| `health_engine.py` | Complete | 0-100 Project Health from seven weighted factors, with per-factor explanations, structured critical drivers and evidence IDs. |
| `confidence_engine.py` | Complete | 0-100 Data Confidence from four weighted factors, with structured data-quality issues. |
| `risk_engine.py` | Complete | Eight deterministic early-warning alert rules, deduplicated and stably ordered. |
| `change_impact_engine.py` | Complete | Change request to requirement to tasks/tests/milestones traversal, plus a coarse schedule estimate and risk level. |
| `scenario_engine.py` | Complete | Non-mutating single-dependency delay simulation that re-runs the three engines for comparison. |
| `ai_assistant.py` | Complete | Evidence-package construction for seven supported questions, Azure Chat Completions request/response handling with strict schema validation and source-ID grounding. |

Supporting modules: `config.py`, `schemas.py`, `scoring_rules.py`, `data_loader.py`,
`validators.py`, `utils.py`, `ui_formatting.py` (presentation helpers only).

**Intentionally out of scope for Version 1:** `dependency_engine.py`, `traceability_engine.py` and
`approval_log.py` were scaffolded in Phase 2 but never needed, and have been **removed**. Dependency
traversal is implemented inside the health, risk, change-impact and scenario engines where it is
actually used; single-hop traceability is implemented by Risk Rule 8 and the Requirements
Traceability page; and Ask EPOS presents AI drafts for human review without persisting an approval
decision. Keeping empty modules would have implied unfinished work where the capability was in fact
delivered under a different design.

### Streamlit pages (`pages/`)
| Page | What it shows |
|------|---------------|
| Portfolio Dashboard | Portfolio KPIs, Health vs Confidence table and scatter, ranked exceptions, per-project evidence. |
| Project Intelligence | One project's Health and Confidence evidence panels, alerts and underlying records. |
| Requirements Traceability | Requirement-to-test-case links, trace status, verification-gap alerts, reference tables. |
| Change Impact | Change-request selection, affected artefacts, schedule estimate, risk level, artefact details. |
| Scenario Planner | Dependency delay simulation with baseline versus scenario comparison. |
| Ask EPOS | Source-grounded GPT-4o draft over deterministic evidence, with disclaimer and grounding checks. |

All pages are presentation-only and call `src/` functions; none contains business logic.

## Implementation phases (Version 1)

### Phase 1 - Analyse and scaffold (complete)
- Workspace inspection (without touching `.env`), structure, configuration and documentation.

### Phase 2 - Data foundation (complete)
- Synthetic CSVs for P-002 and P-007.
- `schemas.py` (Pydantic v2), `data_loader.py`, `validators.py`, `config.py`, `utils.py`.
- Tests for valid/invalid CSVs, duplicate IDs, missing columns.

### Phase 3 - Deterministic analytics (complete)
- `health_engine`, `confidence_engine`, `risk_engine`, plus cross-engine integration tests.

### Phase 3B - Impact and simulation engines (complete)
- `change_impact_engine`, `scenario_engine`, each built and tested before any page used them.

### Phase 4 - Streamlit UI (complete)
- `app.py` navigation and all six pages, calling `src/` functions only.

### Phase 5 - GPT-4o integration (complete)
- Safe configuration state handling, evidence-package builder, Azure REST call, strict
  `CopilotResponse` validation, source-ID grounding checks, safe error handling, and an injectable
  transport so tests never contact the API.

### Phase 6 - Quality review (ongoing)
- `pytest`, `ruff`, `black --check` after every step; AI-absent operation verified; data confirmed
  synthetic; `.env` never read.

## Implementation order (dependencies)
`config` -> `schemas` -> `utils` -> `data_loader`/`validators` -> engines -> pages -> AI layer.

## Version 1 traceability scope
The Requirements Traceability page covers the **single requirement-to-test-case relationship**
present in the data model (`trace_links` with `link_type = verified_by`) and surfaces the Risk
engine's existing `requirement_missing_verification` alerts. It is not a traceability graph across
requirement, task, test, milestone and release. This matches the limitation already documented for
Risk Rule 8; fuller multi-hop traceability is future scope.

## Change Impact Engine (Phase 3B, implemented)
`src/change_impact_engine.py` is a deterministic traversal and estimation engine, built and tested
before any Change Impact page exists. It follows change request to requirement to tasks/test
cases/milestones via trace links, then dependencies referencing affected tasks, and produces a
coarse heuristic schedule estimate and risk level. It uses no AI. The data model has no distinct
release entity; release gates are milestones. See
[change-impact-methodology.md](change-impact-methodology.md).

## Scenario Engine (Phase 3B, implemented)
`src/scenario_engine.py` simulates a single dependency delay on an independent deep copy of the
portfolio and re-runs the existing Health, Confidence and Risk engines for comparison. Baseline
data is never modified and no engine logic is duplicated. Version 1 covers one dependency at a
time; multi-dependency, task-delay and resource-overallocation scenarios are future scope. See
[scenario-methodology.md](scenario-methodology.md).

## Version 2 — future scope (not implemented)
- **A configurable analysis reference date with appropriate cache invalidation.** Version 1 fixes
  the reference date at 2026-08-25 and displays it on every page. Making it user-selectable is a
  deliberate future enhancement rather than an oversight: it requires deciding how a date change
  invalidates the Streamlit result caches, how it interacts with session state across pages, and
  how far the fixed synthetic dataset stays meaningful as the date moves.
- **A portfolio fingerprint in the page cache keys.** The cached page helpers currently key on the
  reference date (plus the selected id where relevant) and do not hash portfolio contents. That is
  safe while exactly one dataset exists per process, but a reload control, support for multiple
  datasets, or any multi-user deployment would first require adding a cheap portfolio fingerprint
  to the cache key so two portfolios cannot share an entry. See
  [architecture.md](architecture.md#caching-and-performance).
- Optional Jira CSV/API import and other structured connectors.
- Swap CSV loader for SQLite/PostgreSQL behind the existing repository interface.
- Companion Power BI dashboard fed by the same validated data.
- Meeting-action extraction from structured notes.
- Full multi-hop requirements traceability (requirement to task to test to milestone to release).

## Version 3 — original prototype direction
- FastAPI service layer and authentication: delivered in EPOS Next.
- Richer resource/capacity model.
- Proper enterprise connectors and a deployment architecture.

> The Version 2/3 lists record the prototype's original direction. Items delivered since are marked
> above; the Streamlit prototype itself remains local-only and synthetic.
