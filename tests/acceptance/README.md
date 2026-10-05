# Acceptance harness (P0-04)

Executable foundation for formal приёмка IDs from `matrix.json`.

| File | Module |
| --- | --- |
| `test_suf_t.py` | SUF-T-* |
| `test_chat_t.py` | CHAT-T-* |
| `test_ass_t.py` | ASS-T-* |
| `test_doc_t.py` | DOC-T-* |
| `test_int_t.py` | INT-T-* |
| `fixtures.py` / `conftest.py` | Shared arrange helpers |
| `harness.py` | Matrix load/update + smoke ID helpers |
| `EXPAND.md` | Wave plan beyond smoke 01/04 |
| `load/` | II.7.4 Locust/k6 — 75 VUs, suggest p95 ≤2s → [`load/report.md`](load/report.md) |
| `generate_matrix.py` | Rebuild ID inventory from TZ (resets statuses) |
| `generate_protocol.py` | Build `protocol.md` from `matrix.json` (customer signature template) |

Smoke subset = IDs ending in `-01` or `-04`. Passing tests mark `pass` in `matrix.json`.

**TEST cutover (bank integrations):** ordered flags + INT-T subset —
[`infra/test/cutover-checklist.md`](../../infra/test/cutover-checklist.md) ·
results [`cutover-int-t-results.md`](../../infra/test/cutover-int-t-results.md).

**Formal SUF-T + CHAT-T smoke on TEST (share with customer):**
[`test_env_results.md`](./test_env_results.md) — URL `https://ai-hub-test.bank.local/`.

```bash
pytest -v tests/acceptance/test_int_t.py
pytest -v \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest
```

## Protocol (приёмка)

After acceptance runs have updated `matrix.json`, generate the formal protocol:

```bash
python tests/acceptance/generate_protocol.py
# optional: --matrix PATH --output PATH --date YYYY-MM-DD --stand "…"
```

Output `protocol.md`: pass/fail summary by module, full scenario table, customer/executor signature blocks (VII.2).

## CI — `acceptance-smoke` (FR-CC-10)

GitHub Actions job in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs on every PR (and push):

- **SUF-T-01** — telephony suggest hints after client utterance
- **CHAT-T-04** — ARM sufler hint with SUZ article title

Fails the PR check on regression. Local equivalent:

```bash
pytest -v \
  tests/acceptance/test_suf_t.py::SufTSmokeAcceptanceTest::test_suf_t_01_telephony_hints_after_client_utterance \
  tests/acceptance/test_chat_t.py::ChatTSmokeAcceptanceTest::test_chat_t_04_arm_sufler_hint_with_article_title
```
