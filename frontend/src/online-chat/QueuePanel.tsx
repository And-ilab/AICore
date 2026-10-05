import { useMemo, useState } from 'react'
import { StatusBadge } from '../components'
import type { QueueItem, QueueSection } from './sessions'

export interface QueuePanelProps {
  sections: QueueSection[]
  selectedId: string
  onSelect: (item: QueueItem) => void
  collapsed?: boolean
  onToggleCollapsed?: () => void
}

export function QueuePanel({
  sections,
  selectedId,
  onSelect,
  collapsed = false,
  onToggleCollapsed,
}: QueuePanelProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(sections.map((section) => [section.id, section.defaultExpanded])),
  )

  const allCollapsed = useMemo(
    () => sections.every((section) => !(expanded[section.id] ?? section.defaultExpanded)),
    [expanded, sections],
  )

  const toggle = (sectionId: string) => {
    setExpanded((current) => ({
      ...current,
      [sectionId]: !current[sectionId],
    }))
  }

  const collapseAll = () => {
    setExpanded(Object.fromEntries(sections.map((section) => [section.id, false])))
  }

  const expandAll = () => {
    setExpanded(Object.fromEntries(sections.map((section) => [section.id, true])))
  }

  if (collapsed) {
    return (
      <aside className="chat-arm__queue chat-arm__queue--collapsed" aria-label="Очереди диалогов">
        <button
          type="button"
          className="chat-arm__queue-expand"
          title="Развернуть панель очереди"
          onClick={onToggleCollapsed}
        >
          »»
        </button>
      </aside>
    )
  }

  return (
    <aside className="chat-arm__queue" aria-label="Очереди диалогов" data-testid="queue-panel">
      <div className="chat-arm__queue-toolbar">
        <button
          type="button"
          className="chat-arm__queue-tool"
          title={allCollapsed ? 'Развернуть все' : 'Свернуть все'}
          onClick={() => (allCollapsed ? expandAll() : collapseAll())}
        >
          <span aria-hidden>{allCollapsed ? '⊞' : '⊟'}</span>
          {allCollapsed ? 'Развернуть все' : 'Свернуть все'}
        </button>
        {onToggleCollapsed ? (
          <button
            type="button"
            className="chat-arm__queue-collapse"
            title="Свернуть панель очереди"
            onClick={onToggleCollapsed}
          >
            ««
          </button>
        ) : null}
      </div>

      <div className="chat-arm__queue-scroll">
        {sections.map((section) => {
          const isOpen = expanded[section.id] ?? section.defaultExpanded
          return (
            <section
              key={section.id}
              className="chat-arm__queue-section"
              data-testid={`queue-section-${section.id}`}
            >
              <button
                type="button"
                className="chat-arm__section-title chat-arm__section-title--toggle"
                aria-expanded={isOpen}
                onClick={() => toggle(section.id)}
              >
                <span>
                  {isOpen ? '▾' : '▸'} {section.title}
                </span>
                <span className="chat-arm__section-count">{section.items.length}</span>
              </button>
              {isOpen ? (
                <ul className="chat-arm__queue-list">
                  {section.items.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className={`chat-arm__queue-item ${
                          item.id === selectedId ? 'chat-arm__queue-item--active' : ''
                        }`}
                        onClick={() => onSelect(item)}
                        data-testid={`queue-${item.id}`}
                      >
                        <span className="chat-arm__queue-item-head">
                          <strong>{item.name}</strong>
                          <span>{item.wait}</span>
                        </span>
                        <span className="chat-arm__queue-meta">
                          {item.channel}
                          {item.dept ? ` · ${item.dept}` : ''}
                        </span>
                        <span className="chat-arm__queue-preview">{item.preview}</span>
                        {item.operatorName ? (
                          <span className="chat-arm__queue-meta">оп.: {item.operatorName}</span>
                        ) : null}
                        <span className="chat-arm__queue-badges">
                          {item.urgent ? <StatusBadge status="danger">срочно</StatusBadge> : null}
                          {item.result === 'offline' ? (
                            <StatusBadge status="warning">офлайн</StatusBadge>
                          ) : null}
                          {item.result === 'lost' ? (
                            <StatusBadge status="neutral">потерянный</StatusBadge>
                          ) : null}
                          {item.active ? <StatusBadge status="success">активный</StatusBadge> : null}
                          {item.readOnly ? <StatusBadge status="neutral">read-only</StatusBadge> : null}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>
          )
        })}
      </div>
    </aside>
  )
}
