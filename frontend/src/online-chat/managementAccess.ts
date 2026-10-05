/** Operational panel — project supervisor role (I.4.2), not analyst (§2.4 п.7 = reports). */
const ONLINE_CHAT_SUPERVISOR_ROLES = new Set([
  'contact_center_supervisor',
])

const ONLINE_CHAT_ADMIN_ROLES = new Set([
  'software_administrator',
  'contact_center_module_administrator',
])

export function canAccessOnlineChatSupervisor(roles: readonly string[]): boolean {
  return roles.some((role) => ONLINE_CHAT_SUPERVISOR_ROLES.has(role))
}

export function canAccessOnlineChatAdmin(roles: readonly string[]): boolean {
  return roles.some((role) => ONLINE_CHAT_ADMIN_ROLES.has(role))
}

/** Supervisor may transfer in view mode; admin observation stays read-only. */
export function canTransferInOnlineChatView(roles: readonly string[]): boolean {
  return roles.includes('contact_center_supervisor')
}
