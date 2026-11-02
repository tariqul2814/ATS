# ATS Resume Checker

An applicant uploads a CV (PDF/DOCX) and a target job description, and the system returns an
**ATS (Applicant Tracking System) compatibility assessment** — an overall score, a band, a
per-category breakdown, and a readable report — produced by a locally hosted LLM.

The system is split into three independently runnable services: an Angular single-page client, a
.NET orchestrator that owns intake and state, and a Python/FastAPI scoring engine that extracts the
CV and scores it with [Ollama](https://ollama.com/).

## Architecture

```
┌──────────────┐   HTTPS    ┌─────────────────────┐  HTTP    ┌──────────────────┐   ┌─────────┐
│  Angular SPA │ ─────────▶ │  .NET Orchestrator  │ ───────▶ │  FastAPI Engine  │ ─▶│ Ollama  │
│ (ats-web-ui) │            │    (ATS_Web_API)    │  202     │  (ats-fastapi)   │   │  (LLM)  │
│              │ ◀───────── │                     │ ◀─────── │                  │   └─────────┘
└──────────────┘  SignalR   └─────────────────────┘  signed  └──────────────────┘
                   (push)         webhook (HMAC)
```

Flow: **Angular → .NET orchestrator → FastAPI → Ollama**, with the result returned to the
orchestrator through an **HMAC-signed webhook** and pushed to the client in real time over **SignalR**.

Key design points:

- **The orchestrator never blocks on the LLM.** It validates and stores the request, returns
  `202 Accepted` with an `analysisId`, and dispatches the scoring work asynchronously.
- **Guarded lifecycle.** An analysis moves `Pending → Dispatched → Completed | Failed`. The webhook
  callback is idempotent, and a background sweeper fails analyses that stall.
- **Configuration-driven.** No hard-coded URLs, paths, secrets, or limits. The .NET side validates
  its options on startup; the FastAPI side uses `APP_`-prefixed settings and fails fast on bad config.

## Repository layout

| Path | What it is | Stack |
|---|---|---|
| `ats-web-ui/` | Single-page client: upload, live status, result report | Angular 20, TypeScript 5.9 |
| `ATS_Web_API/` | Orchestrator: intake, storage, state, webhook, real-time push | .NET 8 minimal API, EF Core, SQL Server, SignalR |
| `ats-fastapi/` | Scoring engine: extracts the CV and scores it with Ollama | Python 3.12, FastAPI, SQLite, Ollama |

The orchestrator is a single project in four layers with dependencies pointing inward only
(`Endpoints → Application → Domain`, and `Infrastructure → Application/Domain`; Domain depends on
nothing).

## How an analysis flows

1. The client submits the CV file + job description to the orchestrator.
2. The orchestrator admits and records the request, returns `202 Accepted` with an `analysisId`, and
   dispatches it to the scoring engine.
3. The engine runs the pipeline in the background: **read CV → extract text → prepare input →
   build prompt → call model → parse & validate result → render report**.
4. The engine posts the outcome back to the orchestrator over an HMAC-signed webhook — exactly one
   terminal result per analysis: `Completed` (score + report) or `Failed` (a safe reason code).
5. The orchestrator pushes the update to the client over SignalR, so the UI reflects it live.

## Prerequisites

- [.NET 8 SDK](https://dotnet.microsoft.com/download)
- [Python 3.12](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/) (LTS) + npm
- [SQL Server](https://www.microsoft.com/sql-server) (or LocalDB) for the orchestrator
- [Ollama](https://ollama.com/) with the scoring model pulled: `ollama pull qwen2.5:3b`

A shared secret links the orchestrator and the engine: the .NET `Webhook:Secret` and the FastAPI
`APP_WEBHOOK__SECRET` **must match**. Keep secrets in .NET user-secrets / a FastAPI `.env` file —
never commit them.

## Getting started

Run each service in its own terminal. Defaults assume the ports below.

### 1. Scoring engine — `ats-fastapi/` (http://127.0.0.1:8000)

```powershell
cd ats-fastapi
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# required: must match the orchestrator's Webhook:Secret (set in .env or the environment)
$env:APP_WEBHOOK__SECRET = "<shared-secret>"

.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

SQLite ships with Python; the database file and schema are created on first start. See
`ats-fastapi/.env.example` for every setting and its default.

### 2. Orchestrator — `ATS_Web_API/` (https://localhost:7120)

```powershell
cd ATS_Web_API
dotnet build
dotnet run --project ATS_Web_API --launch-profile https
```

Configure the SQL Server connection string and `Webhook:Secret` (via user-secrets or
`appsettings`/environment). Options are validated on startup.

### 3. Web client — `ats-web-ui/` (http://localhost:4200)

```powershell
cd ats-web-ui
npm install
npm start
```

`http://localhost:4200` is the backend's allowed CORS origin. Upload limits in the UI environment
files mirror the backend; the backend is authoritative, so change both together.

## Testing

```powershell
# Orchestrator (.NET)        — from ATS_Web_API/
dotnet test

# Scoring engine (FastAPI)   — from ats-fastapi/ (no Ollama or network needed)
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .

# Web client (Angular)       — from ats-web-ui/
npm test
```

## Developer tools (scoring engine)

- **Pipeline notebook** — `ats-fastapi/notebooks/pipeline_stages.ipynb` runs each pipeline stage on
  its own against the sample assets in `tests/assets/`, without starting the FastAPI app. Install
  the `.[notebook]` extra for Jupyter.
- **Streamlit debug harness** — an optional UI that exercises the engine by hand and shows the raw
  LLM response next to the parsed result, via a gated, synchronous `/debug/*` router. The debug
  router is **off by default** and **unauthenticated**, so enable it only on a dev machine
  (`APP_DEBUG__ENABLED=true`). See `ats-fastapi/README.md` for details.

## Vocabulary

- **Analysis** (`ResumeAnalysis`, `analysisId`) — the tracked unit of work: one CV against one job
  description.
- **Job description** — always the target posting text, never a background job.

## Further reading

Each service has its own README with deeper setup, configuration, and operational notes:
[`ats-fastapi/README.md`](ats-fastapi/README.md), plus the project files under `ATS_Web_API/` and
`ats-web-ui/`.
