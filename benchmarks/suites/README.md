# Benchmark suites

## ASR streaming

`asr_streaming.py` provides the ASR implementation behind:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite asr `
  --output .\reports
```

The suite maps to:

- **FR-ASR-01** — streaming recognition in Russian and English;
- **FR-ASR-04** — recognition latency no more than one second;
- **FR-ASR-07** — optimization and verification for telephony audio.

Samples are loaded from `benchmarks/datasets/asr_samples.json`. WAV files
must be uncompressed mono 16-bit PCM. Telephony samples should retain their
original 8 kHz rate; Vosk receives the sample rate stored in the WAV header.

### Modes

If Vosk, a language model, or WAV files are unavailable, the command still
exits successfully and writes a report with `runner_status: stub`, `null`
WER, zero placeholder latency, and a reason for every skipped sample.

For a real run, install Vosk and configure separate language models:

```powershell
$env:VOSK_MODEL_PATH_RU = "C:\models\vosk-model-ru"
$env:VOSK_MODEL_PATH_EN = "C:\models\vosk-model-en"
```

`VOSK_MODEL_PATH` remains a backward-compatible fallback for Russian only.
The suite also looks for known RU/EN model directories under
`backend/services/asr/model/`.

Runner status:

- `stub` — no WAV was measured;
- `partial` — real samples were measured for only one language;
- `ready` — at least one real RU and one real EN sample were measured.

### Metrics

WER is calculated as word-level Levenshtein edits divided by the number of
reference words. Corpus WER and a RU/EN breakdown are written to the report.
Accuracy is reported as `max(0, 100 - WER)`.

Audio is fed to Vosk in 100 ms chunks. `latency_ms.p50/p95` measures decoder
wall-clock processing time for those chunks. It is useful for comparing
models on the same host, but it is **not by itself proof of FR-ASR-04**:
end-to-end acceptance must additionally measure buffering, endpointing,
network transport, final transcript delivery, and concurrent-call load.

Per-sample reference, hypothesis, WER, sample rate, model name, and latency
are available under `suite_details.samples`. The JSON contract is documented
in `benchmarks/report.schema.json`.

## ASR load

`asr_load.py` targets **FR-ASR-03**: at least 70 concurrent telephone streams
without failures. Run it from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\asr_load.py `
  --streams 70 `
  --output .\reports
```

The runner starts all async stream tasks behind one start barrier. With a
Vosk model and an existing WAV from `asr_samples.json`, each task creates an
independent recognizer in a worker thread and processes the same reference
audio. The report contains:

- configured, successful, and failed stream counts;
- chunk-processing p50/p95 and full-stream p50/p95;
- WER/accuracy for real Vosk mode;
- operating system, CPU, logical core count, RAM, Python version, model, and
  sample ID.

GPU discovery is intentionally not guessed. If a GPU participates in the
test, record it before the run:

```powershell
$env:ASR_BENCH_GPU = "NVIDIA L40S 48 GB, driver <version>"
```

When no runnable WAV/model is available, the suite executes 70 lightweight
async stub streams to validate the harness. The report then uses placeholder
metrics and sets `fr_asr_03_load_target_met` to `false`. Only
`mode: async_vosk`, 70 successful streams, zero failures, and measured
metrics may be used as evidence for P1-15.

The p95 reported in `metrics.latency_ms` is decoder time per 100 ms chunk.
The separate `suite_details.stream_latency_ms` describes full-file
processing. Neither value includes Oktell/network transport, which remains
part of the integration load test.

## Embedding chunk grid

`chunk_grid.py` calibrates chunk size and overlap for FR-LLM-03 and the
`kb_cc_production` profile (P1-24). The grid contains nine combinations:

- chunk size: 256, 512, 1024 tokens;
- overlap: 50, 100, 200 tokens;
- metric: recall@5 on `embedding-suz-recall`.

Stub report:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\chunk_grid.py `
  --output .\reports
```

Without measured scores all nine recall values and `best_combination` are
`null`. ModelRegistry keeps the frozen dev baseline `512/100`.

Measured input must cover the complete grid:

```json
{
  "scores": [
    {
      "chunk_size_tokens": 256,
      "overlap_tokens": 50,
      "recall_at_5_percent": 85.0
    }
  ]
}
```

The example shows one row for readability; the real file must contain all
nine unique combinations. Generate the final report and update registry:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\chunk_grid.py `
  --scores .\path\chunk_scores.json `
  --write-registry `
  --sign-off "P1-21 approved by <role/ticket>" `
  --output .\reports
```

The suite selects maximum recall@5. If results tie, it prefers a larger chunk
and smaller overlap to reduce the number of indexed vectors. Registry
comments are preserved; only `optimal_chunk_size_tokens`,
`optimal_chunk_overlap_tokens`, and `chunk_selection_status` are changed.
Placeholder scores can never update ModelRegistry.

## Retrieval threshold calibration

`retrieval_thresholds.py` calibrates the two FR-LLM-04 similarity thresholds:

- `context_inclusion` — a fragment may enter LLM context;
- `deterministic_answer` — a sufficiently strong match may use the
  deterministic-answer path without free-form generation.

ModelRegistry starts with explicit engineering defaults:

```text
context_inclusion = 0.60
deterministic_answer = 0.85
status = dev_frozen
```

This means scores below 0.60 are excluded, scores from 0.60 to 0.85 may be
used as RAG context, and scores from 0.85 are eligible for the deterministic
path. Eligibility does not bypass source, scope, RBAC, or safety checks.

Generate a stub report with the current frozen dev recommendation:

```powershell
.\backend\.venv\Scripts\python.exe `
  .\benchmarks\suites\retrieval_thresholds.py `
  --output .\reports
```

Measured input contains model similarity scores and two labels:

```json
{
  "samples": [
    {
      "id": "query-001/document-007",
      "score": 0.91,
      "relevant": true,
      "deterministic_correct": true
    }
  ]
}
```

`relevant` means the fragment should enter context.
`deterministic_correct` means the fragment alone supports the approved
deterministic answer. A deterministic-correct sample must also be relevant.

Calibration chooses the context threshold with the best relevance F1. The
deterministic threshold must be at least as strict and reach 98% precision
by default. To write measured recommendations:

```powershell
.\backend\.venv\Scripts\python.exe `
  .\benchmarks\suites\retrieval_thresholds.py `
  --samples .\path\retrieval_scores.json `
  --write-registry `
  --sign-off "P1-22 approved by <role/ticket>" `
  --output .\reports
```

Without `--samples`, `--write-registry` is rejected. The API used by the
future P3-04 orchestrator is in `backend/rag/thresholds.py`:
`get_thresholds`, `get_threshold`, `set_thresholds`, and `set_threshold`.
It enforces `0 <= context_inclusion <= deterministic_answer <= 1`.
Because `kb_cc_production` is `dev_frozen`, setter calls also require
`benchmark_report` and `sign_off`.

## Incremental index latency

`index_latency.py` measures FR-UND-08 time from publication of a СУЗ article
until the updated content is visible in `cc_production` search. One run uses
exactly 30 updates, matching the upper daily volume used for planning.

Stub report:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\index_latency.py `
  --output .\reports
```

The stub creates 30 pending article IDs but does not invent latency or a
pass/fail result. A measured event file has this shape:

```json
{
  "events": [
    {
      "article_id": "suz-article-001",
      "published_at": "2026-07-20T10:00:00+03:00",
      "searchable_at": "2026-07-20T10:00:18+03:00"
    }
  ]
}
```

The real file must contain 30 unique events and timezone-aware timestamps:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\index_latency.py `
  --events .\path\index_events.json `
  --output .\reports
```

The JSON report includes p50/p95 and two checks:

- `acceptance_target_passed`: p95 ≤120 seconds, the integration upper bound
  supplied for the benchmark;
- `operational_target_passed`: p95 ≤30 seconds, the stricter architecture
  target recorded for `cc_production`.

FR-UND-08 itself requires automatic retraining/reindex after updates; the
numeric two-minute limit is treated as the integration acceptance boundary.
Measured timestamps must include Celery enqueue, worker processing,
vector-store commit, and a successful search that sees the new version.

## QU synonyms, antonyms, and word order

`qu_synonyms.py` validates the hybrid architecture from
`docs/technical/qu-architecture.md` against 20 CC-SCR-derived pairs:

- 10 synonym/paraphrase pairs must match the source intent;
- 5 antonym/negation pairs must not match;
- 5 word-order pairs contain both meaning-preserving and
  meaning-changing permutations.

Stub report:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite qu `
  --output .\reports
```

The stub documents category sizes but leaves pass/fail as `null`. To evaluate
P3-03 output, provide all 20 predictions:

```json
{
  "predictions": [
    {
      "id": "QU-SYN-001",
      "matched": true,
      "predicted_intent_id": "CC-SCR-001",
      "relevance_score": 0.91
    }
  ]
}
```

The example is abbreviated; prediction IDs must exactly match the dataset:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\qu_synonyms.py `
  --predictions .\path\qu_predictions.json `
  --output .\reports
```

The report contains pass/fail and pass rate for `synonyms`, `antonyms`, and
`word_order`, plus per-pair expected/actual intent. The command exits `0`
even when quality cases fail; malformed or incomplete prediction input is an
execution error.

## QU bilingual consistency

`qu_bilingual.py` maps to **FR-UND-05** and **SUF-T-12**. The dataset contains
10 CC-SCR intents with equivalent RU and EN formulations. Both formulations
must match the expected intent, and their predicted intent IDs must agree.

Stub report:

```powershell
.\backend\.venv\Scripts\python.exe `
  .\benchmarks\suites\qu_bilingual.py `
  --output .\reports
```

Measured predictions use one RU/EN result per pair:

```json
{
  "predictions": [
    {
      "id": "QU-BI-001",
      "ru": {
        "matched": true,
        "intent_id": "CC-SCR-001",
        "relevance_score": 0.93
      },
      "en": {
        "matched": true,
        "intent_id": "CC-SCR-001",
        "relevance_score": 0.89
      }
    }
  ]
}
```

The actual file must contain all 10 IDs:

```powershell
.\backend\.venv\Scripts\python.exe `
  .\benchmarks\suites\qu_bilingual.py `
  --predictions .\path\qu_bilingual_predictions.json `
  --output .\reports
```

The report provides RU match rate, EN match rate, cross-language consistency,
pair pass rate, and per-intent details. Without P3-03 predictions these
values remain `null` placeholders.

## LLM profile `sufler_cc`

`llm_sufler_cc.py` sends 20 synthetic SUZ-grounded prompts through
`ModelGateway` profile `sufler_cc`. It maps to §3.4/§3.6 through
FR-LLM-06 and FR-LLM-07:

- response length ≤500 characters;
- response latency p95 ≤2000 ms;
- hallucination rate ≤3% after manual review.

Dev stub:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py run `
  --suite llm `
  --output .\reports
```

The stub executes all 20 calls and records chars/latency, but these values are
marked as placeholders and are not KPI evidence.

For an OpenAI-compatible endpoint, first configure a real model in the
`llm_sufler_cc` registry slot and provide `OPENAI_BASE_URL`/`OPENAI_API_KEY`.
Then run:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\llm_sufler_cc.py `
  --mode openai `
  --output .\reports
```

Each result contains `response_sha256`. Manual hallucination review must
refer to that exact response:

```json
{
  "reviews": [
    {
      "id": "EMB-SUZ-001",
      "response_sha256": "<hash from report>",
      "hallucinated": false,
      "notes": "All claims are supported by the supplied SUZ fragment."
    }
  ]
}
```

Re-run with all 20 reviews using `--rubric`. A real model plus complete rubric
sets `kpi_evidence=true`. With only 20 prompts, one hallucination equals 5%,
so this dev suite cannot resolve the contractual ≤3% boundary finely enough;
the sign-off dataset must be larger.

## LLM profile `assistant_bank`

`llm_assistant.py` validates the P5-01 Assistant API contract for Part III:

- OpenAI-compatible SSE frames and `[DONE]`;
- an 8000-token dev context fixture;
- OpenAI `tool_calls` shape without executing the tool;
- first-event, first-content, total, and frame-interval latency.

Relevant requirements are FR-ASS-03 (context chat), FR-ASS-14 and FR-ASS-33
(RPA/adapters and tool-use), FR-ASS-21 (latency), and FR-ASS-41 (LLM
abstraction). The numeric 8000-token value is a dev API contract from this
task, not a contractual KPI found in Part III.

Run:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\llm_assistant.py `
  --mode stub `
  --output .\reports
```

The stub constructs exactly 8000 whitespace-separated fixture tokens. This
does not reproduce a vendor tokenizer and is marked `placeholder`. The SSE
parser validates every JSON frame and reconstructs the streamed content.

The tool mock asks for `get_exchange_rate` and expects:

```json
{
  "type": "function",
  "function": {
    "name": "get_exchange_rate",
    "arguments": "{\"currency\":\"USD\"}"
  }
}
```

No exchange-rate adapter, RPA process, or banking operation is executed.
Real endpoint results become measured only after `assistant_bank` is
configured with a non-stub model and `--mode openai`.

## OCR field extraction

`ocr_extraction.py` evaluates Part IV document classification and required
field extraction for DOC-T-01, DOC-T-03, and DOC-T-04. It loads PDF/image
paths and field templates from `benchmarks/datasets/ocr_samples.json`.

Run the placeholder suite directly:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\ocr_extraction.py `
  --output .\reports
```

It is also the default unified OCR runner:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\bench.py `
  run --suite ocr --output .\reports
```

Candidate output uses this schema:

```json
{
  "predictions": [
    {
      "id": "OCR-SYN-001",
      "document_type": "account_statement",
      "fields": {
        "account_number": "BY00...",
        "currency": "BYN"
      }
    }
  ]
}
```

The predictions file must contain every dataset ID exactly once:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\ocr_extraction.py `
  --predictions .\reports\p1-51-ocr-predictions.json `
  --output .\reports
```

The report includes overall and per-document-type field accuracy, field
precision, document-type accuracy, missing/extra fields, and sample-file
availability. A required field counts as extracted only when its value is
non-empty; numeric zero and boolean `false` remain valid values.

Current PDF/image paths and expected field names are placeholders, while gold
field values are absent. Therefore the default stub returns `0%` with
`status=placeholder`, and even supplied predictions are not sign-off evidence
until the sample files and gold values are available.

## Optional reranker A/B

`reranker_ab.py` compares the same QU semantic-pair cases before and after an
on-prem cross-encoder. It reports semantic pass rate, top-1 accuracy,
recall@5, MRR, nDCG@5, p95 latency, and A/B deltas for FR-UND-06/12.

The reranker slot currently has:

```yaml
reranker:
  dev_model: null
  prod_candidate: null
  status: evaluating
```

Therefore the default command creates an explicit non-blocking skip report:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\reranker_ab.py `
  --output .\reports
```

Expected report fields:

```json
{
  "runner_status": "stub",
  "suite_details": {
    "status": "skipped",
    "skip_reason": "reranker_model_not_configured",
    "blocking_for_p1_61": false
  }
}
```

This optional skip does not block P1-61. It must not be presented as evidence
that reranking improves retrieval.

When a pinned on-prem cross-encoder and two result sets exist, run:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\reranker_ab.py `
  --model .\models\reranker-pinned `
  --baseline .\reports\qu-without-reranker.json `
  --reranked .\reports\qu-with-reranker.json `
  --output .\reports
```

Both input files use:

```json
{
  "predictions": [
    {
      "id": "QU-SYN-001",
      "matched": true,
      "ranked_results": [
        {"intent_id": "CC-SCR-001", "score": 0.93}
      ],
      "latency_ms": 12.4
    }
  ]
}
```

Every QU dataset ID must appear exactly once; rankings contain 1–5 unique
intent IDs with descending scores. A reranker is only considered when quality
does not regress and at least one quality metric improves. Final adoption also
requires on-prem/air-gap, license, latency, hardware, and security review.

## LLM profile `docs_ocr`

`llm_docs_ocr.py` checks the P6-01 / P1-53 post-OCR pipeline:

1. load synthetic OCR text and the required field template;
2. call the `docs_ocr` profile through `ModelGateway`;
3. parse the assistant response as structured JSON;
4. compare returned field names with the required fields;
5. write latency and field-extraction metrics to a JSON report.

The suite maps to FR-OCR-01, FR-OCR-02, FR-OCR-13, FR-OCR-14,
FR-OCR-22, and the common Part V performance requirement FR-LLM-07.

Run from the repository root:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\llm_docs_ocr.py `
  --mode stub `
  --output .\reports
```

The report includes:

- structured JSON validity percentage;
- required field-name extraction accuracy;
- field-name precision and extra-field count;
- document type accuracy;
- latency p50/p95;
- one detailed result per document.

The current dataset has OCR text and expected field names, but not gold field
values. Therefore the score covers field-name presence, not exact value
accuracy. The dev stub intentionally returns an empty `fields` object, so its
accuracy is `0%` with `status=placeholder`; this is a valid pipeline contract
check, not model-quality evidence. Configure a real `docs_ocr` model and run
with `--mode openai` to obtain measured results.

## RAG grounding and citations

`rag_grounding.py` enforces FR-LLM-05 for SUZ/KB answers. Every test case in
`rag_query_pairs.json` contains known `source_chunk_ids`. A case passes only
when the cited `chunk_id` set exactly equals the expected set, with no missing,
extra, or duplicate citations.

Run the contract stub:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\rag_grounding.py `
  --output .\reports
```

The stub copies known citations and therefore returns `100%` with
`status=placeholder`; this proves the report and scoring contract, not RAG
quality.

To evaluate the P3-04 orchestrator, export:

```json
{
  "predictions": [
    {
      "id": "RAG-CC-001",
      "answer": "Ответ по подтверждённому фрагменту.",
      "citations": [
        {"chunk_id": "SUZ-CC-SCR-001#chunk-0001"}
      ]
    }
  ]
}
```

The predictions file must contain every dataset ID exactly once:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\rag_grounding.py `
  --predictions .\reports\p3-04-predictions.json `
  --output .\reports
```

The primary `citation_accuracy_percent` is the percentage of exact-match
cases. The report also includes citation precision, recall, invalid IDs,
missing IDs, and duplicate counts. P3-04 should call the reusable
`evaluate_predictions()` function or emit the documented prediction schema.

## LLM fixed-rate load

`llm_load.py` schedules 10 requests per second for 60 seconds by default
(600 requests) and reports latency p50/p95 for FR-LLM-07. Requests are started
at a fixed rate; synchronous `ModelGateway.chat()` calls run in worker threads
so slow responses can overlap without blocking the scheduler.

Run the full dev-stub profile:

```powershell
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\llm_load.py `
  --mode stub `
  --profile sufler_cc `
  --rps 10 `
  --duration 60 `
  --output .\reports
```

The JSON report includes:

- scheduled, successful, timed-out, OOM, and failed request counts;
- request latency p50/p95;
- achieved successful RPS and scheduler lag;
- peak in-flight requests;
- CPU, RAM, OS, Python, accelerator, and VM labels;
- the FR-LLM-07 target decision.

Set reproducibility labels before a capacity-planning run:

```powershell
$env:LLM_BENCH_VM = "test-vm-p10-07"
$env:LLM_BENCH_ACCELERATOR = "NVIDIA-L40S-48GB"
```

The stub run must complete without timeout/OOM, but its latency is marked
`placeholder` and `target_met=false`. A production capacity decision requires
a non-stub model, the full duration of at least 60 seconds, achieved throughput
near the configured minimum, p95 within the ModelRegistry limit, and zero
failures:

```powershell
$env:OPENAI_BASE_URL = "http://llm.internal/v1"
$env:OPENAI_API_KEY = "local-secret"
.\backend\.venv\Scripts\python.exe .\benchmarks\suites\llm_load.py `
  --mode openai `
  --profile sufler_cc `
  --rps 10 `
  --duration 60 `
  --output .\reports
```
