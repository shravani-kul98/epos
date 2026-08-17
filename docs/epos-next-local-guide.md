# EPOS — Running Locally

Everything here runs on one machine with no cloud services and no container runtime.

## Prerequisites
- Python 3.11 or newer
- Node.js 20 with npm 10, only to rebuild or test the interface; `frontend/dist` already holds a
  compiled build

## First run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m api.seed
```

On macOS or Linux, activate the environment with `source .venv/bin/activate` instead.

`python -m api.seed` creates `data/epos_next.db`, loads the starter workspace, and creates one
account per role. It prints a generated password **once**. There is no default password anywhere in
this repository, so nothing usable is committed.

Re-running the seed is safe: existing data and accounts are left alone.

## Start the service

```powershell
python -m uvicorn api.main:app --reload --port 8000
```

- Application: `http://127.0.0.1:8000`, served from `frontend/dist`
- API root: `http://127.0.0.1:8000/api/v1`
- Interactive documentation: `http://127.0.0.1:8000/docs`
- Readiness: `http://127.0.0.1:8000/api/v1/health`

## Signing in

```powershell
$body = @{ email = "pm@epos.example.com"; password = "<the seeded password>" } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/auth/login" `
    -ContentType "application/json" -Body $body).access_token

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/analytics/portfolio" `
    -Headers @{ Authorization = "Bearer $token" }
```

Every endpoint except `/auth/register`, `/auth/login` and `/health` needs that bearer token.

## Configuration

| Variable | Purpose | If absent |
| --- | --- | --- |
| `EPOS_SECRET_KEY` | Signs access tokens | A random key is generated per process, so tokens stop working when the service restarts. Set it for anything beyond local experimentation. |
| `EPOS_DATABASE_URL` | Overrides the SQLite location | Defaults to `data/epos_next.db` |
| `API_KEY`, `ENDPOINT` | Azure OpenAI, for Ask EPOS | Ask EPOS reports itself unavailable; every other feature works normally |

Set these in `.env`. That file is never read or printed by any tooling in this repository.

## Tests

```powershell
python -m pytest -q
python -m ruff check .
python -m black --check .
```

No test makes a network call or needs an API key. Each test creates its own in-memory database, so
the suite never touches `data/epos_next.db`.

## The legacy interface

The original Streamlit application still runs and is unchanged:

```powershell
python -m streamlit run app.py
```

It reads the CSV files directly rather than the database. It is kept as a reference until the new
interface is complete.

## The frontend

The React interface lives in `frontend/`. It needs Node.js 20 (`>=20.11.0 <21`, from the `engines`
field in `frontend/package.json`) and npm 10. A compiled build is already in `frontend/dist`.

```powershell
cd frontend
npm ci              # exact versions from package-lock.json
npm run typecheck   # strict TypeScript
npm run lint        # ESLint
npm run test:ci     # Vitest, one run, JUnit and HTML reports in frontend/test-results
npm run build       # type check, then the Vite production build into frontend/dist
```

The API serves `frontend/dist` itself, so after a build and an API restart the whole product runs
from `http://127.0.0.1:8000` on one origin. Sign-in uses same-origin session cookies, so the Vite
development server (`npm run dev`, port 5173) is a different origin and cannot keep a session.

## Preparing to deploy

Not done yet, and not safe to do yet. Before this could be hosted anywhere:

1. Set `EPOS_SECRET_KEY` from a secret store, never from a file in the repository.
2. Move from SQLite to PostgreSQL. The data access layer is written against SQLModel, so this is a
   connection-string and migration change rather than a rewrite.
3. Add schema migrations. Tables are currently created directly from the models.
4. Serve over HTTPS and narrow `ALLOWED_ORIGINS` in `api/main.py` to the real front-end origin.
5. Add refresh-token rotation and a revocation list. Tokens are currently valid until they expire.
6. Add rate limiting on `/auth/login` and `/auth/register`.
7. Replace the seeded accounts entirely.
