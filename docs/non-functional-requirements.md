# Non-Functional Requirements — Version 1

## Security & privacy
- **NFR-01** Synthetic data only. No real employer, customer, employee or system data.
- **NFR-02** Secrets live only in a local, git-ignored `.env`. No API key appears in code, docs,
  tests, logs, screenshots or output.
- **NFR-03** The application never reads or displays the contents of `.env`; it reads only the
  named variables `API_KEY` and `ENDPOINT` via environment lookup.
- **NFR-04** Only a selected, validated evidence package is sent to the AI endpoint — never the
  whole dataset.

## Reliability & graceful degradation
- **NFR-10** If Azure OpenAI configuration is missing or a call fails, the app shows a safe
  message and all deterministic features keep working.
- **NFR-11** Malformed AI responses never crash the app; they are handled and reported safely.
- **NFR-12** Missing or incomplete data is handled explicitly, never with silent failures.

## Explainability
- **NFR-20** Every Health/Confidence/alert/change conclusion exposes its formula inputs and
  source record IDs.
- **NFR-21** All AI output is labelled `AI-generated decision-support draft; human review required.`

## Testability
- **NFR-30** Every deterministic module is independently unit-tested.
- **NFR-31** Tests make no network/API calls and run without the Azure API key.
- **NFR-32** Score weights and thresholds are centralised so tests assert against documented values.

## Maintainability
- **NFR-40** Business logic is isolated in `src/`; UI files contain no business logic.
- **NFR-41** The data-access layer is abstracted so CSV can later be replaced by SQLite/PostgreSQL.
- **NFR-42** Type hints and Pydantic models are used throughout; functions are small and documented.

## Local-only operation
- **NFR-50** Version 1 runs entirely locally via Streamlit. No Git, Docker, cloud, auth or deployment.
- **NFR-51** No production-grade claims are made for this prototype.
