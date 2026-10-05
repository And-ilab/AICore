# Oktell T+45 smoke test (VI.2 / P4-02)

**Audience:** ops / ДИТ on bank TEST  
**Goal:** switch SuflerTelephony between local mock and TEST Oktell line (T+45), then verify INT-T01…03 basics.  
**Contract:** [tz-oktell-sufler-telephony.md](../integration/oktell-sufler-telephony/tz-oktell-sufler-telephony.md) · FR-SUF-04 · OKT-7

## Feature flag

| Value | Client | When |
| --- | --- | --- |
| `OKTELL_MODE=mock` | `oktell_mock` on `OKTELL_MOCK_WS_URL` (default `ws://127.0.0.1:8766`) | Local / CI / before T+45 |
| `OKTELL_MODE=prod` | Profile `test_line_t45` → `OKTELL_PROD_WS_URL` (or `OKTELL_WS_URL`) | Bank TEST line after T+45 |

P4-02 factory:

```python
from integrations.oktell import OktellClient

client = OktellClient.from_settings()  # reads OKTELL_MODE
print(client.describe())
```

Env templates:

- local: [`infra/.env.example`](../../infra/.env.example)
- TEST cutover: [`infra/test/.env.example`](../../infra/test/.env.example)

## Prerequisites (prod / T+45)

1. ДИТ delivered TEST queue/number (**OKT-7**) with marking `OKTELL_TEST_MARKING` (default `TEST_OKTELL_T45`).
2. Network path from AI Hub app host → Oktell WS (TLS/`wss` as agreed).
3. Service account / Web integration enabled for `subscribeevent` + `phoneevent_*`.
4. Copy `infra/test/.env.example` → `infra/test/.env` and set:
   - `OKTELL_MODE=prod`
   - `OKTELL_ENABLED=true`
   - `OKTELL_PROD_WS_URL=wss://…`
   - `OKTELL_TEST_QUEUE=…`

## Smoke A — mock (always available)

```powershell
# 1) Start mock
.\backend\.venv\Scripts\python.exe .\backend\integrations\oktell_mock\server.py

# 2) In another shell — ensure mock mode
$env:OKTELL_MODE = "mock"
$env:OKTELL_ENABLED = "true"
$env:DJANGO_SETTINGS_MODULE = "sufler.settings"
$env:PYTHONPATH = "backend"

.\backend\.venv\Scripts\python.exe -c @"
import asyncio, os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sufler.settings')
django.setup()
from integrations.oktell import OktellClient

async def main():
    client = OktellClient.from_settings()
    assert client.mode == 'mock'
    result = await client.connect_and_subscribe(run_lifecycle=True)
    print('subscribe', result)
    print(client.describe())
    await client.close()

asyncio.run(main())
"@
```

**Pass:** subscribe `result=1`; lifecycle `ringstarted → commstarted → commstopped`; ASR session stopped.

Automated:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests\integration\test_oktell_client.py tests\test_oktell_mode.py -q
```

## Smoke B — TEST line T+45 (`OKTELL_MODE=prod`)

1. Set env from `infra/test/.env` (`OKTELL_MODE=prod`, real `OKTELL_PROD_WS_URL`).
2. Restart backend / worker so Django settings reload.
3. Run:

```powershell
$env:OKTELL_MODE = "prod"
$env:OKTELL_ENABLED = "true"
$env:OKTELL_PROD_WS_URL = "wss://oktell-test.bank.local/ws"
$env:DJANGO_SETTINGS_MODULE = "sufler.settings"
$env:PYTHONPATH = "backend"

.\backend\.venv\Scripts\python.exe -c @"
import asyncio, os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sufler.settings')
django.setup()
from integrations.oktell import OktellClient

async def main():
    client = OktellClient.from_settings()
    assert client.mode == 'prod'
    assert client.profile.profile_id == 'test_line_t45'
    print(client.describe())
    await client.connect()
    sub = await client.subscribe_phoneevents(qid='smoke-t45')
    print('subscribe', sub)
    name, payload = await client.receive_event()
    print(name, payload.get('chainid'))
    await client.close()

asyncio.run(main())
"@
```

4. From a softphone / Oktell agent: place **one** call into the TEST queue with marking visible in CDR.
5. Confirm Hub / SuflerTelephony session appears (chainid linked) and ASR legs start on `commstarted`.

**Pass criteria**

| Check | Expected |
| --- | --- |
| Mode | `client.mode == "prod"` / profile `test_line_t45` |
| Subscribe | `subscribeeventresult.result == 1` |
| INT-T01 | `phoneevent_ringstarted` with `chainid` |
| INT-T02 | `phoneevent_commstarted` |
| INT-T03 | `phoneevent_commstopped` |
| Marking | Call tagged `TEST_OKTELL_T45` (or configured marking) |

## Smoke C — vendor pickup POST + dual-leg (no their PBX)

Their file «Подслушивание»: after answer they POST JSON. We start two listen instances (`02*` client, `03*` operator) and push text into `/ws/sufler/<Idchain>/`.

```powershell
# 1) Pretend Oktell answered
curl.exe -s -X POST http://127.0.0.1:8001/api/v1/telephony/oktell/call-started `
  -H "Content-Type: application/json" `
  -d "{\"CallerID\":\"375336664177\",\"CalledID\":\"1001\",\"Idchain\":\"test-chain-1\",\"op_name\":\"operator1\",\"call_type\":\"in\"}"

# 2) Open operator window
# http://localhost:5173/sufler?callId=test-chain-1
```

**Pass:** response `201` with legs `02*1001` / `03*1001` and sip users `2001` / `2002`; window leaves demo and shows the mock client phrase + hints.

Two POSTs with different `Idchain` = two instances (многоканальность). `operator1`…`operator5` stay in their Oktell client — we only store `op_name`.

Live listen: `OKTELL_LISTEN_MODE=sip`, passwords in env (never commit the Excel), SIP packets to Oktell `10.1.1.31`, Vosk model on Debian. `scripts/export_oktell_sip_env.py` builds the env file.

**Fail / rollback:** set `OKTELL_MODE=mock`, restart services; file incident with `chainid`, WS URL host, and timestamp.

## Ops notes

- `run_lifecycle=True` is **mock-only** (deterministic mock sequence). On prod, wait for a real TEST call.
- Do not point `OKTELL_MODE=prod` at production customer queues without marking.
- MRCP (FR-ASR-18) is a separate contingency path; this smoke covers WebSocket model T only.
