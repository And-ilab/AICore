import { useState } from 'react'
import { useAiHubColorTheme } from '../ai-hub/colorTheme'
import { OcrDocumentsPanel, type OcrSubTab } from '../ai-hub/ocr/OcrDocumentsPanel'
import { StatusBadge } from '../components'
import { AssistantChat } from './AssistantChat'
import './AssistantWindowApp.css'

type WindowTab = 'assistant' | 'documents'

export interface AssistantWindowAppProps {
  username?: string
  demoMode?: boolean
  readOnly?: boolean
  initiallyOpen?: boolean
  settingsHref?: string
  settingsLabel?: string
}

function readOcrLaunch(): boolean {
  try {
    const params = new URLSearchParams(window.location.search)
    return params.get('ocr') === '1' || params.get('tab') === 'documents'
  } catch {
    return false
  }
}

export function AssistantWindowApp({
  username = 'Пользователь ИИ-ассистента',
  demoMode = false,
  readOnly = false,
  initiallyOpen = true,
  settingsHref = '/ai-hub/admin',
  settingsLabel = 'Центр настроек',
}: AssistantWindowAppProps) {
  const openOcrOnLaunch = readOcrLaunch()
  const [open, setOpen] = useState(initiallyOpen)
  const [maximized, setMaximized] = useState(true)
  const [tab, setTab] = useState<WindowTab>(openOcrOnLaunch ? 'documents' : 'assistant')
  const [ocrSubTab, setOcrSubTab] = useState<OcrSubTab>(openOcrOnLaunch ? 'upload' : 'queue')
  const { theme: colorTheme } = useAiHubColorTheme()

  const openOcrWorkspace = () => {
    setOcrSubTab('upload')
    setTab('documents')
  }

  if (!open) {
    return (
      <main
        className="asst-window-page"
        data-testid="assistant-window-app"
        data-ai-color-theme={colorTheme}
      >
        <button
          type="button"
          className="asst-window-reopen"
          data-testid="asst-window-reopen"
          onClick={() => setOpen(true)}
        >
          Открыть окно ИИ-ассистента
        </button>
      </main>
    )
  }

  return (
    <main
      className="asst-window-page"
      data-testid="assistant-window-app"
      data-ai-color-theme={colorTheme}
    >
      <section
        className={`asst-window${maximized ? ' asst-window--maximized' : ''}${
          tab === 'documents' ? ' asst-window--ocr' : ''
        }`}
        data-testid="assistant-window"
        aria-label="ИИ-ассистент"
      >
        <header className="asst-window__titlebar">
          <div>
            <p className="asst-window__brand">Беларусбанк AI</p>
            <h1>ИИ-ассистент</h1>
            <p className="asst-window__user">{username}</p>
          </div>
          <div className="asst-window__controls" aria-label="Управление окном">
            <a
              href={settingsHref}
              className="asst-window__settings"
              aria-label={settingsLabel}
              title={settingsLabel}
              data-testid="asst-settings-burger"
            >
              ☰
            </a>
            <button
              type="button"
              title="Свернуть"
              aria-label="Свернуть"
              onClick={() => setOpen(false)}
              data-testid="asst-minimize"
            >
              ─
            </button>
            <button
              type="button"
              title={maximized ? 'Восстановить' : 'На весь экран'}
              aria-label={maximized ? 'Восстановить' : 'На весь экран'}
              onClick={() => setMaximized((value) => !value)}
              data-testid="asst-maximize"
            >
              {maximized ? '❐' : '□'}
            </button>
            <button
              type="button"
              title="Закрыть"
              aria-label="Закрыть"
              onClick={() => setOpen(false)}
              data-testid="asst-close"
            >
              ×
            </button>
          </div>
        </header>

        <nav className="asst-window__tabs" aria-label="Модули окна">
          <button
            type="button"
            className={tab === 'assistant' ? 'is-active' : undefined}
            aria-selected={tab === 'assistant'}
            onClick={() => setTab('assistant')}
            data-testid="asst-window-tab-assistant"
          >
            Ассистент
          </button>
          <button
            type="button"
            className={tab === 'documents' ? 'is-active' : undefined}
            aria-selected={tab === 'documents'}
            onClick={() => {
              setOcrSubTab('queue')
              setTab('documents')
            }}
            data-testid="asst-window-tab-documents"
          >
            Документы
          </button>
        </nav>

        <div className="asst-window__body">
          {tab === 'assistant' ? (
            <AssistantChat
              demoMode={demoMode}
              username={username}
              readOnly={readOnly}
              onOpenOcr={openOcrWorkspace}
            />
          ) : (
            <OcrDocumentsPanel initialSubTab={ocrSubTab} />
          )}
        </div>

        <footer className="asst-window__status">
          <StatusBadge status="success">Подключено</StatusBadge>
          <span>БЗ обновлена · assistant_bank · SSE</span>
        </footer>
      </section>
    </main>
  )
}
