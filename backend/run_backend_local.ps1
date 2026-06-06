$env:USE_LOCAL_STORAGE="true"
$env:MODEL_DEVICE="cpu"
$env:DEBUG="true"
$env:LOG_LEVEL="DEBUG"
$env:CORS_ORIGINS="http://localhost:3000,http://localhost:5173,http://localhost:4173"

Write-Host "Starting FastAPI Backend Server on port 8000..."
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
