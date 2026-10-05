import { ensureCsrfToken, ensureDevSession } from '../../auth/ensureDevSession'

export type AssistantSkillScope = 'org' | 'user'

export interface AssistantSkill {
  id: number
  code: string
  scope: AssistantSkillScope
  owner_id: number | null
  name: string
  alias: string
  instruction: string
  needs_attachment: boolean
  enabled: boolean
  department_scope: string
}

export const DEMO_BANK_SKILLS: AssistantSkill[] = [
  {
    id: -1,
    code: 'SKL-01',
    scope: 'org',
    owner_id: null,
    name: 'Служебная записка',
    alias: 'записка',
    instruction: 'Оформи служебную записку.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
  {
    id: -2,
    code: 'SKL-02',
    scope: 'org',
    owner_id: null,
    name: 'Справка по нормативке',
    alias: 'справка',
    instruction: 'Подготовь справку по нормативке.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
  {
    id: -3,
    code: 'SKL-03',
    scope: 'org',
    owner_id: null,
    name: 'Ответ на обращение',
    alias: 'обращение',
    instruction: 'Черновик ответа на обращение.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
  {
    id: -4,
    code: 'SKL-04',
    scope: 'org',
    owner_id: null,
    name: 'Пошаговая инструкция',
    alias: 'инструкция',
    instruction: 'Составь пошаговую инструкцию.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
  {
    id: -5,
    code: 'SKL-05',
    scope: 'org',
    owner_id: null,
    name: 'Чеклист процесса',
    alias: 'чеклист',
    instruction: 'Собери чеклист процесса.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
  {
    id: -6,
    code: 'SKL-06',
    scope: 'org',
    owner_id: null,
    name: 'Сравнить редакции',
    alias: 'сравнить',
    instruction: 'Сравни две редакции.',
    needs_attachment: true,
    enabled: true,
    department_scope: '',
  },
  {
    id: -7,
    code: 'SKL-07',
    scope: 'org',
    owner_id: null,
    name: 'Извлечь реквизиты',
    alias: 'реквизиты',
    instruction: 'Извлеки реквизиты.',
    needs_attachment: true,
    enabled: true,
    department_scope: '',
  },
  {
    id: -8,
    code: 'SKL-08',
    scope: 'org',
    owner_id: null,
    name: 'Официальный перевод RU↔EN',
    alias: 'перевод',
    instruction: 'Переведи официально RU↔EN.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
  {
    id: -9,
    code: 'SKL-09',
    scope: 'org',
    owner_id: null,
    name: 'Коротко',
    alias: 'кратко',
    instruction: 'Ответь максимум двумя короткими предложениями.',
    needs_attachment: false,
    enabled: true,
    department_scope: '',
  },
]

class SkillApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function parseJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  let body: T | { error?: string; details?: Record<string, string[]> } | null = null
  try {
    body = text ? (JSON.parse(text) as T) : null
  } catch {
    throw new SkillApiError(`HTTP ${response.status}`, response.status)
  }
  if (!response.ok) {
    const error = (body ?? {}) as { error?: string; details?: Record<string, string[]> }
    const detail = error.details?.request?.[0] || error.error || `HTTP ${response.status}`
    throw new SkillApiError(detail, response.status)
  }
  if (body == null) {
    throw new SkillApiError('empty_response', response.status)
  }
  return body as T
}

async function authedFetch(input: string, init: RequestInit & { csrf?: boolean } = {}) {
  const { csrf = false, headers: initHeaders, ...rest } = init
  await ensureDevSession()
  const headers = new Headers(initHeaders)
  if (csrf) {
    const token = await ensureCsrfToken()
    if (token) headers.set('X-CSRFToken', token)
  }
  return fetch(input, { ...rest, credentials: 'include', headers })
}

export async function fetchAssistantSkills(): Promise<AssistantSkill[]> {
  const response = await authedFetch('/api/v1/assistant/skills/', { method: 'GET' })
  const body = await parseJson<{ items: AssistantSkill[] }>(response)
  return body.items
}

export async function createUserSkill(payload: {
  name: string
  alias: string
  instruction: string
  needs_attachment?: boolean
}): Promise<AssistantSkill> {
  const response = await authedFetch('/api/v1/assistant/skills/', {
    method: 'POST',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function updateUserSkill(
  id: number,
  payload: Partial<{
    name: string
    alias: string
    instruction: string
    needs_attachment: boolean
  }>,
): Promise<AssistantSkill> {
  const response = await authedFetch(`/api/v1/assistant/skills/${id}/`, {
    method: 'PATCH',
    csrf: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return parseJson(response)
}

export async function deleteUserSkill(id: number): Promise<void> {
  const response = await authedFetch(`/api/v1/assistant/skills/${id}/`, {
    method: 'DELETE',
    csrf: true,
  })
  await parseJson<{ ok: boolean }>(response)
}

export function filterSkills(
  items: AssistantSkill[],
  query: string,
): AssistantSkill[] {
  const needle = query.trim().toLowerCase()
  if (!needle) return items
  return items.filter((item) => {
    const alias = item.alias.toLowerCase()
    const name = item.name.toLowerCase()
    const code = item.code.toLowerCase()
    return alias.includes(needle) || name.includes(needle) || code.includes(needle)
  })
}
