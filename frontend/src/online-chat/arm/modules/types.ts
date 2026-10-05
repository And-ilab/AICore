import type { ArmTheme } from '../theme'

export type ArmModuleId =
  | 'dialogs'
  | 'history'
  | 'stats'
  | 'colleagues'
  | 'internal'
  | 'templates'
  | 'employees'
  | 'settings'
  | 'help'

export type ArmModuleRole = 'operator' | 'supervisor' | 'admin'

/** Structurally matches SchemePalette from ArmOperatorView. */
export type ModuleSchemePalette = {
  label: string
  accent: string
  accentWeak: string
  accentControl: string
  headerBg: string
  panelBg: string
  badge: string
}

export type ArmModuleProps = {
  t: ArmTheme
  scheme: ModuleSchemePalette
  operatorName: string
  armRole: ArmModuleRole
  onBack: () => void
  onNavigate?: (id: ArmModuleId) => void
  onUnreadChange?: (count: number) => void
}

export type PresenceTone = 'online' | 'busy' | 'away' | 'offline'

export type InternalContact = {
  id: string
  name: string
  department: string
  presence: PresenceTone
  title?: string
  activeDialogs?: number
}

export type InternalMessage = {
  id: string
  fromId: string
  text: string
  at: string
  mine: boolean
}

export type InternalThread = {
  contactId: string
  messages: InternalMessage[]
  unread: number
  pinned: boolean
  updatedAt: string
}

export type AppealHistoryItem = {
  id: string
  clientName: string
  phoneMasked: string
  channel: string
  topic: string
  status: 'closed' | 'active' | 'lost' | 'offline'
  operatorName: string
  clientIp?: string
  feedbackRating?: number | null
  openedAt: string
  closedAt?: string
  summary: string
}

export type ReplyTemplateScope = 'personal' | 'shared'

export type ReplyTemplateItem = {
  id: string
  title: string
  category: string
  body: string
  updatedAt: string
  favorite?: boolean
  /** personal = only owner; shared = all operators (supervisor-created). */
  scope?: ReplyTemplateScope
  ownerName?: string
}

export type ArmUiSettings = {
  soundEnabled: boolean
  desktopNotify: boolean
  compactQueue: boolean
  autoExpandSummary: boolean
  fontScale: 'sm' | 'md' | 'lg'
}
