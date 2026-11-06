import { useEffect, useState } from 'react'
import { Card } from '../../components'

interface MonitoringWidget {
  status?: string
  value?: number | null
  message?: string
}

interface MonitoringSummary {
  widgets?: {
    usefulness?: MonitoringWidget
    incorrect_answers?: MonitoringWidget
    hallucinations?: MonitoringWidget
  }
  message?: string
}

function formatPercent(widget: MonitoringWidget | undefined): string {
  if (!widget || widget.value == null || Number.isNaN(widget.value)) return '—'
  return `${widget.value}%`
}

function noteFor(widget: MonitoringWidget | undefined, fallback: string): string {
  if (!widget) return fallback
  if (widget.status === 'empty' || widget.status === 'error') {
    return widget.message || fallback
  }
  return widget.message || fallback
}

/** Three live cards for the assistant monitoring screen. */
export function AssistantMonitoringCards() {
  const [summary, setSummary] = useState<MonitoringSummary | null>(null)
  const [failed, setFailed] = useState('')

  useEffect(() => {
    let cancelled = false
    fetch('/api/v1/assistant/monitoring/summary/', { credentials: 'include' })
      .then(async (response) => {
        const payload = (await response.json().catch(() => ({}))) as MonitoringSummary
        if (!response.ok) {
          throw new Error(payload.message || 'Не удалось загрузить сводку')
        }
        return payload
      })
      .then((payload) => {
        if (!cancelled) setSummary(payload)
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setFailed(error instanceof Error ? error.message : 'Не удалось загрузить сводку')
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  const widgets = summary?.widgets
  const cards: [string, string, string][] = [
    [
      'Полезность',
      formatPercent(widgets?.usefulness),
      noteFor(widgets?.usefulness, 'Оценки пользователей'),
    ],
    [
      'Ошибочные ответы',
      formatPercent(widgets?.incorrect_answers),
      noteFor(widgets?.incorrect_answers, 'Ручная разметка и сбои модели'),
    ],
    [
      'Галлюцинации',
      formatPercent(widgets?.hallucinations),
      noteFor(widgets?.hallucinations, 'Цель ≤ 3%'),
    ],
  ]

  return (
    <section className="admin-stats" aria-label="Сводка мониторинга ассистента">
      {cards.map(([label, value, note]) => (
        <Card key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          <small>{failed && !summary ? failed : note}</small>
        </Card>
      ))}
    </section>
  )
}
