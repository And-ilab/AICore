import { useEffect, useMemo, useState } from 'react'
import {
  findDemoRole,
  readStoredDemoRole,
  storeDemoRole,
  type DemoRoleDefinition,
} from '../../auth/demoRoles'
import {
  getAllowedLauncherModules,
  PortalLauncher,
  RolePicker,
  type LauncherModule,
} from '../../components'
import './AiHubPanel.css'

export interface AiHubPortalHostProps {
  username?: string | null
}

function readOpenModulesFromUrl(): LauncherModule[] {
  try {
    const open = new URLSearchParams(window.location.search).get('open') || ''
    const allowed = new Set<LauncherModule>(['assistant', 'sufler'])
    return open
      .split(',')
      .map((item) => item.trim())
      .filter((item): item is LauncherModule => allowed.has(item as LauncherModule))
  } catch {
    return []
  }
}

export function AiHubPortalHost({
  username = 'Демо-пользователь',
}: AiHubPortalHostProps) {
  const [role, setRole] = useState<DemoRoleDefinition | null>(
    () => findDemoRole(readStoredDemoRole()) ?? null,
  )
  const [picking, setPicking] = useState(() => role == null)
  const requestedWindows = useMemo(() => readOpenModulesFromUrl(), [])

  useEffect(() => {
    storeDemoRole(role?.code ?? null)
  }, [role])

  const selectRole = (next: DemoRoleDefinition) => {
    storeDemoRole(next.code)
    setRole(next)
    setPicking(false)
  }

  if (picking || !role) {
    return (
      <div className="hub-panel-host hub-panel-host--role-pick">
        <header>
          <img src="/assets/belarusbank-logo.png" alt="Беларусбанк" />
          <span>Корпоративный портал · AI Hub · выбор роли</span>
        </header>
        <main>
          <p>Тестовый вход</p>
          <h1>Матрица ролей I.4</h1>
        </main>
        <RolePicker
          selectedCode={role?.code}
          onSelect={selectRole}
        />
      </div>
    )
  }

  const allowed = getAllowedLauncherModules([role.code])
  const initialWindows = requestedWindows.filter((module) =>
    allowed.includes(module),
  )

  return (
    <PortalLauncher
      roles={[role.code]}
      username={username}
      roleLabel={role.label}
      menuVariant="compact"
      initialWindows={initialWindows}
      onChangeRole={() => setPicking(true)}
    />
  )
}
