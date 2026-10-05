import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Button, Card, StatusBadge } from '../../components'
import {
  listOcrTemplates,
  saveOcrTemplate,
  updateOcrTemplate,
  type OcrTemplate,
} from './api/ocrAdmin'
import { OPERATOR_DOC_TITLES, OPERATOR_DOC_TYPES, isOperatorDocType } from '../ocr/docTypes'
import './DocTypesScreen.css'

interface DocTypesScreenProps {
  canEdit?: boolean
}

interface SchemaRow {
  key: string
  required: boolean
  pattern: string
}

const EMPTY_FORM = {
  doc_type: '',
  title: '',
  confidence_min: '0.6',
}

const STATUS_TITLE: Record<string, string> = {
  published: 'Опубликован',
  draft: 'Не опубликован',
  archived: 'В архиве',
}

function emptyRow(): SchemaRow {
  return { key: '', required: false, pattern: '' }
}

function schemaToRows(schema: Record<string, unknown>, requiredKeys: string[]): SchemaRow[] {
  const keys = Object.keys(schema)
  if (!keys.length) return [emptyRow()]
  return keys.map((key) => {
    const spec = schema[key] && typeof schema[key] === 'object'
      ? (schema[key] as { required?: unknown; pattern?: unknown })
      : {}
    return {
      key,
      required: requiredKeys.includes(key) || spec.required === true,
      pattern: String(spec.pattern || ''),
    }
  })
}

function rowsToSchema(rows: SchemaRow[]): Record<string, unknown> {
  const schema: Record<string, unknown> = {}
  for (const row of rows) {
    const key = row.key.trim()
    if (!key) continue
    const spec: Record<string, unknown> = {}
    if (row.required) spec.required = true
    if (row.pattern.trim()) spec.pattern = row.pattern.trim()
    schema[key] = spec
  }
  return schema
}

const EXAMPLE_PATTERNS: Record<string, string> = {
  number: '^[A-ZА-Я]{2}\\d{7}$',
  series: '^[A-ZА-Я]{2}$',
  document_number: '^[A-ZА-Я]{2}\\d{7}$',
  full_name: '^[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\\-\\s]{1,80}$',
  birth_date: '^\\d{2}\\.\\d{2}\\.\\d{4}$',
  issue_date: '^\\d{2}\\.\\d{2}\\.\\d{4}$',
  expiry_date: '^\\d{2}\\.\\d{2}\\.\\d{4}$',
  amount: '^\\d+[.,]\\d{2}$',
  account_number: '^[A-Z]{2}\\d{2}[A-Z0-9]{11,30}$',
}

function rowsToJson(rows: SchemaRow[]): string {
  const schema = rowsToSchema(rows)
  for (const [key, spec] of Object.entries(schema)) {
    if (!spec || typeof spec !== 'object' || Array.isArray(spec)) continue
    const item = spec as Record<string, unknown>
    if (!item.pattern && EXAMPLE_PATTERNS[key]) {
      item.pattern = EXAMPLE_PATTERNS[key]
    }
  }
  return JSON.stringify(schema, null, 2)
}

function parseSchemaJson(raw: string): { schema: Record<string, unknown>; required: string[] } {
  const parsed = JSON.parse(raw) as Record<string, unknown>
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Нужен объект JSON, например { "number": { "required": true, "pattern": "^\\\\d{6,7}$" } }')
  }
  const nested = parsed.fields
  const schema = (
    nested && typeof nested === 'object' && !Array.isArray(nested)
      ? nested
      : parsed
  ) as Record<string, unknown>
  const listed = Array.isArray(parsed.required_fields)
    ? parsed.required_fields.map(String)
    : []
  const fromFlags = Object.entries(schema)
    .filter(([, spec]) => spec && typeof spec === 'object' && (spec as { required?: unknown }).required === true)
    .map(([key]) => key)
  return { schema, required: [...new Set([...listed, ...fromFlags])] }
}

const CYR_SLUG: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z',
  и: 'i', й: 'j', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r',
  с: 's', т: 't', у: 'u', ф: 'f', х: 'h', ц: 'c', ч: 'ch', ш: 'sh', щ: 'sch',
  ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya',
}

function slugFromTitle(title: string, taken: string[] = []): string {
  const mapped = Array.from(title.toLowerCase())
    .map((char) => CYR_SLUG[char] ?? char)
    .join('')
  let slug = mapped.replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 64)
  if (!slug) slug = 'doc'
  let candidate = slug
  let index = 2
  while (taken.includes(candidate)) {
    candidate = `${slug}_${index}`.slice(0, 64)
    index += 1
  }
  return candidate
}

export function DocTypesScreen({ canEdit = true }: DocTypesScreenProps) {
  const [items, setItems] = useState<OcrTemplate[]>([])
  const [selected, setSelected] = useState<string>('passport')
  const [form, setForm] = useState(EMPTY_FORM)
  const [rows, setRows] = useState<SchemaRow[]>([emptyRow()])
  const [editorMode, setEditorMode] = useState<'fields' | 'json'>('fields')
  const [jsonDraft, setJsonDraft] = useState('{}')
  const [jsonError, setJsonError] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [creating, setCreating] = useState(false)

  const reload = useCallback(async () => {
    setError('')
    try {
      const next = (await listOcrTemplates())
        .filter((item) => isOperatorDocType(item.doc_type))
        .map((item) => ({
          ...item,
          title: (
            isOperatorDocType(item.doc_type)
              ? OPERATOR_DOC_TITLES[item.doc_type]
              : item.title
          ),
        }))
        .sort((left, right) => (
          OPERATOR_DOC_TYPES.indexOf(left.doc_type as typeof OPERATOR_DOC_TYPES[number])
          - OPERATOR_DOC_TYPES.indexOf(right.doc_type as typeof OPERATOR_DOC_TYPES[number])
        ))
      setItems(next)
      if (!creating && next.length && !next.some((item) => item.doc_type === selected)) {
        setSelected(next[0].doc_type)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось загрузить типы документов')
    }
  }, [creating, selected])

  useEffect(() => {
    void reload()
  }, [reload])

  useEffect(() => {
    if (creating) return
    const current = items.find((item) => item.doc_type === selected)
    if (!current) return
    setForm({
      doc_type: current.doc_type,
      title: current.title,
      confidence_min: String(current.confidence_min ?? 0.6),
    })
    const nextRows = schemaToRows(current.field_schema || {}, current.required_fields || [])
    setRows(nextRows)
    setJsonDraft(rowsToJson(nextRows))
    setJsonError('')
    setEditorMode('fields')
  }, [creating, items, selected])

  const startNew = () => {
    setCreating(true)
    setSelected('')
    setForm({
      ...EMPTY_FORM,
      title: 'Новый тип документа',
      doc_type: slugFromTitle('Новый тип документа', items.map((item) => item.doc_type)),
    })
    setRows([emptyRow()])
    setJsonDraft('{\n  \n}')
    setEditorMode('fields')
    setMessage('')
    setError('')
    setJsonError('')
  }

  const showJson = () => {
    setJsonDraft(rowsToJson(rows))
    setJsonError('')
    setEditorMode('json')
  }

  const showFields = () => {
    setJsonError('')
    try {
      const parsed = parseSchemaJson(jsonDraft)
      setRows(schemaToRows(parsed.schema, parsed.required))
      setEditorMode('fields')
    } catch (err) {
      setJsonError(err instanceof Error ? err.message : 'Некорректный JSON')
    }
  }

  const onSave = async (event: FormEvent) => {
    event.preventDefault()
    if (!canEdit) return
    setBusy(true)
    setError('')
    setMessage('')
    setJsonError('')
    try {
      let fieldSchema = rowsToSchema(rows)
      let required = rows.filter((row) => row.required && row.key.trim()).map((row) => row.key.trim())
      if (editorMode === 'json') {
        const parsed = parseSchemaJson(jsonDraft)
        fieldSchema = parsed.schema
        required = parsed.required
        setRows(schemaToRows(parsed.schema, parsed.required))
      }
      if (!Object.keys(fieldSchema).length) {
        throw new Error('Добавьте хотя бы одно поле')
      }
      const title = form.title.trim()
      const payload = {
        doc_type: creating
          ? slugFromTitle(title, items.map((item) => item.doc_type))
          : form.doc_type.trim(),
        title,
        required_fields: required,
        confidence_min: Number(form.confidence_min),
        field_schema: fieldSchema,
        publish: true,
        bump_version: true,
      }
      if (!payload.title) {
        throw new Error('Название обязательно')
      }
      const exists = items.some((item) => item.doc_type === payload.doc_type)
      const saved = exists
        ? await updateOcrTemplate(payload.doc_type, payload)
        : await saveOcrTemplate(payload)
      setMessage(`Тип «${saved.title}» сохранён (версия ${saved.template_version})`)
      setCreating(false)
      setSelected(saved.doc_type)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка сохранения')
    } finally {
      setBusy(false)
    }
  }

  const updateRow = (index: number, patch: Partial<SchemaRow>) => {
    setRows((prev) => prev.map((row, rowIndex) => (
      rowIndex === index ? { ...row, ...patch } : row
    )))
  }

  return (
    <div className="doc-types" data-testid="doc-types-screen">
      <section className="doc-types__list" aria-label="Типы документов">
        {items.map((item) => (
          <button
            type="button"
            key={item.doc_type}
            className={!creating && item.doc_type === selected ? 'is-active' : undefined}
            onClick={() => {
              setCreating(false)
              setSelected(item.doc_type)
            }}
            data-testid={`doc-type-${item.doc_type}`}
          >
            <strong>{item.title}</strong>
            <StatusBadge status={item.status === 'published' ? 'success' : 'neutral'}>
              {STATUS_TITLE[item.status] || item.status}
              {item.template_version ? ` · в.${item.template_version}` : ''}
            </StatusBadge>
          </button>
        ))}
        <Button type="button" disabled={!canEdit} onClick={startNew} data-testid="doc-type-new">
          + Новый тип
        </Button>
      </section>

      <Card className="doc-types__editor">
        <header>
          <div>
            <h2>{creating ? 'Новый тип документа' : 'Тип документа'}</h2>
            <p>
              Тип не учит распознавание. Он задаёт, какие поля обязательны после чтения.
            </p>
          </div>
        </header>

        <form className="doc-types__form" onSubmit={(event) => void onSave(event)}>
          <label className="doc-types__wide">
            <span>Название</span>
            <input
              value={form.title}
              disabled={!canEdit || busy}
              onChange={(event) => {
                const title = event.target.value
                setForm((prev) => ({
                  ...prev,
                  title,
                  doc_type: creating
                    ? slugFromTitle(title, items.map((item) => item.doc_type))
                    : prev.doc_type,
                }))
              }}
              placeholder="Паспорт"
            />
            <input type="hidden" data-testid="doc-type-code" value={form.doc_type} readOnly />
          </label>
          <label>
            <span>Минимальная уверенность</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.01}
              value={form.confidence_min}
              disabled={!canEdit || busy}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, confidence_min: event.target.value }))
              }
            />
          </label>

          <div className="doc-types__fields-head">
            <h3>Поля для проверки</h3>
            {editorMode === 'fields' ? (
              <Button
                type="button"
                variant="ghost"
                disabled={!canEdit || busy}
                onClick={showJson}
                data-testid="doc-type-json-open"
              >
                JSON
              </Button>
            ) : (
              <Button
                type="button"
                variant="ghost"
                disabled={!canEdit || busy}
                onClick={showFields}
              >
                Таблица
              </Button>
            )}
          </div>

          {editorMode === 'json' ? (
            <div className="doc-types__json-inline" data-testid="doc-type-json-dialog">
              <p>
                У обязательного поля — <code>&quot;required&quot;: true</code>,
                регулярка — в <code>pattern</code>:
              </p>
              <pre className="doc-types__json-example">{`{
  "number": { "required": true, "pattern": "^[A-ZА-Я]{2}\\\\d{7}$" },
  "series": { "required": true, "pattern": "^[A-ZА-Я]{2}$" },
  "birth_date": { "pattern": "^\\\\d{2}\\\\.\\\\d{2}\\\\.\\\\d{4}$" }
}`}</pre>
              <textarea
                rows={16}
                value={jsonDraft}
                disabled={!canEdit || busy}
                onChange={(event) => setJsonDraft(event.target.value)}
                data-testid="doc-type-schema"
                spellCheck={false}
              />
              {jsonError ? <p className="doc-types__error" role="alert">{jsonError}</p> : null}
            </div>
          ) : (
          <div className="doc-types__fields" data-testid="doc-type-fields">
            <div className="doc-types__fields-row doc-types__fields-row--head">
              <span>Ключ</span>
              <span>Обязательное</span>
              <span />
            </div>
            {rows.map((row, index) => (
              <div className="doc-types__fields-row" key={`row-${index}`}>
                <input
                  value={row.key}
                  placeholder="ФИО"
                  disabled={!canEdit || busy}
                  onChange={(event) => updateRow(index, { key: event.target.value })}
                  aria-label={`Ключ поля ${index + 1}`}
                />
                <label className="doc-types__required">
                  <input
                    type="checkbox"
                    checked={row.required}
                    disabled={!canEdit || busy}
                    onChange={(event) => updateRow(index, { required: event.target.checked })}
                  />
                  Да
                </label>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={!canEdit || busy || rows.length <= 1}
                  onClick={() => setRows((prev) => prev.filter((_, rowIndex) => rowIndex !== index))}
                >
                  ×
                </Button>
              </div>
            ))}
            <Button
              type="button"
              disabled={!canEdit || busy}
              onClick={() => setRows((prev) => [...prev, emptyRow()])}
              data-testid="doc-type-add-field"
            >
              + Поле
            </Button>
          </div>
          )}

          <div className="doc-types__actions">
            <Button type="submit" disabled={!canEdit || busy} data-testid="doc-type-publish">
              Сохранить
            </Button>
          </div>
        </form>

        {error ? <p className="doc-types__error" role="alert">{error}</p> : null}
        {message ? <p className="doc-types__ok" role="status">{message}</p> : null}
      </Card>
    </div>
  )
}
