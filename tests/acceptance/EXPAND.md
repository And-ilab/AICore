# P0-04 acceptance expand plan

## Smoke (done)

IDs matching `*-T-01` / `*-T-04` (not `*-04a`) are implemented in:

| Module | File | Smoke IDs |
| --- | --- | --- |
| sufler | `test_suf_t.py` | SUF-T-01, SUF-T-04 |
| chat | `test_chat_t.py` | CHAT-T-01, CHAT-T-04 |
| assistant | `test_ass_t.py` | ASS-T-01, ASS-T-04 |
| documents | `test_doc_t.py` | DOC-T-01, DOC-T-04 |
| integration | `test_int_t.py` | INT-T-SUZ-01/04, INT-T-AUD-01/04, INT-T-OKT-01/04, INT-T-ASR-01, INT-T-OKTELL-MRCP-01 |

Shared arrange helpers: `fixtures.py` / `conftest.py`. Matrix updates: `harness.mark_acceptance` → `matrix.json` / `matrix.md`.

Run smoke:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\acceptance\test_suf_t.py tests\acceptance\test_chat_t.py tests\acceptance\test_ass_t.py tests\acceptance\test_doc_t.py tests\acceptance\test_int_t.py -q -k "Smoke"
```

## Expand order (next waves)

1. **Wave A — operator UX**  
   SUF-T-02/03/05/12/14 · CHAT-T-02/03/05/06  
   Prefer `POST /api/v1/sufler/suggest`, channel inbox, RBAC tab checks.

2. **Wave B — assistant depth**  
   ASS-T-02/03/04a/05 · ASS-T-RPT-*  
   Add real multipart PDF/A-V upload; keep `attachments[].text` as fallback.

3. **Wave C — OCR quality**  
   DOC-T-02/03/05–08 · wire `benchmarks/suites/ocr_extraction.py` ≥95% for DOC-T-01 full criterion.

4. **Wave D — integrations**  
   INT-T-SUZ-02/03/05–08 · INT-T-OKT-02/03/05–07 · INT-T-AUD-02/03 · INT-T-ASR-02/03 · MRCP lab.

## How to add one ID

1. Copy a smoke test in the matching `test_*_t.py`.
2. Decorate with `@mark_acceptance("…-T-NN")`.
3. Arrange via `fixtures` → call API → assert TZ criterion from `TZ-unified-v1.8%20(МИХ).docx`.
4. Re-run module; confirm `matrix.json` status becomes `pass`.
