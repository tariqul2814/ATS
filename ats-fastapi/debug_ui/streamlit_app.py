"""Streamlit test harness for the ATS scoring engine (ats-debug-ui spec).

A pure HTTP client over the service's /debug endpoints — it imports NOTHING from app/. Point it at a
running scoring engine that has APP_DEBUG__ENABLED=true and use it to see the pipeline's output,
above all the raw LLM response, side by side with the parsed result.

Run:  streamlit run debug_ui/streamlit_app.py
"""

import json

import httpx
import streamlit as st

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_PREFIX = "/debug"
# A CPU-only Ollama run can take several minutes; give LLM-bound calls plenty of room.
LLM_TIMEOUT = 600.0
QUICK_TIMEOUT = 15.0

st.set_page_config(page_title="ATS scoring engine — test harness", page_icon="🧪", layout="wide")


# --- HTTP helpers ---------------------------------------------------------------------------


def _base() -> str:
    return st.session_state.get("base_url", DEFAULT_BASE_URL).rstrip("/")


def _prefix() -> str:
    return st.session_state.get("prefix", DEFAULT_PREFIX).rstrip("/")


def _url(path: str) -> str:
    return f"{_base()}{_prefix()}{path}"


def call(method: str, path: str, *, timeout: float = QUICK_TIMEOUT, prefixed: bool = True, **kwargs):
    """Return (ok, payload). payload is parsed JSON on success, else an error-shaped dict."""
    url = _url(path) if prefixed else f"{_base()}{path}"
    try:
        response = httpx.request(method, url, timeout=timeout, **kwargs)
    except httpx.HTTPError as exc:
        return False, {"reason": "connection_error", "detail": f"{type(exc).__name__}: {exc}"}
    try:
        payload = response.json()
    except json.JSONDecodeError:
        payload = {"reason": "non_json_response", "detail": response.text[:500]}
    ok = response.is_success and payload.get("ok", True)
    return ok, payload


def show_error(payload: dict) -> None:
    st.error(f"**{payload.get('reason', 'error')}** — {payload.get('detail', 'request failed')}")
    if payload.get("partial"):
        with st.expander("Partial output captured before the failure"):
            st.json(payload["partial"])


# --- sidebar: connection + health -----------------------------------------------------------


with st.sidebar:
    st.header("Connection")
    st.session_state.base_url = st.text_input("Service base URL", value=st.session_state.get("base_url", DEFAULT_BASE_URL))
    st.session_state.prefix = st.text_input("Debug prefix", value=st.session_state.get("prefix", DEFAULT_PREFIX))

    st.header("Status")
    if st.button("Refresh status", use_container_width=True):
        st.session_state.pop("status", None)

    # Re-fetch if absent or if a stale session holds an older-shaped tuple (len changed across versions).
    if "status" not in st.session_state or len(st.session_state.status) != 8:
        live_ok, live = call("GET", "/health", prefixed=False)
        ready_ok, ready = call("GET", "/ready", prefixed=False)
        debug_ok, debug = call("GET", "/ping")
        tpl_ok, tpl = call("GET", "/template")
        st.session_state.status = (live_ok, live, ready_ok, ready, debug_ok, debug, tpl_ok, tpl)
    live_ok, live, ready_ok, ready, debug_ok, debug, tpl_ok, tpl = st.session_state.status

    st.write("Service:", "🟢 up" if live_ok else "🔴 down")
    st.write("Debug API:", "🟢 enabled" if debug_ok else "🔴 off / unreachable")
    if ready_ok or isinstance(ready, dict):
        st.write("Ollama:", "🟢 up" if ready.get("ollama") == "up" else "🔴 down")
        st.write("Model:", f"`{ready.get('model', '?')}`")
        st.write("Storage:", "🟢" if ready.get("storage") == "accessible" else "🔴")
    # The prompt template the service actually loaded at startup (unfilled, placeholders intact).
    if tpl_ok:
        st.write("Prompt:", f"`{tpl['name']}`")
        with st.expander("Active prompt template"):
            st.caption("System")
            st.code(tpl["system"])
            st.caption("User (placeholders unfilled)")
            st.code(tpl["user"])
    else:
        st.write("Prompt:", "unavailable")
    if not debug_ok:
        st.warning("Enable APP_DEBUG__ENABLED=true on the service and restart it.")


st.title("ATS scoring engine — test harness")


# --- rendering the parsed result ------------------------------------------------------------


def render_result(result: dict) -> None:
    c1, c2 = st.columns(2)
    c1.metric("Score", f"{result['score']}/100")
    c2.metric("Band", result["band"])

    st.subheader("Breakdown")
    st.table(
        [
            {"Category": b["category"].replace("_", " "), "Score": f"{b['score']}/{b['max']}", "Reason": b["reason"]}
            for b in result["breakdown"]
        ]
    )

    cols = st.columns(2)
    with cols[0]:
        if result["matchedKeywords"]:
            st.subheader("Matched keywords")
            st.write(", ".join(result["matchedKeywords"]))
        if result["strengths"]:
            st.subheader("Strengths")
            for s in result["strengths"]:
                st.markdown(f"- {s}")
    with cols[1]:
        if result["missingKeywords"]:
            st.subheader("Missing keywords")
            for kw in result["missingKeywords"]:
                hint = "skill gap" if kw["skillGap"] else f"add to: {kw['whereToAdd']}"
                st.markdown(f"- **{kw['keyword']}** ({kw['requirement']}) — {hint}")
        if result["formattingIssues"]:
            st.subheader("Formatting issues")
            for i in result["formattingIssues"]:
                st.markdown(f"- {i}")

    if result["topImprovements"]:
        st.subheader("Top improvements")
        for n, imp in enumerate(result["topImprovements"], 1):
            with st.expander(f"{n}. {imp['section']} — {imp['problem']}"):
                st.markdown(f"**Original:** {imp['original']}")
                st.markdown(f"**Suggested:** {imp['suggested']}")

    with st.expander("Rendered report (reportMarkdown)"):
        st.markdown(result["reportMarkdown"])


# --- the primary view: score a CV -----------------------------------------------------------


st.subheader("🎯 Score a CV")
st.caption("Runs the whole pipeline synchronously and shows the raw model reply next to the parsed result.")
upload = st.file_uploader("CV file (PDF or DOCX)", type=["pdf", "docx"], key="score_file")
reference = st.text_input("…or an absolute file reference the service can read", key="score_ref")
jd = st.text_area("Job description", height=180, key="score_jd")

if st.button("Score", type="primary", disabled=not jd or not (upload or reference)):
    with st.spinner("Scoring — the LLM call can take minutes on CPU…"):
        if upload is not None:
            ok, payload = call(
                "POST", "/score", timeout=LLM_TIMEOUT,
                files={"file": (upload.name, upload.getvalue())}, data={"job_description": jd},
            )
        else:
            ok, payload = call(
                "POST", "/score", timeout=LLM_TIMEOUT,
                data={"reference": reference, "job_description": jd},
            )
    st.session_state.last_score = (ok, payload)

if "last_score" in st.session_state:
    ok, payload = st.session_state.last_score
    if not ok:
        show_error(payload)
        if payload.get("partial", {}).get("raw"):
            st.subheader("Raw LLM response (unparsed)")
            st.code(payload["partial"]["raw"], language="json")
    else:
        if payload.get("timings"):
            st.caption("Timings (s): " + "  ·  ".join(f"{k} {v}" for k, v in payload["timings"].items()))
        if payload.get("truncated") and (payload["truncated"]["cv"] or payload["truncated"]["jd"]):
            st.warning(f"Input was truncated to the configured budget: {payload['truncated']}")
        left, right = st.columns(2)
        with left:
            st.subheader("Raw LLM response")
            st.code(payload["raw"], language="json")
        with right:
            st.subheader("Parsed result")
            render_result(payload["result"])
        st.download_button(
            "Download last run (JSON)",
            data=json.dumps(payload, indent=2),
            file_name="ats_debug_run.json",
            mime="application/json",
        )
