import { useState } from 'react'
import { Button, Card, HintCard, StatusBadge } from '../components'
import { relevanceStatusFromPercent, type HintFeedbackChoice } from '../components/hintRelevance'
import type { SuflerHint } from '../sufler/api/suggest'
import { submitSuflerHintFeedback } from './api/onlineChatApi'
import {
  ACTIVE_CLIENT,
  ACTIVE_SUMMARY_HISTORY,
  type ClientInfoData,
  type SummaryHistoryData,
} from './clientContext'

export interface SuflerSidePanelProps {
  hints: SuflerHint[]
  loading?: boolean
  error?: string
  latencyMs?: number | null
  scenarioPath?: string
  clientPreview?: string
  onInsert?: (text: string) => void
  disabled?: boolean
  client?: ClientInfoData
  summary?: SummaryHistoryData
  query?: string
  operatorName?: string
  requestId?: string
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

export function SuflerSidePanel({
  hints,
  loading = false,
  error = '',
  latencyMs = null,
  scenarioPath = '',
  onInsert,
  disabled = false,
  client = ACTIVE_CLIENT,
  summary = ACTIVE_SUMMARY_HISTORY,
  query = '',
  operatorName = '',
  requestId = '',
}: SuflerSidePanelProps) {
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [clientOpen, setClientOpen] = useState(false)
  const [phoneRevealed, setPhoneRevealed] = useState(false)
  const [feedbackByHint, setFeedbackByHint] = useState<Record<number, HintFeedbackChoice>>({})

  return (
    <aside className="chat-arm__sufler" data-testid="sufler-side-panel" aria-label="Клиент и суфлёр">
      <div className="chat-arm__sufler-scroll">
        <Card
          className="chat-arm__context-card"
          padded
          onMouseEnter={() => setSummaryOpen(true)}
          onMouseLeave={() => setSummaryOpen(false)}
        >
          <p className="chat-arm__context-label">Summary клиента</p>
          {summaryOpen ? (
            <>
              <p className="chat-arm__context-text">{summary.summary}</p>
              <hr className="chat-arm__context-rule" />
              <p className="chat-arm__context-label">Детальный summary</p>
              <p className="chat-arm__context-text chat-arm__context-text--pre">
                {summary.detailedSummary}
              </p>
            </>
          ) : (
            <p className="chat-arm__context-preview">{summary.preview}</p>
          )}
        </Card>

        <h3 className="chat-arm__sufler-h3">Клиент</h3>
        <Card
          className="chat-arm__context-card"
          padded
          onMouseEnter={() => setClientOpen(true)}
          onMouseLeave={() => {
            setClientOpen(false)
            setPhoneRevealed(false)
          }}
        >
          <strong>{client.name}</strong>
          {clientOpen ? (
            <dl className="chat-arm__client-fields">
              <div>
                <dt>№ диалога</dt>
                <dd>{client.dialogNo}</dd>
              </div>
              <div>
                <dt>ID посетителя</dt>
                <dd>{client.visitorId}</dd>
              </div>
              <div>
                <dt>Время визита</dt>
                <dd>{client.visitTime}</dd>
              </div>
              <div>
                <dt>Точка входа</dt>
                <dd>
                  {client.entryPath} · {client.entryChannel}
                </dd>
              </div>
              <div>
                <dt>Браузер / устройство</dt>
                <dd>
                  {client.browser} · {client.device}
                </dd>
              </div>
              <div>
                <dt>Канал</dt>
                <dd>{client.channel}</dd>
              </div>
              <div>
                <dt>E-mail</dt>
                <dd>{client.email}</dd>
              </div>
              <div>
                <dt>Телефон</dt>
                <dd className="chat-arm__phone-row">
                  <span>{phoneRevealed ? client.phoneFull : client.phoneMasked}</span>
                  <Button
                    variant="ghost"
                    onClick={() => setPhoneRevealed((value) => !value)}
                  >
                    {phoneRevealed ? 'Скрыть' : 'Показать'}
                  </Button>
                </dd>
              </div>
            </dl>
          ) : (
            <div className="chat-arm__phone-row">
              <span className="app-muted">{client.phoneMasked}</span>
              <Button variant="ghost" disabled={disabled}>
                Изменить
              </Button>
            </div>
          )}
        </Card>

        <header className="chat-arm__sufler-header">
          <h2>Суфлёр</h2>
          <StatusBadge status={loading ? 'info' : 'success'}>
            {loading ? 'запрос…' : 'активен'}
          </StatusBadge>
        </header>
        {scenarioPath ? (
          <div className="chat-arm__scenario-path" data-testid="chat-scenario-path">
            <strong>Активный сценарий</strong>
            <span>{scenarioPath}</span>
          </div>
        ) : null}

        {error ? (
          <Card className="chat-arm__error" role="alert">
            {error}
          </Card>
        ) : null}

        <div className="chat-arm__hints" data-testid="sufler-hints">
          {hints.length === 0 && !loading ? (
            <p className="app-muted">Подсказки появятся после сообщения клиента.</p>
          ) : null}
          {hints.map((hint, index) => (
            <HintCard
              key={hint.rank}
              className={hint.source_type === 'scenario' ? 'chat-arm__scenario-hint' : ''}
              title={hintTitle(hint)}
              relevance={`${hint.relevance_percent}%`}
              relevancePercent={hint.relevance_percent}
              relevanceStatus={relevanceStatusFromPercent(hint.relevance_percent)}
              suzLink={hintSuz(hint)}
              showFeedback={hint.source_type !== 'scenario'}
              feedbackValue={feedbackByHint[hint.rank] ?? null}
              onFeedback={(choice) => {
                setFeedbackByHint((current) => ({ ...current, [hint.rank]: choice }))
                void submitSuflerHintFeedback({
                  operator_name: operatorName,
                  query,
                  hint_rank: hint.rank,
                  hint_text: hint.text,
                  choice,
                  relevance_percent: hint.relevance_percent,
                  citation_title: hint.citations[0]?.title,
                  request_id: requestId,
                  source: 'chat',
                }).catch(() => {})
              }}
              hintIndex={index + 1}
              hintTotal={hints.length}
              showMore={hint.source_type !== 'scenario'}
              detailText={(hint.detail_text || hint.text).trim()}
              onInsert={
                disabled || !onInsert
                  ? undefined
                  : () => onInsert(
                    hint.source_type === 'scenario' && hint.operator_tip
                      ? `${hint.text}\n\n${hint.operator_tip}`
                      : hint.text,
                  )
              }
              defaultExpanded={index === 0}
              data-testid={`chat-hint-${hint.rank}`}
            >
              <span>{hint.text}</span>
              {hint.source_type === 'scenario' && hint.operator_tip ? (
                <span className="chat-arm__scenario-question">
                  <strong>Затем спросите клиента</strong>
                  {hint.operator_tip}
                </span>
              ) : null}
            </HintCard>
          ))}
        </div>
      </div>

      <footer className="chat-arm__sufler-footer">
        <span>
          {latencyMs != null
            ? `orchestrator · ${Math.round(latencyMs)} мс`
            : 'тот же suggest API, что телефония'}
        </span>
        {onInsert && hints[0] && !disabled ? (
          <Button
            variant="ghost"
            onClick={() => onInsert(hints[0].text)}
            data-testid="sufler-insert-top"
          >
            Вставить топ-1
          </Button>
        ) : null}
      </footer>
    </aside>
  )
}
