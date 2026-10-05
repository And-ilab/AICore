import { canOpenAdminCenter } from '../../auth/roleAccess'

export type HubPanelTab = 'assistant' | 'documents' | 'sufler'

const ASSISTANT_ROLES = new Set([
  'software_administrator',
  'contact_center_telephony_operator',
  'contact_center_online_chat_operator',
  'ai_assistant_module_administrator',
  'ai_assistant_user',
  'ai_assistant_analyst',
  'llm_knowledge_base_administrator',
])

const DOCUMENT_ROLES = new Set([
  'software_administrator',
  'document_recognition_module_administrator',
  'document_recognition_user',
  // Analyst: reporting entry via ≡; documents tab not for upload workflow
])

const SUFLER_ROLES = new Set([
  'software_administrator',
  'contact_center_telephony_operator',
])

export function getHubPanelTabs(
  roles: readonly string[],
  rbacTabs: readonly string[] = [],
): HubPanelTab[] {
  const roleSet = new Set(roles)
  const isSystemAdmin = roleSet.has('software_administrator')
  const hasRole = (allowed: Set<string>) => (
    [...allowed].some((role) => roleSet.has(role))
  )
  const hasTab = (tab: string, fallbackRoles: Set<string>) => (
    isSystemAdmin
    || rbacTabs.includes(tab)
    || (!rbacTabs.length && hasRole(fallbackRoles))
  )

  const tabs: HubPanelTab[] = []
  if (hasTab('assistant', ASSISTANT_ROLES)) tabs.push('assistant')
  if (hasTab('ocr', DOCUMENT_ROLES)) tabs.push('documents')
  if (hasTab('sufler_telephony', SUFLER_ROLES)) tabs.push('sufler')
  return tabs
}

/** ≡ menu in Hub panel — admins + analysts with reporting (§2.4 п.7/10/13). */
export function isHubAdminRole(roles: readonly string[]): boolean {
  return canOpenAdminCenter(roles)
}
