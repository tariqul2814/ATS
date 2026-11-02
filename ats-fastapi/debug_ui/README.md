# Developer test harness (Streamlit UI)

A small Streamlit app for exercising the scoring engine by hand and reading its output — above all
the **raw LLM response** next to the parsed `AnalysisResult`. It is a pure HTTP client: it talks only
to the service's gated `/debug` endpoints and imports nothing from `app/`.

See `.claude/specs/ats-debug-ui/` for the spec.

## Prerequisites

1. **Enable the debug API on the service.** In the service's `.env`:
   ```
   APP_DEBUG__ENABLED=true
   ```
   This mounts a synchronous, **unauthenticated** `/debug/*` router. Never enable it in a deployment
   reachable by untrusted callers.

2. **Install the harness dependencies** (includes `streamlit` and `python-multipart`, which the
   service process needs for the `/debug` upload endpoints):
   ```powershell
   .\.venv\Scripts\python.exe -m pip install -e ".[debug-ui]"
   ```

## Run

```powershell
# terminal 1 — the service (with APP_DEBUG__ENABLED=true in .env)
.\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000

# terminal 2 — the UI
.\.venv\Scripts\python.exe -m streamlit run debug_ui/streamlit_app.py
```

Then open the Streamlit URL it prints. Set the **Service base URL** in the sidebar if the service is
not at `http://127.0.0.1:8000`. The sidebar status panel shows whether the service, the debug API,
and Ollama (with the configured model) are reachable.

## What each tab does

- **Score a CV** — upload a CV (or give a file reference) + a job description, run the whole pipeline
  synchronously, and see the raw model reply beside the parsed result (score, breakdown, keywords,
  improvements, strengths, rendered report), plus per-stage timings. Download the run as JSON.
- **Extract / Prepare / Prompt / Parse** — run a single stage with no model call.
- **LLM** — send CV + JD to the model and show the raw, unparsed reply (what you are mainly testing).

The LLM and Score calls can take minutes on a CPU-only Ollama; the UI waits with a spinner.
