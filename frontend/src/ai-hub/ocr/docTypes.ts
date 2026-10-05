export const OPERATOR_DOC_TYPES = ['passport', 'account_statement', 'loan_agreement'] as const

export type OperatorDocType = (typeof OPERATOR_DOC_TYPES)[number]

export const ML_DOC_TYPE = 'ml'

export const OPERATOR_DOC_TITLES: Record<OperatorDocType, string> = {
  passport: 'Паспорт',
  account_statement: 'Банковская выписка',
  loan_agreement: 'Договор',
}

export function isOperatorDocType(value: string): value is OperatorDocType {
  return (OPERATOR_DOC_TYPES as readonly string[]).includes(value)
}

export function isMlDocType(value: string): boolean {
  return value === ML_DOC_TYPE || value === 'auto'
}

export const MINE_DOC_PREFIX = 'mine:'

export function mineDocType(id: number): string {
  return `${MINE_DOC_PREFIX}${id}`
}

export function parseMineTemplateId(value: string): number | null {
  if (!value.startsWith(MINE_DOC_PREFIX)) return null
  const parsed = Number(value.slice(MINE_DOC_PREFIX.length))
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null
}

export function isMineDocType(value: string): boolean {
  return parseMineTemplateId(value) != null
}

export function operatorDocTitle(docType: string): string {
  if (isMlDocType(docType)) return 'ML распознавание'
  if (isOperatorDocType(docType)) return OPERATOR_DOC_TITLES[docType]
  return ''
}

const CHOSEN_TYPES_KEY = 'sufler.ocr.chosenDocTypes'
const UPLOAD_TYPE_KEY = 'sufler.ocr.uploadDocType'

export function readChosenDocType(jobId: string): string {
  try {
    const raw = sessionStorage.getItem(CHOSEN_TYPES_KEY)
    if (!raw) return ''
    const map = JSON.parse(raw) as Record<string, string>
    return typeof map[jobId] === 'string' ? map[jobId] : ''
  } catch {
    return ''
  }
}

export function writeChosenDocType(jobId: string, docType: string): void {
  if (!jobId) return
  try {
    const raw = sessionStorage.getItem(CHOSEN_TYPES_KEY)
    const map = raw ? JSON.parse(raw) as Record<string, string> : {}
    map[jobId] = docType
    sessionStorage.setItem(CHOSEN_TYPES_KEY, JSON.stringify(map))
  } catch {
    // Private mode / disabled storage: keep the in-memory choice only.
  }
}

export function readUploadDocType(fallback = 'passport'): string {
  try {
    const stored = sessionStorage.getItem(UPLOAD_TYPE_KEY) || ''
    if (isMlDocType(stored) || isOperatorDocType(stored) || isMineDocType(stored)) {
      return stored
    }
  } catch {
    // fall through
  }
  return fallback
}

export function writeUploadDocType(docType: string): void {
  try {
    sessionStorage.setItem(UPLOAD_TYPE_KEY, docType)
  } catch {
    // ignore
  }
}
