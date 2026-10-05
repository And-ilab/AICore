/**
 * TZ I.4 / III.2 / IV.2 — SPA access matrix for the 13 contractual roles.
 * Source of truth for portal launcher, ≡ menu, chat write, and admin shell entry.
 */

export type LauncherModule = 'sufler' | 'assistant' | 'online_chat'

export interface SettingsMenuEntry {
  href: string
  label: string
  /** Full config vs reports-only (analysts §2.4 п.7 / 10 / 13). */
  kind: 'admin' | 'reports'
}

/** §2.4 п.1,2,3,8,11 — may open Центр настроек and edit their areas. */
export const ADMIN_ROLES = [
  'software_administrator',
  'llm_knowledge_base_administrator',
  'contact_center_module_administrator',
  'ai_assistant_module_administrator',
  'document_recognition_module_administrator',
] as const

/** §2.4 п.7,10,13 — reporting only, no config edits, no chat write. */
export const REPORTS_ONLY_ROLES = [
  'contact_center_analyst',
  'ai_assistant_analyst',
  'document_recognition_analyst',
] as const

const SUFLER_ROLES = new Set([
  'software_administrator',
  'contact_center_module_administrator',
  'contact_center_telephony_operator',
  'contact_center_online_chat_operator',
  // DEV preview while configuring CC KB / scenarios
  'llm_knowledge_base_administrator',
])

/** Online-chat ops UI — not analyst (reports only per §2.4 п.7 / II.6). */
const ONLINE_CHAT_ROLES = new Set([
  'software_administrator',
  'contact_center_module_administrator',
  'contact_center_online_chat_operator',
  'contact_center_supervisor',
])

/** Open Ассистент window (write or read-only per canWriteAssistantChat). */
const ASSISTANT_ROLES = new Set([
  'software_administrator',
  'llm_knowledge_base_administrator',
  'ai_assistant_module_administrator',
  'ai_assistant_user',
  'ai_assistant_analyst', // III.2 п.10 read-only*
  'contact_center_telephony_operator',
  'contact_center_online_chat_operator',
])

/** May send messages in assistant chat (not analysts). */
const ASSISTANT_CHAT_WRITE_ROLES = new Set([
  'software_administrator',
  'llm_knowledge_base_administrator',
  'ai_assistant_module_administrator',
  'ai_assistant_user',
  'contact_center_telephony_operator',
  'contact_center_online_chat_operator',
])

const SETTINGS_ENTRY_BY_ROLE: Record<string, SettingsMenuEntry> = {
  software_administrator: {
    href: '/ai-hub/admin',
    label: 'Центр настроек',
    kind: 'admin',
  },
  llm_knowledge_base_administrator: {
    href: '/ai-hub/admin',
    label: 'Центр настроек',
    kind: 'admin',
  },
  contact_center_module_administrator: {
    href: '/ai-hub/admin/llm_config_cc',
    label: 'Центр настроек',
    kind: 'admin',
  },
  ai_assistant_module_administrator: {
    href: '/ai-hub/admin',
    label: 'Центр настроек',
    kind: 'admin',
  },
  document_recognition_module_administrator: {
    href: '/ai-hub/admin/ocr',
    label: 'Центр настроек',
    kind: 'admin',
  },
  contact_center_analyst: {
    href: '/admin/reports',
    label: 'Отчётность КЦ',
    kind: 'reports',
  },
  ai_assistant_analyst: {
    href: '/ai-hub/admin/monitoring',
    label: 'Отчётность ассистента',
    kind: 'reports',
  },
  document_recognition_analyst: {
    href: '/ai-hub/admin/ocr_reports',
    label: 'Отчётность OCR',
    kind: 'reports',
  },
}

function hasAny(roles: readonly string[], allowed: readonly string[]): boolean {
  return roles.some((role) => allowed.includes(role))
}

export function getAllowedLauncherModules(
  roles: readonly string[],
): LauncherModule[] {
  const roleSet = new Set(roles)
  const modules: LauncherModule[] = []
  if ([...SUFLER_ROLES].some((role) => roleSet.has(role))) {
    modules.push('sufler')
  }
  if ([...ASSISTANT_ROLES].some((role) => roleSet.has(role))) {
    modules.push('assistant')
  }
  if ([...ONLINE_CHAT_ROLES].some((role) => roleSet.has(role))) {
    modules.push('online_chat')
  }
  return modules
}

export function roleHasLauncherModules(roles: readonly string[]): boolean {
  return getAllowedLauncherModules(roles).length > 0
}

/** Админы модулей + аналитики с отчётностью (≡ → настройки/отчёты). */
export function canOpenAdminCenter(roles: readonly string[]): boolean {
  return hasAny(roles, [...ADMIN_ROLES, ...REPORTS_ONLY_ROLES])
}

export function canWriteAssistantChat(roles: readonly string[]): boolean {
  return roles.some((role) => ASSISTANT_CHAT_WRITE_ROLES.has(role))
}

/** True when the effective access is reports-only (no config save). */
export function isReportsOnlyRole(roles: readonly string[]): boolean {
  if (!hasAny(roles, REPORTS_ONLY_ROLES)) return false
  return !hasAny(roles, ADMIN_ROLES)
}

export function isAssistantAnalystRole(roles: readonly string[]): boolean {
  return roles.includes('ai_assistant_analyst')
}

/**
 * Single ≡ menu target for the highest-priority role.
 * Prefer full admin entry over reports-only when both are present.
 */
export function getSettingsMenuEntry(
  roles: readonly string[],
): SettingsMenuEntry | null {
  for (const code of ADMIN_ROLES) {
    if (roles.includes(code)) return SETTINGS_ENTRY_BY_ROLE[code]
  }
  for (const code of REPORTS_ONLY_ROLES) {
    if (roles.includes(code)) return SETTINGS_ENTRY_BY_ROLE[code]
  }
  return null
}

/** Show ≡ on portal chrome when there is no S/A window to host the menu. */
export function showPortalSettingsButton(roles: readonly string[]): boolean {
  return canOpenAdminCenter(roles) && !roleHasLauncherModules(roles)
}

export function canOpenKbAdminDeepLink(roles: readonly string[]): boolean {
  return roles.some((role) =>
    ['software_administrator', 'llm_knowledge_base_administrator'].includes(role),
  )
}
