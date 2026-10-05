import { useEffect, useRef, useState } from 'react'
import type { AssistantKbOption } from '../assistant/api/knowledgeBases'
import type { KbCatalogStatus } from './hooks/useKnowledgeBaseSelection'
import './KbPicker.css'

export interface KbPickerProps {
  catalog: AssistantKbOption[]
  selected: Record<string, boolean>
  status: KbCatalogStatus
  allSelected: boolean
  someSelected: boolean
  onToggleAll: (checked: boolean) => void
  onToggle: (id: string, checked: boolean) => void
  compact?: boolean
}

function summary(
  catalog: AssistantKbOption[],
  selected: Record<string, boolean>,
  status: KbCatalogStatus,
): string {
  if (status === 'loading') return 'Базы знаний…'
  if (status === 'error') return 'Базы знаний недоступны'
  if (!catalog.length) return 'Нет баз знаний'
  const picked = catalog.filter((kb) => selected[kb.id])
  if (!picked.length) return 'Базы не выбраны'
  if (picked.length === catalog.length) return 'Все базы знаний'
  if (picked.length === 1) return picked[0].label
  return `Базы знаний · ${picked.length}`
}

export function KbPicker({
  catalog,
  selected,
  status,
  allSelected,
  someSelected,
  onToggleAll,
  onToggle,
  compact = false,
}: KbPickerProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const label = summary(catalog, selected, status)

  useEffect(() => {
    if (!open) return
    const onPointerDown = (event: PointerEvent) => {
      const root = rootRef.current
      if (root && !root.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  return (
    <div
      className={`sufler-kb${compact ? ' sufler-kb--compact' : ''}`}
      data-testid="sufler-kb"
      ref={rootRef}
    >
      <button
        type="button"
        className="sufler-kb__trigger"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        data-testid="sufler-kb-trigger"
        title={label}
      >
        <span>{label}</span>
        <span aria-hidden>{open ? '▴' : '▾'}</span>
      </button>
      {open ? (
        <div className="sufler-kb__menu" role="listbox" aria-label="Базы знаний">
          {catalog.length > 0 ? (
            <>
              <label className="sufler-kb__option sufler-kb__option--all">
                <input
                  type="checkbox"
                  checked={allSelected}
                  ref={(node) => {
                    if (node) node.indeterminate = someSelected && !allSelected
                  }}
                  onChange={(event) => onToggleAll(event.target.checked)}
                  data-testid="sufler-kb-select-all"
                />
                Выбрать все
              </label>
              {catalog.map((kb) => (
                <label key={kb.id} className="sufler-kb__option">
                  <input
                    type="checkbox"
                    checked={Boolean(selected[kb.id])}
                    onChange={(event) => onToggle(kb.id, event.target.checked)}
                  />
                  {kb.label}
                </label>
              ))}
            </>
          ) : (
            <p className="sufler-kb__empty" data-testid="sufler-kb-empty">
              {status === 'loading'
                ? 'Загрузка…'
                : status === 'error'
                  ? 'Не удалось загрузить базы знаний'
                  : 'Базы знаний не созданы. Добавьте их в Центре настроек.'}
            </p>
          )}
        </div>
      ) : null}
    </div>
  )
}
