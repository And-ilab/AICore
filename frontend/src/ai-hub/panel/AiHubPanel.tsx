import {
  useEffect,
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { Card, Fab, HintCard, StatusBadge } from '../../components'
import { AssistantChat } from '../../assistant/AssistantChat'
import { OcrDocumentsPanel } from '../ocr/OcrDocumentsPanel'
import {
  canWriteAssistantChat,
  getSettingsMenuEntry,
} from '../../components/portalLauncherAccess'
import {
  getHubPanelTabs,
  isHubAdminRole,
  type HubPanelTab,
} from './hubAccess'
import './AiHubPanel.css'

export interface AiHubPanelProps {
  roles: readonly string[]
  rbacTabs?: readonly string[]
  username?: string | null
  callActive?: boolean
  initialOpen?: boolean
  initialTab?: HubPanelTab
  initialPinned?: boolean
  initialDocumentSubTab?: 'queue' | 'upload' | 'review'
}

const TAB_LABELS: Record<HubPanelTab, string> = {
  assistant: 'Ассистент',
  documents: 'Документы',
  sufler: 'Суфлёр',
}

export function AiHubPanel({
  roles,
  rbacTabs = [],
  username = 'Пользователь банка',
  callActive = false,
  initialOpen = false,
  initialTab,
  initialPinned = false,
  initialDocumentSubTab = 'queue',
}: AiHubPanelProps) {
  const roleTabs = useMemo(
    () => getHubPanelTabs(roles, rbacTabs),
    [rbacTabs, roles],
  )
  const settingsEntry = useMemo(() => getSettingsMenuEntry(roles), [roles])
  const visibleTabs = callActive
    ? roleTabs.filter((tab) => tab === 'sufler')
    : roleTabs
  const [open, setOpen] = useState(initialOpen)
  const [pinned, setPinned] = useState(initialPinned)
  const [activeTab, setActiveTab] = useState<HubPanelTab>(
    initialTab && visibleTabs.includes(initialTab)
      ? initialTab
      : visibleTabs[0] ?? 'assistant',
  )
  const [size, setSize] = useState({ width: 400, height: 560 })

  useEffect(() => {
    if (!visibleTabs.includes(activeTab) && visibleTabs[0]) {
      setActiveTab(visibleTabs[0])
    }
  }, [activeTab, visibleTabs])

  if (!visibleTabs.length) return null

  const togglePin = () => {
    const next = !pinned
    setPinned(next)
    if (next) {
      setSize({
        width: Math.min(960, window.innerWidth - 32),
        height: Math.min(860, window.innerHeight - 32),
      })
    }
  }

  const startResize = (event: ReactPointerEvent<HTMLButtonElement>) => {
    event.preventDefault()
    setPinned(false)
    const startX = event.clientX
    const startY = event.clientY
    const startSize = size
    const move = (moveEvent: PointerEvent) => {
      setSize({
        width: Math.min(
          Math.min(960, window.innerWidth - 24),
          Math.max(360, startSize.width + startX - moveEvent.clientX),
        ),
        height: Math.min(
          Math.min(860, window.innerHeight - 24),
          Math.max(420, startSize.height + startY - moveEvent.clientY),
        ),
      })
    }
    const stop = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', stop)
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', stop)
  }

  return (
    <div className="hub-panel-layer" data-testid="hub-panel-layer">
      {open && (
        <aside
          className={`hub-panel ${pinned ? 'hub-panel--pinned' : ''}`}
          style={{ width: size.width, height: size.height }}
          role="dialog"
          aria-label="Беларусбанк AI Hub"
          data-testid="hub-panel"
        >
          <header className="hub-panel__header">
            <div className="hub-panel__identity">
              <span className="hub-panel__logo">AI</span>
              <div>
                <strong>Беларусбанк AI</strong>
                <small>{username || 'Авторизованный пользователь'}</small>
              </div>
            </div>
            <div className="hub-panel__controls">
              {isHubAdminRole(roles) && settingsEntry && (
                <a
                  href={settingsEntry.href}
                  className="hub-panel__settings"
                  aria-label={settingsEntry.label}
                  title={settingsEntry.label}
                  data-testid="admin-center-gear"
                >
                  ≡
                </a>
              )}
              <button
                type="button"
                aria-label={pinned ? 'Открепить панель' : 'Закрепить панель'}
                aria-pressed={pinned}
                onClick={togglePin}
              >
                {pinned ? '◆' : '◇'}
              </button>
              <button type="button" aria-label="Свернуть панель" onClick={() => setOpen(false)}>
                —
              </button>
              <button type="button" aria-label="Закрыть панель" onClick={() => setOpen(false)}>
                ×
              </button>
            </div>
          </header>

          <div className="hub-panel__tabs" role="tablist" aria-label="Модули AI Hub">
            {visibleTabs.map((tab) => (
              <button
                type="button"
                role="tab"
                key={tab}
                aria-selected={activeTab === tab}
                onClick={() => setActiveTab(tab)}
              >
                {TAB_LABELS[tab]}
                {tab === 'sufler' && callActive && <span>Звонок</span>}
              </button>
            ))}
          </div>

          <main className="hub-panel__body">
            {activeTab === 'assistant' && (
              <AssistantPanel readOnly={!canWriteAssistantChat(roles)} />
            )}
            {activeTab === 'documents' && (
              <div className="hub-tab-content hub-tab-content--documents">
                <OcrDocumentsPanel initialSubTab={initialDocumentSubTab} />
              </div>
            )}
            {activeTab === 'sufler' && <SuflerPanel callActive={callActive} />}
          </main>

          <footer className="hub-panel__footer">
            <StatusBadge status="success">Подключено</StatusBadge>
            <span>БЗ / СУЗ обновлена · 12:34</span>
          </footer>

          {!pinned && (
            <button
              type="button"
              className="hub-panel__resize"
              aria-label="Изменить размер панели"
              onPointerDown={startResize}
            />
          )}
        </aside>
      )}

      <div className="hub-panel__fab">
        <Fab
          badge={callActive ? 1 : visibleTabs.length}
          aria-label={open ? 'Скрыть AI Hub' : 'Открыть AI Hub'}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          data-testid="hub-panel-fab"
        >
          AI
        </Fab>
      </div>
    </div>
  )
}

function AssistantPanel({ readOnly = false }: { readOnly?: boolean }) {
  return (
    <div className="hub-tab-content hub-tab-content--assistant">
      <AssistantChat compact readOnly={readOnly} />
    </div>
  )
}

function SuflerPanel({ callActive }: { callActive: boolean }) {
  return (
    <div className="hub-tab-content">
      <div className="hub-call-status">
        <div><small>Клиент</small><strong>Иван Петров · 03:42</strong></div>
        <StatusBadge status={callActive ? 'danger' : 'neutral'}>
          {callActive ? 'Активный звонок' : 'Ожидание'}
        </StatusBadge>
      </div>
      <Card className="hub-call-transcript">
        <small>Клиент · 10:16</small>
        <p>Можно ли изменить лимит международного перевода?</p>
      </Card>
      <HintCard title="Повышение лимита перевода" relevance="94%" relevancePercent={94} showFeedback>
        Временное повышение лимита доступно после проверки операции. Постоянное
        изменение оформляется в отделении с документом.
      </HintCard>
      <HintCard title="Лимиты международных операций" relevance="88%" relevancePercent={88} showFeedback>
        Проверьте текущий лимит в разделе «Настройки» → «Лимиты».
      </HintCard>
      <p className="hub-sufler-note">Ответ озвучивает оператор. Автоотправка клиенту отключена.</p>
    </div>
  )
}

export function AiHubPanelHost(props: AiHubPanelProps) {
  return (
    <div className="hub-panel-host">
      <header><img src="/assets/belarusbank-logo.png" alt="Беларусбанк" /><span>Корпоративный портал · Рабочее место</span></header>
      <main><p>AI Hub доступен из правого нижнего угла</p><h1>Рабочий стол сотрудника</h1></main>
      <AiHubPanel {...props} />
    </div>
  )
}
