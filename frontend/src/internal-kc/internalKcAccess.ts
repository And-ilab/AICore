export function canAccessInternalKc(roles: readonly string[]): boolean {
  return roles.some((role) =>
    [
      'contact_center_internal_user',
      'software_administrator',
      'contact_center_module_administrator',
    ].includes(role),
  )
}
