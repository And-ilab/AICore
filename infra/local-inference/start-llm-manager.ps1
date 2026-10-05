# Start local LLM manager on :8070 (switches GGUF under OpenAI alias on :8080).
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Manager = Join-Path $PSScriptRoot "llm_manager.py"
$py = Join-Path $Repo "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

Write-Host "Starting LLM manager on http://127.0.0.1:8070 (llama :8080)"
& $py $Manager
