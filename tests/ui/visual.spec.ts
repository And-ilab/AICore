import {
  expect,
  test,
  type Page,
} from '../../frontend/node_modules/@playwright/test/index.js'

const stories = [
  ['button-primary', 'foundation-button--primary'],
  ['card-default', 'foundation-card--default'],
  ['hint-card-compact', 'foundation-hintcard--compact'],
  ['hint-card-expanded', 'foundation-hintcard--expanded'],
  ['sidebar-default', 'foundation-sidebar--default'],
  ['fab-default', 'foundation-fab--default'],
  ['status-badge-success', 'foundation-statusbadge--success'],
  ['portal-launcher-menu', 'portal-launcher--menu-open'],
  ['admin-shell-default', 'ai-hub-admin-shell--default'],
  ['model-params-form', 'ai-hub-admin-shell--model-parameters'],
  ['ai-hub-panel-assistant', 'ai-hub-panel--default-assistant'],
  ['ai-hub-panel-call', 'ai-hub-panel--active-call'],
  ['sufler-phone-active', 'sufler-phone-window--active-call'],
  ['online-chat-arm-ii7', 'online-chat-arm--operator-workspace'],
] as const

async function openStory(page: Page, storyId: string) {
  await page.goto(`/iframe.html?id=${storyId}&viewMode=story`)
  await page.evaluate(() => document.fonts.ready)
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation: none !important;
        caret-color: transparent !important;
        transition: none !important;
      }
      body { background: #f5f7fb !important; }
    `,
  })
}

test('launcher opens both authorized module windows', async ({ page }) => {
  await openStory(page, 'portal-launcher--menu-open')
  await page.getByRole('menuitem', { name: /Суфлёр/ }).click()
  await page.getByTestId('launcher-button').click()
  await page.getByRole('menuitem', { name: /Ассистент/ }).click()

  await expect(page.getByTestId('sufler-window')).toBeVisible()
  await expect(page.getByTestId('assistant-window')).toBeVisible()
})

test('launcher is hidden for unauthorized role', async ({ page }) => {
  await openStory(page, 'portal-launcher--unauthorized')
  await expect(page.getByTestId('launcher-button')).toHaveCount(0)
  await expect(page.getByTestId('launcher-menu')).toHaveCount(0)
})

test('launcher module window can be resized', async ({ page }) => {
  await openStory(page, 'portal-launcher--menu-open')
  await page.getByRole('menuitem', { name: /Суфлёр/ }).click()

  const windowPanel = page.getByTestId('sufler-window')
  const handle = page.getByRole('button', {
    name: 'Изменить размер окна Суфлёр',
  })
  const before = await windowPanel.boundingBox()
  const handleBox = await handle.boundingBox()
  expect(before).not.toBeNull()
  expect(handleBox).not.toBeNull()

  await page.mouse.move(
    handleBox!.x + handleBox!.width / 2,
    handleBox!.y + handleBox!.height / 2,
  )
  await page.mouse.down()
  await page.mouse.move(
    handleBox!.x + handleBox!.width / 2 + 60,
    handleBox!.y + handleBox!.height / 2 + 40,
  )
  await page.mouse.up()

  const after = await windowPanel.boundingBox()
  expect(after!.width).toBeGreaterThan(before!.width)
  expect(after!.height).toBeGreaterThan(before!.height)
})

test('admin sidebar exposes all groups and routable screens', async ({ page }) => {
  await openStory(page, 'ai-hub-admin-shell--default')

  const sidebar = page.getByTestId('admin-sidebar')
  await expect(sidebar).toBeVisible()
  for (const group of ['ОБЩЕЕ', 'АССИСТЕНТ', 'СУФЛЁР / КЦ', 'ДОКУМЕНТЫ', 'ССЫЛКИ']) {
    await expect(sidebar.getByRole('heading', { name: group })).toBeAttached()
  }

  const links = sidebar.getByRole('link')
  await expect(links).toHaveCount(21)
  await expect(page.getByTestId('admin-save-footer')).toBeVisible()
  await expect(page.getByLabel('Демо роль')).toBeVisible()

  const routes = [
    'audit', 'llm_config_assistant', 'model_params', 'prompts_assistant',
    'capabilities', 'kb_admin', 'qu_admin', 'data_sources', 'assistant_tools',
    'monitoring', 'llm_config_cc', 'model_params/cc', 'scenario_editor',
    'scenario_test', 'scenario_bindings', 'sufler_policies', 'ocr', 'doc_types',
    'doc_export', 'external',
  ]
  for (const route of routes) {
    await sidebar.locator(`a[href="/ai-hub/admin/${route}"]`).click()
    const screenId = route === 'model_params/cc' ? 'model_params' : route
    await expect(page.locator(`[data-screen-id="${screenId}"]`)).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/ai-hub/admin/${route}$`))
  }
})

test('scenario catalog opens step editor, follows history and tests dialog', async ({ page }) => {
  const scenario = {
    code: 'CC-SCR-002',
    title: 'Счёт внуку, 6 лет',
    root_question: 'Хочу открыть счёт внуку, ему 6 лет',
    status: 'production',
    channels: 'both',
    version_number: 4,
    is_published: true,
    updated_at: '2026-08-22T10:00:00Z',
    updated_by: 'admin',
    system_prompt: '',
    graph: {
      nodes: [
        {
          id: 'start',
          type: 'start',
          label: 'Определить представителя',
          hint_text: 'Счёт ребёнку открывает законный представитель.',
          clarify_text: 'Вы являетесь законным представителем ребёнка?',
          examples: ['хочу открыть счёт внуку'],
          intent_id: 'CC-SCR-002',
          edges: [{ to: 'yes', label: 'Законный представитель', reply: 'Да, я его мама и законный представитель', keywords: ['мама', 'законный'] }],
        },
        {
          id: 'yes',
          type: 'end',
          label: 'Документы',
          hint_text: 'Возьмите паспорт и документ ребёнка.',
          clarify_text: '',
          examples: ['да'],
          intent_id: '',
          edges: [],
        },
      ],
    },
  }
  await page.route('**/api/admin/scenarios/**', async (route) => {
    const url = route.request().url()
    if (url.endsWith('/test-run/')) {
      const lines = route.request().postDataJSON().lines as string[]
      const second = lines.length > 1
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          code: scenario.code,
          title: scenario.title,
          version_number: 4,
          is_published: true,
          path: second ? ['Определить представителя', 'Документы'] : ['Определить представителя'],
          errors: [],
          ok: true,
          steps: lines.map((input, index) => ({
            index: index + 1,
            input,
            node_id: index ? 'yes' : 'start',
            label: index ? 'Документы' : 'Определить представителя',
            hint_text: index ? 'Возьмите паспорт и документ ребёнка.' : 'Счёт ребёнку открывает законный представитель.',
            clarify_text: index ? '' : 'Вы являетесь законным представителем ребёнка?',
            selected_edge: index ? 'Законный представитель' : '',
            available_choices: index ? [] : [{ label: 'Да', reply: 'Да, я законный представитель' }],
            terminal: Boolean(index),
            ok: true,
          })),
        }),
      })
      return
    }
    if (url.includes('/CC-SCR-002/')) {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(scenario) })
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ items: [scenario], counts: { total: 1, production: 1, draft: 0 } }),
    })
  })

  await openStory(page, 'ai-hub-admin-shell--default')
  await page.evaluate(() => { document.cookie = 'csrftoken=visual-test; path=/' })
  await page.locator('a[href="/ai-hub/admin/scenario_editor"]').click()
  await expect(page.getByTestId('scenario-bindings')).toBeVisible()
  const card = page.getByRole('button', { name: /Открыть сценарий CC-SCR-002/ })
  await expect(card).toBeVisible()
  await card.click()
  await expect(page.getByRole('heading', { name: 'Когда запускается этот шаг' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Что может ответить клиент' })).toBeVisible()
  await expect(page.getByLabel('Ответ клиента')).toHaveValue('Да, я его мама и законный представитель')
  await page.getByRole('button', { name: /Продолжение Документы/ }).click()
  await expect(page.getByLabel('Название шага 2')).toHaveValue('Документы')

  await page.goBack()
  await expect(page.getByTestId('scenario-bindings')).toBeVisible()
  await page.goForward()
  await expect(page.getByLabel('Название шага 1')).toHaveValue('Определить представителя')

  await page.getByRole('button', { name: 'Тестировать' }).click()
  await page.getByLabel('Следующая реплика клиента').fill('Хочу открыть счёт внуку')
  await page.getByRole('button', { name: 'Отправить' }).click()
  await expect(page.getByLabel('Тестовый диалог')).toContainText('Счёт ребёнку открывает законный представитель.')
  await page.getByLabel('Примеры вариантов ответа').getByRole('button', { name: 'Да, я законный представитель', exact: true }).click()
  await expect(page.getByLabel('Тестовый диалог')).toContainText('Сценарий окончен')
})

test('scenario creation waits for required fields and opens first step', async ({ page }) => {
  let createRequests = 0
  await page.route('**/api/admin/scenarios/**', async (route) => {
    if (route.request().method() === 'POST') {
      createRequests += 1
      const payload = route.request().postDataJSON()
      await route.fulfill({
        contentType: 'application/json',
        status: 201,
        body: JSON.stringify({
          ...payload,
          status: 'draft',
          version_number: 1,
          is_published: false,
          updated_at: '2026-08-22T12:00:00Z',
          updated_by: 'admin',
          system_prompt: '',
        }),
      })
      return
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ items: [], counts: { total: 0, production: 0, draft: 0 } }),
    })
  })

  await openStory(page, 'ai-hub-admin-shell--default')
  await page.evaluate(() => { document.cookie = 'csrftoken=visual-test; path=/' })
  await page.locator('a[href="/ai-hub/admin/scenario_bindings"]').click()
  await page.getByRole('button', { name: '+ Новый сценарий' }).click()

  const submit = page.getByRole('button', { name: 'Создать и настроить шаги →' })
  await expect(submit).toBeDisabled()
  expect(createRequests).toBe(0)
  await page.getByLabel('Название сценария *').fill('Проверка нового сценария')
  await page.getByLabel('Что говорит клиент в начале *').fill('Хочу уточнить условия')
  await expect(submit).toBeEnabled()
  await submit.click()

  await expect(page.getByLabel('Название шага 1')).toHaveValue('Начало разговора')
  await expect(page.getByRole('heading', { name: 'Что спрашивает оператор' })).toBeVisible()
  await expect(page.getByRole('button', { name: '+ Добавить вариант ответа' })).toBeVisible()
  expect(createRequests).toBe(1)
})

test('model params validates and saves through API', async ({ page }) => {
  await page.route('**/api/admin/model-registry/model-params/**', async (route) => {
    const payload = route.request().postDataJSON()
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        profile: 'assistant_bank',
        slot: 'llm_assistant_bank',
        ...payload,
        read_only: {
          dev_model: 'stub:assistant_bank',
          prod_candidate: null,
          status: 'approved_dev',
        },
        constraints: {
          temperature: { min: 0, max: 1, step: 0.01 },
          top_p: { min: 0.01, max: 1, step: 0.01 },
          max_tokens: { min: 1, max: 32768 },
          response_chars_max: { min: 1, max: 500 },
        },
        revision: 2,
        updated_at: '2026-07-20T12:30:00Z',
        updated_by: 'admin',
      }),
    })
  })
  await openStory(page, 'ai-hub-admin-shell--model-parameters')

  const overlap = page.getByLabel('Перекрытие фрагментов, токены')
  await overlap.fill('600')
  await expect(page.getByText('Перекрытие должно быть меньше размера фрагмента')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Сохранить' })).toBeDisabled()

  await overlap.fill('120')
  await page.getByLabel('Макс. токенов').fill('1536')
  await page.getByRole('button', { name: 'Сохранить' }).click()

  await expect(page.getByText('Сохранено · ревизия 2')).toBeVisible()
  await expect(page.getByLabel('Макс. токенов')).toHaveValue('1536')
})

test('QU admin previews ranked results with matched example', async ({ page }) => {
  await page.route('**/api/admin/qu/preview/', async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      query: 'оформление отпуска сотруднику',
      limit: 5,
    })
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        query: 'оформление отпуска сотруднику',
        kb_id: 'cc_production',
        min_relevance: 0.65,
        min_relevance_percent: 65,
        documents: [
          {
            rank: 1,
            article_id: 101,
            chunk_index: 0,
            title: 'Положение об отпусках',
            permalink: 'https://suz.local/articles/101',
            snippet: 'Правила оформления ежегодного оплачиваемого отпуска.',
            relevance_score: 0.92,
            relevance_percent: 92,
            meets_min_relevance: true,
            matched_example_id: 7,
            matched_example: 'Как оформить отпуск сотруднику?',
          },
        ],
      }),
    })
  })
  await openStory(page, 'ai-hub-admin-shell--qu-preview')

  await page.getByLabel('Запрос пользователя').fill('оформление отпуска сотруднику')
  await page.getByRole('button', { name: 'Предпросмотр' }).click()

  const results = page.getByRole('table')
  await expect(results).toBeVisible()
  await expect(results.getByText('Положение об отпусках')).toBeVisible()
  await expect(results.getByText('92%')).toBeVisible()
  await expect(results.getByText('Как оформить отпуск сотруднику?')).toBeVisible()
})

test('AI Hub panel hides tabs by RBAC', async ({ page }) => {
  await openStory(page, 'ai-hub-panel--documents-only')
  const tablist = page.getByRole('tablist', { name: 'Модули AI Hub' })

  await expect(tablist.getByRole('tab')).toHaveCount(1)
  await expect(tablist.getByRole('tab', { name: 'Документы' })).toBeVisible()
  await expect(tablist.getByRole('tab', { name: 'Ассистент' })).toHaveCount(0)
  await expect(tablist.getByRole('tab', { name: 'Суфлёр' })).toHaveCount(0)
})

test('OCR documents IV.3 upload → preview → edit with field confidence', async ({ page }) => {
  await openStory(page, 'ai-hub-panel--documents-upload-flow')
  await expect(page.getByTestId('ocr-documents-panel')).toBeVisible()

  const subTabs = page.getByRole('tablist', { name: 'Документы' })
  await expect(subTabs.getByRole('tab', { name: 'Очередь' })).toBeVisible()
  await expect(subTabs.getByRole('tab', { name: 'Загрузить' })).toHaveAttribute(
    'aria-selected',
    'true',
  )
  await expect(subTabs.getByRole('tab', { name: 'Проверка' })).toBeVisible()

  await expect(page.getByTestId('ocr-dropzone')).toBeVisible()
  await page.getByTestId('ocr-file-input').setInputFiles({
    name: 'passport_demo.png',
    mimeType: 'image/png',
    buffer: Buffer.from('fake-passport-scan'),
  })
  await expect(page.getByTestId('ocr-pending-batch')).toContainText('passport_demo.png')

  await page.getByTestId('ocr-start-recognition').click()
  await expect(page.getByTestId('ocr-review')).toBeVisible()
  await expect(page.getByTestId('ocr-bbox-viewer')).toContainText('passport_demo.png')

  await expect(page.getByTestId('ocr-field-editor')).toBeVisible()
  await expect(page.getByTestId('ocr-field-confidence-fio')).toHaveText('96%')
  await expect(page.getByTestId('ocr-field-confidence-number')).toHaveText('72%')
  await expect(page.getByTestId('ocr-field-confidence-issued')).toHaveText('54%')

  const fioInput = page.getByTestId('ocr-field-input-fio')
  await fioInput.fill('Иванов Иван Петрович')
  await expect(fioInput).toHaveValue('Иванов Иван Петрович')
  await page.getByTestId('ocr-field-input-number').click()
  await expect(page.getByTestId('ocr-field-input-number')).toBeFocused()

  await page.getByTestId('ocr-approve-export').click()
  await expect(page.getByTestId('ocr-approved-badge')).toContainText('Подтверждено')

  await subTabs.getByRole('tab', { name: 'Очередь' }).click()
  await expect(page.getByTestId('ocr-queue-table')).toContainText('passport_demo.png')
  await expect(page.getByTestId('ocr-queue-table')).toContainText('Готово')
})

test('active call locks AI Hub to Sufler and controls work', async ({ page }) => {
  await openStory(page, 'ai-hub-panel--active-call')
  const tablist = page.getByRole('tablist', { name: 'Модули AI Hub' })

  await expect(tablist.getByRole('tab')).toHaveCount(1)
  await expect(tablist.getByRole('tab', { name: /Суфлёр/ })).toBeVisible()
  await expect(page.getByText('Активный звонок')).toBeVisible()

  const hint = page.getByRole('button', { name: /Повышение лимита перевода/ })
  await hint.click()
  await expect(hint).toHaveAttribute('aria-expanded', 'true')

  await page.getByRole('button', { name: 'Закрепить панель' }).click()
  await expect(page.getByRole('button', { name: 'Открепить панель' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Свернуть панель' }).click()
  await expect(page.getByTestId('hub-panel')).toHaveCount(0)
  await page.getByTestId('hub-panel-fab').click()
  await expect(page.getByTestId('hub-panel')).toBeVisible()
  await page.getByRole('button', { name: 'Закрыть панель' }).click()
  await expect(page.getByTestId('hub-panel')).toHaveCount(0)
})

test('telephony sufler shows transcript hints with relevance and SUZ link', async ({ page }) => {
  await openStory(page, 'sufler-phone-window--active-call')
  await expect(page.getByTestId('sufler-phone-app')).toBeVisible()
  await expect(page.getByText('ASR активен')).toBeVisible()
  await expect(page.getByTestId('hints-t1')).toBeVisible()

  const hint = page.getByTestId('hint-t1-1')
  await expect(hint).toBeVisible()
  await expect(hint.getByText('96%')).toBeVisible()
  await hint.focus()
  await expect(hint).toHaveAttribute('aria-expanded', 'true')
  await expect(hint.getByRole('link', { name: /Оформление банковской карты/ })).toBeVisible()
})

test('online-chat ARM II-7 shows sufler side panel HintCard on client message', async ({ page }) => {
  await openStory(page, 'online-chat-arm--operator-workspace')
  await expect(page.getByTestId('chat-arm-app')).toBeVisible()
  await expect(page.getByTestId('sufler-side-panel')).toBeVisible()
  await expect(page.getByTestId('msg-t1-client')).toContainText('лимит снятия')
  await expect(page.getByTestId('sufler-hints')).toBeVisible()

  const hint = page.getByTestId('chat-hint-1')
  await expect(hint).toBeVisible()
  await expect(hint.getByText('94%')).toBeVisible()
  await hint.focus()
  await expect(hint).toHaveAttribute('aria-expanded', 'true')
  await expect(hint.getByRole('link', { name: /Лимиты снятия наличных/ })).toBeVisible()
  await expect(hint.getByRole('button', { name: 'Вставить в ответ' })).toBeVisible()
  await hint.getByRole('button', { name: 'Вставить в ответ' }).click()
  await expect(page.getByTestId('chat-composer')).toHaveValue(/2 000 BYN/)
})

test('online-chat operator sees queue sections and can switch 9 statuses', async ({ page }) => {
  await openStory(page, 'online-chat-arm--operator-workspace')
  await expect(page.getByTestId('queue-panel')).toBeVisible()
  await expect(page.getByTestId('queue-section-waiting')).toBeVisible()
  await expect(page.getByTestId('queue-1')).toContainText('Анна Козлова')
  await expect(page.getByTestId('queue-total')).toContainText('в очередях: 9')

  const statuses = page.getByTestId('operator-status-selector')
  await expect(statuses).toBeVisible()
  await expect(statuses.getByRole('radio')).toHaveCount(9)
  await expect(page.getByTestId('operator-status-online')).toHaveAttribute(
    'aria-checked',
    'true',
  )

  await page.getByTestId('operator-status-lunch').click()
  await expect(page.getByTestId('operator-status-lunch')).toHaveAttribute(
    'aria-checked',
    'true',
  )
  await expect(page.getByTestId('status-routing-hint')).toBeVisible()

  await page.getByTestId('queue-m1').click()
  await expect(page.getByTestId('chat-messages')).toContainText('SWIFT')
  await expect(page.getByRole('heading', { name: 'Светлана Р.' })).toBeVisible()
})

test('internal KC test dialog matches II-KC layout and returns relevance', async ({ page }) => {
  await openStory(page, 'internal-kc-test-dialog--prompt-harness')
  await expect(page.getByTestId('internal-kc-app')).toBeVisible()
  await expect(page.getByTestId('ikc-window')).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Тест-диалог · внутренний пользователь КЦ' }),
  ).toBeVisible()
  await expect(page.getByTestId('ikc-scenario')).toHaveValue('CC-SCR-008')
  await expect(page.getByTestId('ikc-prompt')).toHaveValue('sufler_cc')
  await expect(page.getByTestId('ikc-history')).toContainText('Запрос · 10:14')
  await expect(page.getByTestId('relevance-turn-1')).toHaveText('91%')

  await page.getByTestId('ikc-draft').fill('А какие документы нужны для открытия вклада?')
  await page.getByTestId('ikc-send').click()

  const latestRelevance = page.locator('[data-testid^="relevance-turn-"]').last()
  await expect(latestRelevance).toHaveText('89%')
  await expect(page.getByTestId('ikc-history')).toContainText('паспорт и заявление')
  await expect(page.getByTestId('ikc-history')).toContainText('Эталон QU')
})

test('assistant window III.3 streams tokens, shows tools and feedback', async ({ page }) => {
  await openStory(page, 'assistant-window--chat-with-sources')
  await expect(page.getByTestId('assistant-window-app')).toBeVisible()
  await expect(page.getByTestId('assistant-window')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'ИИ-ассистент' })).toBeVisible()
  await expect(page.getByTestId('asst-lenta')).toContainText('Как оформить отпуск?')
  await expect(page.getByTestId('asst-lenta')).toContainText('Источники (2)')

  await expect(page.getByTestId('asst-tools-panel')).toHaveCount(0)
  await page.getByTestId('asst-composer-tools').click()
  await expect(page.getByTestId('asst-tools-panel')).toBeVisible()
  await expect(page.getByTestId('tool-state-sql')).toContainText('SQL')
  await page.getByTestId('tool-run-sql').click()
  await expect(page.getByTestId('asst-sandbox-modal')).toBeVisible()
  await expect(page.getByRole('dialog', { name: 'Текст SQL-запроса' })).toBeVisible()
  await page.getByRole('button', { name: 'Отмена' }).click()
  await expect(page.getByTestId('asst-sandbox-modal')).toHaveCount(0)
  await expect(page.getByTestId('asst-tools-panel')).toHaveCount(0)

  const seedFeedback = page.locator('[data-testid^="feedback-useful-"]').first()
  await seedFeedback.click()
  await expect(page.getByText('Оценка сохранена')).toBeVisible()
  await expect(page.locator('[data-testid^="feedback-useful-"]')).toHaveCount(0)
  await expect(page.locator('[data-testid^="feedback-incomplete-"]')).toHaveCount(0)
  await expect(page.locator('[data-testid^="feedback-incorrect-"]')).toHaveCount(0)

  await page.getByTestId('asst-draft').fill('Нужна справка о вкладе')
  await page.getByTestId('asst-send').click()
  await expect(page.getByTestId('asst-streaming-flag')).toBeVisible()
  await expect(page.getByTestId('asst-lenta')).toContainText(
    'Ответ ассистента: запрос принят',
    { timeout: 5000 },
  )
  await expect(page.getByTestId('asst-streaming-flag')).toHaveCount(0)
})

test('assistant slash picker selects SKL-01 chip and CRUD personal skill', async ({ page }) => {
  await openStory(page, 'assistant-window--chat-with-sources')
  await expect(page.getByTestId('asst-draft')).toBeVisible()

  await page.getByTestId('asst-draft').fill('/за')
  await expect(page.getByTestId('asst-skill-picker')).toBeVisible()
  await expect(page.getByTestId('asst-skill-skl-01')).toBeVisible()
  await expect(page.getByTestId('asst-skill-skl-01')).toContainText('записка')
  await page.getByTestId('asst-skill-skl-01').click()
  await expect(page.getByTestId('asst-skill-chip')).toBeVisible()
  await expect(page.getByTestId('asst-skill-chip')).toContainText('/записка')
  await expect(page.getByTestId('asst-skill-chip')).not.toContainText('SKL-01')

  await page.getByTestId('asst-my-skills').click()
  await expect(page.getByTestId('asst-my-skills-panel')).toBeVisible()
  await page.getByTestId('asst-my-skill-add').click()
  await expect(page.getByTestId('asst-my-skill-name')).toHaveValue('Мой навык')
  await page.getByTestId('asst-my-skill-name').fill('Личный тон')
  await page.getByTestId('asst-my-skill-alias').fill('lichny')
  await page.getByTestId('asst-my-skill-instruction').fill('Отвечай коротко.')
  await page.getByTestId('asst-my-skill-save').click()
  await page.getByTestId('asst-my-skills-close').click()

  await page.getByTestId('asst-draft').fill('/li')
  await expect(page.getByTestId('asst-skill-picker')).toBeVisible()
  await expect(page.getByTestId('asst-skill-mine-lichny')).toBeVisible()
  await page.getByTestId('asst-skill-mine-lichny').click()
  await expect(page.getByTestId('asst-skill-chip')).toContainText('lichny')
})

for (const [snapshotName, storyId] of stories) {
  test(snapshotName, async ({ page }) => {
    await openStory(page, storyId)
    const story = page.locator('#storybook-root')
    await expect(story).toBeVisible()
    await expect(story).toHaveScreenshot(`${snapshotName}.png`, {
      animations: 'disabled',
      scale: 'css',
    })
  })
}
