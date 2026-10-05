# Sufler benchmarks

## Unified CLI

`bench.py` is the common entry point for AI Model Layer benchmarks. Available
suites are `asr`, `embedding`, `qu`, `llm`, and `ocr`.

Run a suite from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite asr `
  --output .\reports
```

`--output` is optional and defaults to `reports/`. A successful run exits
with code `0`, prints the report path, and writes
`<suite>-<UTC timestamp>.json`.

Embedding, QU, LLM, and OCR are stubs. ASR invokes the streaming Vosk runner
when models and WAV samples are available; otherwise it writes the same
explicit placeholder values. ASR setup and metric semantics are documented
in `suites/README.md`.

The output contract is defined by `report.schema.json` (JSON Schema draft
2020-12). Report shape:

```json
{
  "schema_version": "1.0",
  "report_id": "asr-20260720T140000000000Z",
  "suite": "asr",
  "runner_status": "stub",
  "generated_at": "2026-07-20T14:00:00+00:00",
  "datasets": ["asr-synthetic-samples"],
  "metrics": {
    "latency_ms": {
      "p50": 0.0,
      "p95": 0.0,
      "status": "placeholder"
    },
    "accuracy_percent": {
      "value": null,
      "status": "placeholder"
    },
    "wer_percent": {
      "value": null,
      "status": "placeholder"
    }
  }
}
```

CLI integration test:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  .\tests\benchmarks\test_bench_cli.py -v
```

## Layered sufler evaluation

`datasets/sufler_eval_100.json` is a frozen, versioned set of exactly 100
cases: 25 no-hint/phatic and personal-question controls, 35 scenario
start/branch/off-topic cases, and 40 grounded banking questions.

The standalone runner executes classification, scenario, retrieval, and full
suggest layers and writes matching JSON and Markdown reports:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\sufler_eval.py `
  --output .\reports\sufler-eval
```

Full suggest uses the network-free stub gateway by default. A live configured
gateway requires both `--gateway-mode openai` and `--allow-live-llm`.

## ASR hotword benchmark

Suite `suites/asr_hotword.py` maps to **FR-ASR-09**: specialized dictionaries
must improve recognition of banking terms, abbreviations, and contractions.

The canonical dataset is `datasets/asr_bank_terms.json` and contains exactly
50 terms. The benchmark compares two transcript sets generated from the same
audio samples:

1. ASR without hotword boost;
2. the same ASR/model/configuration with the banking dictionary enabled.

The suite evaluates results; it does not fabricate transcripts or emulate a
vendor-specific boost implementation.

### Recognition input

Both input files use dataset IDs:

```json
{
  "recognitions": [
    {
      "id": "bank-001",
      "text": "оплата через ерип"
    },
    {
      "id": "bank-002",
      "text": "подключить м банкинг"
    }
  ]
}
```

A compact object is also supported:

```json
{
  "bank-001": "оплата через ерип",
  "bank-002": "подключить м банкинг"
}
```

Missing transcripts count as incorrect. Unknown or duplicate IDs fail the
benchmark to prevent comparing different samples.

### Run

From the repository root:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\asr_hotword.py `
  --without-boost .\path\without_boost.json `
  --with-boost .\path\with_boost.json `
  --output .\benchmarks\results\asr_hotword.json
```

The report contains accuracy for both modes, improvement in percentage points,
missing transcript IDs, and per-term recognition details. It is the
machine-readable input for the ASR evaluation report.

### Verification

```powershell
.\backend\.venv\Scripts\python.exe -m pytest `
  .\tests\benchmarks\test_asr_hotword.py -v
```
