# Start local E5 embedding HTTP service on :8090 (CPU).
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$ServiceDir = Join-Path $Repo "backend\services\embedding"
$ModelsDir = Join-Path $Repo "models"
$EmbedCache = Join-Path $ModelsDir "hf-cache"
$py = Join-Path $Repo "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$env:HF_HOME = $EmbedCache
$env:EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
$env:EMBEDDING_DIMENSIONS = "1024"
$env:TRANSFORMERS_CACHE = $EmbedCache
$env:SENTENCE_TRANSFORMERS_HOME = $EmbedCache

Write-Host "Starting embedding service on http://127.0.0.1:8090"
Set-Location $ServiceDir
& $py -m uvicorn main:app --host 127.0.0.1 --port 8090
