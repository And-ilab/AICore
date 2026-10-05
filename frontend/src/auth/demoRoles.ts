/** Contractual I.4 role catalog for demo/test role selection (TZ §2.4 / roles.py). */

export interface DemoRoleDefinition {
  number: number
  code: string
  label: string
  group: string
}

export const DEMO_ROLE_CATALOG: readonly DemoRoleDefinition[] = [
  {
    number: 1,
    code: 'software_administrator',
    label: 'Администратор ПО',
    group: 'Администрирование',
  },
  {
    number: 2,
    code: 'llm_knowledge_base_administrator',
    label: 'Администратор базы знаний LLM',
    group: 'Администрирование',
  },
  {
    number: 3,
    code: 'contact_center_module_administrator',
    label: 'Администратор модуля Контакт-центра',
    group: 'Контакт-центр',
  },
  {
    number: 4,
    code: 'contact_center_telephony_operator',
    label: 'Оператор канала телефония Контакт-центра',
    group: 'Контакт-центр',
  },
  {
    number: 5,
    code: 'contact_center_online_chat_operator',
    label: 'Оператор онлайн-чата Контакт-центра',
    group: 'Контакт-центр',
  },
  {
    number: 6,
    code: 'contact_center_internal_user',
    label: 'Внутренний пользователь Контакт-центра',
    group: 'Контакт-центр',
  },
  {
    number: 7,
    code: 'contact_center_analyst',
    label: 'Аналитик Контакт-центра',
    group: 'Контакт-центр',
  },
  /** Project role for online-chat ops panel (not one of the 13 contractual I.4 codes in roles.py). */
  {
    number: 14,
    code: 'contact_center_supervisor',
    label: 'Супервизор Контакт-центра (онлайн-чат)',
    group: 'Контакт-центр',
  },
  {
    number: 8,
    code: 'ai_assistant_module_administrator',
    label: 'Администратор модуля ИИ-ассистент',
    group: 'ИИ-ассистент',
  },
  {
    number: 9,
    code: 'ai_assistant_user',
    label: 'Пользователь ИИ-ассистента',
    group: 'ИИ-ассистент',
  },
  {
    number: 10,
    code: 'ai_assistant_analyst',
    label: 'Аналитик ИИ-ассистента',
    group: 'ИИ-ассистент',
  },
  {
    number: 11,
    code: 'document_recognition_module_administrator',
    label: 'Администратор модуля распознавания документов',
    group: 'Документы',
  },
  {
    number: 12,
    code: 'document_recognition_user',
    label: 'Пользователь модуля распознавания документов',
    group: 'Документы',
  },
  {
    number: 13,
    code: 'document_recognition_analyst',
    label: 'Аналитик модуля распознавания документов',
    group: 'Документы',
  },
] as const

export const DEMO_ROLE_STORAGE_KEY = 'ai-hub-demo-role'

/** Stable demo personas for shell FIO when a RolePicker role is active. */
export const DEMO_ROLE_PERSONA: Record<string, { name: string; title: string }> = {
  software_administrator: { name: 'Админов А.П.', title: 'Администратор ПО' },
  contact_center_module_administrator: {
    name: 'Смирнов А.Н.',
    title: 'Администратор модуля КЦ',
  },
  contact_center_online_chat_operator: {
    name: 'Иванов И.И.',
    title: 'Оператор онлайн-чата',
  },
  contact_center_supervisor: {
    name: 'Козлова Е.В.',
    title: 'Супервизор КЦ',
  },
  contact_center_analyst: {
    name: 'Орлова Н.Д.',
    title: 'Аналитик КЦ',
  },
}

export function findDemoRole(code: string | null | undefined): DemoRoleDefinition | undefined {
  if (!code) return undefined
  return DEMO_ROLE_CATALOG.find((role) => role.code === code)
}

export function readStoredDemoRole(): string | null {
  try {
    const value =
      sessionStorage.getItem(DEMO_ROLE_STORAGE_KEY)
      ?? localStorage.getItem(DEMO_ROLE_STORAGE_KEY)
    return findDemoRole(value)?.code ?? null
  } catch {
    return null
  }
}

export function storeDemoRole(code: string | null): void {
  try {
    if (!code) {
      sessionStorage.removeItem(DEMO_ROLE_STORAGE_KEY)
      localStorage.removeItem(DEMO_ROLE_STORAGE_KEY)
      return
    }
    sessionStorage.setItem(DEMO_ROLE_STORAGE_KEY, code)
    localStorage.setItem(DEMO_ROLE_STORAGE_KEY, code)
  } catch {
    /* ignore quota / private mode */
  }
}

export function personaForDemoRole(code: string | null | undefined): {
  name: string
  title: string
} | null {
  if (!code) return null
  const known = DEMO_ROLE_PERSONA[code]
  if (known) return known
  const role = findDemoRole(code)
  if (!role) return null
  return { name: 'Сотрудник КЦ', title: role.label }
}
