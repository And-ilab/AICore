import { useState } from 'react'
import {
  findDemoRole,
  personaForDemoRole,
  readStoredDemoRole,
  storeDemoRole,
} from './auth/demoRoles'
import { usePortalAuth } from './auth/usePortalAuth'
import { AiHubAdminApp } from './ai-hub/admin/AiHubAdminApp'
import { isAdminCenterRole } from './ai-hub/admin/adminNav'
import { AiHubPortalHost } from './ai-hub/panel/AiHubPortalHost'
import { AiHubReportsApp } from './ai-hub/reports/AiHubReportsApp'
import { canAccessCcReports } from './ai-hub/reports/reportsAccess'
import { InternalKcDialogApp } from './internal-kc/InternalKcDialogApp'
import { canAccessInternalKc } from './internal-kc/internalKcAccess'
import { AssistantWindowApp } from './assistant/AssistantWindowApp'
import { LiveSuflerPhoneApp } from './sufler/LiveSuflerPhoneApp'
import { ChatArmApp } from './online-chat/ChatArmApp'
import {
  canOperateOnlineChatArm,
  canViewOnlineChatArm,
} from './online-chat/chatArmAccess'
import { ChatAdminApp } from './online-chat/admin/ChatAdminApp'
import {
  canAccessOnlineChatAdmin,
  canAccessOnlineChatSupervisor,
  canTransferInOnlineChatView,
} from './online-chat/managementAccess'
import { OperatorPicker } from './online-chat/OperatorPicker'
import { ChatSimulatorApp } from './online-chat/simulator/ChatSimulatorApp'
import { ChatPlatformShellWithAvatar } from './online-chat/shell/ChatPlatformShellWithAvatar'
import { SupervisorApp } from './online-chat/supervisor/SupervisorApp'
import { ArmMenuHost } from './online-chat/arm/ArmMenuHost'
import type { ThemeKind } from './online-chat/arm/theme'
import {
  Button,
  Card,
  PortalLauncher,
  StatusBadge,
  canWriteAssistantChat,
  getAllowedLauncherModules,
  getSettingsMenuEntry,
  type LauncherModule,
} from './components'
import './App.css'

function jobTitleFromRoles(roles: readonly string[]): string {
  const persona = personaForDemoRole(roles[0])
  if (persona) return persona.title
  const role = findDemoRole(roles[0])
  if (role) return role.label
  if (roles.includes('contact_center_module_administrator')) return 'Администратор модуля КЦ'
  if (roles.includes('contact_center_supervisor')) return 'Супервизор КЦ'
  if (roles.includes('contact_center_online_chat_operator')) return 'Оператор онлайн-чата'
  return 'Сотрудник КЦ'
}

function employeeDisplayName(
  username: string | null | undefined,
  roles: readonly string[],
) {
  const persona = personaForDemoRole(roles[0])
  if (persona) return persona.name
  if (username && username !== 'Development user') return username
  return 'Сотрудник КЦ'
}

const ONLINE_CHAT_UI_ROLES = new Set([
  'contact_center_online_chat_operator',
  'contact_center_supervisor',
  'contact_center_module_administrator',
  'software_administrator',
])

/**
 * RolePicker selection is the source of truth for online-chat tab isolation.
 * Multi-role auth without a picked demo role does not unlock all tabs at once.
 */
function rolesForUi(authRoles: readonly string[], queryRole?: string | null): string[] {
  if (queryRole && findDemoRole(queryRole)) {
    storeDemoRole(queryRole)
    return [queryRole]
  }
  const demo = readStoredDemoRole()
  if (demo) return [demo]
  const chatRoles = authRoles.filter((role) => ONLINE_CHAT_UI_ROLES.has(role))
  if (chatRoles.length === 1) return chatRoles
  if (chatRoles.length > 1) return []
  return chatRoles
}

function StandaloneModule({
  module,
  roles,
  username,
}: {
  module: LauncherModule
  roles: readonly string[]
  username?: string | null
}) {
  const allowed = getAllowedLauncherModules(roles).includes(module)
  const label = module === 'sufler' ? 'Суфлёр' : 'Ассистент'

  if (!allowed) {
    return (
      <main className="standalone-module standalone-module--denied">
        <Card>
          <StatusBadge status="danger">403</StatusBadge>
          <h1>Нет доступа</h1>
          <p>Роль пользователя не разрешает открывать модуль «{label}».</p>
          <Button onClick={() => window.location.assign('/')}>Вернуться на портал</Button>
        </Card>
      </main>
    )
  }

  if (module === 'sufler') {
    return (
      <LiveSuflerPhoneApp
        operatorName={username ?? 'Иванова М.П.'}
      />
    )
  }

  return (
    <AssistantWindowApp
      username={username ?? 'Пользователь ИИ-ассистента'}
      demoMode={import.meta.env.VITE_SUFLER_DEMO === '1'}
      readOnly={!canWriteAssistantChat(roles)}
      settingsHref={getSettingsMenuEntry(roles)?.href ?? '/ai-hub/admin'}
      settingsLabel={getSettingsMenuEntry(roles)?.label ?? 'Центр настроек'}
    />
  )
}

function App() {
  const auth = usePortalAuth()
  const route = window.location.pathname.replace(/\/+$/, '') || '/'
  const [chatThemeKind, setChatThemeKind] = useState<ThemeKind>('light')
  const [armMenuOpen, setArmMenuOpen] = useState(() => {
    try {
      const params = new URLSearchParams(window.location.search)
      return Boolean(params.get('historyDialog') || params.get('historyOperator'))
    } catch {
      return false
    }
  })

  if (auth.status === 'loading') {
    return (
      <main className="standalone-module" aria-busy="true">
        <Card>Проверяем права доступа…</Card>
      </main>
    )
  }

  if (route === '/sufler' || route === '/assistant') {
    return (
      <StandaloneModule
        module={route.slice(1) as LauncherModule}
        roles={auth.roles}
        username={auth.username}
      />
    )
  }

  if (route === '/online-chat' || route.startsWith('/online-chat/')) {
    const params = new URLSearchParams(window.location.search)
    const roles = rolesForUi(auth.roles, params.get('demo_role'))
    const isSupervisorRoute = route === '/online-chat/supervisor'
    const isOperatorsRoute = route === '/online-chat/operators'
    const isAdminRoute = route === '/online-chat/admin'
    const isSimulatorRoute = route === '/online-chat/simulator'
    const canOperateArm = canOperateOnlineChatArm(roles)
    const canViewArm = canViewOnlineChatArm(roles)
    const canSupervisor = canAccessOnlineChatSupervisor(roles)
    const canAdmin = canAccessOnlineChatAdmin(roles)
    const showSimulator = import.meta.env.DEV || import.meta.env.VITE_SUFLER_DEMO === '1'
    const simOperatePreview = params.get('mode') === 'operate' && Boolean(params.get('operator')?.trim())
    const allowed = isSupervisorRoute
      ? canSupervisor
      : isOperatorsRoute
        ? (canSupervisor || canAdmin)
        : isAdminRoute
          ? canAdmin
          : isSimulatorRoute
            ? showSimulator
            : route === '/online-chat' && (canViewArm || simOperatePreview || showSimulator)

    if (!allowed) {
      return (
        <main className="standalone-module standalone-module--denied">
          <Card>
            <StatusBadge status="danger">403</StatusBadge>
            <h1>Нет доступа к разделу онлайн-чата</h1>
            <p>Для выбранного маршрута требуется соответствующая роль Контакт-центра.</p>
            <Button onClick={() => window.location.assign('/ai-hub')}>Выбрать роль</Button>
          </Card>
        </main>
      )
    }

    const operatorFromQuery = params.get('operator')?.trim() || ''
    /** Simulator / multi-window: work as this operator (writable), not observation. */
    const simOperate = params.get('mode') === 'operate' && Boolean(operatorFromQuery)
    const forcedView = !simOperate && (
      params.get('mode') === 'view' || (!canOperateArm && canViewArm)
    )
    const allowTransferView = canTransferInOnlineChatView(roles)
    const viewerName = employeeDisplayName(auth.username, roles)
    const viewerTitle = jobTitleFromRoles(roles)
    const armRole = simOperate
      ? 'operator' as const
      : canAdmin
        ? 'admin' as const
        : canSupervisor
          ? 'supervisor' as const
          : 'operator' as const

    // «Чаты» = own ARM. Operator observation lives under /online-chat/operators.
    const operateHref = simOperate
      ? `/online-chat?mode=operate&operator=${encodeURIComponent(operatorFromQuery)}`
      : '/online-chat'
    const viewingOperatorArm =
      forcedView && Boolean(operatorFromQuery) && isOperatorsRoute

    const shellProps = {
      currentPath: route,
      displayName: simOperate
        ? operatorFromQuery
        : viewingOperatorArm
          ? `Просмотр · ${operatorFromQuery}`
          : viewerName,
      jobTitle: simOperate
        ? 'Оператор онлайн-чата · симулятор'
        : viewingOperatorArm
          ? `${viewerTitle} · режим просмотра`
          : viewerTitle,
      // Admins manage the line but do not operate dialogs — hide «Чаты».
      showArm: simOperate
        ? true
        : (canOperateArm || canSupervisor) && !canAdmin,
      showOperators: simOperate ? false : (canSupervisor || canAdmin),
      showSupervisor: simOperate ? false : canSupervisor,
      showAdmin: simOperate ? false : canAdmin,
      showSimulator: simOperate ? false : showSimulator,
      armNavLabel: 'Чаты',
      armHref: operateHref,
      operatorsHref: '/online-chat/operators',
      themeKind: chatThemeKind,
      onToggleTheme: () =>
        setChatThemeKind((kind) => (kind === 'light' ? 'dark' : 'light')),
      // Hamburger is part of АРМ for every role on /online-chat (picker + operate + view).
      showMenuButton: route === '/online-chat' || route === '/online-chat/operators',
      menuOpen: armMenuOpen,
      onMenuToggle: () => setArmMenuOpen((open) => !open),
    }
    if (isSupervisorRoute) {
      return (
        <ChatPlatformShellWithAvatar {...shellProps} showMenuButton={false}>
          <SupervisorApp demoMode={import.meta.env.DEV || import.meta.env.VITE_SUFLER_DEMO === '1'} />
        </ChatPlatformShellWithAvatar>
      )
    }
    if (isOperatorsRoute) {
      // Viewing a specific operator ARM stays on the Operators tab.
      if (forcedView && operatorFromQuery) {
        return (
          <ChatPlatformShellWithAvatar {...shellProps}>
            <ChatArmApp
              demoMode={import.meta.env.VITE_SUFLER_DEMO === '1'}
              operatorName={operatorFromQuery}
              actorName={viewerName}
              themeKind={chatThemeKind}
              statsDrawerOpen={armMenuOpen}
              onStatsDrawerOpenChange={setArmMenuOpen}
              armRole={armRole}
              viewOnly
              allowTransferInView={allowTransferView}
            />
          </ChatPlatformShellWithAvatar>
        )
      }
      return (
        <ChatPlatformShellWithAvatar {...shellProps}>
          <ArmMenuHost
            open={armMenuOpen}
            onOpenChange={setArmMenuOpen}
            armRole={armRole}
            menuContext="picker"
            themeKind={chatThemeKind}
            operatorName={viewerName}
          >
            <OperatorPicker allowTransfer={allowTransferView} />
          </ArmMenuHost>
        </ChatPlatformShellWithAvatar>
      )
    }
    if (isAdminRoute) {
      return (
        <ChatPlatformShellWithAvatar {...shellProps} showMenuButton={false}>
          <ChatAdminApp />
        </ChatPlatformShellWithAvatar>
      )
    }
    if (isSimulatorRoute) {
      return (
        <ChatPlatformShellWithAvatar {...shellProps} showMenuButton={false}>
          <ChatSimulatorApp />
        </ChatPlatformShellWithAvatar>
      )
    }

    // Module admin: no operator ARM — send to management / operators list.
    if (canAdmin && !canOperateArm && !simOperate && !forcedView) {
      window.location.replace('/online-chat/admin')
      return null
    }

    if (forcedView && !operatorFromQuery) {
      if (canAdmin && !canSupervisor) {
        window.location.replace('/online-chat/admin')
        return null
      }
      return (
        <ChatPlatformShellWithAvatar {...shellProps}>
          <ArmMenuHost
            open={armMenuOpen}
            onOpenChange={setArmMenuOpen}
            armRole={armRole}
            menuContext="picker"
            themeKind={chatThemeKind}
            operatorName={viewerName}
          >
            <OperatorPicker allowTransfer={allowTransferView} />
          </ArmMenuHost>
        </ChatPlatformShellWithAvatar>
      )
    }

    // Legacy: /online-chat?mode=view&operator=… → Operators tab.
    if (forcedView && operatorFromQuery && !simOperate) {
      const next = new URLSearchParams(params)
      next.set('mode', 'view')
      next.set('operator', operatorFromQuery)
      window.location.replace(`/online-chat/operators?${next.toString()}`)
      return null
    }

    return (
      <ChatPlatformShellWithAvatar {...shellProps}>
        <ChatArmApp
          demoMode={import.meta.env.VITE_SUFLER_DEMO === '1'}
          operatorName={simOperate ? operatorFromQuery : viewerName}
          actorName={simOperate ? operatorFromQuery : viewerName}
          themeKind={chatThemeKind}
          statsDrawerOpen={armMenuOpen}
          onStatsDrawerOpenChange={setArmMenuOpen}
          armRole={armRole}
          viewOnly={false}
          allowTransferInView={false}
        />
      </ChatPlatformShellWithAvatar>
    )
  }

  if (
    route === '/internal-kc'
    || route.startsWith('/internal-kc/')
    || route === '/ai-hub/internal-kc'
    || route.startsWith('/ai-hub/internal-kc/')
  ) {
    if (!canAccessInternalKc(auth.roles)) {
      return (
        <main className="standalone-module standalone-module--denied">
          <Card>
            <StatusBadge status="danger">403</StatusBadge>
            <h1>Нет доступа к тест-диалогу КЦ</h1>
            <p>Требуется роль внутреннего пользователя Контакт-центра (cc.test_dialog.use).</p>
            <Button onClick={() => window.location.assign('/')}>Вернуться на портал</Button>
          </Card>
        </main>
      )
    }
    return (
      <InternalKcDialogApp
        username={auth.username ?? undefined}
        demoMode={import.meta.env.VITE_SUFLER_DEMO === '1' || import.meta.env.DEV}
      />
    )
  }

  if (route === '/ai-hub') {
    return <AiHubPortalHost username={auth.username} />
  }

  if (route === '/ai-hub/admin' || route.startsWith('/ai-hub/admin/')) {
    if (!isAdminCenterRole(auth.roles)) {
      return (
        <main className="standalone-module standalone-module--denied">
          <Card>
            <StatusBadge status="danger">403</StatusBadge>
            <h1>Нет доступа к Центру настроек</h1>
            <p>
              Нужна админ-роль I.4 (п.1–3, 8, 11) или аналитик с отчётностью
              (п.7 КЦ / п.10 ассистент / п.13 OCR).
            </p>
            <Button onClick={() => window.location.assign('/')}>Вернуться на портал</Button>
          </Card>
        </main>
      )
    }
    return (
      <AiHubAdminApp
        roles={auth.roles}
        demoRoleSwitcher={
          import.meta.env.DEV
          && !auth.roles.includes('software_administrator')
        }
      />
    )
  }

  if (
    route === '/ai-hub/reports'
    || route.startsWith('/ai-hub/reports/')
    || route === '/admin/reports'
    || route.startsWith('/admin/reports/')
  ) {
    if (!canAccessCcReports(auth.roles)) {
      return (
        <main className="standalone-module standalone-module--denied">
          <Card>
            <StatusBadge status="danger">403</StatusBadge>
            <h1>Нет доступа к отчётности КЦ</h1>
            <p>Требуется роль аналитика Контакт-центра (cc.reports.view).</p>
            <Button onClick={() => window.location.assign('/')}>Вернуться на портал</Button>
          </Card>
        </main>
      )
    }
    const section = route.includes('/asr')
      ? 'asr-qa' as const
      : route.includes('/live')
        ? 'live' as const
        : route.includes('/sufler')
          ? 'sufler' as const
          : 'chat' as const
    return (
      <AiHubReportsApp
        username={auth.username ?? undefined}
        section={section}
      />
    )
  }

  return (
    <div className="portal-route">
      {auth.status === 'unavailable' && (
        <div className="portal-route__auth-status" role="status">
          Launcher скрыт: авторизация недоступна
        </div>
      )}
      {canAccessCcReports(auth.roles) && (
        <div className="portal-route__reports-entry">
          <Card>
            <h2>Отчётность</h2>
            <p className="app-muted">
              Аналитика, оперативная панель, конструктор отчётов и записи разговоров.
            </p>
            <Button onClick={() => window.location.assign('/ai-hub/reports')}>
              Открыть отчёты
            </Button>
            <Button
              variant="ghost"
              onClick={() => window.location.assign('/ai-hub/reports/live')}
            >
              Оперативная панель
            </Button>
            <Button
              variant="ghost"
              onClick={() => window.location.assign('/ai-hub/reports?builder=1')}
            >
              Конструктор
            </Button>
            <Button
              variant="ghost"
              onClick={() => window.location.assign('/ai-hub/reports/asr')}
            >
              Записи разговоров
            </Button>
          </Card>
        </div>
      )}
      {canAccessInternalKc(auth.roles) && (
        <div className="portal-route__reports-entry">
          <Card>
            <StatusBadge status="info">II.3.5.5 · II-KC</StatusBadge>
            <h2>Тест-диалог внутреннего пользователя КЦ</h2>
            <p className="app-muted">
              Проверка промптов и сценариев без клиентского канала: ответ LLM и % релевантности.
            </p>
            <Button onClick={() => window.location.assign('/internal-kc')}>
              Открыть тест-диалог
            </Button>
          </Card>
        </div>
      )}
      <PortalLauncher roles={auth.roles} />
    </div>
  )
}

export default App
