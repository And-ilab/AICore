# AI Hub backend

`hub` хранит редактируемые параметры ModelRegistry в таблице
`hub_modelregistrysettings`. YAML `config/model_registry.yaml` остаётся
источником первичных defaults и неизменяемых сведений о slot/model/status.

После обновления кода примените миграцию:

```powershell
python manage.py migrate
```

API формы:

```text
GET /api/admin/model-registry/model-params/?profile=assistant_bank
PUT /api/admin/model-registry/model-params/?profile=assistant_bank

GET /api/admin/model-registry/model-params/?profile=sufler_cc
PUT /api/admin/model-registry/model-params/?profile=sufler_cc
```

Backend повторно проверяет temperature, Top P, max tokens, длину ответа,
chunk/overlap и оба retrieval threshold. RBAC разделяет профили ассистента и
КЦ; frontend role switcher не влияет на API-права.
