import { useEffect, useId, useMemo, useRef, useState, type CSSProperties, type JSX } from 'react'
import { TopicGroupIcon, TopicLeafIcon } from './topicIcons'
import type { ArmTheme } from './theme'
import type { DialogTopicNode } from '../api/onlineChatApi'

type MenuNode = {
  key: string
  label: string
  topicId?: string
  topicPath?: string
  children: MenuNode[]
}

function mapToMenuNodes(nodes: DialogTopicNode[]): MenuNode[] {
  return nodes.map((node) => {
    return {
      key: node.id || node.label,
      label: node.label,
      topicId: node.is_selectable ? node.id : undefined,
      topicPath: node.is_selectable ? (node.full_path || node.label) : undefined,
      children: Array.isArray(node.children) ? mapToMenuNodes(node.children) : [],
    }
  })
}

/** Full paths are joined with " / " (spaces around the slash); some labels
 * contain bare slashes with no surrounding spaces (e.g. "Утеря/перевыпуск/
 * обновление карт"), so splitting on that exact separator is required to
 * recover the leaf label without cutting compound labels in half. */
function leafLabel(path: string): string {
  const segments = path.split(' / ').map((part) => part.trim()).filter(Boolean)
  return segments.at(-1) || path.trim()
}

export function TopicSelect({
  t,
  value,
  options,
  recommendedPath = '',
  recommendedId = '',
  onChange,
  disabled = false,
  placeholder = 'Тематика не выбрана',
  style,
}: {
  t: ArmTheme
  value: string
  options: DialogTopicNode[]
  recommendedPath?: string
  recommendedId?: string
  onChange: (nextPath: string, nextId: string) => void
  disabled?: boolean
  placeholder?: string
  style?: CSSProperties
}): JSX.Element {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [trail, setTrail] = useState<MenuNode[]>([])
  const rootRef = useRef<HTMLDivElement | null>(null)
  const listId = useId()

  useEffect(() => {
    if (!open) return
    const onDoc = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const leaves = useMemo(() => {
    const rows: Array<{ id: string; path: string }> = []
    const walk = (nodes: DialogTopicNode[]) => {
      for (const node of nodes) {
        if (node.is_selectable) {
          rows.push({ id: node.id, path: node.full_path || node.label })
        }
        if (Array.isArray(node.children) && node.children.length > 0) {
          walk(node.children)
        }
      }
    }
    walk(options)
    return rows
  }, [options])

  const selected = leaves.find((item) => item.path === value) ?? null
  const hasSelection = Boolean(selected?.path)

  const filteredLeaves = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return leaves
    return leaves.filter((item) => item.path.toLowerCase().includes(needle))
  }, [leaves, query])

  const menuRoots = useMemo(() => mapToMenuNodes(options), [options])
  const levelNodes = trail.length > 0
    ? (trail[trail.length - 1]?.children || [])
    : menuRoots
  const showSearch = query.trim().length > 0
  const recommendedLabel = recommendedPath ? leafLabel(recommendedPath) : ''

  const openRoot = () => {
    setTrail([])
    setQuery('')
  }

  return (
    <div ref={rootRef} style={{ position: 'relative', minWidth: 220, ...style }}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => {
          if (!disabled) {
            setOpen((prev) => {
              const next = !prev
              if (next) openRoot()
              return next
            })
          }
        }}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          padding: '5px 8px',
          borderRadius: 8,
          border: `1px solid ${t.stroke.secondary}`,
          background: t.bg.elevated,
          cursor: disabled ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.55 : 1,
          fontFamily: 'inherit',
        }}
      >
        {hasSelection ? (
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
            <TopicLeafIcon size={13} color={t.text.secondary} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: 12, color: t.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {leafLabel(selected?.path || '')}
            </span>
          </span>
        ) : (
          <span style={{ color: t.text.tertiary, fontSize: 12 }}>{placeholder}</span>
        )}
        <span
          aria-hidden
          style={{
            color: t.text.tertiary,
            fontSize: 11,
            transform: open ? 'rotate(180deg)' : 'none',
            transition: 'transform 120ms ease',
          }}
        >
          ▼
        </span>
      </button>
      {open ? (
        <div
          id={listId}
          role="listbox"
          aria-label="Тематика закрытия"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 40,
            maxHeight: 320,
            overflowY: 'auto',
            padding: 6,
            borderRadius: 10,
            border: `1px solid ${t.stroke.secondary}`,
            background: t.bg.elevated,
            boxShadow: t.kind === 'light'
              ? '0 12px 28px rgba(20, 40, 30, 0.14)'
              : '0 12px 28px rgba(0, 0, 0, 0.35)',
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
          }}
        >
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Поиск темы или пути..."
            style={{
              border: `1px solid ${t.stroke.secondary}`,
              borderRadius: 8,
              padding: '6px 8px',
              background: t.bg.editor,
              color: t.text.primary,
              fontFamily: 'inherit',
              fontSize: 12,
            }}
          />
          {recommendedPath && !showSearch && trail.length === 0 ? (
            <button
              type="button"
              role="option"
              aria-selected={recommendedPath === selected?.path}
              onClick={() => {
                onChange(recommendedPath, recommendedId)
                setOpen(false)
                openRoot()
              }}
              style={{
                display: 'flex',
                alignItems: 'center',
                width: '100%',
                textAlign: 'left',
                padding: '6px 8px',
                borderRadius: 8,
                border: `1px solid ${t.stroke.secondary}`,
                background: t.fill.tertiary,
                cursor: 'pointer',
                fontFamily: 'inherit',
                marginBottom: 4,
              }}
            >
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, width: '100%', minWidth: 0 }}>
                <span style={{ fontSize: 10, color: t.text.secondary, flexShrink: 0 }}>Рекомендуемая:</span>
                <TopicLeafIcon size={13} color={t.text.secondary} style={{ flexShrink: 0 }} />
                <span style={{ fontSize: 12, color: t.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {recommendedLabel}
                </span>
              </span>
            </button>
          ) : null}

          {!showSearch && trail.length > 0 ? (
            <button
              type="button"
              onClick={() => setTrail((prev) => prev.slice(0, -1))}
              style={{
                display: 'flex',
                alignItems: 'center',
                width: '100%',
                textAlign: 'left',
                padding: '6px 8px',
                borderRadius: 8,
                border: `1px solid ${t.stroke.secondary}`,
                background: 'transparent',
                cursor: 'pointer',
                fontFamily: 'inherit',
                marginBottom: 4,
              }}
            >
              ← Назад
            </button>
          ) : null}

          {!showSearch && trail.length > 0 ? (
            <TextPath t={t} trail={trail} />
          ) : null}

          {showSearch
            ? filteredLeaves.map((topic) => {
                const active = topic.path === selected?.path
                return (
                  <button
                    key={topic.id}
                    type="button"
                    role="option"
                    aria-selected={active}
                    title={topic.path}
                    onClick={() => {
                      onChange(topic.path, topic.id)
                      setOpen(false)
                      openRoot()
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      width: '100%',
                      textAlign: 'left',
                      padding: '6px 8px',
                      borderRadius: 8,
                      border: active ? `1px solid ${t.stroke.secondary}` : '1px solid transparent',
                      background: active ? t.fill.tertiary : 'transparent',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                  >
                    <TopicLeafIcon size={13} color={t.text.secondary} style={{ flexShrink: 0 }} />
                    <span style={{ fontSize: 12, color: t.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {leafLabel(topic.path)}
                    </span>
                  </button>
                )
              })
            : levelNodes.map((node) => {
                const isLeaf = !node.children?.length || Boolean(node.topicId)
                const active = (node.topicPath || node.label) === selected?.path
                return (
                  <button
                    key={node.key}
                    type="button"
                    role="option"
                    aria-selected={active}
                    title={node.topicPath || node.label}
                    onClick={() => {
                      if (isLeaf && node.topicPath) {
                        onChange(node.topicPath, String(node.topicId || ''))
                        setOpen(false)
                        openRoot()
                        return
                      }
                      setTrail((prev) => [...prev, node])
                      setQuery('')
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                      textAlign: 'left',
                      padding: '6px 8px',
                      borderRadius: 8,
                      border: active ? `1px solid ${t.stroke.secondary}` : '1px solid transparent',
                      background: active ? t.fill.tertiary : 'transparent',
                      cursor: 'pointer',
                      fontFamily: 'inherit',
                    }}
                  >
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                      {isLeaf ? (
                        <TopicLeafIcon size={13} color={t.text.secondary} style={{ flexShrink: 0 }} />
                      ) : (
                        <TopicGroupIcon size={13} color={t.accent.control} style={{ flexShrink: 0 }} />
                      )}
                      <span style={{ fontSize: 12, color: t.text.primary, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {node.label}
                      </span>
                    </span>
                    {!isLeaf ? <span style={{ color: t.text.tertiary, flexShrink: 0 }}>›</span> : null}
                  </button>
                )
              })}
          {(showSearch ? filteredLeaves.length : levelNodes.length) === 0 ? (
            <span style={{ padding: '6px 8px', color: t.text.tertiary, fontSize: 12 }}>
              Ничего не найдено
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

function TextPath({ t, trail }: { t: ArmTheme; trail: MenuNode[] }): JSX.Element {
  return (
    <div style={{ fontSize: 11, color: t.text.tertiary, padding: '2px 6px 6px' }}>
      {trail.map((item) => item.label).join(' / ')}
    </div>
  )
}
