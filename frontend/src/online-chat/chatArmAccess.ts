const ONLINE_CHAT_ARM_OPERATE_ROLES = new Set([
  'contact_center_online_chat_operator',
  // Supervisor has own writable ARM (empty by default; dialogs only after take-over / transfer).
  'contact_center_supervisor',
])

const ONLINE_CHAT_ARM_VIEW_ROLES = new Set([
  'contact_center_online_chat_operator',
  'contact_center_module_administrator',
  'contact_center_supervisor',
  'software_administrator',
])

/** Full operator ARM (accept / reply / presence). */
export function canOperateOnlineChatArm(roles: readonly string[]): boolean {
  return roles.some((role) => ONLINE_CHAT_ARM_OPERATE_ROLES.has(role))
}

/** May open ARM at least in read-only observation mode. */
export function canViewOnlineChatArm(roles: readonly string[]): boolean {
  return roles.some((role) => ONLINE_CHAT_ARM_VIEW_ROLES.has(role))
}

/** @deprecated Prefer canOperate / canView; kept for existing imports. */
export function canAccessOnlineChatArm(roles: readonly string[]): boolean {
  return canViewOnlineChatArm(roles)
}
