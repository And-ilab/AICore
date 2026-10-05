import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, HintCard, StatusBadge } from '../components'
import { useAiHubColorTheme } from '../ai-hub/colorTheme'
import {
  relevanceStatusFromPercent,
  type HintFeedbackChoice,
} from '../components/hintRelevance'
import {
  useSuflerTranscript,
  type TranscriptLine,
} from './hooks/useSuflerTranscript'
import { useLiveDualAsr, type DualSpeaker } from './hooks/useLiveDualAsr'
import { useKnowledgeBaseSelection } from './hooks/useKnowledgeBaseSelection'
import { isRealCallerPhone, useClientSummary } from './hooks/useClientSummary'
import { KbPicker } from './KbPicker'
import {
  submitSuflerHintFeedback,
  type ClientHistorySummaryBlock,
} from '../online-chat/api/onlineChatApi'
import type { SuflerHint } from './api/suggest'
import { NO_SUZ_HINT_MESSAGE } from './emptyHintCopy'
import { ScenarioPathWidget } from './ScenarioPathWidget'
import './SuflerPhoneApp.css'

export interface SuflerPhoneAppProps {
  roles?: readonly string[]
  callId?: string
  demoMode?: boolean
  demoLines?: TranscriptLine[]
  seedLines?: TranscriptLine[]
  operatorName?: string
  /** Embed inside portal module window (II.3.2 / I-0b). */
  embedded?: boolean
  /** Caller phone from telephony. A placeholder is not replaced with a demo number. */
  clientPhone?: string
  callFacts?: CallFacts
}

export interface CallFacts {
  callerId?: string
  calledId?: string
  callType?: string
  operator?: string
  idchain?: string
  previousQuestion?: string
  previousAskedAt?: string
}

function hintTitle(hint: SuflerHint): string {
  if (hint.source_type === 'scenario') return 'Ответ по активному сценарию'
  return hint.citations[0]?.title || `Подсказка ${hint.rank}`
}

function hintSuz(hint: SuflerHint) {
  const citation = hint.citations[0]
  if (!citation?.permalink) return null
  return { title: citation.title, href: citation.permalink }
}

/** II-2 demo: 3 hints 92% / 87% / 81% on transfer-to-RF turn. */
const DEFAULT_DEMO: TranscriptLine[] = [
  {
    id: 't1-client',
    speaker: 'client',
    text: 'Подскажите, как оформить перевод в Россию через мобильный банк?',
    isFinal: true,
    turnId: 't1',
    hints: [
      {
        rank: 1,
        text: 'Перевод в РФ доступен через «Платежи» → «За рубеж». Проверьте суточный лимит клиента и статус карты.',
        detail_text:
          'Перевод в РФ доступен через «Платежи» → «За рубеж» в мобильном банке или интернет-банке. Перед отправкой проверьте суточный лимит клиента, статус карты и разрешение на международные операции. Если лимит исчерпан, направьте клиента в отделение или предложите оформить изменение лимита в приложении. Актуальные комиссии и лимиты сверяйте в статье СУЗ.',
        relevance_score: 0.92,
        relevance_percent: 92,
        citations: [
          {
            article_id: 201,
            chunk_index: 0,
            title: 'Переводы в РФ — лимиты',
            permalink: 'https://suz.local/articles/201',
          },
        ],
      },
      {
        rank: 2,
        text: 'Для перевода нужен действующий лимит на международные операции в интернет-банке или мобильном приложении.',
        detail_text:
          'Для перевода нужен действующий лимит на международные операции в интернет-банке или мобильном приложении. Если операция отклоняется, сначала проверьте, включены ли платежи за рубеж и не исчерпан ли суточный лимит. При необходимости подскажите клиенту, где в приложении открыть раздел лимитов, либо направьте в отделение с паспортом.',
        relevance_score: 0.87,
        relevance_percent: 87,
        citations: [
          {
            article_id: 202,
            chunk_index: 0,
            title: 'Лимиты международных переводов',
            permalink: 'https://suz.local/articles/202',
          },
        ],
      },
      {
        rank: 3,
        text: 'Комиссия зависит от суммы и валюты; актуальные тарифы — в справочнике СУЗ раздела переводов.',
        detail_text:
          'Комиссия зависит от суммы, валюты и способа перевода. Не называйте конкретный процент или сумму, если их нет в открытой статье СУЗ. Откройте справочник раздела переводов, назовите клиенту только подтверждённые условия и при расхождении направьте в отделение.',
        relevance_score: 0.81,
        relevance_percent: 81,
        citations: [
          {
            article_id: 203,
            chunk_index: 0,
            title: 'Комиссии за переводы за рубеж',
            permalink: 'https://suz.local/articles/203',
          },
        ],
      },
    ],
  },
  {
    id: 't1-operator',
    speaker: 'operator',
    text: 'Хорошо, сейчас посмотрю условия перевода за рубеж.',
    isFinal: true,
    turnId: 't1-op',
  },
]

function formatAskedAt(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function CallFactsCard({ facts }: { facts: CallFacts }) {
  const caller = (facts.callerId || '').trim()
  const realPhone = isRealCallerPhone(caller)
  const rows: { label: string; value: string }[] = [
    {
      label: 'Номер',
      value: realPhone ? caller : 'Октелл номер не передал',
    },
  ]
  const line = (facts.calledId || '').trim()
  if (line) rows.push({ label: 'Линия', value: line })
  const direction = (facts.callType || '').trim().toLowerCase()
  if (direction === 'in' || direction === 'out') {
    rows.push({
      label: 'Направление',
      value: direction === 'out' ? 'Исходящий' : 'Входящий',
    })
  }
  const operator = (facts.operator || '').trim()
  if (operator && operator.toLowerCase() !== 'sufler') {
    rows.push({ label: 'Оператор', value: operator })
  }
  const chain = (facts.idchain || '').trim()
  if (chain && chain !== 'live') rows.push({ label: 'Звонок', value: chain })
  const previous = realPhone ? (facts.previousQuestion || '').trim() : ''
  const previousWhen = previous ? formatAskedAt(facts.previousAskedAt || '') : ''

  return (
    <Card className="sufler-phone__summary-card" data-testid="call-facts">
      <strong>Звонок</strong>
      <dl className="sufler-phone__call-facts">
        {rows.map((row) => (
          <div key={row.label}>
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
        {previous ? (
          <div>
            <dt>Прошлый звонок</dt>
            <dd>
              {previous}
              {previousWhen ? <small>{previousWhen}</small> : null}
            </dd>
          </div>
        ) : null}
      </dl>
    </Card>
  )
}

function ClientSummaryCard({
  preview,
  summary,
  detailedSummary,
  blocks,
  isFirst,
  loading,
}: {
  preview: string
  summary: string
  detailedSummary: string
  blocks: ClientHistorySummaryBlock[]
  isFirst: boolean
  loading?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const toggle = () => setExpanded((current) => !current)

  return (
    <div
      className="sufler-phone__summary"
      tabIndex={0}
      role="button"
      aria-label="Summary клиента"
      aria-expanded={expanded}
      data-testid="client-summary"
      onClick={toggle}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          toggle()
        }
      }}
    >
      <Card className="sufler-phone__summary-card">
        <strong>Summary клиента</strong>
        {expanded ? (
          <div className="sufler-phone__summary-body" onClick={(event) => event.stopPropagation()}>
            <p>{summary}</p>
            <hr />
            <small>Детальный summary</small>
            {isFirst || blocks.length === 0 ? (
              <p className="sufler-phone__summary-detailed">
                {isFirst
                  ? 'Первое обращение клиента — предыдущей истории нет.'
                  : detailedSummary || 'Нет предыдущих обращений по этому номеру.'}
              </p>
            ) : (
              <div className="sufler-phone__summary-blocks">
                {blocks.map((block, index) => (
                  <article
                    key={`${block.date_label}-${index}`}
                    className="sufler-phone__summary-block"
                  >
                    <header>
                      <span>{block.date_label}</span>
                      <span>{block.topic}</span>
                    </header>
                    <p>{block.essence || 'Нет краткого описания сути обращения.'}</p>
                    <small>
                      {block.channel || '—'} · {block.operator_name || 'оператор не указан'}
                    </small>
                  </article>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className="sufler-phone__summary-preview">
            {loading ? 'Загрузка истории…' : preview}
          </p>
        )}
      </Card>
    </div>
  )
}

export function SuflerPhoneApp({
  callId,
  demoMode = false,
  demoLines = DEFAULT_DEMO,
  seedLines = [],
  operatorName = 'Оператор КЦ',
  embedded = false,
  clientPhone = '',
  callFacts,
}: SuflerPhoneAppProps) {
  const resolvedCallId = useMemo(
    () =>
      callId?.trim()
      || `dev-call-${
        globalThis.crypto?.randomUUID?.()
        || `${Date.now()}-${Math.random().toString(36).slice(2)}`
      }`,
    [callId],
  )
  const { theme: colorTheme } = useAiHubColorTheme()
  const kb = useKnowledgeBaseSelection()
  const clientHistory = useClientSummary(clientPhone, { allowDemo: demoMode })
  const {
    lines,
    connected,
    error,
    latencyMs,
    scenario,
    suggestedScenario,
    ingestLive,
    pushAsr,
    enterSuggested,
    exitActive,
    resumeActive,
    resetConversation,
    setRecognitionPaused,
  } = useSuflerTranscript({
    callId: resolvedCallId,
    demoMode,
    demoLines,
    seedLines,
    getKbSlugs: kb.getKbSlugs,
  })
  const liveTurns = useRef<Record<DualSpeaker, string>>({ client: '', operator: '' })
  const dialogueRef = useRef<HTMLElement>(null)
  const [typedLine, setTypedLine] = useState('')
  const [linkDown, setLinkDown] = useState(false)
  useEffect(() => {
    if (connected) {
      setLinkDown(false)
      return
    }
    const timer = window.setTimeout(() => setLinkDown(true), 2500)
    return () => window.clearTimeout(timer)
  }, [connected])
  const [feedbackByHint, setFeedbackByHint] = useState<Record<string, HintFeedbackChoice>>({})
  const [resumeOpen, setResumeOpen] = useState(false)

  const handleUtterance = (speaker: DualSpeaker, text: string, isFinal: boolean) => {
    if (!liveTurns.current[speaker]) {
      liveTurns.current[speaker] = `${speaker}-${Date.now()}`
    }
    const turnId = liveTurns.current[speaker]
    ingestLive({
      type: isFinal ? 'asr.final' : 'asr.partial',
      speaker,
      text,
      turn_id: turnId,
    })
    if (isFinal) liveTurns.current[speaker] = ''
  }

  const live = useLiveDualAsr(handleUtterance)

  useEffect(() => {
    setRecognitionPaused(live.paused)
  }, [live.paused, setRecognitionPaused])

  const submitTypedLine = () => {
    const text = typedLine.trim()
    if (!text) return
    handleUtterance('client', text, true)
    setTypedLine('')
  }

  const clearImitation = () => {
    resetConversation()
    liveTurns.current = { client: '', operator: '' }
    setTypedLine('')
    setFeedbackByHint({})
  }

  const startLive = () => {
    clearImitation()
    void live.start()
  }

  const stopLive = () => {
    live.stop()
    clearImitation()
  }

  const visibleError = demoMode
    ? live.error
    : [live.error, error].find(
        (message) =>
          Boolean(message)
          && !/ошибка суфлёра|повторите попытку/i.test(message),
      )
  const blocks = useMemo(() => lines, [lines])
  const lastScenarioHintTurnId = useMemo(() => {
    for (let index = blocks.length - 1; index >= 0; index -= 1) {
      const line = blocks[index]
      if (
        line.speaker === 'client'
        && line.hints?.some((hint) => hint.source_type === 'scenario')
      ) {
        return line.turnId
      }
    }
    return ''
  }, [blocks])
  const dialogueTail = useMemo(
    () =>
      [
        blocks.length,
        scenario?.code ?? '',
        scenario?.path?.join('>') ?? '',
        ...blocks.map((line) => `${line.id}:${line.hints?.length ?? 0}:${line.hintStatus ?? ''}`),
      ].join('|'),
    [blocks, scenario],
  )

  useEffect(() => {
    const scroller = dialogueRef.current
    if (!scroller) return
    const stickToBottom = () => {
      scroller.scrollTop = scroller.scrollHeight
    }
    stickToBottom()
    const frame = window.requestAnimationFrame(stickToBottom)
    const observer = new ResizeObserver(stickToBottom)
    observer.observe(scroller)
    Array.from(scroller.children).forEach((child) => observer.observe(child))
    return () => {
      window.cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [dialogueTail, live.caption, live.systemCaption])

  const handleHintFeedback = (
    line: TranscriptLine,
    hint: SuflerHint,
    choice: HintFeedbackChoice,
  ) => {
    const key = `${line.turnId}-${hint.rank}`
    setFeedbackByHint((current) => ({ ...current, [key]: choice }))
    void submitSuflerHintFeedback({
      operator_name: operatorName,
      query: line.text,
      hint_rank: hint.rank,
      hint_text: hint.text,
      choice,
      relevance_percent: hint.relevance_percent,
      citation_title: hint.citations[0]?.title,
      request_id: line.requestId,
      source: 'telephony',
      call_id: resolvedCallId,
    }).catch(() => {})
  }

  return (
    <main
      className={`sufler-phone${embedded ? ' sufler-phone--embedded' : ''}`}
      data-testid="sufler-phone-app"
      data-ai-color-theme={colorTheme}
    >
      <header className="sufler-phone__header">
        <div>
          <p className="sufler-phone__eyebrow">Суфлёр · активный звонок</p>
          <h1>Телефония</h1>
        </div>
        {suggestedScenario && (!scenario?.path?.length || scenario.paused) ? (
          <button
            type="button"
            className="sufler-phone__lamp"
            data-testid="sufler-scenario-lamp"
            onClick={() => void enterSuggested(suggestedScenario.code)}
          >
            <span className="sufler-phone__lamp-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="18" height="18">
                <path
                  fill="currentColor"
                  d="M9 21h6v-1.5H9zm3-19a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2zm0 2a5 5 0 0 1 2.9 9.1l-.4.3V15.5h-5v-2.1l-.4-.3A5 5 0 0 1 12 4z"
                />
              </svg>
            </span>
            <span>
              <small>Похожий сценарий</small>
              <strong>{suggestedScenario.code}</strong>
              {suggestedScenario.title}
            </span>
          </button>
        ) : null}
        <div className="sufler-phone__meta">
          {embedded ? null : (
            <a
              href="/ai-hub/admin"
              className="sufler-phone__settings"
              aria-label="Настройки"
              title="Настройки"
              data-testid="admin-center-gear"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                <path
                  fill="currentColor"
                  d="M19.14 12.94c.04-.31.06-.63.06-.94s-.02-.63-.06-.94l2.03-1.58a.5.5 0 0 0 .12-.64l-1.92-3.32a.5.5 0 0 0-.6-.22l-2.39.96a7.03 7.03 0 0 0-1.63-.94l-.36-2.54A.5.5 0 0 0 13.9 1h-3.8a.5.5 0 0 0-.49.42l-.36 2.54c-.59.24-1.13.55-1.63.94l-2.39-.96a.5.5 0 0 0-.6.22L2.81 8.48a.5.5 0 0 0 .12.64L4.96 10.7c-.04.31-.06.63-.06.94s.02.63.06.94l-2.03 1.58a.5.5 0 0 0-.12.64l1.92 3.32c.13.23.4.32.64.22l2.39-.96c.5.39 1.04.7 1.63.94l.36 2.54c.05.24.25.42.49.42h3.8c.24 0 .44-.18.49-.42l.36-2.54c.59-.24 1.13-.55 1.63-.94l2.39.96c.24.1.51 0 .64-.22l1.92-3.32a.5.5 0 0 0-.12-.64l-2.03-1.58ZM12 15.5A3.5 3.5 0 1 1 12 8.5a3.5 3.5 0 0 1 0 7Z"
                />
              </svg>
              Настройки
            </a>
          )}
          <KbPicker
            catalog={kb.catalog}
            selected={kb.selected}
            status={kb.status}
            allSelected={kb.allSelected}
            someSelected={kb.someSelected}
            onToggleAll={kb.toggleAll}
            onToggle={(id, checked) =>
              kb.setSelected((current) => ({ ...current, [id]: checked }))
            }
            compact
          />
          <StatusBadge status={live.paused ? 'warning' : live.recording ? 'success' : linkDown && demoMode ? 'warning' : 'info'}>
            {live.paused
              ? 'Распознавание на паузе'
              : live.recording
                ? 'Имитация'
                : !demoMode
                  ? (linkDown ? 'Нет связи' : 'Слушаем')
                  : linkDown
                    ? 'ASR офлайн'
                    : 'Готов'}
          </StatusBadge>
          <StatusBadge status="info">Консультация</StatusBadge>
          <span>{operatorName}</span>
        </div>
      </header>
      {scenario?.path?.length ? (
        <div className="sufler-phone__scenario-wrap">
          <div
            className={`sufler-phone__scenario${
              scenario.completed
                ? ' sufler-phone__scenario--completed'
                : scenario.paused
                  ? ' sufler-phone__scenario--paused'
                  : ''
            }`}
            data-testid="sufler-scenario-path"
          >
            <span className="sufler-phone__scenario-label">
              {scenario.completed
                ? 'Сценарий окончен'
                : scenario.paused
                  ? 'Сценарий на паузе'
                  : 'Активный сценарий'}
            </span>
            <strong>{scenario.code}</strong>
            <span className="sufler-phone__scenario-path">
              {scenario.path.map((part, index) => (
                <span key={`${part}-${index}`}>
                  {index > 0 ? <i>→</i> : null}
                  {part}
                </span>
              ))}
            </span>
            {scenario.completed ? null : scenario.paused ? (
              <Button onClick={() => setResumeOpen(true)}>Вернуться в сценарий</Button>
            ) : (
              <Button onClick={() => void exitActive()}>Выйти из сценария</Button>
            )}
          </div>
          {resumeOpen ? (
            <div
              className="sufler-phone__resume-dialog"
              role="dialog"
              aria-labelledby="sufler-resume-title"
              data-testid="sufler-scenario-resume-dialog"
            >
              <p id="sufler-resume-title">Вернуться в сценарий</p>
              <div className="sufler-phone__resume-actions">
                <Button
                  onClick={() => {
                    setResumeOpen(false)
                    void resumeActive('start')
                  }}
                >
                  С начала
                </Button>
                <Button
                  onClick={() => {
                    setResumeOpen(false)
                    void resumeActive('checkpoint')
                  }}
                >
                  С места остановки
                </Button>
                <Button variant="ghost" onClick={() => setResumeOpen(false)}>
                  Отмена
                </Button>
              </div>
            </div>
          ) : null}
        </div>
      ) : null}

      {visibleError ? (
        <Card className="sufler-phone__error" role="alert">
          {visibleError}
        </Card>
      ) : null}

      <div className="sufler-phone__workspace">
        <section
          ref={dialogueRef}
          className="sufler-phone__dialogue"
          aria-label="Диалог звонка"
        >
          {blocks.map((line) => {
            const hints = line.speaker === 'client' ? line.hints?.slice(0, 5) ?? [] : []
            return (
              <article
                key={line.id}
                className={`sufler-phone__pair sufler-phone__pair--${line.speaker}`}
                data-testid={`turn-${line.turnId}-${line.speaker}`}
              >
                <Card
                  className={`sufler-phone__bubble sufler-phone__bubble--${line.speaker}${
                    line.speaker === 'operator' ? ' is-draft' : ''
                  }`}
                >
                  <header>
                    <strong>{line.speaker === 'client' ? 'Клиент' : 'Оператор'}</strong>
                    {line.speaker === 'operator' ? (
                      <StatusBadge status="info">
                        {live.recording || live.systemCapture
                          ? 'системный звук'
                          : 'оператор'}
                      </StatusBadge>
                    ) : (
                      <StatusBadge status={line.isFinal ? 'neutral' : 'info'}>
                        {line.isFinal ? 'final' : 'partial'}
                      </StatusBadge>
                    )}
                  </header>
                  <p>{line.text}</p>
                </Card>

                {hints.length > 0 && (() => {
                  const scenarioHints = hints.filter((hint) => hint.source_type === 'scenario').slice(0, 1)
                  const kbHints = hints.filter((hint) => hint.source_type !== 'scenario').slice(0, 1)
                  const split = scenarioHints.length > 0 && kbHints.length > 0
                  const renderHint = (hint: SuflerHint, index: number, total: number) => (
                    <HintCard
                      key={`${line.turnId}-${hint.rank}`}
                      className={hint.source_type === 'scenario' ? 'sufler-phone__scenario-hint' : ''}
                      title={hintTitle(hint)}
                      relevance={`${hint.relevance_percent}%`}
                      relevancePercent={hint.relevance_percent}
                      relevanceStatus={relevanceStatusFromPercent(hint.relevance_percent)}
                      suzLink={hintSuz(hint)}
                      showFeedback={hint.source_type !== 'scenario'}
                      feedbackValue={feedbackByHint[`${line.turnId}-${hint.rank}`] ?? null}
                      onFeedback={(choice) => handleHintFeedback(line, hint, choice)}
                      hintIndex={index + 1}
                      hintTotal={total}
                      showMore={hint.source_type !== 'scenario'}
                      detailText={(hint.detail_text || hint.text).trim()}
                      defaultExpanded={index === 0}
                      data-testid={`hint-${line.turnId}-${hint.rank}`}
                    >
                      <span>{hint.text}</span>
                    </HintCard>
                  )
                  return (
                    <div
                      className={`sufler-phone__hints${
                        scenarioHints.length ? ' sufler-phone__hints--scenario' : ''
                      }${split ? ' sufler-phone__hints--split' : ''}`}
                      data-testid={`hints-${line.turnId}`}
                    >
                      {split ? (
                        <>
                          <div className="sufler-phone__hints-col sufler-phone__hints-col--scenario">
                            <div className="sufler-phone__hints-title">Сценарий ведёт оператора</div>
                            {scenarioHints.map((hint, index) =>
                              renderHint(hint, index, scenarioHints.length),
                            )}
                          </div>
                          <div className="sufler-phone__hints-col sufler-phone__hints-col--kb">
                            <div className="sufler-phone__hints-title">Подсказки по базе знаний</div>
                            {kbHints.map((hint, index) => renderHint(hint, index, kbHints.length))}
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="sufler-phone__hints-title">
                            {scenarioHints.length
                              ? 'Сценарий ведёт оператора'
                              : 'Подсказки по базе знаний'}
                          </div>
                          {(scenarioHints.length ? scenarioHints : kbHints).map((hint, index, list) =>
                            renderHint(hint, index, list.length),
                          )}
                        </>
                      )}
                      {scenario?.completed
                      && scenarioHints.length
                      && line.turnId === lastScenarioHintTurnId ? (
                        <div className="sufler-phone__scenario-finished" role="status">
                          Сценарий окончен
                        </div>
                      ) : null}
                    </div>
                  )
                })()}
                {line.speaker === 'client' && line.isFinal && hints.length === 0 && (line.hintStatus === 'loading' || line.hintMessage) && (
                  <div className="sufler-phone__hints-empty" role="status">
                    {line.hintStatus === 'loading'
                      ? (line.hintMessage || 'Подсказки загружаются…')
                      : (line.hintMessage || NO_SUZ_HINT_MESSAGE)}
                  </div>
                )}
              </article>
            )
          })}
          {!blocks.length && (
            <Card className="sufler-phone__empty">
              {live.caption
                ? `Слышу клиента: ${live.caption}`
                : live.systemCaption
                  ? `Оператор: ${live.systemCaption}`
                : live.recording
                  ? 'Говорите в микрофон (клиент). Системный звук оператора появится в ленте после кнопки «Системный звук».'
                  : demoMode
                    ? 'Нажмите «Начать имитацию»: микрофон — клиент, системный звук — оператор. Реплики оператора пишутся в ленту.'
                    : 'Слушаем линию. Когда заговорят, текст появится здесь.'}
            </Card>
          )}
        </section>

        <aside className="sufler-phone__context" aria-label="Контекст">
          <header className="sufler-phone__context-header">
            <strong>Контекст</strong>
          </header>
          {callFacts ? <CallFactsCard facts={callFacts} /> : null}
          {(demoMode || isRealCallerPhone(clientPhone)) && (
            <ClientSummaryCard
              {...clientHistory.data}
              loading={clientHistory.loading}
            />
          )}
          {scenario?.path?.length ? (
            <ScenarioPathWidget
              scenario={scenario}
              onReturn={() => void resumeActive('checkpoint')}
              onReturnToStep={(nodeId) => void resumeActive('step', nodeId)}
            />
          ) : null}
        </aside>
      </div>

      <footer className="sufler-phone__footer">
        <span className="sufler-phone__footer-status">
          {live.recording
            ? [
                live.caption ? `Клиент: ${live.caption}` : '',
                live.systemCaption ? `Оператор: ${live.systemCaption}` : '',
                !live.caption && !live.systemCaption
                  ? live.status || 'Имитация разговора'
                  : '',
              ]
                .filter(Boolean)
                .join(' · ')
            : linkDown
              ? 'Нет связи с распознаванием'
              : demoMode
                ? 'Готов к имитации'
                : 'Слушаем линию'}
          {!live.recording && latencyMs != null
            ? ` · p95 подсказки ${Math.round(latencyMs)} мс`
            : ''}
        </span>
        <div className="sufler-phone__live">
          {live.recording ? (
            <>
              <label className="sufler-phone__typed">
                <input
                  value={typedLine}
                  placeholder="Реплика клиента…"
                  aria-label="Реплика клиента"
                  onChange={(event) => setTypedLine(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      submitTypedLine()
                    }
                  }}
                />
              </label>
              <span className="sufler-phone__levels" aria-hidden="true">
                <i
                  className="sufler-phone__level sufler-phone__level--mic"
                  style={{ transform: `scaleY(${Math.min(1, live.micLevel * 8)})` }}
                />
                <i
                  className="sufler-phone__level sufler-phone__level--sys"
                  style={{ transform: `scaleY(${Math.min(1, live.systemLevel * 8)})` }}
                />
              </span>
              <Button
                variant="ghost"
                onClick={live.swapSpeakers}
                title={
                  live.micSpeaker === 'client'
                    ? 'Микрофон пишет клиента'
                    : 'Микрофон пишет оператора'
                }
              >
                {live.micSpeaker === 'client' ? 'Клиент' : 'Оператор'}
              </Button>
              {live.systemCapture ? (
                <Button
                  variant="ghost"
                  disabled
                  title="Системный звук пишется как оператор"
                >
                  Оператор · sys
                </Button>
              ) : (
                <Button
                  variant="ghost"
                  onClick={() => void live.enableSystemAudio()}
                  title="Захват системного звука как оператора. В Chrome отметьте «Также системный звук»."
                >
                  Системный звук
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={live.paused ? live.resume : live.pause}
              >
                {live.paused ? 'Продолжить' : 'Пауза'}
              </Button>
              <Button variant="secondary" onClick={stopLive}>
                Стоп
              </Button>
            </>
          ) : demoMode ? (
            <Button variant="primary" onClick={startLive}>
              Начать имитацию
            </Button>
          ) : null}
          {demoMode && !live.recording && (
            <Button
              variant="secondary"
              onClick={() =>
                pushAsr({
                  type: 'asr.final',
                  speaker: 'client',
                  text: 'Как заменить ПИН-код карты?',
                  turn_id: `demo-${Date.now()}`,
                })
              }
            >
              Демо-реплика
            </Button>
          )}
        </div>
      </footer>
    </main>
  )
}
