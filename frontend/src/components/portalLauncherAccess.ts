/**
 * Re-exports TZ I.4 launcher/settings access for portal components.
 * Matrix lives in auth/roleAccess.ts.
 */

export type { LauncherModule, SettingsMenuEntry } from '../auth/roleAccess'
export {
  ADMIN_ROLES,
  REPORTS_ONLY_ROLES,
  canOpenAdminCenter,
  canOpenKbAdminDeepLink,
  canWriteAssistantChat,
  getAllowedLauncherModules,
  getSettingsMenuEntry,
  isAssistantAnalystRole,
  isReportsOnlyRole,
  roleHasLauncherModules,
  showPortalSettingsButton,
} from '../auth/roleAccess'
