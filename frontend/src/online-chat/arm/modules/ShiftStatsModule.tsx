import { useEffect, useMemo, useState } from 'react'
import { listDialogs, type OnlineChatDialog } from '../../api/onlineChatApi'
import { getSupervisorOverview } from '../../api/managementApi'
import { Text } from '../primitives'
import { ArmModuleFrame } from './ArmModuleFrame'
import type { ArmModuleProps } from './types'

function startOfToday(): Date {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false
  const t = new Date(iso).getTime()
  return t >= startOfToday().getTime()
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return '—'
  const total = Math.max(0, Math.round(seconds))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatPresence(presence: string | undefined): string {
  const map: Record<string, string> = {
    online: 'в сети',
    break: 'перерыв',
    lunch: 'обед',
    training: 'инструктаж',
    meeting: 'на встрече',
    offline: 'не в сети',
    tech_issue: 'тех. перерыв',
    busy: 'занят',
  }
  return map[presence ?? ''] ?? presence ?? '—'
}

type Kpi = { id: string; label: string; value: string }

export function ShiftStatsModule({ t, scheme, operatorName, armRole, onBack }: ArmModuleProps) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [kpis, setKpis] = useState<Kpi[]>([])
  const [topics, setTopics] = useState<{ topic: string; count: number }[]>([])
  const [presenceLabel, setPresenceLabel] = useState('—')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    void Promise.all([
      getSupervisorOverview().catch(() => null),
      listDialogs('closed').catch(() => [] as OnlineChatDialog[]),
      listDialogs('active').catch(() => [] as OnlineChatDialog[]),
    ])
      .then(([overview, closed, active]) => {
        if (cancelled) return
        const mineClosed = closed.filter(
          (d) => d.operator_name === operatorName && isToday(d.closed_at),
        )
        const mineActive = active.filter((d) => d.operator_name === operatorName)
        const op = overview?.operators?.find((item) => item.name === operatorName)
        const avgFirst = op?.avg_first_response_seconds ?? null
        const closedCount = op?.closed_today ?? mineClosed.length
        const activeCount = op?.active_dialogs ?? op?.load ?? mineActive.length

        const withTopic = mineClosed.filter((d) => d.close_topic?.trim())
        const answeredFast = mineClosed.filter((d) => {
          if (!d.accepted_at || !d.created_at) return false
          const wait = (new Date(d.accepted_at).getTime() - new Date(d.created_at).getTime()) / 1000
          return wait <= 20
        }).length
        const slaPct =
          mineClosed.length > 0
            ? `${Math.round((answeredFast / mineClosed.length) * 100)}%`
            : '—'

        setKpis([
          { id: 'closed', label: 'Закрыто за смену', value: String(closedCount) },
          { id: 'active', label: 'Активных сейчас', value: String(activeCount) },
          { id: 'aht', label: 'Среднее время первого ответа', value: formatDuration(avgFirst) },
          { id: 'sla', label: 'Доля ответов ≤ 20 с', value: slaPct },
          {
            id: 'topics',
            label: 'С тематикой закрытия',
            value: String(withTopic.length),
          },
          {
            id: 'channels',
            label: 'Каналов сегодня',
            value: String(new Set(mineClosed.map((d) => d.channel).filter(Boolean)).size || '—'),
          },
        ])

        const topicCounts = new Map<string, number>()
        for (const d of mineClosed) {
          const topic = d.close_topic?.trim() || 'Без тематики'
          topicCounts.set(topic, (topicCounts.get(topic) ?? 0) + 1)
        }
        const topicRows = [...topicCounts.entries()]
          .map(([topic, count]) => ({ topic, count }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 8)
        setTopics(topicRows)
        setPresenceLabel(formatPresence(op?.presence))
      })
      .catch(() => {
        if (!cancelled) setError('Не удалось загрузить показатели смены')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [operatorName])

  const maxTopic = useMemo(
    () => Math.max(1, ...topics.map((item) => item.count)),
    [topics],
  )

  return (
    <ArmModuleFrame
      t={t}
      scheme={scheme}
      title="Статистика смены"
      onBack={onBack}
    >
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Text style={{ fontSize: 13, color: t.text.secondary }}>
          {armRole === 'supervisor' ? 'Вид супервизора' : 'Личные показатели'}
          {presenceLabel !== '—' ? ` · сейчас ${presenceLabel}` : ''}
        </Text>

        {error ? (
          <Text style={{ fontSize: 13, color: '#C62828' }}>{error}</Text>
        ) : null}
        {loading ? (
          <Text style={{ fontSize: 13, color: t.text.secondary }}>Загрузка показателей…</Text>
        ) : null}

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))',
            gap: 10,
          }}
        >
          {kpis.map((kpi) => (
            <div
              key={kpi.id}
              style={{
                padding: 14,
                borderRadius: 10,
                border: `1px solid ${t.stroke.secondary}`,
                background: t.bg.editor,
              }}
            >
              <Text style={{ fontSize: 11, color: t.text.tertiary, minHeight: 28 }}>{kpi.label}</Text>
              <Text
                weight="semibold"
                style={{
                  fontSize: 26,
                  marginTop: 4,
                  letterSpacing: '-0.02em',
                  fontVariantNumeric: 'tabular-nums',
                  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                  textAlign: 'right',
                }}
              >
                {kpi.value}
              </Text>
            </div>
          ))}
        </div>

        <section
          style={{
            padding: 14,
            borderRadius: 10,
            border: `1px solid ${t.stroke.secondary}`,
            background: t.bg.editor,
          }}
        >
          <Text weight="semibold" style={{ marginBottom: 12 }}>Тематики закрытых диалогов за сегодня</Text>
          {topics.length === 0 ? (
            <Text style={{ fontSize: 12, color: t.text.secondary }}>
              Пока нет закрытых диалогов за сегодня
            </Text>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {topics.map((item) => (
                <div key={item.topic}>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      marginBottom: 4,
                      gap: 8,
                    }}
                  >
                    <Text style={{ fontSize: 12 }}>{item.topic}</Text>
                    <Text
                      style={{
                        fontSize: 12,
                        color: t.text.secondary,
                        fontVariantNumeric: 'tabular-nums',
                        minWidth: 24,
                        textAlign: 'right',
                      }}
                    >
                      {item.count}
                    </Text>
                  </div>
                  <div
                    style={{
                      height: 6,
                      borderRadius: 999,
                      background: t.fill.tertiary,
                      overflow: 'hidden',
                    }}
                  >
                    <div
                      style={{
                        width: `${(item.count / maxTopic) * 100}%`,
                        height: '100%',
                        background: scheme.accentControl,
                        borderRadius: 999,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </ArmModuleFrame>
  )
}
