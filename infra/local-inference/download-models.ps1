# Download CPU-friendly local models for Sufler RAG chat.
# - Qwen2.5-1.5B-Instruct Q4_K_M (GGUF) for llama.cpp
# - llama-server Windows binary
# - multilingual-e5-large via huggingface_hub (for embedding service)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Repo = Split-Path -Parent $Root
$ModelsDir = Join-Path $Repo "models"
$LlamaDir = Join-Path $ModelsDir "llama.cpp"
$LlmDir = Join-Path $ModelsDir "llm"
$EmbedCache = Join-Path $ModelsDir "hf-cache"

New-Item -ItemType Directory -Force -Path $ModelsDir, $LlamaDir, $LlmDir, $EmbedCache | Out-Null

$Ggufs = @(
    @{
        Name = "qwen2.5-3b-instruct-q4_k_m.gguf"
        Url  = "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf"
    },
    @{
        Name = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
        Url  = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    }
)
foreach ($item in $Ggufs) {
    $path = Join-Path $LlmDir $item.Name
    if (-not (Test-Path $path)) {
        Write-Host "Downloading LLM GGUF → $path"
        curl.exe -L --retry 3 -o $path $item.Url
    } else {
        Write-Host "LLM GGUF already present: $path"
    }
}

$LlamaZip = Join-Path $ModelsDir "llama-bin.zip"
$LlamaServer = Join-Path $LlamaDir "llama-server.exe"
if (-not (Test-Path $LlamaServer)) {
    Write-Host "Resolving latest llama.cpp Windows release…"
    $release = Invoke-RestMethod -Uri "https://api.github.com/repos/ggerganov/llama.cpp/releases/latest"
    $asset = $release.assets | Where-Object {
        $_.name -match "bin-win-cpu-x64\.zip$"
    } | Select-Object -First 1
    if (-not $asset) {
        $asset = $release.assets | Where-Object {
            $_.name -match "win-cpu-x64\.zip$"
        } | Select-Object -First 1
    }
    if (-not $asset) {
        throw "Could not find a CPU Windows zip in the latest llama.cpp release"
    }
    Write-Host "Downloading $($asset.name)"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $LlamaZip -UseBasicParsing
    Expand-Archive -Path $LlamaZip -DestinationPath $LlamaDir -Force
    $found = Get-ChildItem -Path $LlamaDir -Recurse -Filter "llama-server.exe" | Select-Object -First 1
    if (-not $found) {
        throw "llama-server.exe not found after extract"
    }
    if ($found.DirectoryName -ne $LlamaDir) {
        Copy-Item $found.FullName -Destination $LlamaServer -Force
    }
} else {
    Write-Host "llama-server already present: $LlamaServer"
}

Write-Host "Prefetching embedding model intfloat/multilingual-e5-large into $EmbedCache"
$py = Join-Path $Repo "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = "python"
}
& $py -m pip install --upgrade pip
& $py -m pip install "huggingface_hub>=0.26" "sentence-transformers==3.4.1" "torch==2.6.0" "fastapi==0.115.6" "uvicorn==0.34.0"
$env:HF_HOME = $EmbedCache
& $py -c @"
from sentence_transformers import SentenceTransformer
m = SentenceTransformer('intfloat/multilingual-e5-large', cache_folder=r'$EmbedCache')
v = m.encode(['query: тест'], normalize_embeddings=True)
print('e5-large ready, dim=', len(v[0]))
"@

Write-Host "Done. Models under $ModelsDir"
