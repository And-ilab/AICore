import { useEffect, useState } from 'react'
import { operatorsApi, type ChatOperator } from './api/managementApi'
import './shell/Management.css'

export interface OperatorPickerProps {
  title?: string
  subtitle?: string
  /** When true, selected ARM opens with transfer enabled (supervisor). */
  allowTransfer?: boolean
}

function presenceLabel(presence: string): string {
  const map: Record<string, string> = {
    online: 'онлайн',
    busy: 'занят',
    break: 'перерыв',
    lunch: 'обед',
    training: 'обучение',
    meeting: 'встреча',
    tech_issue: 'техпроблема',
    offline: 'офлайн',
  }
  return map[presence] ?? presence
}

export function OperatorPicker({
  title = 'Выберите оператора',
  subtitle = '',
  allowTransfer = false,
}: OperatorPickerProps) {
  const [items, setItems] = useState<ChatOperator[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    void operatorsApi
      .list()
      .then((list) => {
        if (!cancelled) {
          setItems(
            list.filter(
              (item) => item.is_active !== false && (item.role ?? 'operator') === 'operator',
            ),
          )
          setError('')
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) {
          setError(caught instanceof Error ? caught.message : 'Не удалось загрузить операторов')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const hrefFor = (name: string) => {
    // Stay under /online-chat/operators so the «Операторы» tab remains active.
    const params = new URLSearchParams({
      mode: 'view',
      operator: name,
    })
    if (allowTransfer) params.set('transfer', '1')
    return `/online-chat/operators?${params.toString()}`
  }

  const historyHrefFor = (name: string) => {
    const params = new URLSearchParams({
      mode: 'view',
      operator: name,
      historyOperator: name,
    })
    return `/online-chat/operators?${params.toString()}`
  }

  return (
    <main className="chat-management">
      <div className="chat-management__inner">
        <div className="chat-management__heading">
          <div>
            <h1>{title}</h1>
            {subtitle ? <p className="chat-management__muted">{subtitle}</p> : null}
          </div>
        </div>

        {error && <p className="chat-management__error" role="alert">{error}</p>}

        <section className="chat-management__card" aria-labelledby="operator-pick-heading">
          <h2 id="operator-pick-heading">Операторы</h2>
          {loading && <p className="chat-management__muted">Загружаем список…</p>}
          {!loading && items.length === 0 && (
            <div className="chat-management__empty">Операторы не найдены. Запустите симулятор</div>
          )}
          <ul className="chat-management__list">
            {items.map((operator) => (
              <li className="chat-management__list-item" key={operator.id}>
                <header>
                  <div>
                    <strong>{operator.name}</strong>
                    <div className="chat-management__muted">
                      {operator.department_name
                        || (typeof operator.department === 'object' && operator.department
                          ? operator.department.name
                          : 'Без отдела')}
                    </div>
                  </div>
                  <span className={`chat-management__pill is-${operator.presence}`}>
                    {presenceLabel(operator.presence)}
                  </span>
                </header>
                <div className="chat-management__actions">
                  <a className="chat-button is-secondary" href={hrefFor(operator.name)}>
                    Смотреть АРМ
                  </a>
                  <a className="chat-button is-secondary" href={historyHrefFor(operator.name)}>
                    История обращений
                  </a>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  )
}
