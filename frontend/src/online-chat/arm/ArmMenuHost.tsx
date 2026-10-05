import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { getInternalUnreadCount } from '../api/managementApi'
import {
  ArmOverlayMenu,
  getSchemePalette,
  type ArmMenuContext,
  type ArmStatsTab,
} from './ArmOperatorView'
import { ARM_THEME_DARK, ARM_THEME_LIGHT, type ThemeKind } from './theme'
import { ArmModulesHost, isArmWorkspaceModule } from './modules'
import type { ArmModuleId } from './modules'

type ArmRole = 'operator' | 'supervisor' | 'admin'

export function ArmMenuHost({
  open,
  onOpenChange,
  armRole,
  menuContext,
  themeKind = 'light',
  operatorName = 'Оператор',
  children,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  armRole: ArmRole
  menuContext: ArmMenuContext
  themeKind?: ThemeKind
  operatorName?: string
  children: ReactNode
}) {
  const t = themeKind === 'light' ? ARM_THEME_LIGHT : ARM_THEME_DARK
  const scheme = useMemo(() => getSchemePalette(t, 'belarusbank_emerald'), [t])
  const [activeId, setActiveId] = useState<ArmStatsTab>(
    menuContext === 'picker' ? 'employees' : 'dialogs',
  )
  const [internalUnread, setInternalUnread] = useState(0)

  useEffect(() => {
    let cancelled = false
    const poll = () => {
      void getInternalUnreadCount(operatorName)
        .then((result) => {
          if (!cancelled) setInternalUnread(result.unread_count)
        })
        .catch(() => undefined)
    }
    poll()
    const timer = window.setInterval(poll, 4000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [operatorName])

  const showModule = isArmWorkspaceModule(activeId)

  return (
    <div
      className="arm-menu-host"
      style={{ position: 'relative', height: '100%', minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
    >
      <ArmOverlayMenu
        t={t}
        scheme={scheme}
        open={open}
        armRole={armRole}
        menuContext={menuContext}
        activeId={activeId}
        badges={{ internal: internalUnread }}
        onSelect={(id) => {
          setActiveId(id)
          onOpenChange(false)
        }}
        onClose={() => onOpenChange(false)}
      />
      {showModule ? (
        <ArmModulesHost
          tab={activeId as ArmModuleId}
          t={t}
          scheme={scheme}
          operatorName={operatorName}
          armRole={armRole}
          onBack={() => setActiveId(menuContext === 'picker' ? 'employees' : 'dialogs')}
          onNavigate={(id) => setActiveId(id as ArmStatsTab)}
          onUnreadChange={setInternalUnread}
        />
      ) : (
        children
      )}
    </div>
  )
}
