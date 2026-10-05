import { useCallback, useEffect, useState } from 'react'
import { DataTable } from './charts'
import { statusLabelRu } from './demoData'
import {
  CcReportsApiError,
  fetchCcLive,
  type LiveDashboard,
} from './api/ccReports'
import { localizeCell } from './labels'

function formatSec(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '—'
  if (value < 60) return `${Math.round(value)} с`
  const mins = Math.floor(value / 60)
  const sec = Math.round(value % 60)
  return `${mins}м ${sec}с`
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString('ru-RU', {
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

export function LiveOpsScreen() {
  const [data, setData] = useState<LiveDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [alertsOpen, setAlertsOpen] = useState(false)
  const [seenAlertIds, setSeenAlertIds] = useState<string[]>(() => {
    try {
      return JSON.parse(localStorage.getItem('cc-live-seen-alerts') || '[]') as string[]
    } catch {
      return []
    }
  })

  const reload = useCallback(async () => {
    try {
      const next = await fetchCcLive()
      setData(next)
      setError(null)
    } catch (err) {
      setError(
        err instanceof CcReportsApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Не удалось загрузить оперативную панель',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
    const timer = window.setInterval(() => {
      void reload()
    }, 15000)
    return () => window.clearInterval(timer)
  }, [reload])

  const kpis = data?.kpis
  const departments = data?.departments || []
  const maxActive = Math.max(1, ...departments.map((item) => item.active))
  const operators = data?.operators || []
  const feed = data?.dialog_feed?.length ? data.dialog_feed : []
  const llmFeed = data?.llm_feed || []
  const alerts = data?.alerts || []
  const unreadAlerts = alerts.filter((alert) => !seenAlertIds.includes(alert.id))

  const markAlertsSeen = () => {
    const ids = alerts.map((alert) => alert.id)
    setSeenAlertIds(ids)
    try {
      localStorage.setItem('cc-live-seen-alerts', JSON.stringify(ids))
    } catch {
      /* ignore */
    }
  }

  const openDialog = (dialogId?: string) => {
    if (!dialogId) return
    window.open(
      `/online-chat?historyDialog=${encodeURIComponent(dialogId)}`,
      '_blank',
      'noopener,noreferrer',
    )
  }

  return (
    <div className="rpt-body" data-testid="cc-live-screen">
      <div className="rpt-row" style={{ marginBottom: 8 }}>
        <span className="rpt-muted">
          {data?.generated_at ? `Обновлено ${formatTime(data.generated_at)}` : 'Оперативные показатели'}
        </span>
        <span className="rpt-spacer" />
        <div style={{ position: 'relative' }}>
          <button
            type="button"
            className="rpt-btn"
            aria-label="Оповещения"
            onClick={() => {
              setAlertsOpen((open) => !open)
              markAlertsSeen()
            }}
          >
            🔔 {unreadAlerts.length ? `(${unreadAlerts.length})` : ''}
          </button>
          {alertsOpen ? (
            <div
              className="rpt-card"
              style={{
                position: 'absolute',
                right: 0,
                top: 'calc(100% + 6px)',
                width: 360,
                zIndex: 20,
                boxShadow: '0 12px 28px rgba(0,0,0,0.16)',
              }}
            >
              <div className="rpt-card__head">Оповещения</div>
              <div className="rpt-card__body">
                {alerts.length ? (
                  <ul className="rpt-alerts">
                    {alerts.map((alert) => (
                      <li key={alert.id} className={`rpt-alert rpt-alert--${alert.tone}`}>
                        <strong>{alert.title}</strong>
                        <span>{alert.detail}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="rpt-muted">Активных оповещений нет.</p>
                )}
              </div>
            </div>
          ) : null}
        </div>
        <button type="button" className="rpt-btn" disabled={loading} onClick={() => void reload()}>
          {loading ? 'Загрузка…' : 'Обновить'}
        </button>
      </div>

      {error ? (
        <div className="rpt-card" style={{ marginBottom: 12 }}>
          <div className="rpt-card__body" style={{ color: '#c62828' }}>
            {error}
          </div>
        </div>
      ) : null}

      <div className="rpt-stats">
        {[
          { label: 'В работе', value: String(kpis?.in_progress ?? '—'), tone: 'info' },
          { label: 'В очереди', value: String(kpis?.in_queue ?? '—'), tone: 'warning' },
          {
            label: 'Ср. ожидание',
            value: formatSec(kpis?.avg_wait_sec),
            tone: 'info',
          },
          {
            label: 'Операторы online',
            value: String(kpis?.operators_online ?? '—'),
            tone: 'success',
          },
          {
            label: 'SLA первого ответа',
            value: kpis?.sla_ok_pct != null ? `${kpis.sla_ok_pct}%` : '—',
            tone: 'success',
          },
          {
            label: 'Закрыто сегодня',
            value: String(kpis?.closed_today ?? data?.chat?.closed_today ?? '—'),
            tone: 'neutral',
          },
        ].map((kpi) => (
          <div key={kpi.label} className={`rpt-stat rpt-stat--${kpi.tone}`}>
            <span>{kpi.label}</span>
            <strong>{kpi.value}</strong>
          </div>
        ))}
      </div>

      <div className="rpt-card">
        <div className="rpt-card__head">Оповещения</div>
        <div className="rpt-card__body">
          {alerts.length ? (
            <ul className="rpt-alerts">
              {alerts.map((alert) => (
                <li key={alert.id} className={`rpt-alert rpt-alert--${alert.tone}`}>
                  <strong>{alert.title}</strong>
                  <span>{alert.detail}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rpt-muted">Активных оповещений нет.</p>
          )}
        </div>
      </div>

      <div className="rpt-grid-2">
        <div className="rpt-card">
          <div className="rpt-card__head">Нагрузка по отделам</div>
          <div className="rpt-card__body">
            {departments.length ? (
              <div className="rpt-dept">
                {departments.map((dept) => (
                  <div key={dept.name} className="rpt-dept__row">
                    <span>{dept.name}</span>
                    <div className="rpt-dept__track">
                      <div
                        className="rpt-dept__fill"
                        style={{ width: `${(dept.active / maxActive) * 100}%` }}
                      />
                    </div>
                    <strong>
                      {dept.active} акт. / {dept.queue} очер.
                    </strong>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rpt-muted">Нет активных отделов/очередей.</p>
            )}
          </div>
        </div>

        <div className="rpt-card">
          <div className="rpt-card__head">Топ операторов по активным диалогам</div>
          <div className="rpt-card__body">
            <div style={{ display: 'grid', gap: 8 }}>
              {operators
                .filter((op) => op.active_dialogs > 0)
                .slice(0, 8)
                .map((op) => (
                  <div key={op.name} className="rpt-row rpt-row--between">
                    <span>{op.name}</span>
                    <span className="rpt-badge rpt-badge--success">
                      {op.active_dialogs} активных
                    </span>
                  </div>
                ))}
              {!operators.some((op) => op.active_dialogs > 0) ? (
                <p className="rpt-muted">Сейчас нет активных диалогов у операторов.</p>
              ) : null}
            </div>
          </div>
        </div>
      </div>

      <div className="rpt-card">
        <div className="rpt-card__head">Операторы</div>
        <div className="rpt-card__body">
          <DataTable
            headers={['Оператор', 'Статус', 'Канал', 'Активных']}
            rows={
              operators.length
                ? operators.map((op) => [
                    op.name,
                    statusLabelRu(op.status),
                    op.channel === 'online_chat' ? 'Онлайн-чат' : op.channel,
                    String(op.active_dialogs),
                  ])
                : [['—', '—', '—', '0']]
            }
          />
        </div>
      </div>

      <div className="rpt-card">
        <div className="rpt-card__head">Лента диалогов · клик открывает просмотр</div>
        <div className="rpt-card__body">
          <DataTable
            headers={[
              'Время',
              'Ref',
              'Канал',
              'Клиент',
              'Оператор',
              'Статус',
              'Тематика',
              'Ожидание',
              'Оценка',
            ]}
            rows={
              feed.length
                ? feed.map((row) => [
                    formatTime(row.at),
                    row.ref,
                    row.channel,
                    row.client,
                    row.operator,
                    localizeCell(row.status),
                    row.topic,
                    formatSec(row.wait_sec),
                    localizeCell(row.feedback),
                  ])
                : [['—', '—', '—', 'Нет диалогов', '—', '—', '—', '—', '—']]
            }
            onRowClick={(_row, index) => {
              const item = feed[index]
              if (item?.id) openDialog(item.id)
            }}
          />
        </div>
      </div>

      <div className="rpt-card">
        <div className="rpt-card__head">Оценки подсказок суфлёра</div>
        <div className="rpt-card__body">
          <DataTable
            headers={['Время', 'Канал', 'Оператор', 'Тематика', 'Релевантность', 'Отметка', 'Вопрос']}
            rows={
              llmFeed.length
                ? llmFeed.map((row) => [
                    formatTime(row.at),
                    row.channel,
                    row.operator,
                    row.topic,
                    row.relevance_pct ? `${row.relevance_pct}%` : '—',
                    localizeCell(row.feedback),
                    row.query || '—',
                  ])
                : [['—', '—', '—', 'Нет отметок суфлёра', '—', '—', '—']]
            }
          />
        </div>
      </div>
    </div>
  )
}
