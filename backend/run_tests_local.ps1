$ErrorActionPreference = "Stop"

Write-Host "Setting up local Python virtual environment..."
if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

Write-Host "Installing ONLY the bare minimum dependencies to run the simulated tests..."
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install fastapi uvicorn pydantic pydantic-settings python-multipart numpy pytest pytest-asyncio httpx firebase-admin

Write-Host "Running tests..."
$env:USE_LOCAL_STORAGE="true"
$env:MODEL_DEVICE="cpu"
$env:DEBUG="true"
$env:LOG_LEVEL="DEBUG"
$env:CORS_ORIGINS="http://localhost:3000,http://localhost:5173"

.venv\Scripts\python.exe -m pytest tests/ -v
