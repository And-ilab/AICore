import { useEffect, useMemo, useState } from 'react'
import { REPLY_TEMPLATES } from '../../api/onlineChatApi'
import { Button, Pill, Row, Text, TextArea } from '../primitives'
import { ArmModuleFrame, formatDateTime, ModuleEmpty } from './ArmModuleFrame'
import { DEFAULT_TEMPLATES } from './demoData'
import type { ArmModuleProps, ReplyTemplateItem, ReplyTemplateScope } from './types'

const STORAGE_KEY = 'arm-reply-templates-v1'
export const CATEGORIES = ['Общие', 'Карты', 'Ипотека', 'Платежи', 'Прочее']

function normalizeTemplate(item: ReplyTemplateItem): ReplyTemplateItem {
  return {
    ...item,
    scope: item.scope ?? 'shared',
    ownerName: item.ownerName ?? '',
  }
}

function seedTemplates(): ReplyTemplateItem[] {
  const fromApi = REPLY_TEMPLATES.map((body, index) =>
    normalizeTemplate({
      id: `seed-${index}`,
      title: body.slice(0, 42) + (body.length > 42 ? '…' : ''),
      category: 'Общие',
      body,
      updatedAt: new Date().toISOString(),
      favorite: index < 2,
      scope: 'shared',
    }),
  )
  const merged = DEFAULT_TEMPLATES.map(normalizeTemplate)
  for (const item of fromApi) {
    if (!merged.some((tpl) => tpl.body === item.body)) merged.push(item)
  }
  return merged
}

function readAllTemplates(): ReplyTemplateItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return seedTemplates()
    const parsed = JSON.parse(raw) as ReplyTemplateItem[]
    return parsed.length ? parsed.map(normalizeTemplate) : seedTemplates()
  } catch {
    return seedTemplates()
  }
}

function writeAllTemplates(items: ReplyTemplateItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.map(normalizeTemplate)))
  } catch {
    /* ignore */
  }
}

function visibleFor(operatorName: string, all: ReplyTemplateItem[]): ReplyTemplateItem[] {
  const name = operatorName.trim()
  if (!name) return all.filter((item) => item.scope === 'shared')
  return all.filter(
    (item) => item.scope === 'shared' || (item.scope === 'personal' && item.ownerName === name),
  )
}

/** Templates visible to this operator: shared + own personal. */
export function loadReplyTemplates(operatorName = ''): ReplyTemplateItem[] {
  return visibleFor(operatorName, readAllTemplates())
}

function saveVisibleMutation(
  operatorName: string,
  nextVisible: ReplyTemplateItem[],
) {
  const all = readAllTemplates()
  const nextIds = new Set(nextVisible.map((item) => item.id))
  const keptOthers = all.filter((item) => {
    const isMinePersonal = item.scope === 'personal' && item.ownerName === operatorName
    const isShared = item.scope === 'shared'
    if (isMinePersonal) return nextIds.has(item.id)
    if (isShared) return nextIds.has(item.id) || !visibleFor(operatorName, all).some((v) => v.id === item.id)
    // other operators' personal templates
    return true
  })
  const byId = new Map(keptOthers.map((item) => [item.id, item]))
  for (const item of nextVisible) byId.set(item.id, normalizeTemplate(item))
  writeAllTemplates([...byId.values()])
}

export function TemplatesModule({ t, scheme, operatorName, armRole, onBack }: ArmModuleProps) {
  const [items, setItems] = useState<ReplyTemplateItem[]>(() => loadReplyTemplates(operatorName))
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [draft, setDraft] = useState<ReplyTemplateItem | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const canCreateShared = armRole === 'supervisor'

  useEffect(() => {
    setItems(loadReplyTemplates(operatorName))
  }, [operatorName])

  const persistItems = (next: ReplyTemplateItem[]) => {
    setItems(next)
    saveVisibleMutation(operatorName, next)
  }

  const categories = useMemo(() => {
    const counts = new Map<string, number>()
    for (const cat of CATEGORIES) counts.set(cat, 0)
    for (const item of items) {
      counts.set(item.category, (counts.get(item.category) ?? 0) + 1)
    }
    return CATEGORIES.map((name) => ({ name, count: counts.get(name) ?? 0 }))
  }, [items])

  const inCategory = useMemo(() => {
    if (!selectedCategory) return []
    const q = query.trim().toLowerCase()
    return items.filter((item) => {
      if (item.category !== selectedCategory) return false
      if (!q) return true
      return (
        item.title.toLowerCase().includes(q)
        || item.body.toLowerCase().includes(q)
      )
    })
  }, [items, selectedCategory, query])

  const selected = items.find((item) => item.id === selectedId) ?? null
  const editing = draft ?? selected

  const startCreate = (scope: ReplyTemplateScope = 'personal') => {
    const blank: ReplyTemplateItem = {
      id: `tpl-${Date.now()}`,
      title: 'Новый шаблон',
      category: selectedCategory ?? 'Общие',
      body: 'Здравствуйте, {{client_name}}!',
      updatedAt: new Date().toISOString(),
      scope,
      ownerName: scope === 'personal' ? operatorName : '',
    }
    setDraft(blank)
    setSelectedId(blank.id)
    if (!selectedCategory) setSelectedCategory(blank.category)
  }

  const saveDraft = () => {
    if (!draft) return
    const next = { ...normalizeTemplate(draft), updatedAt: new Date().toISOString() }
    const exists = items.some((item) => item.id === next.id)
    const updated = exists
      ? items.map((item) => (item.id === next.id ? next : item))
      : [next, ...items]
    persistItems(updated)
    setSelectedId(next.id)
    setDraft(null)
    setNotice(
      next.scope === 'shared'
        ? 'Общий шаблон сохранён — виден всем операторам.'
        : 'Личный шаблон сохранён — виден только вам.',
    )
  }

  const removeSelected = () => {
    if (!selected) return
    persistItems(items.filter((item) => item.id !== selected.id))
    setDraft(null)
    setSelectedId(null)
    setNotice('Шаблон удалён')
  }

  const toggleFavorite = () => {
    if (!selected) return
    persistItems(
      items.map((item) =>
        item.id === selected.id ? { ...item, favorite: !item.favorite } : item,
      ),
    )
  }

  const previewBody = (body: string) =>
    body
      .replaceAll('{{client_name}}', 'Анна')
      .replaceAll('{{operator_name}}', operatorName)

  const copyBody = async () => {
    if (!editing) return
    try {
      await navigator.clipboard.writeText(previewBody(editing.body))
      setNotice('Текст скопирован в буфер')
    } catch {
      setNotice('Не удалось скопировать')
    }
  }

  return (
    <ArmModuleFrame
      t={t}
      scheme={scheme}
      title="Шаблоны ответов"
      onBack={onBack}
      bodyStyle={{ overflow: 'hidden', display: 'flex' }}
      actions={
        <>
          {canCreateShared ? (
            <>
              <Button
                variant="secondary"
                onClick={() => startCreate('personal')}
                style={{ padding: '8px 14px', fontSize: 13 }}
              >
                + Личный
              </Button>
              <Button
                variant="primary"
                onClick={() => startCreate('shared')}
                style={{ padding: '8px 14px', fontSize: 13, fontWeight: 700 }}
              >
                + Общий
              </Button>
            </>
          ) : (
            <Button
              variant="primary"
              onClick={() => startCreate('personal')}
              style={{ padding: '8px 16px', fontSize: 14, fontWeight: 700 }}
            >
              + Новый
            </Button>
          )}
          {draft ? (
            <Button variant="secondary" onClick={saveDraft}>Сохранить</Button>
          ) : null}
        </>
      }
    >
      <aside
        style={{
          width: 320,
          flexShrink: 0,
          borderRight: `1px solid ${t.stroke.secondary}`,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          background: t.bg.editor,
        }}
      >
        <div style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {selectedCategory ? (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSelectedCategory(null)
                setSelectedId(null)
                setDraft(null)
                setQuery('')
              }}
              style={{ alignSelf: 'flex-start' }}
            >
              ← Категории
            </Button>
          ) : null}
          {selectedCategory ? (
            <>
              <Text weight="semibold" style={{ fontSize: 14 }}>{selectedCategory}</Text>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Поиск в категории"
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: `1px solid ${t.stroke.secondary}`,
                  background: t.bg.elevated,
                  color: t.text.primary,
                  fontFamily: 'inherit',
                  fontSize: 13,
                }}
              />
            </>
          ) : (
            <Text style={{ fontSize: 12, color: t.text.secondary }}>
              Сначала выберите категорию шаблонов
            </Text>
          )}
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 12px' }}>
          {!selectedCategory ? (
            categories.map((cat) => (
              <button
                key={cat.name}
                type="button"
                onClick={() => setSelectedCategory(cat.name)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  padding: '12px 14px',
                  marginBottom: 6,
                  borderRadius: 10,
                  border: `1px solid ${t.stroke.secondary}`,
                  background: t.bg.elevated,
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  color: t.text.primary,
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 8,
                }}
              >
                <Text weight="semibold" style={{ fontSize: 14 }}>{cat.name}</Text>
                <Pill size="sm">{cat.count}</Pill>
              </button>
            ))
          ) : inCategory.length === 0 ? (
            <Text style={{ fontSize: 12, color: t.text.secondary, padding: 8 }}>Нет шаблонов</Text>
          ) : (
            inCategory.map((item) => {
              const active = item.id === (draft?.id ?? selectedId)
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setSelectedId(item.id)
                    setDraft(null)
                  }}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    padding: '10px 12px',
                    marginBottom: 4,
                    borderRadius: 8,
                    border: `1px solid ${active ? scheme.accent : 'transparent'}`,
                    background: active ? t.fill.tertiary : 'transparent',
                    cursor: 'pointer',
                    fontFamily: 'inherit',
                    color: t.text.primary,
                  }}
                >
                  <Row style={{ justifyContent: 'space-between', gap: 6 }}>
                    <Text weight="semibold" style={{ fontSize: 13 }}>
                      {item.favorite ? '★ ' : ''}
                      {item.title}
                    </Text>
                    <Pill size="sm">{item.scope === 'personal' ? 'личный' : 'общий'}</Pill>
                  </Row>
                  <Text
                    style={{
                      fontSize: 11,
                      color: t.text.secondary,
                      marginTop: 4,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {item.body}
                  </Text>
                </button>
              )
            })
          )}
        </div>
      </aside>

      <section style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: 16 }}>
        {!editing ? (
          <ModuleEmpty
            t={t}
            title={selectedCategory ? 'Выберите шаблон или создайте новый' : 'Выберите категорию слева'}
            hint={
              canCreateShared
                ? 'Супервизор может создать личный или общий шаблон.'
                : 'Ваши шаблоны видны только вам; общие — всем операторам.'
            }
          />
        ) : (
          <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 12 }}>
            {notice ? (
              <div
                style={{
                  padding: '8px 10px',
                  borderRadius: 8,
                  background: t.fill.tertiary,
                  fontSize: 12,
                  color: t.text.secondary,
                }}
              >
                {notice}
              </div>
            ) : null}

            <label style={{ display: 'grid', gap: 4 }}>
              <Text style={{ fontSize: 11, color: t.text.tertiary }}>Название</Text>
              <input
                value={editing.title}
                onChange={(e) =>
                  setDraft({ ...(draft ?? editing), title: e.target.value })
                }
                style={inputStyle(t)}
              />
            </label>

            <label style={{ display: 'grid', gap: 4 }}>
              <Text style={{ fontSize: 11, color: t.text.tertiary }}>Категория</Text>
              <select
                value={editing.category}
                onChange={(e) =>
                  setDraft({ ...(draft ?? editing), category: e.target.value })
                }
                style={inputStyle(t)}
              >
                {CATEGORIES.map((item) => (
                  <option key={item} value={item}>{item}</option>
                ))}
              </select>
            </label>

            {canCreateShared && draft ? (
              <label style={{ display: 'grid', gap: 4 }}>
                <Text style={{ fontSize: 11, color: t.text.tertiary }}>Видимость</Text>
                <select
                  value={draft.scope ?? 'personal'}
                  onChange={(e) => {
                    const scope = e.target.value as ReplyTemplateScope
                    setDraft({
                      ...draft,
                      scope,
                      ownerName: scope === 'personal' ? operatorName : '',
                    })
                  }}
                  style={inputStyle(t)}
                >
                  <option value="personal">Только мой</option>
                  <option value="shared">Общий для всех</option>
                </select>
              </label>
            ) : (
              <Text style={{ fontSize: 12, color: t.text.secondary }}>
                {editing.scope === 'shared' ? 'Общий шаблон' : 'Личный шаблон'}
              </Text>
            )}

            <label style={{ display: 'grid', gap: 4 }}>
              <Text style={{ fontSize: 11, color: t.text.tertiary }}>Текст шаблона</Text>
              <TextArea
                value={editing.body}
                onChange={(value) => setDraft({ ...(draft ?? editing), body: value })}
                rows={6}
              />
            </label>

            <div
              style={{
                padding: 12,
                borderRadius: 8,
                border: `1px solid ${t.stroke.secondary}`,
                background: t.fill.secondary,
              }}
            >
              <Text style={{ fontSize: 11, color: t.text.tertiary, marginBottom: 6 }}>Предпросмотр</Text>
              <Text style={{ fontSize: 13, lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                {previewBody(editing.body)}
              </Text>
            </div>

            <Row style={{ gap: 8, flexWrap: 'wrap' }}>
              {draft ? (
                <Button variant="primary" size="sm" onClick={saveDraft}>Сохранить</Button>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => setDraft({ ...editing })}
                >
                  Редактировать
                </Button>
              )}
              <Button variant="secondary" size="sm" onClick={copyBody}>Копировать</Button>
              {!draft && selected ? (
                <Button variant="ghost" size="sm" onClick={toggleFavorite}>
                  {selected.favorite ? 'Убрать из избранного' : 'В избранное'}
                </Button>
              ) : null}
              {!draft && selected ? (
                <Button variant="ghost" size="sm" onClick={removeSelected}>Удалить</Button>
              ) : null}
            </Row>
            {selected && !draft ? (
              <Text style={{ fontSize: 11, color: t.text.tertiary }}>
                Обновлён: {formatDateTime(selected.updatedAt)}
              </Text>
            ) : null}
          </div>
        )}
      </section>
    </ArmModuleFrame>
  )
}

function inputStyle(t: ArmModuleProps['t']) {
  return {
    width: '100%',
    padding: '8px 10px',
    borderRadius: 8,
    border: `1px solid ${t.stroke.secondary}`,
    background: t.bg.editor,
    color: t.text.primary,
    fontFamily: 'inherit',
    fontSize: 13,
  } as const
}
