import { useCallback, useEffect, useState } from 'react'
import { channelLabelRu } from './demoData'
import {
  getAsrSession,
  listAsrSessions,
  seedAsrDemo,
  setTrainingCandidate,
  type AsrCatalogueStats,
  type AsrSessionDetail,
  type AsrSessionSummary,
  type RecognitionStatus,
} from './api/asrQa'

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDuration(sec: number): string {
  const minutes = Math.floor(sec / 60)
  const seconds = sec % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function formatMs(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function statusLabel(status: RecognitionStatus): string {
  if (status === 'recognized') return 'Распознано'
  if (status === 'unrecognized') return 'Не распознано'
  return 'Частично'
}

function speakerLabel(speaker: string): string {
  return speaker === 'operator' ? 'Оператор' : 'Клиент'
}

const EMPTY_STATS: AsrCatalogueStats = {
  total: 0,
  recognized: 0,
  unrecognized: 0,
  partial: 0,
  training_candidates: 0,
  low_confidence: 0,
}

export function AsrQaScreen() {
  const [channel, setChannel] = useState('')
  const [status, setStatus] = useState('')
  const [lowOnly, setLowOnly] = useState(false)
  const [items, setItems] = useState<AsrSessionSummary[]>([])
  const [stats, setStats] = useState<AsrCatalogueStats>(EMPTY_STATS)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [detail, setDetail] = useState<AsrSessionDetail | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const loadList = useCallback(async () => {
    setError('')
    const filters = {
      channel: (channel || '') as 'telephony' | 'online_chat' | '',
      recognition_status: (status || '') as RecognitionStatus | '',
      low_confidence_only: lowOnly,
    }
    let payload = await listAsrSessions(filters)
    if (!payload.items.length) {
      payload = await seedAsrDemo(false)
      payload = await listAsrSessions(filters)
    }
    setItems(payload.items)
    setStats(payload.stats)
    setSelectedId((current) => {
      if (current && payload.items.some((item) => item.id === current)) return current
      return payload.items[0]?.id ?? null
    })
  }, [channel, lowOnly, status])

  useEffect(() => {
    void loadList().catch((requestError: unknown) => {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить каталог ASR')
    })
  }, [loadList])

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null)
      return
    }
    void getAsrSession(selectedId)
      .then(setDetail)
      .catch((requestError: unknown) => {
        setError(requestError instanceof Error ? requestError.message : 'Не удалось открыть запись')
      })
  }, [selectedId])

  const markCandidate = async (utteranceId: number, next: boolean) => {
    if (selectedId == null || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await setTrainingCandidate(selectedId, utteranceId, next)
      setDetail((current) => {
        if (!current) return current
        return {
          ...current,
          has_training_candidate: result.session.has_training_candidate,
          utterances: current.utterances.map((row) => (
            row.id === result.utterance.id ? result.utterance : row
          )),
        }
      })
      setItems((current) => current.map((item) => (
        item.id === result.session.id
          ? { ...item, has_training_candidate: result.session.has_training_candidate }
          : item
      )))
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось отметить кандидата')
    } finally {
      setBusy(false)
    }
  }

  const selected = items.find((item) => item.id === selectedId) || items[0]
  const utterances = detail?.utterances || []

  return (
    <div className="rpt-body" data-testid="asr-qa-screen">
      <div className="rpt-stats" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <div className="rpt-stat"><span>Все записи</span><strong>{stats.total}</strong></div>
        <div className="rpt-stat rpt-stat--success"><span>Распознано</span><strong>{stats.recognized}</strong></div>
        <div className="rpt-stat rpt-stat--warning"><span>Проблемные</span><strong>{stats.unrecognized + stats.partial}</strong></div>
        <div className="rpt-stat rpt-stat--info"><span>Учебные примеры</span><strong>{stats.training_candidates}</strong></div>
      </div>

      {error ? <p className="rpt-muted" role="alert">{error}</p> : null}

      <div className="rpt-card">
        <div className="rpt-card__head">Фильтры</div>
        <div className="rpt-card__body">
          <div className="rpt-grid-2">
            <label className="rpt-field">
              Канал
              <select value={channel} onChange={(e) => setChannel(e.target.value)}>
                <option value="">Все</option>
                <option value="telephony">Телефония</option>
                <option value="online_chat">Онлайн-чат</option>
              </select>
            </label>
            <label className="rpt-field">
              Статус
              <select value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">Все</option>
                <option value="recognized">Распознано</option>
                <option value="partial">Частично</option>
                <option value="unrecognized">Не распознано</option>
              </select>
            </label>
            <label className="rpt-row" style={{ fontSize: 13, alignSelf: 'end' }}>
              <input
                type="checkbox"
                checked={lowOnly}
                onChange={(e) => setLowOnly(e.target.checked)}
              />
              Только низкая уверенность
            </label>
          </div>
        </div>
      </div>

      <div className="rpt-asr-layout">
        <div className="rpt-card">
          <div className="rpt-card__head">Записи</div>
          <div className="rpt-asr-list">
            {items.map((item) => (
              <button
                key={item.id}
                type="button"
                className={selected?.id === item.id ? 'is-active' : ''}
                onClick={() => setSelectedId(item.id)}
              >
                <div className="rpt-row rpt-row--between">
                  <strong>{item.session_id}</strong>
                  <span className="rpt-badge">{statusLabel(item.recognition_status)}</span>
                </div>
                <div className="rpt-muted">
                  {formatDateTime(item.started_at)} · {channelLabelRu(item.channel)} ·{' '}
                  {item.operator_name}
                  {item.has_training_candidate ? ' · кандидат эталона' : ''}
                </div>
              </button>
            ))}
            {items.length === 0 ? (
              <p className="rpt-muted" style={{ padding: 12 }}>
                Нет записей по выбранным фильтрам.
              </p>
            ) : null}
          </div>
        </div>

        <div className="rpt-card">
          <div className="rpt-card__head">
            <span>{selected?.session_id || 'Запись'}</span>
            {selected ? (
              <span className="rpt-badge rpt-badge--info">
                {channelLabelRu(selected.channel)}
              </span>
            ) : null}
          </div>
          {selected ? (
            <div className="rpt-card__body" style={{ display: 'grid', gap: 12 }}>
              <div className="rpt-muted">
                {formatDateTime(selected.started_at)} · {selected.operator_name} ·{' '}
                {formatDuration(selected.duration_sec)} · уверенность{' '}
                {Math.round(selected.avg_confidence * 100)}%
              </div>
              {selected.audio_url ? (
                <audio controls src={selected.audio_url} style={{ width: '100%' }}>
                  Аудио недоступно
                </audio>
              ) : (
                <div className="rpt-muted">Для онлайн-чата аудиозаписи нет.</div>
              )}
              <div className="rpt-table-wrap">
                <table className="rpt-table">
                  <thead>
                    <tr>
                      <th>Время</th>
                      <th>Спикер</th>
                      <th>Текст</th>
                      <th>Уверенность</th>
                      <th>Эталон</th>
                    </tr>
                  </thead>
                  <tbody>
                    {utterances.map((row) => (
                      <tr key={row.id}>
                        <td>{formatMs(row.start_ms)}</td>
                        <td>{speakerLabel(row.speaker)}</td>
                        <td>{row.text}</td>
                        <td>{Math.round(row.confidence * 100)}%</td>
                        <td>
                          {row.is_unrecognized ? '—' : (
                            <button
                              type="button"
                              className="rpt-btn"
                              disabled={busy}
                              onClick={() => void markCandidate(row.id, !row.training_candidate)}
                            >
                              {row.training_candidate ? 'Снять кандидата' : 'Кандидат эталона'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {utterances.length === 0 ? (
                      <tr>
                        <td colSpan={5}>Транскрипт ещё не загружен.</td>
                      </tr>
                    ) : null}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="rpt-muted" style={{ padding: 12 }}>Выберите запись в каталоге.</p>
          )}
        </div>
      </div>
    </div>
  )
}
