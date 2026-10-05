import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from 'react'
import { ensureDevSession, resetDevSessionCache } from '../../auth/ensureDevSession'
import { Button, Card, StatusBadge } from '../../components'
import {
  ModelParamsScreen,
  type ModelParamsScreenHandle,
} from './ModelParamsScreen'
import {
  SuflerPoliciesScreen,
  type SuflerPoliciesScreenHandle,
} from './SuflerPoliciesScreen'
import { QuPreviewScreen } from './QuPreviewScreen'
import { KbAdminScreen } from './KbAdminScreen'
import { PromptsAssistantScreen } from './PromptsAssistantScreen'
import { CapabilitiesScreen } from './CapabilitiesScreen'
import { AssistantToolsScreen } from './AssistantToolsScreen'
import { DocTypesScreen } from './DocTypesScreen'
import { OcrDocumentsPanel } from '../ocr/OcrDocumentsPanel'
import { CcReportsScreen } from '../reports/CcReportsScreen'
import { AsrQaScreen } from '../reports/AsrQaScreen'
import { ScenarioEditorScreen } from './ScenarioEditorScreen'
import { ScenarioTestScreen } from './ScenarioTestScreen'
import { ScenarioBindingsScreen } from './ScenarioBindingsScreen'
import '../reports/ReportsTheme.css'
import type { ModelParamsData } from './api/modelRegistry'
import {
  ADMIN_GROUPS,
  ADMIN_NAV,
  adminRoute,
  defaultAdminScreen,
  isAdminReportsOnlyRole,
  resolveAdminRoute,
  type AdminNavItem,
  type AdminProfile,
  type AdminScreen,
  type DemoAdminRole,
} from './adminNav'
import { useAiHubColorTheme } from '../colorTheme'
import './AiHubAdmin.css'

interface AiHubAdminAppProps {
  roles: readonly string[]
  initialScreen?: AdminScreen
  initialProfile?: AdminProfile
  initialModelParams?: ModelParamsData
  demoRoleSwitcher?: boolean
  /** Storybook/visual: skip Django login gate (no API in iframe). */
  skipSessionBootstrap?: boolean
}

interface ScreenCopy {
  title: string
  subtitle: string
  status: string
  cards: readonly [string, string, string][]
}

const SCREEN_COPY: Record<AdminScreen, ScreenCopy> = {
  audit: {
    title: 'Подразделения и журнал',
    subtitle: 'Область подразделений, роли и единый журнал изменений настроек.',
    status: 'Аудит включён',
    cards: [['Подразделения', '12', 'Активные области'], ['Изменения', '28', 'За последние 7 дней'], ['Ожидают проверки', '3', 'Запросы доступа']],
  },
  llm_config_assistant: {
    title: 'Конфигурация LLM',
    subtitle: 'Профиль ассистента банка, резервная модель и контроль доступности.',
    status: 'Утверждено (тест)',
    cards: [
      ['Основная модель', 'stub-assistant-bank', 'Реестр моделей'],
      ['Резервная модель', 'Включён', 'Совместимо с OpenAI'],
      ['Доступность', '99.9%', 'Последние 24 часа'],
    ],
  },
  model_params: {
    title: 'Параметры модели LLM',
    subtitle: 'Генерация · RAG / индексация · preset по умолчанию / подробнее',
    status: 'Черновик',
    cards: [['Температура', '0.35', 'Генерация'], ['Preset', 'Стандарт', '§3.3.2'], ['Контекст', '≥8200', 'read-only']],
  },
  prompts_assistant: {
    title: 'Промпты ассистента',
    subtitle: 'Библиотека системных, рабочих и областных промптов профиля ассистента.',
    status: 'Редактирование',
    cards: [['Промпты', 'assistant_*', 'Отдельно от КЦ'], ['Студия', '3 колонки', 'Библиотека · Редактор · Просмотр'], ['Публикация', 'черновик → vN', 'Журнал «Общее»']],
  },
  capabilities: {
    title: 'Навыки и инструменты',
    subtitle: 'Навыки · промпты типа Task · deep link на детальные экраны',
    status: 'Черновой реестр',
    cards: [['Навыки', '9', 'Карточки'], ['Task-промпты', '6', 'События'], ['Политики', 'III.6.5', 'SQL только чтение']],
  },
  kb_admin: {
    title: 'Базы знаний',
    subtitle: 'CRUD · scope AD · индексация и webhook СУЗ',
    status: 'Индекс актуален',
    cards: [['Индекс', '98%', 'Выбранная БЗ'], ['Документов', '1 240', 'В выбранной БЗ'], ['Webhook СУЗ', 'OK', 'Битрикс']],
  },
  qu_admin: {
    title: 'Модуль понимания',
    subtitle: '',
    status: 'Модуль понимания',
    cards: [['Выборка', '', ''], ['Модерация', '', ''], ['Предпросмотр', '', '']],
  },
  data_sources: {
    title: 'Источники данных',
    subtitle: 'Адаптеры внешних систем. Базы знаний СУЗ и ручная загрузка — в разделе «Базы знаний».',
    status: 'Адаптеры',
    cards: [['CRM', 'В сети', 'read-only'], ['Файловый каталог', 'В сети', 'Синхронизация 5 мин'], ['HR API', 'На проверке', 'Тестовый контур']],
  },
  assistant_tools: {
    title: 'Инструменты ассистента',
    subtitle: 'Библиотека бланков банка (Word/PDF/Excel/PPT/BPMN), RPA и SQL.',
    status: 'Шаблоны UC-ASS-05',
    cards: [['RPA', '—', 'Следующий этап'], ['Шаблоны', 'CRUD', 'Активные бланки'], ['SQL', '—', 'Только чтение']],
  },
  monitoring: {
    title: 'Мониторинг ассистента',
    subtitle: 'Качество ответов, полезность, ошибки и галлюцинации.',
    status: 'Данные за 24 ч',
    cards: [['Полезность', '87%', 'Оценки пользователей'], ['Ошибочные ответы', '1.8%', 'Ручная разметка'], ['Галлюцинации', '2.1%', 'Цель ≤3%']],
  },
  llm_config_cc: {
    title: 'Конфигурация LLM КЦ',
    subtitle: 'Профиль суфлёра КЦ для подсказок операторам контакт-центра.',
    status: 'Утверждено (тест)',
    cards: [
      ['Основная модель', 'stub-sufler-cc', 'Реестр моделей'],
      ['Ответ', '≤500 симв.', 'Лимит ответа'],
      ['Задержка', '1–2 с', 'Целевой показатель'],
    ],
  },
  scenario_editor: {
    title: 'Настройка сценария',
    subtitle: 'Пошаговая настройка реплик клиента, ответов оператора и продолжений.',
    status: 'Редактор',
    cards: [['Опубликовано', '47', 'Рабочий контур'], ['Черновики', '5', 'Ожидают проверки'], ['Покрытие', '94%', 'Сценарии КЦ']],
  },
  scenario_test: {
    title: 'Тест сценария',
    subtitle: 'Интерактивное прохождение диалога по репликам клиента.',
    status: 'Песочница',
    cards: [['Ветки', '12 / 12', 'Пройдено'], ['Среднее время', '1.4 с', 'Ответ узла'], ['Ошибки', '0', 'Последний прогон']],
  },
  scenario_bindings: {
    title: 'Сценарии суфлёра',
    subtitle: 'Выберите сценарий, чтобы посмотреть или изменить разговор по шагам.',
    status: 'Каталог',
    cards: [['Телефония', '18', 'Активные'], ['Онлайн-чат', '14', 'Активные'], ['Внутренний КЦ', '6', 'Тестовые']],
  },
  sufler_policies: {
    title: 'Политики суфлёра',
    subtitle: 'Порог релевантности, лимит карточек и режим Консультация / Услуга.',
    status: 'Политика суфлёра',
    cards: [['Порог подсказки', '20%', 'Оператор'], ['Макс. карточек', '1–5', 'На одну реплику'], ['Режим', 'Консультация', 'По умолчанию']],
  },
  sufler_stats: {
    title: 'Статистика суфлёра',
    subtitle: 'Отчётность КЦ: полезность по отметкам «Воспользовался / Неполный / Не воспользовался».',
    status: 'Отчётность КЦ',
    cards: [['Полезность', 'pie', 'FR-RPT-CC-08'], ['Релевантность', 'каналы', 'FR-RPT-CC-07'], ['Слабые', 'таблица', 'Не воспользовался']],
  },
  sufler_training: {
    title: 'Модуль обучения',
    subtitle: '',
    status: 'Модуль обучения',
    cards: [['Очередь', '', ''], ['Эталон', '', ''], ['Обучение', '', '']],
  },
  ocr: {
    title: 'OCR',
    subtitle: 'Загрузка документов, очередь распознавания и проверка полей (HITL).',
    status: 'Модуль OCR',
    cards: [['Очередь', 'Задачи', 'В работе'], ['Загрузка', 'PDF / JPG / PNG', 'Пакетно'], ['Проверка', 'HITL', 'Поля и %']],
  },
  doc_types: {
    title: 'Типы документов',
    subtitle: 'Какие поля обязательны после распознавания.',
    status: '8 типов',
    cards: [['Кредитная заявка', '24 поля', 'Активна'], ['Паспорт', '12 полей', 'Активен'], ['Справка о доходах', '16 полей', 'Черновик']],
  },
  doc_export: {
    title: 'Экспорт документов',
    subtitle: 'Маршруты выгрузки проверенного JSON и статусы интеграций.',
    status: 'Очередь пуста',
    cards: [['JSON API', 'В сети', 'Основной канал'], ['Архив', 'В сети', 'Изолированное хранилище'], ['Ошибки', '0', 'За 24 часа']],
  },
  external: {
    title: 'Внешние системы',
    subtitle: 'Статус Bitrix24, онлайн-чата, Oktell и других интеграций.',
    status: '3 в сети',
    cards: [['Bitrix24', 'В сети', 'Адаптер CRM'], ['Онлайн-чат', 'В сети', 'Webhook'], ['Oktell', 'Имитация', 'WebSocket / MRCP']],
  },
  asr_qa: {
    title: 'QA записей ASR',
    subtitle: 'Каталог записей, аудиоплеер и синхронный транскрипт для аналитика КЦ.',
    status: 'Контроль качества ASR',
    cards: [['Каталог', 'Все записи', 'Хранение 1 год'], ['Фильтры', 'Опционально', 'Низкая уверенность'], ['Учебные', 'Кандидаты', 'Дообучение ASR']],
  },
  cc_reports: {
    title: 'Отчётность КЦ',
    subtitle: 'Таблицы, фильтры периода, экспорт CSV/XLSX и графики ASR.',
    status: 'Отчёты КЦ',
    cards: [['Аналитика', 'Черновой ETL', 'Статистика ASR'], ['Экспорт', 'CSV / XLSX', 'UTF-8'], ['Графики', 'Качество ASR', 'Распознавание']],
  },
  ocr_reports: {
    title: 'Отчётность OCR',
    subtitle: 'Сводки по объёму, качеству HITL и экспорту документов (§6.2).',
    status: 'Отчёты OCR',
    cards: [['Документы', '1 240', 'За период'], ['HITL', '4.2%', 'Доля ручной проверки'], ['Экспорт', 'CSV / PDF', 'Конструктор']],
  },
}

const DEMO_ROLE_LABELS: Record<DemoAdminRole, string> = {
  software_admin: 'Админ ПО',
  kb_admin: 'Админ БЗ',
  cc_admin: 'Админ сценариев / КЦ',
  doc_admin: 'Админ OCR',
  auditor: 'Аудитор (чтение)',
}

function demoCanEdit(role: DemoAdminRole, item?: AdminNavItem): boolean {
  if (role === 'software_admin') return true
  if (!item || role === 'auditor') return false
  if (item.group === 'АССИСТЕНТ') return role === 'kb_admin'
  if (item.group === 'СУФЛЁР / КЦ') return role === 'cc_admin' || role === 'kb_admin'
  if (item.group === 'ДОКУМЕНТЫ') return role === 'doc_admin'
  return item.demoRoles.includes(role)
}

function demoRoleFromAuth(roles: readonly string[]): DemoAdminRole {
  if (roles.includes('software_administrator')) return 'software_admin'
  if (roles.includes('contact_center_module_administrator')) return 'cc_admin'
  if (roles.includes('document_recognition_module_administrator')) return 'doc_admin'
  if (
    roles.includes('llm_knowledge_base_administrator')
    || roles.includes('ai_assistant_module_administrator')
  ) {
    return 'kb_admin'
  }
  return 'software_admin'
}

function hasRole(roles: readonly string[], item: AdminNavItem): boolean {
  return item.roleCodes.some((role) => roles.includes(role))
}

export function AiHubAdminApp({
  roles,
  initialScreen,
  initialProfile,
  initialModelParams,
  demoRoleSwitcher = false,
  skipSessionBootstrap = false,
}: AiHubAdminAppProps) {
  const resolved = resolveAdminRoute(window.location.pathname)
  const pathIsAdminRoot =
    window.location.pathname.replace(/\/+$/, '') === '/ai-hub/admin'
  const fallbackScreen = pathIsAdminRoot
    ? defaultAdminScreen(roles)
    : resolved.screen
  const [screen, setScreen] = useState(initialScreen ?? fallbackScreen)
  const [profile, setProfile] = useState(initialProfile ?? resolved.profile)
  const [testScenarioCode, setTestScenarioCode] = useState('')
  const [selectedScenarioCode, setSelectedScenarioCode] = useState(
    () => new URLSearchParams(window.location.search).get('scenario') ?? '',
  )
  const [demoRole, setDemoRole] = useState<DemoAdminRole>(() => demoRoleFromAuth(roles))
  const [saved, setSaved] = useState(false)
  const emptyFormState = {
    dirty: false,
    valid: false,
    saving: false,
    message: '',
  }
  const modelParamsRef = useRef<ModelParamsScreenHandle>(null)
  const suflerPoliciesRef = useRef<SuflerPoliciesScreenHandle>(null)
  const [modelFormState, setModelFormState] = useState(emptyFormState)
  const [policiesFormState, setPoliciesFormState] = useState(emptyFormState)
  const handleModelFormState = useCallback(
    (state: typeof modelFormState) => setModelFormState(state),
    [],
  )
  const handlePoliciesFormState = useCallback(
    (state: typeof policiesFormState) => setPoliciesFormState(state),
    [],
  )

  const [sessionReady, setSessionReady] = useState(skipSessionBootstrap)
  const [sessionError, setSessionError] = useState('')
  const { theme: colorTheme } = useAiHubColorTheme()

  useEffect(() => {
    if (skipSessionBootstrap) return
    let cancelled = false
    void (async () => {
      // Single bootstrap for the admin shell — child screens share the session.
      const ok = await ensureDevSession()
      if (cancelled) return
      if (!ok) {
        resetDevSessionCache()
        const retry = await ensureDevSession()
        if (cancelled) return
        if (!retry) {
          setSessionError(
            'Не удалось войти в Django (dev-role-01). Проверьте API :8001 и что VITE_DEV_AUTH_PASSWORD = AUTH_MOCK_LDAP_DEFAULT_PASSWORD.',
          )
          setSessionReady(false)
          return
        }
      }
      setSessionError('')
      setSessionReady(true)
    })()
    return () => {
      cancelled = true
    }
  }, [skipSessionBootstrap])

  useEffect(() => {
    const syncFromLocation = () => {
      const route = resolveAdminRoute(window.location.pathname)
      const isRoot = window.location.pathname.replace(/\/+$/, '') === '/ai-hub/admin'
      const nextScreen = isRoot ? defaultAdminScreen(roles) : route.screen
      const scenarioCode = new URLSearchParams(window.location.search).get('scenario') ?? ''
      setScreen(nextScreen)
      setProfile(route.profile)
      setSelectedScenarioCode(scenarioCode)
      setTestScenarioCode(nextScreen === 'scenario_test' ? scenarioCode : '')
    }
    window.addEventListener('popstate', syncFromLocation)
    return () => window.removeEventListener('popstate', syncFromLocation)
  }, [roles])

  const visibleNav = useMemo(
    () => demoRoleSwitcher ? ADMIN_NAV : ADMIN_NAV.filter((item) => hasRole(roles, item)),
    [demoRoleSwitcher, roles],
  )
  const activeItem = ADMIN_NAV.find(
    (item) => item.id === screen && (item.profile === undefined || item.profile === profile),
  )
  const reportsOnly = !demoRoleSwitcher && isAdminReportsOnlyRole(roles)
  const isSoftwareAdmin = roles.includes('software_administrator')
  const canEdit = isSoftwareAdmin
    || (demoRoleSwitcher && demoRole === 'software_admin')
    || (
      demoRoleSwitcher
        ? demoCanEdit(demoRole, activeItem)
        : Boolean(activeItem && hasRole(roles, activeItem) && !reportsOnly)
    )

  useEffect(() => {
    if (demoRoleSwitcher || !visibleNav.length) return
    const allowed = visibleNav.some(
      (item) =>
        item.id === screen
        && (item.profile === undefined || item.profile === profile),
    )
    if (!allowed) {
      const first = visibleNav[0]
      setScreen(first.id)
      setProfile(first.profile ?? 'assistant')
    }
  }, [demoRoleSwitcher, visibleNav, screen, profile])

  const scenarioCatalogVisible = screen === 'scenario_bindings'
    || (screen === 'scenario_editor' && !selectedScenarioCode)
  const copy = SCREEN_COPY[scenarioCatalogVisible ? 'scenario_bindings' : screen]
  const screenBadge = activeItem?.label ?? copy.title
  const profileBadge = screen === 'model_params'
    ? profile === 'cc' ? 'Профиль суфлёра КЦ' : 'Профиль ассистента'
    : undefined

  const navigate = (event: MouseEvent<HTMLAnchorElement>, item: AdminNavItem) => {
    event.preventDefault()
    setScreen(item.id)
    if (item.id === 'scenario_editor') {
      setSelectedScenarioCode('')
    }
    setProfile(item.profile ?? (item.id === 'llm_config_cc' ? 'cc' : 'assistant'))
    setSaved(false)
    setModelFormState({ dirty: false, valid: false, saving: false, message: '' })
    setPoliciesFormState({ dirty: false, valid: false, saving: false, message: '' })
    window.history.pushState({}, '', adminRoute(item))
  }

  if (!sessionReady) {
    return (
      <div
        className="admin-center admin-center--boot"
        data-testid="admin-shell-boot"
        data-ai-color-theme={colorTheme}
      >
        <Card>
          <StatusBadge status={sessionError ? 'danger' : 'info'}>
            {sessionError ? 'Ошибка входа' : 'Вход…'}
          </StatusBadge>
          <h1>Центр настроек AI Hub</h1>
          <p>
            {sessionError
              || 'Устанавливаем сессию Django и CSRF для API админки…'}
          </p>
          {sessionError ? (
            <Button
              onClick={() => {
                setSessionError('')
                setSessionReady(false)
                resetDevSessionCache()
                void (async () => {
                  const ok = await ensureDevSession()
                  if (ok) {
                    setSessionReady(true)
                    return
                  }
                  setSessionError(
                    'Не удалось войти в Django (dev-role-01). Проверьте API :8001 и пароль mock LDAP.',
                  )
                })()
              }}
            >
              Повторить вход
            </Button>
          ) : null}
        </Card>
      </div>
    )
  }

  return (
    <div
      className="admin-center"
      data-testid="admin-shell"
      data-ai-color-theme={colorTheme}
    >
      <aside className="admin-sidebar" data-testid="admin-sidebar">
        <a className="admin-sidebar__brand" href="/ai-hub/admin">
          <img src="/assets/belarusbank-logo.png" alt="Беларусбанк" />
          <span><strong>AI Hub</strong><small>Центр настроек</small></span>
        </a>
        <nav aria-label="Настройки AI Hub">
          {ADMIN_GROUPS.map((group) => {
            const items = visibleNav.filter((item) => item.group === group)
            if (!items.length) return null
            return (
              <section key={group} className="admin-sidebar__group">
                <h2>{group}</h2>
                {items.map((item) => {
                  const active = item.id === screen
                    && (item.profile === undefined || item.profile === profile)
                  const demoReadable =
                    demoRole === 'software_admin' || item.demoRoles.includes(demoRole)
                  return (
                    <a
                      key={`${item.id}-${item.profile ?? 'default'}`}
                      href={adminRoute(item)}
                      aria-current={active ? 'page' : undefined}
                      onClick={(event) => navigate(event, item)}
                    >
                      <span>{item.featured ? '★ ' : ''}{item.label}</span>
                      {demoRoleSwitcher && !demoReadable && <small>(чтение)</small>}
                    </a>
                  )
                })}
              </section>
            )
          })}
        </nav>
      </aside>

      <div className="admin-workspace">
        <header className="admin-topbar">
          <div>
            <strong>Центр настроек AI Hub</strong>
            <span>Управление конфигурацией платформы</span>
          </div>
          <div className="admin-topbar__actions">
            {demoRoleSwitcher && (
              <label className="admin-role-switcher">
                <span>Демо роль</span>
                <select
                  value={demoRole}
                  onChange={(event) => setDemoRole(event.target.value as DemoAdminRole)}
                >
                  {Object.entries(DEMO_ROLE_LABELS).map(([value, label]) => (
                    <option value={value} key={value}>{label}</option>
                  ))}
                </select>
              </label>
            )}
            {!demoRoleSwitcher && <StatusBadge status="success">RBAC активен</StatusBadge>}
            <div className="admin-topbar__fabs">
              <a
                href="/ai-hub?open=sufler"
                className="admin-topbar__chat-fab"
                data-testid="admin-back-to-sufler"
                title="Открыть суфлёр"
                aria-label="Открыть суфлёр"
              >
                <span className="admin-topbar__chat-fab-mark" aria-hidden="true">S</span>
              </a>
              <a
                href="/ai-hub?open=assistant"
                className="admin-topbar__chat-fab"
                data-testid="admin-back-to-chat"
                title="Открыть ИИ-чат"
                aria-label="Открыть ИИ-чат"
              >
                <span className="admin-topbar__chat-fab-mark" aria-hidden="true">AI</span>
              </a>
              <a
                href="/assistant?ocr=1"
                className="admin-topbar__chat-fab"
                data-testid="admin-open-ocr"
                title="Открыть OCR"
                aria-label="Открыть OCR на весь экран"
              >
                <span className="admin-topbar__chat-fab-mark" aria-hidden="true">OCR</span>
              </a>
            </div>
          </div>
        </header>

        <main
          className={`admin-main${
            screen === 'sufler_stats' || screen === 'cc_reports' || screen === 'asr_qa' || screen === 'qu_admin' || screen === 'sufler_training' || screen === 'scenario_editor' || screen === 'scenario_test'
              ? ' admin-main--wide'
              : ''
          }`}
          data-screen-id={screen}
        >
          <div className="admin-breadcrumbs" aria-label="Хлебные крошки">
            <a href="/ai-hub/admin">Центр настроек</a><span>/</span><span>{copy.title}</span>
          </div>
          <header className="admin-page-header">
            <div>
              <div className="admin-page-header__title">
                <h1>{copy.title}</h1>
                {profileBadge && <StatusBadge status="info">{profileBadge}</StatusBadge>}
              </div>
              {copy.subtitle ? <p>{copy.subtitle}</p> : null}
            </div>
            <StatusBadge status={canEdit ? 'success' : 'neutral'}>
              {canEdit ? copy.status : 'Только просмотр'}
            </StatusBadge>
          </header>

          {!canEdit && (
            <div className="admin-readonly" role="status">
              Текущая роль может просматривать экран, но не изменять настройки.
            </div>
          )}

          {screen === 'model_params' ? (
            <ModelParamsScreen
              ref={modelParamsRef}
              profile={profile}
              canEdit={canEdit}
              initialData={initialModelParams}
              onStateChange={handleModelFormState}
            />
          ) : screen === 'sufler_policies' ? (
            <SuflerPoliciesScreen
              ref={suflerPoliciesRef}
              canEdit={canEdit}
              onStateChange={handlePoliciesFormState}
            />
          ) : screen === 'qu_admin' ? (
            <QuPreviewScreen key="qu_admin" canEdit={canEdit} />
          ) : screen === 'sufler_training' ? (
            <QuPreviewScreen key="sufler_training" canEdit={canEdit} initialTab="moderation" />
          ) : screen === 'kb_admin' ? (
            <KbAdminScreen canEdit={canEdit} />
          ) : screen === 'prompts_assistant' ? (
            <PromptsAssistantScreen canEdit={canEdit} />
          ) : screen === 'capabilities' ? (
            <CapabilitiesScreen canEdit={canEdit} />
          ) : screen === 'assistant_tools' ? (
            <AssistantToolsScreen canEdit={canEdit} />
          ) : screen === 'ocr' ? (
            <div className="admin-ocr-screen" data-testid="admin-ocr-screen">
              <OcrDocumentsPanel />
            </div>
          ) : screen === 'doc_types' ? (
            <DocTypesScreen canEdit={canEdit} />
          ) : screen === 'sufler_stats' ? (
            <div className="rpt-app admin-reports-embed">
              <CcReportsScreen initialReport="usefulness" scope="sufler" />
            </div>
          ) : screen === 'cc_reports' ? (
            <div className="rpt-app admin-reports-embed">
              <CcReportsScreen />
            </div>
          ) : screen === 'asr_qa' ? (
            <div className="rpt-app admin-reports-embed">
              <AsrQaScreen />
            </div>
          ) : screen === 'scenario_editor' && selectedScenarioCode ? (
            <ScenarioEditorScreen
              canEdit={canEdit}
              initialCode={selectedScenarioCode}
              onBack={() => {
                setScreen('scenario_bindings')
                setSelectedScenarioCode('')
                window.history.pushState({}, '', '/ai-hub/admin/scenario_bindings')
              }}
              onOpenTest={(code) => {
                setTestScenarioCode(code)
                setScreen('scenario_test')
                window.history.pushState({}, '', `/ai-hub/admin/scenario_test?scenario=${encodeURIComponent(code)}`)
              }}
              onScenarioCreated={(code) => {
                setSelectedScenarioCode(code)
                window.history.replaceState({}, '', `/ai-hub/admin/scenario_editor?scenario=${encodeURIComponent(code)}`)
              }}
            />
          ) : screen === 'scenario_test' ? (
            <ScenarioTestScreen
              canEdit={canEdit}
              initialCode={testScenarioCode || selectedScenarioCode}
              onEditScenario={(code) => {
                setSelectedScenarioCode(code)
                setScreen('scenario_editor')
                window.history.pushState({}, '', `/ai-hub/admin/scenario_editor?scenario=${encodeURIComponent(code)}`)
              }}
            />
          ) : scenarioCatalogVisible ? (
            <ScenarioBindingsScreen
              onOpenScenario={(code) => {
                setSelectedScenarioCode(code)
                setScreen('scenario_editor')
                window.history.pushState({}, '', `/ai-hub/admin/scenario_editor?scenario=${encodeURIComponent(code)}`)
              }}
              onCreateScenario={() => {
                setSelectedScenarioCode('new')
                setScreen('scenario_editor')
                window.history.pushState({}, '', '/ai-hub/admin/scenario_editor?scenario=new')
              }}
            />
          ) : (
            <>
              <section className="admin-stats" aria-label={`Сводка экрана ${copy.title}`}>
                {copy.cards.map(([label, value, note]) => (
                  <Card key={label}>
                    <span>{label}</span>
                    <strong>{value}</strong>
                    <small>{note}</small>
                  </Card>
                ))}
              </section>

              <Card className="admin-settings-card">
                <header>
                  <div>
                    <h2>Настройки экрана</h2>
                    <p>Черновой контент подготовлен для следующей профильной UI-задачи.</p>
                  </div>
                  <StatusBadge status="info">{screenBadge}</StatusBadge>
                </header>
                <div className="admin-form-grid">
                  <label>
                    <span>Название конфигурации</span>
                    <input defaultValue={copy.title} disabled={!canEdit} />
                  </label>
                  <label>
                    <span>Область</span>
                    <select defaultValue="bank" disabled={!canEdit}>
                      <option value="bank">Весь банк</option>
                      <option value="cc">Контакт-центр</option>
                      <option value="department">Подразделение</option>
                    </select>
                  </label>
                  <label className="admin-form-grid__wide">
                    <span>Описание</span>
                    <textarea defaultValue={copy.subtitle} rows={4} disabled={!canEdit} />
                  </label>
                </div>
              </Card>
            </>
          )}
        </main>

        {screen !== 'qu_admin' && screen !== 'sufler_training' && screen !== 'kb_admin' && screen !== 'prompts_assistant' && screen !== 'capabilities' && screen !== 'assistant_tools' && screen !== 'doc_types' && screen !== 'ocr' && screen !== 'sufler_stats' && screen !== 'cc_reports' && screen !== 'asr_qa' && screen !== 'scenario_editor' && screen !== 'scenario_test' && screen !== 'scenario_bindings' && (
        <footer className="admin-save-footer" data-testid="admin-save-footer">
          <span>
            {screen === 'model_params'
              ? modelFormState.message || (modelFormState.dirty ? 'Есть несохранённые изменения' : 'Настройки синхронизированы')
              : screen === 'sufler_policies'
                ? policiesFormState.message || (policiesFormState.dirty ? 'Есть несохранённые изменения' : 'Настройки синхронизированы')
                : saved ? 'Изменения сохранены' : 'Есть несохранённые изменения'}
          </span>
          <div>
            <Button
              variant="ghost"
              disabled={
                !canEdit
                || (screen === 'model_params' && !modelFormState.dirty)
                || (screen === 'sufler_policies' && !policiesFormState.dirty)
              }
              onClick={() => {
                if (screen === 'model_params') modelParamsRef.current?.reset()
                else if (screen === 'sufler_policies') suflerPoliciesRef.current?.reset()
                else setSaved(false)
              }}
            >
              Сбросить
            </Button>
            <Button
              disabled={
                !canEdit
                || (
                  screen === 'model_params'
                  && (
                    !modelFormState.dirty
                    || !modelFormState.valid
                    || modelFormState.saving
                  )
                )
                || (
                  screen === 'sufler_policies'
                  && (
                    !policiesFormState.dirty
                    || !policiesFormState.valid
                    || policiesFormState.saving
                  )
                )
              }
              onClick={() => {
                if (screen === 'model_params') {
                  void modelParamsRef.current?.save()
                } else if (screen === 'sufler_policies') {
                  void suflerPoliciesRef.current?.save()
                } else {
                  setSaved(true)
                }
              }}
            >
              {(modelFormState.saving && screen === 'model_params')
                || (policiesFormState.saving && screen === 'sufler_policies')
                ? 'Сохранение…'
                : 'Сохранить'}
            </Button>
          </div>
        </footer>
        )}
      </div>
    </div>
  )
}
