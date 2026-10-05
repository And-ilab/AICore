const VOWELS = /[аеёиоуыэюяaeiouyіў]/i
const NOISE_CHARS = /[ħһɨı]/
const KNOWN_KEYS = new Set([
  'full_name', 'surname', 'given_name', 'patronymic', 'series', 'number',
  'document_number', 'birth_date', 'issue_date', 'expiry_date', 'birth_place',
  'address', 'issued_by', 'department_code', 'nationality', 'sex', 'inn',
  'personal_number', 'payer', 'beneficiary', 'amount', 'currency', 'purpose',
  'account_number', 'period', 'opening_balance', 'closing_balance',
  'agreement_number', 'agreement_date', 'principal', 'interest_rate', 'term',
  'application_number', 'application_date', 'product', 'operation_id',
  'operation_date', 'status', 'date', 'registration_date',
])

const KEY_ALIASES: Array<[RegExp, string]> = [
  [/expir|годен|срок\s*действ/i, 'expiry_date'],
  [/date of issue|дата выдачи/i, 'issue_date'],
  [/date of birth|дата рожд/i, 'birth_date'],
  [/surname|фамил|прэзвішч|прозвішч/i, 'surname'],
  [/given\s*names?|имя|ім[яі]/i, 'given_name'],
  [/patronym|отчеств/i, 'patronymic'],
  [/identification|личн(ый|ый|ы)|асабіст|personal number/i, 'personal_number'],
  [/nationalit|граждан|грамадзян/i, 'nationality'],
  [/\bsex\b|\bпол\b|gender/i, 'sex'],
  [/passport no|номер документа|document number/i, 'document_number'],
]

export const FIELD_TITLES: Record<string, string> = {
  full_name: 'ФИО',
  surname: 'Фамилия',
  given_name: 'Имя',
  patronymic: 'Отчество',
  series: 'Серия',
  number: 'Номер',
  document_number: 'Номер документа',
  birth_date: 'Дата рождения',
  issue_date: 'Дата выдачи',
  expiry_date: 'Срок действия',
  birth_place: 'Место рождения',
  address: 'Адрес',
  issued_by: 'Кем выдан',
  personal_number: 'Личный номер',
  nationality: 'Гражданство',
  sex: 'Пол',
}

function norm(value: string): string {
  return value.replace(/[_]+/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase()
}

function isOcrNoise(text: string): boolean {
  const compact = text.replace(/\s+/g, ' ').trim()
  if (!compact) return true
  if (NOISE_CHARS.test(compact)) return true
  const letters = compact.replace(/[^A-Za-zА-Яа-яЁёІіЎў]/g, '')
  const hasLatin = /[A-Za-z]/.test(letters)
  const hasCyrillic = /[А-Яа-яЁёІіЎў]/.test(letters)
  if (letters && hasLatin && hasCyrillic && letters.length <= 14) return true
  const words = compact.match(/[A-Za-zА-Яа-яЁёІіЎў]+/g) || []
  if (words.length && words.every((word) => word.length <= 8 && !VOWELS.test(word))) {
    return true
  }
  return compact.length < 3
}

export function isFormHeaderLabel(text: string): boolean {
  const compact = norm(text)
  if (!compact) return false
  if ((compact.match(/\//g) || []).length >= 2) return true
  if (compact.length > 48) return true
  const markers = ['тип/type', 'code of issuing', 'код дзяржавы', 'нумар пашпарта', 'passport no']
  return markers.filter((marker) => compact.includes(marker)).length >= 2
}

export function canonicalOcrFieldKey(id: string, label = ''): string | null {
  const folded = norm(id)
  if (KNOWN_KEYS.has(id) || KNOWN_KEYS.has(folded.replace(/\s+/g, '_'))) {
    return KNOWN_KEYS.has(id) ? id : folded.replace(/\s+/g, '_')
  }
  const blob = `${id} ${label}`
  for (const [pattern, key] of KEY_ALIASES) {
    if (pattern.test(blob)) return key
  }
  return null
}

export function isUsableOcrFieldKey(key: string): boolean {
  const folded = norm(key)
  if (!folded) return false
  if (canonicalOcrFieldKey(key)) return true
  if (isFormHeaderLabel(key) || isOcrNoise(folded)) return false
  return true
}

function looksStructuredValue(value: string): boolean {
  const compact = value.trim()
  if (!compact) return false
  if (/\d/.test(compact)) return true
  return compact.split(/\s+/).length >= 2
}

export function filterOcrFields<T extends {
  id: string
  value: string
  label?: string
  confidence?: number | null
}>(fields: T[]): T[] {
  const byKey = new Map<string, T>()
  const leftovers: T[] = []

  for (const field of fields) {
    const label = field.label || ''
    if (isFormHeaderLabel(field.id) || isFormHeaderLabel(label)) continue
    if (!isUsableOcrFieldKey(field.id) && !canonicalOcrFieldKey(field.id, label)) continue
    const canon = canonicalOcrFieldKey(field.id, label)
    if (canon) {
      const titled = {
        ...field,
        id: canon,
        label: FIELD_TITLES[canon] || field.label || canon,
      }
      const current = byKey.get(canon)
      if (!current || (field.confidence || 0) > (current.confidence || 0)) {
        byKey.set(canon, titled)
      }
      continue
    }
    leftovers.push(field)
  }

  const knownValues = new Set(
    [...byKey.values()].map((field) => norm(field.value)).filter(Boolean),
  )
  const result = [...byKey.values()]
  for (const field of leftovers) {
    const value = norm(field.value)
    if (value && knownValues.has(value)) continue
    const snake = /_/.test(field.id) || norm(field.id).split(' ').length >= 2
    if (!snake && !looksStructuredValue(field.value)) continue
    result.push(field)
  }
  return result
}
