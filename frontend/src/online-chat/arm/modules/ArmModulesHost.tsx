import { ColleagueDialogsModule } from './ColleagueDialogsModule'
import { HelpModule } from './HelpModule'
import { HistoryModule } from './HistoryModule'
import { InternalChatModule } from './InternalChatModule'
import { SettingsModule } from './SettingsModule'
import { ShiftStatsModule } from './ShiftStatsModule'
import { TemplatesModule } from './TemplatesModule'
import type { ArmModuleId, ArmModuleProps } from './types'

export function ArmModulesHost({
  tab,
  t,
  scheme,
  operatorName,
  armRole,
  onBack,
  onNavigate,
  onUnreadChange,
}: ArmModuleProps & { tab: ArmModuleId }) {
  const common: ArmModuleProps = {
    t,
    scheme,
    operatorName,
    armRole,
    onBack,
    onNavigate,
    onUnreadChange,
  }

  switch (tab) {
    case 'history':
      return <HistoryModule {...common} />
    case 'stats':
      return <ShiftStatsModule {...common} />
    case 'colleagues':
      return <ColleagueDialogsModule {...common} />
    case 'internal':
      return <InternalChatModule {...common} />
    case 'templates':
      return <TemplatesModule {...common} />
    case 'settings':
      return <SettingsModule {...common} />
    case 'help':
      return <HelpModule {...common} />
    case 'dialogs':
    case 'employees':
    default:
      return null
  }
}

export function isArmWorkspaceModule(tab: ArmModuleId): boolean {
  return tab !== 'dialogs' && tab !== 'employees'
}
