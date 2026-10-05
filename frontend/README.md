# Frontend foundation

Базовый UI-слой Суфлёра: Vite, React, TypeScript, Tailwind CSS, Storybook и
визуальные тесты Playwright.

## Требования

- актуальная LTS-версия Node.js;
- npm из поставки Node.js.

## Docker

Вместе с backend-стеком:

```powershell
cd ../infra
docker compose up --build -d
```

UI: <http://localhost:5173/>. Прокси `/api` → сервис `backend:8000`.
Переменные `FRONTEND_PORT_HOST` и `VITE_DEV_RBAC_ROLES` — в `infra/.env`.

Для bank TEST (prod-like): `frontend/Dockerfile.prod` + `nginx.prod.conf`
собирают static build и проксируют `/api` на Daphne — см.
[`infra/test/README.md`](../infra/test/README.md).

## Команды

```bash
npm install
npm run dev
npm run lint
npm run build
```

Storybook:

```bash
npm run storybook
npm run build-storybook
```

Визуальные тесты:

```bash
npm run playwright:install
npm run test:visual              # все UI Playwright-проекты (ui + visual)
npm run test:visual:canvas       # только canvas-registry (P8-09 / project=visual)
npm run test:visual:update       # обновить baseline PNG для canvas-registry
```

### Обновление baseline (P8-09)

CI job **`ui-visual`** гоняет `playwright test --project=visual` по каждому
экрану из [`docs/ui/canvas-registry.yaml`](../docs/ui/canvas-registry.yaml).
Сравнение с эталоном: **`maxDiffPixelRatio = 0.001` (0.1%)** — больший diff
валит сборку.

Обновлять PNG только после осознанного изменения UI / canvas:

1. Убедиться, что Storybook story из `visual.story_id` отражает целевой экран.
2. Из `frontend/` обновить эталоны **в Linux** (как CI `ubuntu-latest`), чтобы
   не ловить OS-diff шрифтов:
   ```bash
   # предпочтительно — тот же образ, что Playwright CI
   docker run --rm -e CI=true -v "${PWD}/..:/work" -w /work/frontend `
     mcr.microsoft.com/playwright:v1.61.1-jammy `
     npx playwright test --project=visual --update-snapshots
   ```
   Локально (Windows) допустимо только для быстрой проверки:
   ```bash
   npm run test:visual:update
   ```
3. Просмотреть diff в `tests/ui/visual/__snapshots__/` (и Playwright report).
4. Закоммитить обновлённые PNG вместе с UI-изменением.
5. Если добавили canvas в registry — перегенерировать specs:
   ```bash
   python tests/ui/visual/generate_from_registry.py
   ```

`test:visual:update` без review PNG в PR считается ошибкой. Baseline для CI
должен быть снят в Linux (Docker-команда выше).

Specs: `tests/ui/visual/<task_id>.spec.ts`. Эталоны:
`tests/ui/visual/__snapshots__/`.

## Структура

- `src/tokens.css` — брендовые, семантические, spacing и shadow tokens;
- `src/components` — компоненты, их стили, barrel export и stories;
- `.storybook` — конфигурация каталога компонентов;
- `../tests/ui` — Playwright UI tests; `../tests/ui/visual` — canvas-registry baselines (P8-09);
- `public/assets` — статические канонические assets.

Обязательные брендовые значения определены только через tokens:
`--color-primary: #0D3880`, `--color-primary-dark: #0A2A66`,
`--color-secondary: #E31E24`, `--radius: 8px`.

Логотип `public/assets/belarusbank-logo.png` скопирован из канонического
`canvases/assets/belarusbank-logo.png`. Канонический PNG извлечён без
преобразований из `BELARUSBANK_LOGO_DATA_URL` в
`canvases/online-chat-mockups.canvas.tsx`; исходный canvas не изменяется.

## UI WORKFLOW

1. Проверить требования в `docs/ui` и актуальную спецификацию v1.4.
2. Добавить или уточнить tokens, не встраивая брендовые цвета в компоненты.
3. Реализовать доступный типизированный компонент в `src/components`.
4. Добавить отдельную Storybook story для состояний компонента.
5. Создать или осознанно обновить visual baseline.
6. На PR review проверить API, доступность, stories и PNG-diff.

Изменение baseline без соответствующего изменения компонента или tokens
считается ошибкой. Генерируемые `storybook-static`, `node_modules`,
Playwright reports и test results не коммитятся.

## Портальный launcher I-0

`src/components/PortalLauncher.tsx` реализует основной вариант I.5:

- кнопка AI 56×56 px в правом нижнем углу;
- меню выбора «Суфлёр | Ассистент»;
- одновременное открытие двух независимых окон;
- сворачивание, закрытие, разворачивание и drag-resize окон;
- standalone routes `/sufler` и `/assistant`;
- скрытие launcher и защита routes по ролям I.4.

В приложении роли загружаются из `GET /api/auth/me/`. Vite проксирует `/api`
на Django `http://127.0.0.1:8000`. Если backend недоступен или пользователь не
авторизован, launcher не отображается. Только для локальной разработки можно
задать роли через запятую:

```powershell
$env:VITE_DEV_RBAC_ROLES="contact_center_telephony_operator"
npm run dev
```

Storybook states:

- `Portal/Launcher / Menu Open` — visual baseline I-0;
- `Portal/Launcher / Both Windows` — параллельная работа;
- `Portal/Launcher / Unauthorized` — RBAC-hidden state.

Baseline `tests/ui/__snapshots__/portal-launcher-menu.png` обновляется только
через `npm run test:visual:update` после проверки canvas I-0 и PNG diff.

## Admin center

Маршрут `/ai-hub/admin/` реализован в `src/ai-hub/admin/` по
`ai-hub-settings-mockup`: полноэкранная оболочка, sidebar 240 px с группами,
breadcrumbs и sticky footer «Сохранить». Все 18 screen id доступны как
`/ai-hub/admin/<screen_id>`; профиль КЦ параметров модели использует
`/ai-hub/admin/model_params/cc`.

Production-навигация фильтруется по административным ролям I.4. Переключатель
«Демо роль» включён только в dev/Storybook и не повышает реальные права.
Story `AI Hub/Admin Shell / Default` является основой visual review для
последующих задач P2-04, P3-03, P3-05, P4-03, P4-07 и P5-03.

Экран `Параметры модели LLM` использует API
`/api/admin/model-registry/model-params/`. Форма содержит sliders generation,
chunk/overlap и retrieval thresholds, показывает inline validation и сохраняет
данные в Django DB. Story `AI Hub/Admin Shell / Model Parameters` и baseline
`model-params-form.png` фиксируют layout.

## AI Hub panel

Маршрут `/ai-hub` рендерит host из `src/ai-hub/panel/`: FAB 56 px,
slide-in panel 400 px, pin/minimize/close и вкладки «Ассистент», «Документы»,
«Суфлёр». Вкладки скрываются по I.4 RBAC; `sufler_chat` не даёт вкладку Hub.
При `callActive` tab bar блокируется на единственной вкладке «Суфлёр».

Storybook states: default assistant, documents-only, active call и closed FAB.
HintCard в «Суфлёре» использует общий compact/expand-in-place pattern.
