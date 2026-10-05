import { useMemo, useState, type FormEvent } from 'react'
import { Button, StatusBadge } from '../components'
import {
  requestTestDialogPrompt,
  type TestDialogTurn,
} from './api/testDialog'
import {
  SEED_TURNS,
  buildDemoPromptResult,
  resultToTurn,
} from './demoResponses'
import './InternalKcDialogApp.css'

const SCENARIO_OPTIONS = [
  { value: 'CC-SCR-008', label: 'CC-SCR-008 · Вклады' },
  { value: 'CC-SCR-003', label: 'CC-SCR-003 · Переводы' },
  { value: 'CC-SCR-001', label: 'CC-SCR-001 · Карты' },
] as const

export interface InternalKcDialogAppProps {
  username?: string
  demoMode?: boolean
  initialTurns?: TestDialogTurn[]
  initialDraft?: string
  initialScenario?: string
  initiallyOpen?: boolean
}

function UserMessage({ text, time }: { text: string; time: string }) {
  return (
    <div className="ikc-user">
      <div className="ikc-user__bubble">
        <div className="ikc-meta">Запрос · {time}</div>
        <p>{text}</p>
      </div>
    </div>
  )
}

function LlmResponse({ turn }: { turn: TestDialogTurn }) {
  return (
    <article className="ikc-llm" data-testid={`llm-turn-${turn.id}`}>
      <div className="ikc-llm__head">
        <strong>Ответ LLM</strong>
        <StatusBadge
          status={turn.relevanceTone}
          data-testid={`relevance-${turn.id}`}
        >
          {turn.relevance}
        </StatusBadge>
      </div>
      <p className="ikc-llm__text">{turn.llmText}</p>
      <div className="ikc-llm__sources">
        {turn.sources.map((source) => (
          <a
            key={`${turn.id}-${source.title}`}
            className="ikc-source"
            href={source.permalink || '#'}
            target="_blank"
            rel="noreferrer"
          >
            {source.title}
            {source.scenario ? ` · ${source.scenario}` : ''} ↗
          </a>
        ))}
      </div>
      {turn.etalon ? (
        <p className="ikc-etalon">Эталон QU: «{turn.etalon}»</p>
      ) : null}
      <div className="ikc-llm__actions">
        <Button type="button" variant="ghost">
          Эталон подтверждён
        </Button>
        <Button type="button" variant="ghost">
          Низкая релевантность
        </Button>
      </div>
    </article>
  )
}

export function InternalKcDialogApp({
  username = '',
  demoMode = true,
  initialTurns = SEED_TURNS,
  initialDraft = 'А какие документы нужны для открытия вклада?',
  initialScenario = 'CC-SCR-008',
  initiallyOpen = true,
}: InternalKcDialogAppProps) {
  const [windowOpen, setWindowOpen] = useState(initiallyOpen)
  const [maximized, setMaximized] = useState(false)
  const [scenario, setScenario] = useState(initialScenario)
  const [draft, setDraft] = useState(initialDraft)
  const [turns, setTurns] = useState<TestDialogTurn[]>(initialTurns)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')

  const historyLabel = useMemo(
    () => `История тест-диалога · ${turns.length} запрос${turns.length === 1 ? '' : turns.length < 5 ? 'а' : 'ов'}`,
    [turns.length],
  )

  const sendPrompt = async () => {
    const text = draft.trim()
    if (!text || sending) return
    setSending(true)
    setError('')
    try {
      const result = demoMode
        ? buildDemoPromptResult(text, scenario)
        : await requestTestDialogPrompt({
            text,
            scenarioId: scenario,
            usePipeline: true,
          })
      const turn = resultToTurn(result, `turn-${Date.now()}`)
      setTurns((current) => [...current, turn])
      setDraft('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка запроса')
    } finally {
      setSending(false)
    }
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    void sendPrompt()
  }

  if (!windowOpen) {
    return (
      <main className="ikc-page" data-testid="internal-kc-app">
        <Button
          type="button"
          onClick={() => setWindowOpen(true)}
          data-testid="ikc-reopen"
        >
          Открыть окно тест-диалога
        </Button>
      </main>
    )
  }

  return (
    <main className="ikc-page" data-testid="internal-kc-app">
      <section
        className={`ikc-window${maximized ? ' ikc-window--maximized' : ''}`}
        data-testid="ikc-window"
        aria-label="Тест-диалог · внутренний пользователь КЦ"
      >
        <header className="ikc-window__titlebar">
          <div>
            <h1>Тест-диалог · внутренний пользователь КЦ</h1>
            {username ? (
              <p className="ikc-window__user">{username}</p>
            ) : null}
          </div>
          <div className="ikc-window__controls" aria-label="Управление окном">
            <button
              type="button"
              title="Свернуть"
              onClick={() => setWindowOpen(false)}
              data-testid="ikc-minimize"
            >
              ─
            </button>
            <button
              type="button"
              title={maximized ? 'Восстановить' : 'Развернуть'}
              onClick={() => setMaximized((value) => !value)}
              data-testid="ikc-maximize"
            >
              {maximized ? '❐' : '□'}
            </button>
            <button
              type="button"
              title="Закрыть"
              onClick={() => setWindowOpen(false)}
              data-testid="ikc-close"
            >
              ×
            </button>
          </div>
        </header>

        <div className="ikc-params">
          <label>
            Сценарий
            <select
              value={scenario}
              onChange={(event) => setScenario(event.target.value)}
              data-testid="ikc-scenario"
            >
              {SCENARIO_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Промпт
            <select value="sufler_cc" disabled data-testid="ikc-prompt">
              <option value="sufler_cc">sufler_cc (production)</option>
            </select>
          </label>
        </div>

        <div className="ikc-body">
          <div className="ikc-history" data-testid="ikc-history">
            <p className="ikc-history__label">{historyLabel}</p>
            {turns.map((turn, index) => (
              <div key={turn.id} className="ikc-turn" data-testid={`turn-${turn.id}`}>
                {index > 0 ? <hr className="ikc-divider" /> : null}
                <UserMessage text={turn.userText} time={turn.userTime} />
                <LlmResponse turn={turn} />
              </div>
            ))}
          </div>

          <form className="ikc-composer" onSubmit={onSubmit}>
            <label htmlFor="ikc-draft">Новый тестовый запрос</label>
            <textarea
              id="ikc-draft"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder="Введите тестовый вопрос или перефразировку эталонной реплики…"
              data-testid="ikc-draft"
            />
            <div className="ikc-composer__actions">
              <Button type="submit" disabled={sending || !draft.trim()} data-testid="ikc-send">
                {sending ? 'Отправка…' : 'Отправить'}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setDraft('')}
                data-testid="ikc-clear"
              >
                Очистить
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setTurns([])
                  setDraft('')
                  setError('')
                }}
                data-testid="ikc-new-dialog"
              >
                Новый диалог
              </Button>
            </div>
            {error ? (
              <p className="ikc-error" role="alert">
                {error}
              </p>
            ) : null}
          </form>
        </div>
      </section>
    </main>
  )
}
