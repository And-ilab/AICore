# Start llama.cpp OR prefer the LLM manager (model switcher).
# Usage:
#   .\start-llm.ps1                  # manager on :8070, llama on :8080
#   .\start-llm.ps1 -Direct          # only llama-server (no switcher API)
#   .\start-llm.ps1 -ModelId qwen2.5-1.5b-instruct -Direct
param(
  [string]$ModelId = "",
  [switch]$Direct
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

if (-not $Direct) {
  & (Join-Path $PSScriptRoot "start-llm-manager.ps1")
  exit $LASTEXITCODE
}

$ModelsDir = Join-Path $Repo "models"
$LlamaServer = Join-Path $ModelsDir "llama.cpp\llama-server.exe"
if (-not (Test-Path $LlamaServer)) {
  $LlamaServer = Get-ChildItem -Path (Join-Path $ModelsDir "llama.cpp") -Recurse -Filter "llama-server.exe" |
    Select-Object -First 1 -ExpandProperty FullName
}

$CatalogPath = Join-Path $PSScriptRoot "models.json"
$Catalog = Get-Content -Raw -Path $CatalogPath | ConvertFrom-Json
$Alias = $Catalog.openai_alias
$Selected = $null
if ($ModelId) {
  $Selected = $Catalog.models | Where-Object { $_.id -eq $ModelId } | Select-Object -First 1
  if (-not $Selected) { throw "Unknown ModelId: $ModelId" }
} else {
  $Preferred = $Catalog.default_model_id
  $Selected = $Catalog.models | Where-Object { $_.id -eq $Preferred } | Select-Object -First 1
  if (-not $Selected) { $Selected = $Catalog.models[0] }
}

$Gguf = Join-Path $ModelsDir ("llm\" + $Selected.gguf)
if (-not (Test-Path $LlamaServer)) { throw "llama-server.exe missing. Run download-models.ps1" }
if (-not (Test-Path $Gguf)) { throw "GGUF missing: $Gguf. Run download-models.ps1" }

$threads = [Environment]::ProcessorCount
Write-Host "Starting LLM on http://127.0.0.1:8080/v1 (model=$($Selected.id), threads=$threads)"
& $LlamaServer `
  -m $Gguf `
  --host 127.0.0.1 `
  --port 8080 `
  -c 4096 `
  -t $threads `
  --alias $Alias
