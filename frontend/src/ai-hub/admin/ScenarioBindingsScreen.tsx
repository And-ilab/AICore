import { useEffect, useMemo, useState } from 'react'
import { Button, Card, StatusBadge } from '../../components'
import { listDialogScenarios, type ScenarioListItem } from './api/scenarios'
import './ScenarioEditor.css'

interface ScenarioBindingsScreenProps {
  onOpenScenario: (code: string) => void
  onCreateScenario: () => void
}

export function ScenarioBindingsScreen({
  onOpenScenario,
  onCreateScenario,
}: ScenarioBindingsScreenProps) {
  const [items, setItems] = useState<ScenarioListItem[]>([])
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState<'all' | 'production' | 'draft'>('all')
  const [channel, setChannel] = useState<'all' | 'telephony' | 'online_chat'>('all')

  useEffect(() => {
    void listDialogScenarios()
      .then((payload) => setItems(payload.items))
      .catch((caught: unknown) => {
        setError(caught instanceof Error ? caught.message : 'Не удалось загрузить привязки')
      })
  }, [])

  const channelLabel = (value: string) => {
    if (value === 'telephony') return 'Телефония'
    if (value === 'online_chat') return 'Онлайн-чат'
    return 'Телефония / чат'
  }

  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase('ru')
    return items.filter((item) => {
      const matchesText = !needle
        || item.code.toLocaleLowerCase('ru').includes(needle)
        || item.title.toLocaleLowerCase('ru').includes(needle)
      const matchesStatus = status === 'all' || item.status === status
      const matchesChannel = channel === 'all'
        || item.channels === 'both'
        || item.channels === channel
      return matchesText && matchesStatus && matchesChannel
    })
  }, [channel, items, query, status])

  return (
    <div className="scr-catalog" data-testid="scenario-bindings">
      {error ? <Card>{error}</Card> : null}
      <section className="admin-stats" aria-label="Привязки сценариев">
        <Card>
          <span>Телефония</span>
          <strong>
            {items.filter((item) => item.channels === 'both' || item.channels === 'telephony').length}
          </strong>
          <small>Канал</small>
        </Card>
        <Card>
          <span>Онлайн-чат</span>
          <strong>
            {items.filter((item) => item.channels === 'both' || item.channels === 'online_chat').length}
          </strong>
          <small>Канал</small>
        </Card>
        <Card>
          <span>Опубликовано</span>
          <strong>{items.filter((item) => item.status === 'production').length}</strong>
          <small>Production</small>
        </Card>
      </section>
      <section className="scr-catalog__body" aria-label="Каталог сценариев">
        <div className="scr-catalog__heading">
          <div>
            <h2>Выберите сценарий</h2>
            <p>Нажмите на карточку, чтобы открыть настройку разговора.</p>
          </div>
          <Button onClick={onCreateScenario}>+ Новый сценарий</Button>
        </div>
        <header className="scr-catalog__toolbar">
          <label className="scr-catalog__search">
            <span>Найти сценарий</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Код или название"
            />
          </label>
          <label>
            <span>Статус</span>
            <select value={status} onChange={(event) => setStatus(event.target.value as typeof status)}>
              <option value="all">Все статусы</option>
              <option value="production">Опубликованные</option>
              <option value="draft">Черновики</option>
            </select>
          </label>
          <label>
            <span>Канал</span>
            <select value={channel} onChange={(event) => setChannel(event.target.value as typeof channel)}>
              <option value="all">Все каналы</option>
              <option value="telephony">Телефония</option>
              <option value="online_chat">Онлайн-чат</option>
            </select>
          </label>
        </header>
        <p className="scr-catalog__count">Найдено: {filtered.length}</p>
        <div className="scr-catalog__grid">
          {filtered.map((item) => (
            <button
              type="button"
              className="scr-catalog__card"
              key={item.code}
              onClick={() => onOpenScenario(item.code)}
              aria-label={`Открыть сценарий ${item.code}: ${item.title}`}
            >
              <span className="scr-catalog__card-head">
                <span>{item.code}</span>
                <StatusBadge status={item.status === 'production' ? 'success' : 'warning'}>
                  {item.status === 'production' ? 'Опубликован' : 'Черновик'}
                </StatusBadge>
              </span>
              <strong className="scr-catalog__card-title">{item.title}</strong>
              <span className="scr-catalog__card-replica">{item.root_question || 'Стартовая реплика пока не настроена'}</span>
              <span className="scr-catalog__card-foot">
                <small>v{item.version_number || 1} · {channelLabel(item.channels)}</small>
                <b>Открыть →</b>
              </span>
            </button>
          ))}
        </div>
        {!filtered.length && !error ? (
          <div className="scr-catalog__empty">Сценарии по заданным фильтрам не найдены.</div>
        ) : null}
      </section>
    </div>
  )
}
