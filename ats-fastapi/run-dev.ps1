# Dev launcher: start the FastAPI scoring engine and the Streamlit debug harness
# together, each in its own window. Dev-only convenience -- not for production.
#
# Usage (from ats-fastapi/):   .\run-dev.ps1
#
# Each service runs in its own PowerShell window so you keep separate logs and can
# Ctrl+C either one without stopping the other. Close a window to stop that service.

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found at $python -- create the venv first."
    exit 1
}

# Mount the /debug/* router the Streamlit harness talks to. Child windows launched
# below inherit this env var. (Debug router is dev-only; never ship it on.)
$env:APP_DEBUG__ENABLED = "true"

$backendCmd  = "& '$python' -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000"
$frontendCmd = "& '$python' -m streamlit run debug_ui/streamlit_app.py"

Write-Host "Starting backend (uvicorn :8000) and Streamlit harness (:8501) in separate windows..."
Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", $backendCmd
Start-Process powershell -WorkingDirectory $root -ArgumentList "-NoExit", "-Command", $frontendCmd
Write-Host "Launched. Give the backend a few seconds; if Streamlit loaded first, click Refresh status."
