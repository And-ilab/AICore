import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
} from 'react'
import { Button, Card, StatusBadge, Table, TableBody, TableCell, TableHead, TableHeaderCell, TableRow } from '../../components'
import {
  approveOcrJob,
  createMyOcrTemplate,
  deleteMyOcrTemplate,
  downloadOcrFieldsDocx,
  exportOcrJob,
  ocrExportRows,
  fetchOcrResult,
  listMyOcrTemplates,
  listOcrDocTypes,
  listOcrJobs,
  ocrJobOriginalUrl,
  updateMyOcrTemplate,
  uploadOcrDocument,
  type OcrDocType,
  type OcrUserTemplate,
  type OcrUserTemplateField,
} from '../admin/api/ocrAdmin'
import {
  OPERATOR_DOC_TITLES,
  OPERATOR_DOC_TYPES,
  isMineDocType,
  isMlDocType,
  isOperatorDocType,
  mineDocType,
  ML_DOC_TYPE,
  operatorDocTitle,
  parseMineTemplateId,
  readChosenDocType,
  readUploadDocType,
  writeChosenDocType,
  writeUploadDocType,
} from './docTypes'
import { filterOcrFields } from './fieldQuality'
import './OcrDocumentsPanel.css'

export type OcrSubTab = 'queue' | 'upload' | 'review' | 'mine'

export interface OcrField {
  id: string
  apiKey: string
  label: string
  value: string
  confidence: number
  bbox: { left: number; top: number; width: number; height: number }
}

export interface OcrQueueItem {
  id: string
  file: string
  docType: string
  status: 'queued' | 'ocr' | 'review' | 'done' | 'error'
  progress: number
  confidence: number | null
  batchId?: string
  sourceArchive?: string
}

export function canCreateOcrUserTemplate(
  status: OcrQueueItem['status'] | undefined,
  fields: OcrField[],
  approved: boolean,
): boolean {
  if (!status || status === 'queued' || status === 'ocr' || status === 'error') return false
  if (approved || status === 'done') return true
  if (status !== 'review' || !fields.length) return false
  return !fields.some((field) => !field.value.trim() || field.confidence < 0.6)
}

const STATUS_LABEL: Record<OcrQueueItem['status'], string> = {
  queued: 'Очередь',
  ocr: 'OCR',
  review: 'На проверке',
  done: 'Готово',
  error: 'Ошибка валидации',
}

const ACCEPT =
  '.png,.jpg,.jpeg,.pdf,.tiff,.tif,.zip,.rar,image/png,image/jpeg,application/pdf,image/tiff,application/zip,application/x-rar-compressed'

/** UI id → backend field key (and reverse for known aliases). */
const UI_TO_API: Record<string, string> = {
  fio: 'full_name',
  full_name: 'full_name',
  series: 'series',
  number: 'number',
  issued: 'issue_date',
  issue_date: 'issue_date',
}

const API_TO_UI: Record<string, string> = {
  full_name: 'fio',
  issue_date: 'issued',
  series: 'series',
  number: 'number',
}

const FIELD_LABELS: Record<string, string> = {
  fio: 'ФИО',
  full_name: 'ФИО',
  surname: 'Фамилия',
  given_name: 'Имя',
  patronymic: 'Отчество',
  series: 'Серия паспорта',
  number: 'Номер',
  issued: 'Дата выдачи',
  issue_date: 'Дата выдачи',
  birth_date: 'Дата рождения',
  address: 'Адрес / прописка',
  registration_date: 'Дата регистрации',
  issued_by: 'Кем выдан',
  birth_place: 'Место рождения',
  personal_number: 'Личный номер',
  document_number: 'Номер документа',
  payer: 'Плательщик',
  beneficiary: 'Получатель',
  amount: 'Сумма',
  purpose: 'Назначение',
  currency: 'Валюта',
  product: 'Продукт',
  application_date: 'Дата заявления',
  application_number: 'Номер заявления',
  signature_present: 'Подпись',
  account_number: 'Счёт',
  opening_balance: 'Входящий остаток',
  closing_balance: 'Исходящий остаток',
  period: 'Период',
  agreement_number: 'Номер договора',
  agreement_date: 'Дата договора',
  principal: 'Сумма кредита',
  interest_rate: 'Процентная ставка',
  term: 'Срок',
  operation_id: 'Номер операции',
  operation_date: 'Дата операции',
  status: 'Статус',
  title: 'Заголовок',
  nationality: 'Гражданство',
  sex: 'Пол',
  inn: 'ИНН',
  expiry_date: 'Срок действия',
}

const HIDDEN_FIELD_KEYS = new Set(['signature_present', 'title', 'full_name'])

const DOC_TYPE_TITLE: Record<string, string> = {
  unknown: 'Документ',
  other: 'Документ',
  passport: OPERATOR_DOC_TITLES.passport,
  account_statement: OPERATOR_DOC_TITLES.account_statement,
  loan_agreement: OPERATOR_DOC_TITLES.loan_agreement,
}

const PASSPORT_OPERATOR_FIELDS = [
  'surname',
  'given_name',
  'series',
  'number',
  'birth_date',
  'issue_date',
] as const

const BUILTIN_SCHEMAS: Record<string, Record<string, unknown>> = {
  passport: Object.fromEntries(PASSPORT_OPERATOR_FIELDS.map((key) => [key, {}])),
  account_statement: {
    account_number: {},
    currency: {},
    period: {},
    opening_balance: {},
    closing_balance: {},
  },
  loan_agreement: {
    agreement_number: {},
    agreement_date: {},
    principal: {},
    interest_rate: {},
    term: {},
  },
}

function humanizeKey(key: string): string {
  if (/[А-Яа-яЁё]/.test(key)) return key.replace(/_/g, ' ')
  return key.replace(/_/g, ' ').trim() || 'Поле'
}

function russianFieldLabel(id: string, apiKey: string, explicit?: string): string {
  return FIELD_LABELS[id] || FIELD_LABELS[apiKey] || (
    explicit && String(explicit).trim() && String(explicit).length <= 40
      ? String(explicit).trim()
      : ''
  ) || humanizeKey(apiKey || id)
}

function typeTitle(docType: string, mine: OcrUserTemplate[] = []): string {
  const mineId = parseMineTemplateId(docType)
  if (mineId) {
    return mine.find((item) => item.id === mineId)?.name || 'Мой шаблон'
  }
  return operatorDocTitle(docType) || DOC_TYPE_TITLE[docType] || docType || DOC_TYPE_TITLE.unknown
}

function suggestUserTemplateName(item: OcrQueueItem, currentFields: OcrField[]): string {
  const stamp = new Date().toISOString().slice(0, 10)
  const typeName = isOperatorDocType(item.docType) ? operatorDocTitle(item.docType) : ''
  const first = currentFields.find((field) => field.value.trim())
  const title = typeName || first?.label?.trim() || 'Документ'
  return `${title} · ${stamp}`.slice(0, 80)
}

function isPassportPageType(docType: string): boolean {
  return docType.startsWith('passport_')
}

function apiDocType(docType: string): string {
  if (isPassportPageType(docType)) return 'passport'
  return docType || 'unknown'
}

function resolveDisplayType(docType: string, _pageKinds: string[] = []): string {
  if (isMlDocType(docType)) return ML_DOC_TYPE
  if (isOperatorDocType(docType)) return docType
  if (isPassportPageType(docType) || docType === 'unknown' || !docType) return 'passport'
  return 'passport'
}

function rememberChosenType(
  store: { current: Record<string, string> },
  jobId: string,
  type: string,
) {
  if (!jobId) return
  store.current[jobId] = type
  writeChosenDocType(jobId, type)
}

function chosenTypeForJob(
  store: { current: Record<string, string> },
  jobId: string,
  fallback = '',
): string {
  return store.current[jobId] || readChosenDocType(jobId) || fallback
}

function inferDocTypeFromName(fileName: string): string {
  const name = fileName.toLowerCase()
  if (/passport|pasport|паспорт/.test(name)) return 'passport'
  if (/poruchen|platezh|payment/.test(name)) return 'payment_order'
  if (/kvitan|receipt|chek/.test(name)) return 'payment_receipt'
  if (/vypisk|spravk|statement/.test(name)) return 'account_statement'
  if (/kredit|loan/.test(name)) return 'loan_agreement'
  if (/zayavl|anket|application/.test(name)) return 'banking_application'
  if (/dogovor|contract/.test(name)) return 'loan_agreement'
  return ''
}

const DEFAULT_BBOX: Record<string, OcrField['bbox']> = {
  fio: { left: 12, top: 28, width: 52, height: 7 },
  series: { left: 12, top: 40, width: 18, height: 7 },
  number: { left: 32, top: 40, width: 28, height: 7 },
  issued: { left: 12, top: 52, width: 30, height: 7 },
}

/** Demo passport fields for Storybook / offline visual tests. */
const DEMO_PASSPORT_FIELDS: OcrField[] = [
  {
    id: 'surname',
    apiKey: 'surname',
    label: 'Фамилия',
    value: 'Иванов',
    confidence: 0.96,
    bbox: DEFAULT_BBOX.fio,
  },
  {
    id: 'given_name',
    apiKey: 'given_name',
    label: 'Имя',
    value: 'Иван',
    confidence: 0.96,
    bbox: DEFAULT_BBOX.fio,
  },
  {
    id: 'series',
    apiKey: 'series',
    label: 'Серия паспорта',
    value: 'MP',
    confidence: 0.88,
    bbox: DEFAULT_BBOX.series,
  },
  {
    id: 'number',
    apiKey: 'number',
    label: 'Номер',
    value: '4123456',
    confidence: 0.72,
    bbox: DEFAULT_BBOX.number,
  },
  {
    id: 'issued',
    apiKey: 'issue_date',
    label: 'Дата выдачи',
    value: '12.03.2019',
    confidence: 0.54,
    bbox: DEFAULT_BBOX.issued,
  },
]

function confidenceTone(confidence: number): 'success' | 'warning' | 'danger' {
  if (confidence >= 0.85) return 'success'
  if (confidence >= 0.6) return 'warning'
  return 'danger'
}

function formatConfidence(value: number | null): string {
  if (value == null) return '—'
  return `${Math.round(value * 100)}%`
}

function avgConfidence(fields: OcrField[]): number | null {
  if (!fields.length) return null
  const sum = fields.reduce((acc, field) => acc + field.confidence, 0)
  return sum / fields.length
}

function mapBackendStatus(raw: unknown, validationStatus?: unknown): OcrQueueItem['status'] {
  const status = String(raw || '')
  const validation = String(validationStatus || '')
  if (status === 'queued') return 'queued'
  if (status === 'ocr_processing') return 'ocr'
  if (status === 'processing_error') return 'error'
  if (status === 'completed') {
    if (validation === 'valid' || validation === 'approved') return 'done'
    return 'review'
  }
  return 'queued'
}

function fieldValue(raw: unknown): string {
  if (raw == null) return ''
  if (typeof raw === 'object' && raw !== null && 'value' in raw) {
    const value = (raw as { value?: unknown }).value
    return value == null ? '' : String(value)
  }
  return String(raw)
}

function fieldConfidence(raw: unknown): number {
  if (raw && typeof raw === 'object' && 'confidence' in raw) {
    const conf = (raw as { confidence?: unknown }).confidence
    if (typeof conf === 'number' && Number.isFinite(conf)) {
      return conf > 1 ? conf / 100 : conf
    }
  }
  return 0
}

function unwrapOcrResult(
  payload: Record<string, unknown> | null | undefined,
): Record<string, unknown> | null {
  if (!payload) return null
  const nested = payload.result
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    const inner = nested as Record<string, unknown>
    if (inner.fields || inner.normalized_fields || inner.extractor_fields) {
      return inner
    }
  }
  return payload
}

function rawResultFields(result: Record<string, unknown> | null | undefined): unknown {
  const payload = unwrapOcrResult(result)
  if (!payload) return null
  for (const key of ['fields', 'normalized_fields', 'extractor_fields'] as const) {
    const fields = payload[key]
    if (fields && typeof fields === 'object' && Object.keys(fields as object).length) {
      return fields
    }
  }
  return payload.fields
}

function fieldsAreEmpty(fields: OcrField[]): boolean {
  return !fields.length || fields.every((field) => !String(field.value).trim())
}

function fieldsFromResult(fieldsRaw: unknown): OcrField[] {
  if (!fieldsRaw || typeof fieldsRaw !== 'object') return []
  const entries = Object.entries(fieldsRaw as Record<string, unknown>)
  const preferred = ['full_name', 'series', 'number', 'issue_date']
  const ordered = [
    ...preferred.filter((key) => key in (fieldsRaw as object)),
    ...entries.map(([key]) => key).filter((key) => !preferred.includes(key)),
  ]
  const mapped = ordered
    .filter((apiKey) => !HIDDEN_FIELD_KEYS.has(apiKey))
    .map((apiKey, index) => {
      const raw = (fieldsRaw as Record<string, unknown>)[apiKey]
      const id = API_TO_UI[apiKey] || apiKey
      const bbox = DEFAULT_BBOX[id] || {
        left: 10,
        top: 18 + index * 12,
        width: 48,
        height: 7,
      }
      const explicitLabel = (
        raw && typeof raw === 'object' && raw !== null && 'label' in raw
          ? String((raw as { label?: unknown }).label || '')
          : ''
      )
      return {
        id,
        apiKey,
        label: russianFieldLabel(id, apiKey, explicitLabel),
        value: fieldValue(raw),
        confidence: fieldConfidence(raw),
        bbox,
      }
    })
    .filter((field) => Boolean(String(field.value).trim()))
  return filterOcrFields(mapped)
}

function fieldsToApiPayload(fields: OcrField[]): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of fields) {
    const key = field.apiKey || UI_TO_API[field.id] || field.id
    payload[key] = {
      value: field.value,
      confidence: field.confidence,
    }
  }
  return payload
}

function pageKindsFromResult(result: Record<string, unknown> | null | undefined): string[] {
  const payload = unwrapOcrResult(result)
  const raw = payload?.page_kinds
  return Array.isArray(raw) ? raw.map((item) => String(item)) : []
}

function withPassportIdentity(
  schema: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  const source = schema || {}
  const next: Record<string, unknown> = {}
  for (const key of PASSPORT_OPERATOR_FIELDS) {
    const current = source[key]
    next[key] = current && typeof current === 'object' ? current : {}
  }
  return next
}

function schemaForType(
  docType: string,
  templates: OcrDocType[],
  mineTemplates: OcrUserTemplate[] = [],
): Record<string, unknown> | undefined {
  const mineId = parseMineTemplateId(docType)
  if (mineId) {
    const mine = mineTemplates.find((item) => item.id === mineId)
    if (!mine) return undefined
    const next: Record<string, unknown> = {}
    for (const field of mine.fields || []) {
      if (field.key) next[field.key] = field
    }
    return next
  }
  if (isMlDocType(docType) || !docType || docType === 'unknown' || docType === 'other') {
    return undefined
  }
  const type = isPassportPageType(docType)
    ? 'passport'
    : isOperatorDocType(docType) ? docType : ''
  if (!type) return undefined
  const raw = templates.find((tpl) => tpl.doc_type === type)?.field_schema
    || BUILTIN_SCHEMAS[type]
  return type === 'passport' ? withPassportIdentity(raw) : raw
}

function looksLikePassportFields(fields: OcrField[]): boolean {
  const values = new Map(
    fields.map((field) => [field.apiKey || field.id, String(field.value || '').trim()]),
  )
  return Boolean(
    (values.get('surname') && values.get('given_name'))
    || (values.get('series') && values.get('number')),
  )
}

function typeForExtractedFields(
  rawType: string,
  parsed: OcrField[],
  pageKinds: string[] = [],
  forcedType = '',
): string {
  if (isMlDocType(forcedType)) return ML_DOC_TYPE
  if (forcedType && isOperatorDocType(forcedType)) {
    return resolveDisplayType(forcedType, pageKinds)
  }
  if (isMlDocType(rawType)) return ML_DOC_TYPE
  const detected = rawType && rawType !== 'unknown' ? rawType : ''
  if (detected === 'passport' || isPassportPageType(detected)) {
    return looksLikePassportFields(parsed)
      ? resolveDisplayType(detected, pageKinds)
      : (parsed.length ? ML_DOC_TYPE : resolveDisplayType(detected, pageKinds))
  }
  if (isOperatorDocType(detected)) return detected
  if (detected) return detected
  return looksLikePassportFields(parsed) ? 'passport' : ML_DOC_TYPE
}

function fieldsForExtractedType(
  parsed: OcrField[],
  resolvedType: string,
  templates: OcrDocType[],
  mineTemplates: OcrUserTemplate[] = [],
): OcrField[] {
  if (isMineDocType(resolvedType)) {
    return mergeTemplateFields(parsed, schemaForType(resolvedType, templates, mineTemplates))
  }
  if (isMlDocType(resolvedType) || !schemaForType(resolvedType, templates, mineTemplates)) {
    return parsed
  }
  if (resolvedType === 'passport' && parsed.length && !looksLikePassportFields(parsed)) {
    return parsed
  }
  return mergeTemplateFields(parsed, schemaForType(resolvedType, templates, mineTemplates))
}

function demoFieldsForFile(fileName: string, docType: string, templates: OcrDocType[] = []): OcrField[] {
  const inferred = docType && docType !== 'unknown' ? docType : inferDocTypeFromName(fileName)
  if (inferred === 'passport' || fileName.toLowerCase().includes('passport')) {
    return DEMO_PASSPORT_FIELDS.map((field) => ({ ...field, bbox: { ...field.bbox } }))
  }
  const schema = schemaForType(inferred, templates)
  if (schema) return mergeTemplateFields([], schema)
  return []
}

function jobToQueueItem(job: Record<string, unknown>): OcrQueueItem {
  const status = mapBackendStatus(job.status, job.validation_status)
  const progress =
    status === 'queued' ? 0
      : status === 'ocr' ? 50
        : 100
  const userTemplateId = Number(job.user_template_id || 0)
  const rawType = String(job.document_type || '')
  const docType = userTemplateId > 0
    ? mineDocType(userTemplateId)
    : isMlDocType(rawType)
      ? ML_DOC_TYPE
      : rawType || inferDocTypeFromName(String(job.filename || job.file || '')) || 'unknown'
  return {
    id: String(job.job_id || job.id || ''),
    file: String(job.filename || job.file || 'document'),
    docType,
    status,
    progress,
    confidence: null,
    batchId: job.batch_id ? String(job.batch_id) : undefined,
    sourceArchive: job.source_archive ? String(job.source_archive) : undefined,
  }
}

function isSupportedUpload(file: File): boolean {
  const name = file.name.toLowerCase()
  return (
    name.endsWith('.png')
    || name.endsWith('.jpg')
    || name.endsWith('.jpeg')
    || name.endsWith('.pdf')
    || name.endsWith('.tiff')
    || name.endsWith('.tif')
    || name.endsWith('.zip')
    || name.endsWith('.rar')
    || file.type === 'image/png'
    || file.type === 'image/jpeg'
    || file.type === 'application/pdf'
    || file.type === 'image/tiff'
    || file.type === 'application/zip'
    || file.type === 'application/x-zip-compressed'
    || file.type === 'application/vnd.rar'
    || file.type === 'application/x-rar-compressed'
  )
}

function mergeTemplateFields(
  ocrFields: OcrField[],
  schema: Record<string, unknown> | undefined,
): OcrField[] {
  const known = new Map(ocrFields.map((field) => [field.apiKey, field]))
  const schemaKeys = schema ? Object.keys(schema) : []
  const ordered = schemaKeys.filter((key) => !HIDDEN_FIELD_KEYS.has(key))
  if (!ordered.length) return ocrFields.filter((field) => !HIDDEN_FIELD_KEYS.has(field.apiKey))
  return ordered.map((apiKey, index) => {
    const spec = schema?.[apiKey]
    const explicitLabel = spec && typeof spec === 'object' && spec !== null && 'label' in spec
      ? String((spec as { label?: unknown }).label || '').trim()
      : ''
    const existing = known.get(apiKey)
    if (existing) {
      return {
        ...existing,
        label: explicitLabel || russianFieldLabel(existing.id, existing.apiKey),
      }
    }
    const id = API_TO_UI[apiKey] || apiKey
    return {
      id,
      apiKey,
      label: explicitLabel || russianFieldLabel(id, apiKey),
      value: '',
      confidence: 0,
      bbox: DEFAULT_BBOX[id] || {
        left: 10,
        top: 18 + index * 12,
        width: 48,
        height: 7,
      },
    }
  })
}

function uploadJobs(response: Record<string, unknown>): Record<string, unknown>[] {
  const items = response.items
  if (Array.isArray(items) && items.length) {
    return items.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
  }
  return [response]
}

function DocTypeSelectGroups({
  templateOptions,
  myTemplates,
  extraValue,
  extraTitle,
}: {
  templateOptions: Array<{ doc_type: string; title: string }>
  myTemplates: OcrUserTemplate[]
  extraValue?: string
  extraTitle?: string
}) {
  const extra = extraValue
    && extraValue !== ML_DOC_TYPE
    && !isMineDocType(extraValue)
    && !templateOptions.some((item) => item.doc_type === extraValue)
  return (
    <>
      <option value={ML_DOC_TYPE}>ML без шаблона</option>
      <optgroup label="Типы банка">
        {templateOptions.map((item) => (
          <option key={item.doc_type} value={item.doc_type}>
            {item.title || item.doc_type}
          </option>
        ))}
      </optgroup>
      {myTemplates.length ? (
        <optgroup label="Мои шаблоны">
          {myTemplates.map((item) => (
            <option key={item.id} value={mineDocType(item.id)}>
              {item.name}
            </option>
          ))}
        </optgroup>
      ) : null}
      {extra && extraValue ? (
        <option value={extraValue}>{extraTitle || extraValue}</option>
      ) : null}
    </>
  )
}

export interface OcrDocumentsPanelProps {
  initialSubTab?: OcrSubTab
  onClose?: () => void
}

export function OcrDocumentsPanel({
  initialSubTab = 'queue',
  onClose,
}: OcrDocumentsPanelProps) {
  const [subTab, setSubTab] = useState<OcrSubTab>(initialSubTab)
  const [queue, setQueue] = useState<OcrQueueItem[]>([])
  const [statusFilter, setStatusFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('any')
  const [search, setSearch] = useState('')
  const [pendingFiles, setPendingFiles] = useState<File[]>([])
  const [docType, setDocType] = useState(() => readUploadDocType('passport'))
  const [dragOver, setDragOver] = useState(false)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [fieldsByJob, setFieldsByJob] = useState<Record<string, OcrField[]>>({})
  const [, setSelectedFieldId] = useState<string | null>(null)
  const [approved, setApproved] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [templates, setTemplates] = useState<OcrDocType[]>([])
  const [myTemplates, setMyTemplates] = useState<OcrUserTemplate[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [createName, setCreateName] = useState('')
  const [mineError, setMineError] = useState('')
  const [mineEditorId, setMineEditorId] = useState<number | null>(null)
  const [mineDraftName, setMineDraftName] = useState('')
  const [mineDraftFields, setMineDraftFields] = useState<OcrUserTemplateField[]>([])
  const [mineConfirmDelete, setMineConfirmDelete] = useState(false)
  const [previewByJob, setPreviewByJob] = useState<Record<string, string>>({})
  const [recognizeProgress, setRecognizeProgress] = useState(0)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const chosenTypeByJob = useRef<Record<string, string>>({})
  const recognizingRef = useRef(false)

  const activeItem = queue.find((item) => item.id === activeId) ?? queue[0]
  const rawActiveFields = filterOcrFields(activeId ? fieldsByJob[activeId] || [] : [])
  const fields = isMlDocType(activeItem?.docType || '') && !isMineDocType(activeItem?.docType || '')
    ? rawActiveFields
    : mergeTemplateFields(
      rawActiveFields,
      schemaForType(activeItem?.docType || '', templates, myTemplates),
    )

  const loadQueue = useCallback(async () => {
    if (recognizingRef.current) return
    try {
      const jobs = await listOcrJobs()
      const remote = jobs.map(jobToQueueItem).filter((item) => item.id)
      setQueue((prev) => {
        const prevById = new Map(prev.map((item) => [item.id, item]))
        const remoteIds = new Set(remote.map((item) => item.id))
        const local = prev.filter((item) => item.id.startsWith('demo-') && !remoteIds.has(item.id))
        const merged = remote.map((item) => {
          const was = prevById.get(item.id)
          const chosen = chosenTypeForJob(chosenTypeByJob, item.id, was?.docType || '')
          if (chosen && (isMlDocType(chosen) || isOperatorDocType(chosen) || isPassportPageType(chosen) || isMineDocType(chosen))) {
            return {
              ...item,
              docType: chosen,
              confidence: was?.confidence ?? item.confidence,
            }
          }
          if (was && isPassportPageType(was.docType) && item.docType === 'passport') {
            return {
              ...item,
              docType: was.docType,
              confidence: was.confidence ?? item.confidence,
            }
          }
          return item
        })
        return [...local, ...merged]
      })
      setError('')
    } catch {
      // Storybook / offline: keep local queue as-is.
    }
  }, [])

  useEffect(() => {
    setSubTab(initialSubTab)
  }, [initialSubTab])

  useEffect(() => {
    void loadQueue()
    void listOcrDocTypes()
      .then(setTemplates)
      .catch(() => setTemplates([]))
    void listMyOcrTemplates()
      .then(setMyTemplates)
      .catch(() => setMyTemplates([]))
  }, [loadQueue])

  useEffect(() => {
    const pending = queue.some((item) => item.status === 'queued' || item.status === 'ocr')
    if (!pending) return
    const timer = window.setInterval(() => {
      void loadQueue()
    }, 2500)
    return () => window.clearInterval(timer)
  }, [loadQueue, queue])

  useEffect(() => {
    const empty = queue.filter((item) => (
      (item.status === 'review' || item.status === 'done')
      && !item.id.startsWith('demo-')
      && !item.id.startsWith('pending-')
      && fieldsAreEmpty(fieldsByJob[item.id] || [])
    ))
    if (!empty.length) return undefined
    let cancelled = false
    void Promise.all(empty.slice(0, 4).map(async (item) => {
      try {
        const result = await fetchOcrResult(item.id)
        if (cancelled) return
        const parsed = fieldsFromResult(rawResultFields(result))
        const chosen = chosenTypeForJob(chosenTypeByJob, item.id, item.docType)
        if (isMineDocType(chosen)) {
          const nextFields = fieldsForExtractedType(parsed, chosen, templates, myTemplates)
          if (fieldsAreEmpty(nextFields)) return
          rememberChosenType(chosenTypeByJob, item.id, chosen)
          setFieldsByJob((prev) => ({ ...prev, [item.id]: nextFields }))
          setQueue((prev) => prev.map((row) => (
            row.id === item.id
              ? {
                  ...row,
                  docType: chosen,
                  confidence: avgConfidence(nextFields.filter((field) => field.value)),
                }
              : row
          )))
          return
        }
        if (isMlDocType(chosen)) {
          if (fieldsAreEmpty(parsed)) return
          rememberChosenType(chosenTypeByJob, item.id, ML_DOC_TYPE)
          setFieldsByJob((prev) => ({ ...prev, [item.id]: parsed }))
          setQueue((prev) => prev.map((row) => (
            row.id === item.id
              ? {
                  ...row,
                  docType: ML_DOC_TYPE,
                  confidence: avgConfidence(parsed.filter((field) => field.value)),
                }
              : row
          )))
          return
        }
        const resolvedType = typeForExtractedFields(
          String(result.document_type || item.docType || ''),
          parsed,
          pageKindsFromResult(result),
          isOperatorDocType(chosen) ? chosen : '',
        )
        const nextFields = fieldsForExtractedType(parsed, resolvedType, templates, myTemplates)
        if (fieldsAreEmpty(nextFields)) return
        setFieldsByJob((prev) => ({ ...prev, [item.id]: nextFields }))
        setQueue((prev) => prev.map((row) => (
          row.id === item.id
            ? {
                ...row,
                docType: resolvedType,
                confidence: avgConfidence(nextFields.filter((field) => field.value)),
              }
            : row
        )))
      } catch {
        // Keep empty template until the operator reopens the job.
      }
    }))
    return () => {
      cancelled = true
    }
  }, [fieldsByJob, myTemplates, queue, templates])

  const filteredQueue = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return queue.filter((item) => {
      if (statusFilter !== 'all' && item.status !== statusFilter) return false
      if (typeFilter !== 'any' && item.docType !== typeFilter) return false
      if (needle && !item.file.toLowerCase().includes(needle)) return false
      return true
    })
  }, [queue, search, statusFilter, typeFilter])

  const stats = useMemo(() => ({
    queued: queue.filter((item) => item.status === 'queued').length,
    ocr: queue.filter((item) => item.status === 'ocr').length,
    hitl: queue.filter((item) => item.status === 'review').length,
    errors: queue.filter((item) => item.status === 'error').length,
  }), [queue])

  const openReview = useCallback(async (item: OcrQueueItem) => {
    setActiveId(item.id)
    setApproved(item.status === 'done')
    setSubTab('review')
    setError('')
    setRecognizeProgress(item.status === 'queued' || item.status === 'ocr' ? item.progress : 100)
    if (!previewByJob[item.id] && !item.id.startsWith('demo-')) {
      setPreviewByJob((prev) => ({ ...prev, [item.id]: ocrJobOriginalUrl(item.id) }))
    }

    const chosenOnOpen = chosenTypeForJob(chosenTypeByJob, item.id, item.docType)
    const cached = isMlDocType(chosenOnOpen) && !isMineDocType(chosenOnOpen)
      ? filterOcrFields(fieldsByJob[item.id] || [])
      : mergeTemplateFields(
        filterOcrFields(fieldsByJob[item.id] || []),
        schemaForType(item.docType, templates, myTemplates),
      )

    try {
      const result = await fetchOcrResult(item.id)
      const parsed = fieldsFromResult(rawResultFields(result))
      const chosen = chosenOnOpen || chosenTypeForJob(chosenTypeByJob, item.id, item.docType)
      if (isMineDocType(chosen)) {
        const nextFields = fieldsForExtractedType(parsed, chosen, templates, myTemplates)
        const shown = nextFields.some((field) => field.value.trim()) ? nextFields : cached
        if (shown.length) {
          rememberChosenType(chosenTypeByJob, item.id, chosen)
          setFieldsByJob((prev) => ({ ...prev, [item.id]: shown }))
          setSelectedFieldId(shown[0]?.id ?? null)
          setQueue((prev) => prev.map((row) => (
            row.id === item.id
              ? { ...row, confidence: avgConfidence(shown), docType: chosen }
              : row
          )))
          return
        }
      }
      if (isMlDocType(chosen) && !isMineDocType(chosen)) {
        const shown = parsed.some((field) => field.value.trim()) ? parsed : cached
        if (shown.length) {
          rememberChosenType(chosenTypeByJob, item.id, ML_DOC_TYPE)
          setFieldsByJob((prev) => ({ ...prev, [item.id]: shown }))
          setSelectedFieldId(shown[0]?.id ?? null)
          setQueue((prev) => prev.map((row) => (
            row.id === item.id
              ? { ...row, confidence: avgConfidence(shown), docType: ML_DOC_TYPE }
              : row
          )))
          return
        }
        rememberChosenType(chosenTypeByJob, item.id, ML_DOC_TYPE)
        setQueue((prev) => prev.map((row) => (
          row.id === item.id ? { ...row, docType: ML_DOC_TYPE } : row
        )))
        return
      }
      const resolvedType = typeForExtractedFields(
        String(result.document_type || item.docType || ''),
        parsed,
        pageKindsFromResult(result),
        isOperatorDocType(chosen) ? chosen : '',
      )
      const nextFields = fieldsForExtractedType(parsed, resolvedType, templates, myTemplates)
      const shown = nextFields.some((field) => field.value.trim()) ? nextFields : cached
      if (shown.length) {
        setFieldsByJob((prev) => ({ ...prev, [item.id]: shown }))
        setSelectedFieldId(shown[0]?.id ?? null)
        const conf = avgConfidence(shown)
        setQueue((prev) => prev.map((row) => (
          row.id === item.id ? { ...row, confidence: conf, docType: resolvedType } : row
        )))
        return
      }
      setQueue((prev) => prev.map((row) => (
        row.id === item.id ? { ...row, docType: resolvedType } : row
      )))
    } catch {
      if (!fieldsAreEmpty(cached)) {
        setFieldsByJob((prev) => ({ ...prev, [item.id]: cached }))
        setSelectedFieldId(cached[0]?.id ?? null)
        return
      }
    }

    const inferredType = item.docType !== 'unknown' ? item.docType : inferDocTypeFromName(item.file)
    const fallback = item.id.startsWith('demo-')
      ? mergeTemplateFields(
        demoFieldsForFile(item.file, inferredType, templates),
        schemaForType(inferredType, templates, myTemplates),
      )
      : mergeTemplateFields([], schemaForType(inferredType, templates, myTemplates))
    setFieldsByJob((prev) => ({ ...prev, [item.id]: fallback }))
    setSelectedFieldId(fallback[0]?.id ?? null)
  }, [fieldsByJob, myTemplates, previewByJob, templates])

  const addFiles = useCallback((fileList: FileList | File[]) => {
    const files = Array.from(fileList).filter(isSupportedUpload)
    if (!files.length) return
    setPendingFiles((prev) => [...prev, ...files])
  }, [])

  const onFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files?.length) {
      addFiles(event.target.files)
      event.target.value = ''
    }
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragOver(false)
    if (event.dataTransfer.files?.length) {
      addFiles(event.dataTransfer.files)
    }
  }

  const startRecognition = async () => {
    if (!pendingFiles.length || busy) return
    writeUploadDocType(docType)
    recognizingRef.current = true
    setBusy(true)
    setError('')
    setRecognizeProgress(8)
    const created: OcrQueueItem[] = []
    const nextFields: Record<string, OcrField[]> = {}
    const nextPreviews: Record<string, string> = {}

    const firstPreview = URL.createObjectURL(pendingFiles[0])
    const pendingId = `pending-${Date.now()}`
    nextPreviews[pendingId] = firstPreview
    setPreviewByJob((prev) => ({ ...prev, [pendingId]: firstPreview }))
    rememberChosenType(chosenTypeByJob, pendingId, isMlDocType(docType) && !isMineDocType(docType) ? ML_DOC_TYPE : docType)
    setQueue((prev) => [
      {
        id: pendingId,
        file: pendingFiles[0].name,
        docType: isMlDocType(docType) && !isMineDocType(docType) ? ML_DOC_TYPE : docType,
        status: 'ocr',
        progress: 8,
        confidence: null,
      },
      ...prev,
    ])
    setActiveId(pendingId)
    setSubTab('review')

    try {
      for (const [index, file] of pendingFiles.entries()) {
        setRecognizeProgress(Math.min(88, 12 + Math.round(((index + 0.4) / pendingFiles.length) * 70)))
        const mineId = parseMineTemplateId(docType)
        const forcedType = mineId
          ? mineDocType(mineId)
          : isOperatorDocType(docType) ? docType : ''
        const uploadType = mineId ? '' : (forcedType ? apiDocType(forcedType) : ML_DOC_TYPE)

        try {
          const isArchive = /\.(zip|rar)$/i.test(file.name)
          const response = await uploadOcrDocument(
            file,
            uploadType,
            !isArchive,
            mineId ?? undefined,
          )
          for (const job of uploadJobs(response)) {
            const jobId = String(job.job_id || response.job_id || `upload-${Date.now()}-${index}`)
            let result =
              (job.result as Record<string, unknown> | undefined)
              || (response.result as Record<string, unknown> | undefined)
              || null
            if (fieldsAreEmpty(fieldsFromResult(rawResultFields(result))) && !jobId.startsWith('demo-')) {
              result = await fetchOcrResult(jobId).catch(() => result)
            }
            const detected = String(
              (result?.document_type && result.document_type !== 'unknown' ? result.document_type : '')
              || job.document_type
              || forcedType
              || inferDocTypeFromName(file.name)
              || 'unknown',
            )
            const parsed = fieldsFromResult(rawResultFields(result))
            const resolvedType = mineId
              ? mineDocType(mineId)
              : forcedType
                ? typeForExtractedFields(
                  detected,
                  parsed,
                  pageKindsFromResult(result),
                  forcedType,
                )
                : ML_DOC_TYPE
            const fields = forcedType
              ? fieldsForExtractedType(parsed, resolvedType, templates, myTemplates)
              : parsed
            rememberChosenType(chosenTypeByJob, jobId, resolvedType)
            const mapped = jobToQueueItem({
              ...job,
              job_id: jobId,
              filename: job.filename || file.name,
              document_type: resolvedType,
              status: result ? 'completed' : job.status,
              validation_status: result?.validation_status || job.validation_status || 'pending_review',
            })
            const item: OcrQueueItem = {
              ...mapped,
              status: result ? 'review' : mapped.status,
              progress: result ? 100 : mapped.progress,
              confidence: avgConfidence(fields.filter((field) => field.value)),
            }
            created.push(item)
            nextFields[jobId] = fields
            if (file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name)) {
              nextPreviews[jobId] = URL.createObjectURL(file)
            } else {
              nextPreviews[jobId] = ocrJobOriginalUrl(jobId)
            }
          }
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Не удалось загрузить документ'
          const storybookDemo = /passport_demo/i.test(file.name)
          if (storybookDemo) {
            const jobId = `demo-${Date.now()}-${index}`
            const fields = forcedType
              ? (isMineDocType(forcedType)
                ? fieldsForExtractedType([], forcedType, templates, myTemplates)
                : demoFieldsForFile(file.name, forcedType, templates))
              : []
            const item: OcrQueueItem = {
              id: jobId,
              file: file.name,
              docType: forcedType || ML_DOC_TYPE,
              status: 'review',
              progress: 100,
              confidence: avgConfidence(fields),
            }
            created.push(item)
            nextFields[jobId] = fields
            rememberChosenType(chosenTypeByJob, jobId, item.docType)
            if (file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name)) {
              nextPreviews[jobId] = URL.createObjectURL(file)
            }
            continue
          }
          setError(
            /401|403|authentication|permission|csrf/i.test(message)
              ? 'Нет доступа к OCR. Обновите страницу и повторите загрузку.'
              : `Распознавание не запустилось: ${message}`,
          )
          const jobId = `error-${Date.now()}-${index}`
          const fields = forcedType
            ? mergeTemplateFields([], schemaForType(forcedType, templates, myTemplates))
            : []
          created.push({
            id: jobId,
            file: file.name,
            docType: forcedType || ML_DOC_TYPE,
            status: 'error',
            progress: 0,
            confidence: null,
          })
          nextFields[jobId] = fields
          rememberChosenType(chosenTypeByJob, jobId, forcedType || ML_DOC_TYPE)
          if (file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name)) {
            nextPreviews[jobId] = URL.createObjectURL(file)
          }
        }
      }

      setFieldsByJob((prev) => ({ ...prev, ...nextFields }))
      setPreviewByJob((prev) => ({ ...prev, ...nextPreviews }))
      setQueue((prev) => [
        ...created,
        ...prev.filter((item) => item.id !== pendingId),
      ])
      setPendingFiles([])
      setRecognizeProgress(100)
      if (created[0]) {
        setActiveId(created[0].id)
        setSelectedFieldId(nextFields[created[0].id]?.[0]?.id ?? null)
        setApproved(false)
        setSubTab('review')
      }
    } finally {
      recognizingRef.current = false
      setBusy(false)
    }
  }

  const updateField = (id: string, value: string) => {
    if (!activeId) return
    setFieldsByJob((prev) => ({
      ...prev,
      [activeId]: (prev[activeId] || []).map((field) => (
        field.id === id ? { ...field, value } : field
      )),
    }))
    setApproved(false)
  }

  const templateOptions = useMemo(() => {
    const byType = new Map(templates.map((item) => [item.doc_type, item]))
    return OPERATOR_DOC_TYPES.map((doc_type) => {
      const item = byType.get(doc_type)
      return {
        doc_type,
        title: OPERATOR_DOC_TITLES[doc_type],
        field_schema: item?.field_schema || BUILTIN_SCHEMAS[doc_type],
      }
    })
  }, [templates])

  const applyDocType = (jobId: string, nextType: string) => {
    const type = isMineDocType(nextType)
      ? nextType
      : isOperatorDocType(nextType)
        ? nextType
        : isMlDocType(nextType) ? ML_DOC_TYPE : nextType || ML_DOC_TYPE
    rememberChosenType(chosenTypeByJob, jobId, type)
    setQueue((prev) => prev.map((item) => (
      item.id === jobId ? { ...item, docType: type } : item
    )))
    setFieldsByJob((prev) => ({
      ...prev,
      [jobId]: isMlDocType(type) && !isMineDocType(type)
        ? filterOcrFields(prev[jobId] || [])
        : mergeTemplateFields(
          filterOcrFields(prev[jobId] || []),
          schemaForType(type, templates, myTemplates),
        ),
    }))
  }

  const createPreviewFields = fields.filter((field) => (
    field.value.trim() && (approved || activeItem?.status === 'done' || field.confidence >= 0.6)
  ))
  const canSaveMine = canCreateOcrUserTemplate(activeItem?.status, fields, approved)

  const openCreateDialog = () => {
    if (!activeItem || !canSaveMine) return
    setCreateName(suggestUserTemplateName(activeItem, fields))
    setMineError('')
    setCreateOpen(true)
  }

  const saveMyTemplate = async () => {
    if (!activeItem) return
    const name = createName.trim()
    if (name.length < 1 || name.length > 80) {
      setMineError('Имя должно быть от 1 до 80 символов')
      return
    }
    setBusy(true)
    setMineError('')
    try {
      const created = await createMyOcrTemplate(activeItem.id, name)
      setMyTemplates((prev) => (
        [...prev.filter((item) => item.id !== created.id), created]
          .sort((a, b) => a.name.localeCompare(b.name, 'ru'))
      ))
      setCreateOpen(false)
      openMineEditor(created)
    } catch (err) {
      setMineError(err instanceof Error ? err.message : 'Не удалось сохранить шаблон')
    } finally {
      setBusy(false)
    }
  }

  const openMineEditor = (template: OcrUserTemplate) => {
    setMineEditorId(template.id)
    setMineDraftName(template.name)
    setMineDraftFields((template.fields || []).map((field) => ({
      key: field.key,
      label: field.label,
      type: field.type || 'string',
      pattern: field.pattern || '',
    })))
    setMineConfirmDelete(false)
    setMineError('')
    setSubTab('mine')
  }

  const closeMineEditor = () => {
    setMineEditorId(null)
    setMineConfirmDelete(false)
    setMineError('')
  }

  const updateDraftField = (index: number, patch: Partial<OcrUserTemplateField>) => {
    setMineDraftFields((prev) => prev.map((field, i) => (
      i === index ? { ...field, ...patch } : field
    )))
  }

  const addDraftField = () => {
    const next = mineDraftFields.length + 1
    setMineDraftFields((prev) => [
      ...prev,
      { key: `field_${next}`, label: '', type: 'string', pattern: '' },
    ])
  }

  const removeDraftField = (index: number) => {
    setMineDraftFields((prev) => prev.filter((_, i) => i !== index))
  }

  const moveDraftField = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= mineDraftFields.length) return
    setMineDraftFields((prev) => {
      const next = [...prev]
      const [item] = next.splice(index, 1)
      next.splice(target, 0, item)
      return next
    })
  }

  const saveMineEditor = async () => {
    if (mineEditorId == null) return
    const name = mineDraftName.trim()
    if (name.length < 1 || name.length > 80) {
      setMineError('Имя должно быть от 1 до 80 символов')
      return
    }
    const fields = mineDraftFields.map((field) => ({
      key: field.key.trim(),
      label: field.label.trim() || field.key.trim(),
      type: field.type || 'string',
      pattern: (field.pattern || '').trim(),
    }))
    if (!fields.length) {
      setMineError('Добавьте хотя бы одно поле')
      return
    }
    setBusy(true)
    setMineError('')
    try {
      const updated = await updateMyOcrTemplate(mineEditorId, { name, fields })
      setMyTemplates((prev) => (
        prev.map((item) => (item.id === updated.id ? updated : item))
      ))
      setMineDraftName(updated.name)
      setMineDraftFields(updated.fields || [])
    } catch (err) {
      setMineError(err instanceof Error ? err.message : 'Не удалось сохранить шаблон')
    } finally {
      setBusy(false)
    }
  }

  const removeMine = async (templateId: number) => {
    setBusy(true)
    setMineError('')
    try {
      await deleteMyOcrTemplate(templateId)
      setMyTemplates((prev) => prev.filter((item) => item.id !== templateId))
      if (parseMineTemplateId(docType) === templateId) {
        setDocType(ML_DOC_TYPE)
        writeUploadDocType(ML_DOC_TYPE)
      }
      closeMineEditor()
    } catch (err) {
      setMineError(err instanceof Error ? err.message : 'Не удалось удалить')
    } finally {
      setBusy(false)
    }
  }

  const approveAndExport = async () => {
    if (!activeItem) return
    setBusy(true)
    setError('')
    const currentFields = fieldsByJob[activeItem.id] || fields
    const payload = fieldsToApiPayload(currentFields)
    const documentType = apiDocType(activeItem.docType || 'passport')
    const stem = activeItem.file.replace(/\.[^.]+$/u, '') || 'ocr-export'
    try {
      if (!activeItem.id.startsWith('demo-')) {
        await approveOcrJob(activeItem.id, documentType, payload)
        try {
          await exportOcrJob(activeItem.id, 'docx', {
            documentType,
            fields: payload,
          })
        } catch {
          downloadOcrFieldsDocx(ocrExportRows(currentFields), stem)
        }
      } else {
        downloadOcrFieldsDocx(ocrExportRows(currentFields), stem)
      }
      setApproved(true)
      setQueue((prev) => prev.map((item) => (
        item.id === activeItem.id
          ? {
              ...item,
              status: 'done',
              confidence: avgConfidence(currentFields) ?? 0.95,
              progress: 100,
            }
          : item
      )))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось утвердить')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`ocr-docs${onClose ? ' ocr-docs--overlay' : ''}`} data-testid="ocr-documents-panel">
      <div className="hub-document-tabs" role="tablist" aria-label="Документы">
        {([
          ['queue', 'Очередь'],
          ['upload', 'Загрузить'],
          ['review', 'Проверка'],
          ['mine', 'Мои шаблоны'],
        ] as const).map(([id, label]) => (
          <button
            type="button"
            role="tab"
            key={id}
            aria-selected={subTab === id}
            data-testid={`ocr-subtab-${id}`}
            onClick={() => setSubTab(id)}
          >
            {label}
          </button>
        ))}
        {onClose ? (
          <button
            type="button"
            className="ocr-docs__close"
            onClick={onClose}
            aria-label="Закрыть OCR"
            data-testid="ocr-workspace-close"
          >
            ×
          </button>
        ) : null}
      </div>

      {subTab === 'queue' && (
        <div className="ocr-docs__queue" data-testid="ocr-queue">
          <div className="ocr-docs__filters">
            <label>
              <span className="visually-hidden">Статус</span>
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
                data-testid="ocr-filter-status"
              >
                <option value="all">Все статусы</option>
                <option value="queued">Очередь</option>
                <option value="ocr">OCR</option>
                <option value="review">На проверке</option>
                <option value="done">Готово</option>
                <option value="error">Ошибка</option>
              </select>
            </label>
            <label>
              <span className="visually-hidden">Тип</span>
              <select
                value={typeFilter}
                onChange={(event) => setTypeFilter(event.target.value)}
                data-testid="ocr-filter-type"
              >
                <option value="any">Любой тип</option>
                {templateOptions.map((item) => (
                  <option key={item.doc_type} value={item.doc_type}>
                    {item.title || item.doc_type}
                  </option>
                ))}
              </select>
            </label>
            <input
              type="search"
              placeholder="Поиск по файлу…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              data-testid="ocr-filter-search"
            />
            <Button
              type="button"
              onClick={() => {
                setStatusFilter('all')
                setTypeFilter('any')
                setSearch('')
                void loadQueue()
              }}
            >
              Обновить
            </Button>
          </div>

          <Table data-testid="ocr-queue-table" caption="Очередь OCR">
            <TableHead>
              <TableRow>
                <TableHeaderCell>Файл</TableHeaderCell>
                <TableHeaderCell>doc_type</TableHeaderCell>
                <TableHeaderCell>Статус</TableHeaderCell>
                <TableHeaderCell>Прогресс</TableHeaderCell>
                <TableHeaderCell>Confidence</TableHeaderCell>
                <TableHeaderCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {filteredQueue.map((item) => (
                <TableRow key={item.id} data-testid={`ocr-queue-row-${item.id}`}>
                  <TableCell>
                    {item.file}
                    {item.sourceArchive ? (
                      <small className="ocr-docs__archive"> · {item.sourceArchive}</small>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {templateOptions.find((tpl) => tpl.doc_type === item.docType)?.title || typeTitle(item.docType, myTemplates)}
                  </TableCell>
                  <TableCell>{STATUS_LABEL[item.status]}</TableCell>
                  <TableCell>
                    <div className="ocr-docs__progress" aria-label={`Прогресс ${item.progress}%`}>
                      <span style={{ width: `${item.progress}%` }} />
                      <em>{item.progress}%</em>
                    </div>
                  </TableCell>
                  <TableCell>{formatConfidence(item.confidence)}</TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      data-testid={`ocr-open-${item.id}`}
                      onClick={() => void openReview(item)}
                    >
                      Открыть
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          <div className="ocr-docs__stats" data-testid="ocr-queue-stats">
            <span>В очереди · {stats.queued}</span>
            <span>OCR сейчас · {stats.ocr}</span>
            <span>На проверке · {stats.hitl}</span>
            <span>Ошибки · {stats.errors}</span>
          </div>

          <Button type="button" onClick={() => setSubTab('upload')}>
            Загрузить документы
          </Button>
        </div>
      )}

      {subTab === 'upload' && (
        <div className="ocr-docs__upload" data-testid="ocr-upload">
          <div className="ocr-docs__upload-grid">
            <div
              className={`ocr-docs__dropzone${dragOver ? ' is-dragover' : ''}`}
              data-testid="ocr-dropzone"
              onDragEnter={(event) => {
                event.preventDefault()
                setDragOver(true)
              }}
              onDragOver={(event) => {
                event.preventDefault()
                setDragOver(true)
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
            >
              <strong>Перетащите файлы или выберите с диска</strong>
              <span>PDF, JPEG, PNG, TIFF · пакет ZIP / RAR</span>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPT}
                className="visually-hidden"
                data-testid="ocr-file-input"
                onChange={onFileInput}
              />
              <Button
                type="button"
                data-testid="ocr-choose-files"
                onClick={() => fileInputRef.current?.click()}
              >
                Выбрать файлы
              </Button>
            </div>
            <aside className="ocr-docs__upload-side">
              <label className="ocr-docs__doctype">
                <span>Тип документа</span>
                <select
                  value={docType}
                  onChange={(event) => {
                    setDocType(event.target.value)
                    writeUploadDocType(event.target.value)
                  }}
                  data-testid="ocr-doc-type"
                >
                  <DocTypeSelectGroups
                    templateOptions={templateOptions}
                    myTemplates={myTemplates}
                  />
                </select>
              </label>
              <p className="ocr-docs__hint">
                Антивирусная проверка файлов перед добавлением в очередь OCR. Архив ZIP/RAR
                распаковывается в отдельные задания очереди.
              </p>
              {pendingFiles.length > 0 && (
                <Card className="ocr-docs__batch" data-testid="ocr-pending-batch">
                  <strong>Пакет · {pendingFiles.length} файл(ов)</strong>
                  <ol>
                    {pendingFiles.map((file) => (
                      <li key={`${file.name}-${file.size}-${file.lastModified}`}>{file.name}</li>
                    ))}
                  </ol>
                </Card>
              )}
            </aside>
          </div>

          {error && <p className="ocr-docs__hint" role="alert">{error}</p>}

          <Button
            type="button"
            data-testid="ocr-start-recognition"
            disabled={!pendingFiles.length || busy}
            onClick={() => void startRecognition()}
          >
            {busy ? 'Распознавание…' : 'Начать распознавание'}
          </Button>
        </div>
      )}

      {subTab === 'review' && activeItem && (
        <div className="ocr-docs__review" data-testid="ocr-review">
          <section className="ocr-docs__viewer" data-testid="ocr-bbox-viewer" aria-label="Просмотр документа">
            <header>
              <strong>{activeItem.file}</strong>
              <StatusBadge status={activeItem.status === 'error' ? 'danger' : activeItem.status === 'done' ? 'success' : 'warning'}>
                {STATUS_LABEL[activeItem.status]}
              </StatusBadge>
            </header>
            <div className="ocr-docs__scan">
              {(() => {
                const preview = previewByJob[activeItem.id]
                  || (!activeItem.id.startsWith('demo-') && !activeItem.id.startsWith('pending-')
                    ? ocrJobOriginalUrl(activeItem.id)
                    : '')
                const isPdf = /\.pdf$/i.test(activeItem.file)
                if (!preview) {
                  return <p className="ocr-docs__scan-label">Документ ещё загружается…</p>
                }
                if (isPdf) {
                  return (
                    <iframe
                      className="ocr-docs__scan-frame"
                      title={activeItem.file}
                      src={preview}
                    />
                  )
                }
                return (
                  <img
                    className="ocr-docs__scan-img"
                    src={preview}
                    alt={activeItem.file}
                    data-testid="ocr-scan-image"
                  />
                )
              })()}
            </div>
            <div className="ocr-docs__recognize" data-testid="ocr-recognize-progress">
              <div
                className="ocr-docs__recognize-bar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={
                  busy || activeItem.status === 'queued' || activeItem.status === 'ocr'
                    ? recognizeProgress || activeItem.progress
                    : 100
                }
                role="progressbar"
              >
                <span
                  style={{
                    width: `${
                      busy || activeItem.status === 'queued' || activeItem.status === 'ocr'
                        ? Math.max(recognizeProgress, activeItem.progress)
                        : 100
                    }%`,
                  }}
                />
              </div>
              <em>
                {busy || activeItem.status === 'queued' || activeItem.status === 'ocr'
                  ? `Распознавание… ${Math.max(recognizeProgress, activeItem.progress)}%`
                  : 'Распознавание завершено'}
              </em>
            </div>
          </section>

          <section className="ocr-docs__fields" data-testid="ocr-field-editor" aria-label="Извлечённые поля">
            <h2>Извлечённые поля</h2>
            {error ? <p className="ocr-docs__hint" role="alert">{error}</p> : null}
            {fields.every((field) => !field.value.trim()) ? (
              <p className="ocr-docs__hint">Поля шаблона пустые. Проверьте скан или введите значения вручную.</p>
            ) : null}
            <ul>
              {fields.map((field) => (
                <li key={field.id} data-testid={`ocr-field-${field.id}`}>
                  <div className="ocr-docs__field-head">
                    <label htmlFor={`ocr-field-input-${field.id}`}>{field.label}</label>
                    <StatusBadge
                      status={confidenceTone(field.confidence)}
                      data-testid={`ocr-field-confidence-${field.id}`}
                    >
                      {formatConfidence(field.confidence)}
                    </StatusBadge>
                  </div>
                  <input
                    id={`ocr-field-input-${field.id}`}
                    value={field.value}
                    data-testid={`ocr-field-input-${field.id}`}
                    onFocus={() => setSelectedFieldId(field.id)}
                    onChange={(event) => updateField(field.id, event.target.value)}
                  />
                </li>
              ))}
            </ul>

            <div className="ocr-docs__approve">
              <label>
                <span className="visually-hidden">Тип документа</span>
                <select
                  value={
                    isMineDocType(activeItem.docType)
                      ? activeItem.docType
                      : isMlDocType(activeItem.docType) ? ML_DOC_TYPE : activeItem.docType
                  }
                  onChange={(event) => applyDocType(activeItem.id, event.target.value)}
                  data-testid="ocr-review-doc-type"
                >
                  <DocTypeSelectGroups
                    templateOptions={templateOptions}
                    myTemplates={myTemplates}
                    extraValue={activeItem.docType}
                    extraTitle={typeTitle(activeItem.docType, myTemplates)}
                  />
                </select>
              </label>
              <Button
                type="button"
                data-testid="ocr-approve-export"
                disabled={busy}
                onClick={() => void approveAndExport()}
              >
                Утвердить и экспорт
              </Button>
              <Button
                type="button"
                data-testid="ocr-create-template"
                disabled={busy || !canSaveMine}
                title={canSaveMine ? undefined : 'сначала исправьте и утвердите'}
                onClick={openCreateDialog}
              >
                Создать шаблон
              </Button>
            </div>
            {error && <p className="ocr-docs__hint" role="alert">{error}</p>}
            {approved && (
              <StatusBadge status="success" data-testid="ocr-approved-badge">
                Подтверждено · файл скачан
              </StatusBadge>
            )}
          </section>
        </div>
      )}

      {subTab === 'mine' && (
        <div className="ocr-docs__mine" data-testid="ocr-my-templates">
          <section className="ocr-docs__mine-list" aria-label="Мои шаблоны">
            {myTemplates.length === 0 ? (
              <p className="ocr-docs__hint">
                Пока нет шаблонов. Сохраните набор полей после проверки документа.
              </p>
            ) : myTemplates.map((item) => (
              <button
                type="button"
                key={item.id}
                className={item.id === mineEditorId ? 'is-active' : undefined}
                data-testid={`ocr-my-template-${item.id}`}
                onClick={() => openMineEditor(item)}
              >
                <strong>{item.name}</strong>
                <span>
                  {(item.fields || []).length ? `${item.fields.length} полей` : 'Нет полей'}
                  {item.source_file ? ` · ${item.source_file}` : ''}
                </span>
              </button>
            ))}
          </section>

          <Card className="ocr-docs__mine-editor">
            {mineEditorId == null ? (
              <header>
                <div>
                  <h2>Мой шаблон</h2>
                  <p>Выберите шаблон слева, чтобы изменить имя и поля. В каталог банка он не попадает.</p>
                </div>
              </header>
            ) : (
              <div data-testid="ocr-my-template-editor">
                <header>
                  <div>
                    <h2>Мой шаблон</h2>
                    <p>
                      {myTemplates.find((item) => item.id === mineEditorId)?.source_file
                        ? `Источник: ${myTemplates.find((item) => item.id === mineEditorId)?.source_file}`
                        : 'Личный набор полей. В каталог банка не публикуется.'}
                    </p>
                  </div>
                </header>

                <div className="ocr-docs__mine-form">
                  <label className="ocr-docs__mine-wide">
                    <span>Название</span>
                    <input
                      value={mineDraftName}
                      maxLength={80}
                      data-testid="ocr-my-template-edit-name"
                      onChange={(event) => setMineDraftName(event.target.value)}
                    />
                  </label>

                  <div className="ocr-docs__mine-fields-head">
                    <h3>Поля для проверки</h3>
                  </div>
                  <div className="ocr-docs__mine-fields" data-testid="ocr-my-template-fields">
                    <div className="ocr-docs__mine-fields-row ocr-docs__mine-fields-row--head">
                      <span>Подпись</span>
                      <span>Ключ</span>
                      <span>Тип</span>
                      <span />
                    </div>
                    {mineDraftFields.map((field, index) => (
                      <div
                        className="ocr-docs__mine-fields-block"
                        key={`${field.key}-${index}`}
                        data-testid={`ocr-my-template-field-${index}`}
                      >
                        <div className="ocr-docs__mine-fields-row">
                          <input
                            value={field.label}
                            maxLength={80}
                            placeholder="ФИО"
                            aria-label={`Подпись поля ${index + 1}`}
                            data-testid={`ocr-my-template-field-label-${index}`}
                            onChange={(event) => updateDraftField(index, { label: event.target.value })}
                          />
                          <input
                            value={field.key}
                            maxLength={64}
                            placeholder="full_name"
                            aria-label={`Ключ поля ${index + 1}`}
                            data-testid={`ocr-my-template-field-key-${index}`}
                            onChange={(event) => updateDraftField(index, { key: event.target.value })}
                          />
                          <select
                            value={field.type || 'string'}
                            aria-label={`Тип поля ${index + 1}`}
                            data-testid={`ocr-my-template-field-type-${index}`}
                            onChange={(event) => updateDraftField(index, { type: event.target.value })}
                          >
                            <option value="string">Текст</option>
                            <option value="date">Дата</option>
                            <option value="number">Число</option>
                          </select>
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={mineDraftFields.length <= 1}
                            data-testid={`ocr-my-template-field-remove-${index}`}
                            onClick={() => removeDraftField(index)}
                          >
                            ×
                          </Button>
                        </div>
                        <input
                          className="ocr-docs__mine-pattern"
                          value={field.pattern || ''}
                          maxLength={200}
                          placeholder="Шаблон, необязательно"
                          aria-label={`Шаблон поля ${index + 1}`}
                          data-testid={`ocr-my-template-field-pattern-${index}`}
                          onChange={(event) => updateDraftField(index, { pattern: event.target.value })}
                        />
                        <div className="ocr-docs__mine-field-move">
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={index === 0}
                            aria-label="Выше"
                            onClick={() => moveDraftField(index, -1)}
                          >
                            ↑
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            disabled={index === mineDraftFields.length - 1}
                            aria-label="Ниже"
                            onClick={() => moveDraftField(index, 1)}
                          >
                            ↓
                          </Button>
                        </div>
                      </div>
                    ))}
                    <Button
                      type="button"
                      disabled={busy}
                      data-testid="ocr-my-template-add-field"
                      onClick={addDraftField}
                    >
                      + Поле
                    </Button>
                  </div>

                  {mineError ? <p className="ocr-docs__hint" role="alert">{mineError}</p> : null}
                  <div className="ocr-docs__mine-actions">
                    <Button
                      type="button"
                      data-testid="ocr-my-template-save"
                      disabled={busy}
                      onClick={() => void saveMineEditor()}
                    >
                      Сохранить
                    </Button>
                    {mineConfirmDelete ? (
                      <>
                        <Button
                          type="button"
                          data-testid="ocr-my-template-delete-confirm"
                          disabled={busy}
                          onClick={() => void removeMine(mineEditorId)}
                        >
                          Да, удалить
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => setMineConfirmDelete(false)}
                        >
                          Отмена
                        </Button>
                      </>
                    ) : (
                      <Button
                        type="button"
                        variant="ghost"
                        data-testid="ocr-my-template-delete"
                        disabled={busy}
                        onClick={() => setMineConfirmDelete(true)}
                      >
                        Удалить
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {createOpen && activeItem && (
        <div className="ocr-docs__dialog-backdrop" role="presentation">
          <div
            className="ocr-docs__dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="ocr-create-template-title"
            data-testid="ocr-create-template-dialog"
          >
            <h2 id="ocr-create-template-title">Создать шаблон</h2>
            <label>
              <span>Имя</span>
              <input
                value={createName}
                maxLength={80}
                data-testid="ocr-create-template-name"
                onChange={(event) => setCreateName(event.target.value)}
              />
            </label>
            <p className="ocr-docs__hint">Поля шаблона</p>
            <ul className="ocr-docs__mine-preview" data-testid="ocr-create-template-fields">
              {createPreviewFields.length ? createPreviewFields.map((field) => (
                <li key={field.id}>{field.label || field.apiKey}</li>
              )) : (
                <li>Нет заполненных валидных полей</li>
              )}
            </ul>
            {mineError ? <p className="ocr-docs__hint" role="alert">{mineError}</p> : null}
            <div className="ocr-docs__mine-actions">
              <Button
                type="button"
                data-testid="ocr-create-template-save"
                disabled={busy || !createName.trim()}
                onClick={() => void saveMyTemplate()}
              >
                Сохранить
              </Button>
              <Button
                type="button"
                data-testid="ocr-create-template-cancel"
                disabled={busy}
                onClick={() => setCreateOpen(false)}
              >
                Отмена
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
