# ats-fastapi — ATS scoring engine

Scores a CV (PDF/DOCX) against a job description using a local **Ollama** model and posts the
result back to the .NET orchestrator through an HMAC-signed webhook. Spec: `../.claude/specs/ats-fastapi/`.

## Setup

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

SQLite needs no separate install — the engine ships inside Python's `sqlite3` module and the
database file + schema are created on first start. Check with:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; print(sqlite3.sqlite_version)"
```

## Configuration

Settings come from environment variables (or a `.env` file) with the `APP_` prefix and `__` for nesting.
Only the webhook secret is required; see `.env.example` for every setting and its default.

```powershell
$env:APP_WEBHOOK__SECRET = "<same secret as the orchestrator's Webhook:Secret>"
```

## Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

Startup fails fast with a clear error if configuration is missing or inconsistent (e.g. no webhook
secret, or `num_ctx` too small for the input caps).

- `POST /analyze` — dispatch intake (returns `202`, work runs in the background)
- `GET /health` — liveness
- `GET /ready` — readiness (Ollama + model + storage)

Ollama must be running with the model pulled: `ollama pull qwen2.5:3b`.

The default timings are for a CPU-only host (measured: ~25 tok/s prompt, ~6.5 tok/s output; a 2-page
CV scores in about 100s). With a GPU, lower `APP_LLM__TIMEOUT_SECONDS` and raise
`APP_LLM__MAX_CONCURRENCY` / `APP_LLM__MAX_IN_FLIGHT`.

**Orchestrator note:** `resumeFileReference` must be an absolute path. If the orchestrator still sends
a relative key, set `APP_STORAGE__BASE_ROOT` to its storage folder.

## How an analysis flows

One dispatch travels through these modules. The orchestrator gets its `202` at step 1; everything
below it runs in the background and the result comes back over the signed webhook.

```
POST /analyze          api/routes_analyze.py        authenticate, admit, record, schedule, return 202
  background run       pipeline/run.py              run_analysis, under the analysis time budget
    read CV            ports/file_store.py          adapters/local_path_file_store.py
    extract text       pipeline/extract.py          PDF or DOCX -> plain text
    prepare input      pipeline/prepare.py          normalise, neutralise, truncate to the budget
    build prompt       pipeline/prompt.py           versioned template + the prepared inputs
    call model         ports/llm_client.py          adapters/ollama_llm_client.py (one reformat retry)
    parse result       pipeline/parse.py            JSON -> validated AnalysisResult, render report
  deliver callback     pipeline/deliver.py          HMAC-signed webhook, retried with back-off
```

Each analysis ends with exactly one terminal callback — `Completed` or `Failed` — except on
shutdown, where scoring is cancelled and the orchestrator's sweeper fails it. The analysis id is
attached to every log line through the logging context in `observability.py`.

### Failure reasons

When a stage fails, the `Failed` callback carries a safe reason code. They are defined in one place,
`pipeline/errors.py`:

| Exception | Reason code | Raised by |
|---|---|---|
| `FileRetrievalError` | `file_not_found` | read CV (`file_store`) |
| `ExtractionEmptyError` | `extraction_empty` | extract text (`extract`) |
| `ExtractionError` | `extraction_failed` | extract text (`extract`) |
| `InputTooLargeError` | `input_too_large` | prepare input (`prepare`) |
| `LlmUnavailableError` | `llm_unreachable` | call model (`ollama_llm_client`) |
| `LlmTimeoutError` | `llm_timeout` | call model, or the overall analysis budget |
| `ResultParseError` | `result_unparseable` | parse result (`parse`), after one reformat retry |
| `AnalysisError` (base) | `unexpected_error` | any unmapped failure |

## Test

```powershell
.\.venv\Scripts\python.exe -m pytest                       # unit suite (no Ollama/network needed)
.\.venv\Scripts\python.exe -m pytest --cov --cov-report=term
```

## Notebook

`notebooks/pipeline_stages.ipynb` runs each pipeline stage on its own with the sample assets in
`tests/assets/`. Install `.[notebook]` to get Jupyter.

## Developer test harness (Streamlit)

An optional web UI for exercising the engine by hand and seeing the **raw LLM response** next to the
parsed result. It drives a gated, synchronous `/debug/*` router that runs each pipeline stage
in-process (no callback, no HMAC, no background task). Spec: `../.claude/specs/ats-debug-ui/`.

The debug router is **off by default** and **unauthenticated** — enable it only on a dev machine.

```powershell
# 1. enable it on the service (in .env), then run the service
#    APP_DEBUG__ENABLED=true
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000

# 2. install the UI deps and run it in a second terminal
.\.venv\Scripts\python.exe -m pip install -e ".[debug-ui]"
.\.venv\Scripts\python.exe -m streamlit run debug_ui/streamlit_app.py
```

Endpoints added only when enabled: `GET /debug/ping`, `POST /debug/{extract,prepare,prompt,parse,llm,score}`.
See `debug_ui/README.md` for details.
