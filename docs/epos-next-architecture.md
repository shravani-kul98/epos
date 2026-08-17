# EPOS Next — Architecture

EPOS Next is the product interface for the EPOS engineering portfolio intelligence platform. It
replaces the Streamlit prototype's presentation layer with a React front end and a FastAPI service
layer, while **reusing the existing deterministic engines unchanged** as the source of truth.

## Guiding principles
1. **The deterministic engines remain authoritative.** No score, band, alert, impact or scenario is
   ever recalculated in the API layer or the browser. Services adapt data into engine inputs and
   translate engine outputs into product language.
2. **Product language, not developer language.** Internal factor keys such as `task_execution` are
   never sent to or rendered by the UI. The API emits display labels.
3. **The AI explains; it never acts.** The model cannot write to the database, run SQL, calculate
   scores, or cite anything absent from the evidence package.
4. **The legacy prototype stays runnable.** The Streamlit app and the deterministic engine tests
   behind it are untouched.

## Layers

```
Browser (React + TypeScript)
   |  JSON over HTTP, no secrets
   v
FastAPI service layer  (api/)
   |- routers/    request handling, validation, status codes
   |- services/   adapters: database records -> engine inputs -> product language
   |- models.py   SQLModel tables (SQLite persistence)
   v
Deterministic engines (src/)  -- unchanged, still covered by the existing suite
   health | confidence | risk | change impact | scenario | ai_assistant
   v
Azure OpenAI (backend only; the key never leaves the server process)
```

## Why a service layer rather than calling engines from routers
The engines consume `PortfolioData`, a typed container built by the CSV loader. The database is now
the system of record, so `api/services/portfolio_service.py` builds an equivalent `PortfolioData`
from SQLModel rows. This keeps a single adapter seam: the engines never learn that a database
exists, and the existing engine tests remain valid.

## Data flow for a scored request
1. Router receives `GET /api/v1/projects/{id}/dashboard`.
2. `portfolio_service` reads the database and materialises a `PortfolioData`.
3. `analytics_service` calls `calculate_project_health`, `calculate_project_confidence` and
   `generate_early_warnings` exactly as the Streamlit pages do.
4. `analytics_service` maps factor keys to display labels and attaches plain-language descriptions.
5. The router returns a typed response model. No engine internals cross the boundary.

## Free-text copilot routing
Ask EPOS accepts arbitrary text. The backend never hands raw text to a database.

```
free text
   -> read-only and secret-seeking refusal guard
   -> local subject-by-operation matcher
   -> Azure semantic classifier for unmatched, modified, mixed, or conversational input
   -> approved intent(s) + validated selectors (project, change request, domain, record, scenario)
   -> deterministic record lookup or deterministic evidence builder
   -> Azure evidence explanation, or selected documentation explanation
  -> source-id validation against the evidence actually sent
  -> response + evidence drawer
```

The semantic call may classify and extract selectors but may not answer or calculate. Explicit IDs
win over model output, and every model-selected project, change request, and domain is checked
against the loaded portfolio. If Azure is unavailable or malformed, the local matcher remains the
fallback. Unrecognised or ambiguous input returns `clarification` with suggested prompts.

For mixed questions, the classifier may choose one secondary intent. Each intent is answered
independently through its normal evidence path and the application combines the two validated
responses. The model is never asked to merge or calculate across evidence packages.

Long-tail record questions select one typed collection from the validated portfolio, apply project,
domain, and stored-status filters in Python, and add a deterministic matched-count record. At most
40 records reach the explanation call. Scenario questions may extract only a stored dependency and
a delay inside the configured bounds; RBAC is checked before the existing deterministic,
non-mutating scenario engine runs.

Conversation follow-ups receive at most six ownership-checked history entries. User questions,
prior matched intents, and validated source IDs are included; model-authored assistant prose is not
reused as factual context.

**The model can never:** write to SQLite, mutate any record, execute SQL, calculate a score, or
return a source ID absent from the evidence package. Unknown IDs and selectors are removed before
use.

## Persistence
SQLite via SQLModel. `api/seed.py` imports the existing synthetic CSVs as seed data, so the demo
portfolio is identical to the one the engines were tested against. Seeding is idempotent.

Alembic owns schema evolution. Mutable governed records use optimistic row versions and soft
deletion, while every write appends a structured `ActivityEvent`. Gate Reviews are immutable human
decisions: database triggers reject updates and deletes, and a new review cycle preserves prior
outcomes rather than rewriting them.

Gate readiness is calculated only in `src/gate_rules.py`. Routers adapt persisted criteria and
reviews into engine inputs; React renders the returned readiness, blockers, warnings, evidence
references, timestamp, methodology version, and applicable baseline. See
[Gate readiness](gate-readiness-methodology.md).

## Security posture (local prototype)
- Bearer authentication, permission-based roles, and persisted project membership protect API
   reads and writes. Project-scoped records fail closed as not found outside the caller's scope.
- CORS restricted to the local Vite dev origin.
- The Azure key is read only by the backend, from the environment, and is never serialised into any
  response.
- The AI layer is read-only by construction.

## What is deliberately not built
No multi-tenancy, cloud deployment, real enterprise-system connectors, full traceability graph, or
transitive change propagation. Gate readiness does not yet consume risk, action, change,
traceability, milestone, or dependency adapters. These boundaries remain future scope in
[roadmap.md](roadmap.md).
