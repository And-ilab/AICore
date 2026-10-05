const CC_REPORTS_ROLES = new Set([
  'software_administrator',
  'contact_center_analyst',
  'contact_center_module_administrator',
  'contact_center_online_chat_operator',
  'contact_center_telephony_operator',
  'contact_center_supervisor',
])

function isDevRuntime(): boolean {
  return Boolean(import.meta.env.DEV || import.meta.env.VITE_SUFLER_DEMO === '1')
}

/** II.6 / cc.reports.view — in local DEV allow everyone so the module is usable. */
export function canAccessCcReports(roles: readonly string[]): boolean {
  if (isDevRuntime()) return true
  return roles.some((role) => CC_REPORTS_ROLES.has(role))
}
