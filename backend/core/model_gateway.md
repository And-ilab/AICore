# ModelGateway

`model_gateway.py` is the only application-level entry point for LLM calls.
Feature modules select a logical profile and do not import a vendor SDK.

ModelRegistry mapping:

- `sufler_cc` → `llm_sufler_cc`;
- `assistant_bank` → `llm_assistant_bank`;
- `docs_ocr` → `llm_docs_ocr`.

Each slot provides `dev_model`, `prod_candidate`, `kpi.profile`,
`kpi.gateway_mode`, and `kpi.api_compatibility`. The gateway validates this
mapping on every profile lookup.

## Dev stub

The registry defaults to `gateway_mode: stub`. No network request or API key
is required:

```python
from core.model_gateway import ModelGateway

gateway = ModelGateway.from_registry()
response = gateway.chat(
    "sufler_cc",
    [{"role": "user", "content": "Как изменить ПИН-код?"}],
)
text = response["choices"][0]["message"]["content"]
```

The three profiles return different canned responses. `docs_ocr` returns a
JSON string with placeholder structured fields.

SSE stub:

```python
for event in gateway.stream(
    "assistant_bank",
    [{"role": "user", "content": "Нужна справка"}],
):
    send_to_http_client(event)
```

Every item is a complete SSE frame (`data: {...}\n\n`); the final frame is
`data: [DONE]\n\n`.

## OpenAI-compatible mode

Configure the slot with a real `dev_model` or `prod_candidate` and
`gateway_mode: openai`, then provide:

```text
OPENAI_BASE_URL=http://llm.internal/v1
OPENAI_API_KEY=<secret, when required>
```

The gateway sends `POST <base>/chat/completions`. `chat()` returns the
endpoint JSON unchanged. `stream()` forwards OpenAI-compatible `data:` SSE
frames. The API key is read from the environment and must not be committed to
ModelRegistry.

A process-level override is also available for tests or controlled startup:

```python
gateway = ModelGateway.from_registry(
    mode="openai",
    base_url="http://llm.internal/v1",
)
```

Vendor replacement requires only an OpenAI-compatible endpoint and a
ModelRegistry model change; callers keep the same profile and interface.
