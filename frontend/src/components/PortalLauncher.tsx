import {
  useMemo,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react'
import {
  useAiHubColorTheme,
  type AiHubColorTheme,
} from '../ai-hub/colorTheme'
import { AssistantChat } from '../assistant/AssistantChat'
import { LiveSuflerPhoneApp } from '../sufler/LiveSuflerPhoneApp'
import { Button } from './Button'
import { Card } from './Card'
import { Fab } from './Fab'
import { StatusBadge } from './StatusBadge'
import { storeDemoRole } from '../auth/demoRoles'
import {
  canWriteAssistantChat,
  getAllowedLauncherModules,
  getSettingsMenuEntry,
  showPortalSettingsButton,
  type LauncherModule,
  type SettingsMenuEntry,
} from './portalLauncherAccess'
import './PortalLauncher.css'

export type { LauncherModule }

export interface PortalLauncherProps {
  roles: readonly string[]
  username?: string | null
  roleLabel?: string | null
  menuVariant?: 'card' | 'compact'
  initialMenuOpen?: boolean
  initialWindows?: readonly LauncherModule[]
  onOpenModule?: (module: LauncherModule) => void
  onChangeRole?: () => void
  children?: ReactNode
}

const MODULE_LABELS: Record<LauncherModule, string> = {
  sufler: 'Суфлёр',
  assistant: 'Ассистент',
  online_chat: 'Онлайн-чат',
}

const MODULE_GLYPH: Record<LauncherModule, string> = {
  sufler: 'S',
  assistant: 'A',
  online_chat: 'C',
}

function ModuleGlyph({ module }: { module: LauncherModule }) {
  return (
    <span className={`portal-launcher__glyph portal-launcher__glyph--${module}`}>
      {MODULE_GLYPH[module]}
    </span>
  )
}

interface ModuleWindowProps {
  module: LauncherModule
  username?: string | null
  roleLabel?: string | null
  roles?: readonly string[]
  settingsEntry?: SettingsMenuEntry | null
  colorTheme?: AiHubColorTheme
  tiled?: boolean
  onClose: () => void
  onMinimize: () => void
}

function clampWindowSize(width: number, height: number) {
  const maxWidth = Math.max(320, window.innerWidth - 48)
  const maxHeight = Math.max(280, window.innerHeight - 120)
  return {
    width: Math.min(maxWidth, Math.max(360, width)),
    height: Math.min(maxHeight, Math.max(420, height)),
  }
}

function clampWindowPosition(left: number, top: number, width: number, _height: number) {
  const maxLeft = Math.max(0, window.innerWidth - Math.min(width, 80))
  const maxTop = Math.max(0, window.innerHeight - 48)
  return {
    left: Math.min(maxLeft, Math.max(0, left)),
    top: Math.min(maxTop, Math.max(0, top)),
  }
}

type ResizeEdge = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

const RESIZE_EDGES: ResizeEdge[] = ['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw']

function ModuleWindow({
  module,
  username,
  roleLabel,
  roles = [],
  settingsEntry = null,
  colorTheme = 'classic',
  tiled = false,
  onClose,
  onMinimize,
}: ModuleWindowProps) {
  const initialSize =
    module === 'sufler'
      ? { width: 960, height: 580 }
      : { width: 720, height: 720 }
  const [size, setSize] = useState(initialSize)
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null)
  const [maximized, setMaximized] = useState(false)
  const [dragging, setDragging] = useState(false)

  const resizeBy = (widthDelta: number, heightDelta: number) => {
    if (maximized) return
    setSize((current) => clampWindowSize(current.width + widthDelta, current.height + heightDelta))
  }

  const bindPointerDrag = (
    event: ReactPointerEvent<HTMLElement>,
    onMove: (moveEvent: PointerEvent) => void,
  ) => {
    event.preventDefault()
    const handle = event.currentTarget
    handle.setPointerCapture(event.pointerId)
    const onPointerUp = () => {
      handle.removeEventListener('pointermove', onMove)
      handle.removeEventListener('pointerup', onPointerUp)
      setDragging(false)
    }
    handle.addEventListener('pointermove', onMove)
    handle.addEventListener('pointerup', onPointerUp)
  }

  const startEdgeResize = (edge: ResizeEdge) => (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (maximized || tiled) return
    event.stopPropagation()
    const frame = event.currentTarget.closest('.portal-module-window')
    if (!(frame instanceof HTMLElement)) return
    const rect = frame.getBoundingClientRect()
    const startX = event.clientX
    const startY = event.clientY
    const startSize = { width: rect.width, height: rect.height }
    const startPos = { left: rect.left, top: rect.top }
    setDragging(true)
    bindPointerDrag(event, (moveEvent) => {
      const dx = moveEvent.clientX - startX
      const dy = moveEvent.clientY - startY
      let width = startSize.width
      let height = startSize.height
      let left = startPos.left
      let top = startPos.top
      if (edge.includes('e')) width = startSize.width + dx
      if (edge.includes('s')) height = startSize.height + dy
      if (edge.includes('w')) width = startSize.width - dx
      if (edge.includes('n')) height = startSize.height - dy
      const nextSize = clampWindowSize(width, height)
      if (edge.includes('w')) left = startPos.left + (startSize.width - nextSize.width)
      if (edge.includes('n')) top = startPos.top + (startSize.height - nextSize.height)
      setSize(nextSize)
      setPosition(clampWindowPosition(left, top, nextSize.width, nextSize.height))
    })
  }

  const startMove = (event: ReactPointerEvent<HTMLElement>) => {
    if (maximized || tiled) return
    if ((event.target as HTMLElement).closest('.portal-module-window__controls')) return
    const frame = event.currentTarget.closest('.portal-module-window')
    if (!(frame instanceof HTMLElement)) return
    const rect = frame.getBoundingClientRect()
    const startX = event.clientX
    const startY = event.clientY
    const startLeft = rect.left
    const startTop = rect.top
    setDragging(true)
    bindPointerDrag(event, (moveEvent) => {
      setPosition(clampWindowPosition(
        startLeft + moveEvent.clientX - startX,
        startTop + moveEvent.clientY - startY,
        size.width,
        size.height,
      ))
    })
  }

  const title =
    module === 'sufler' ? 'Суфлёр · активный звонок' : 'Беларусбанк AI'
  const subtitle =
    module === 'sufler'
      ? `Консультация · ${username || 'Оператор КЦ'}`
      : `${username || 'Пользователь'} · ${roleLabel || 'Пользователь ИИ-ассистента'}`
  const popOutTitle = `Открыть отдельно`
  const maximizeTitle = maximized ? 'Восстановить' : 'На весь экран'

  return (
    <section
      className={`portal-module-window portal-module-window--${module}${
        maximized ? ' portal-module-window--maximized' : ''
      }${tiled && !maximized ? ' portal-module-window--tiled' : ''}${
        position && !maximized && !tiled ? ' portal-module-window--moved' : ''
      }${
        dragging ? ' is-dragging' : ''
      }`}
      style={
        maximized || tiled
          ? undefined
          : {
              width: `${size.width}px`,
              height: `${size.height}px`,
              ...(position
                ? { left: `${position.left}px`, top: `${position.top}px` }
                : {}),
            }
      }
      role="dialog"
      aria-label={title}
      data-testid={`${module}-window`}
      data-ai-color-theme={colorTheme}
    >
      <header
        className="portal-module-window__header"
        onPointerDown={startMove}
      >
        <div className="portal-module-window__identity">
          <ModuleGlyph module={module} />
          <div>
            <strong>{title}</strong>
            <span>{subtitle}</span>
          </div>
        </div>
        <div className="portal-module-window__controls">
          {settingsEntry && (
            <a
              href={settingsEntry.href}
              className="portal-module-window__settings"
              aria-label={settingsEntry.label}
              title={settingsEntry.label}
              data-testid="admin-center-gear"
            >
              ≡
            </a>
          )}
          <a
            href={`/${module}`}
            aria-label={popOutTitle}
            title={popOutTitle}
          >
            ↗
          </a>
          <button
            type="button"
            onClick={onMinimize}
            aria-label="Свернуть"
            title="Свернуть"
          >
            —
          </button>
          <button
            type="button"
            onClick={() => setMaximized((value) => !value)}
            aria-label={maximizeTitle}
            title={maximizeTitle}
            data-testid={`${module}-maximize`}
          >
            {maximized ? '❐' : '□'}
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            title="Закрыть"
          >
            ×
          </button>
        </div>
      </header>

      {module === 'sufler' ? (
        <div className="portal-module-window__body portal-module-window__body--sufler-app">
          <LiveSuflerPhoneApp
            embedded
            operatorName={username || 'Иванова М.П.'}
          />
        </div>
      ) : (
        <AssistantWindowContent
          username={username}
          roleLabel={roleLabel}
          readOnly={!canWriteAssistantChat(roles)}
        />
      )}

      {!maximized && !tiled
        ? RESIZE_EDGES.map((edge) => (
            <button
              key={edge}
              type="button"
              className={`portal-module-window__edge portal-module-window__edge--${edge}`}
              onPointerDown={startEdgeResize(edge)}
              onKeyDown={
                edge === 'se'
                  ? (event) => {
                      if (event.key.startsWith('Arrow')) event.preventDefault()
                      const delta = event.shiftKey ? 40 : 10
                      if (event.key === 'ArrowRight') resizeBy(delta, 0)
                      if (event.key === 'ArrowLeft') resizeBy(-delta, 0)
                      if (event.key === 'ArrowDown') resizeBy(0, delta)
                      if (event.key === 'ArrowUp') resizeBy(0, -delta)
                    }
                  : undefined
              }
              aria-label={`Изменить размер окна ${MODULE_LABELS[module]}`}
              title="Потяните за край, чтобы изменить размер"
            />
          ))
        : null}
    </section>
  )
}

function AssistantWindowContent({
  readOnly = false,
}: {
  username?: string | null
  roleLabel?: string | null
  readOnly?: boolean
}) {
  return (
    <div className="portal-module-window__body portal-module-window__body--assistant">
      <div className="portal-assistant-chat-host">
        <AssistantChat compact readOnly={readOnly} />
      </div>
    </div>
  )
}

function PortalBackdrop({
  children,
  roleLabel,
  onChangeRole,
  settingsEntry,
  colorTheme,
  onToggleColorTheme,
}: {
  children: ReactNode
  roleLabel?: string | null
  onChangeRole?: () => void
  /** ≡ on portal chrome for roles without S/A windows (analysts / OCR admin). */
  settingsEntry?: SettingsMenuEntry | null
  colorTheme: AiHubColorTheme
  onToggleColorTheme: () => void
}) {
  const colorThemeTitle =
    colorTheme === 'classic'
      ? 'Переключить на цветовую схему онлайн-чата'
      : 'Вернуть текущую цветовую схему'
  return (
    <div className="portal-launcher__backdrop" data-ai-color-theme={colorTheme}>
      <header className="portal-launcher__portal-header">
        <img src="/assets/belarusbank-logo.png" alt="Беларусбанк" />
        <nav aria-label="Навигация корпоративного портала">
          <a href="#home">Главная</a>
          <a href="#requests">Заявки</a>
          <a href="#knowledge">База знаний</a>
          <a href="#contact-center">Контакт-центр</a>
        </nav>
        <div className="portal-launcher__portal-user">
          {settingsEntry && (
            <a
              href={settingsEntry.href}
              className="portal-launcher__settings-btn"
              aria-label={settingsEntry.label}
              title={settingsEntry.label}
              data-testid="admin-center-gear"
            >
              ≡
            </a>
          )}
          {roleLabel && (
            <button
              type="button"
              className="portal-launcher__role-chip"
              onClick={onChangeRole}
              data-testid="change-role-button"
            >
              Роль: {roleLabel}
            </button>
          )}
          <button
            type="button"
            className={`portal-launcher__color-toggle${
              colorTheme === 'emerald' ? ' is-emerald' : ''
            }`}
            onClick={onToggleColorTheme}
            title={colorThemeTitle}
            aria-label={colorThemeTitle}
            aria-pressed={colorTheme === 'emerald'}
            data-testid="ai-color-theme-toggle"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
              <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
              <path
                d="M12 3a9 9 0 0 1 0 18"
                fill="currentColor"
                opacity="0.35"
              />
            </svg>
          </button>
          <span>Алексей Морозов</span>
        </div>
      </header>
      <main className="portal-launcher__portal-content">
        <p className="portal-launcher__portal-eyebrow">
          Внутренний корпоративный портал банка · компактная кнопка AI, по клику выезжают иконки модулей
        </p>
        <h1>Добрый день, Алексей</h1>
        <div className="portal-launcher__portal-grid" aria-hidden="true">
          <Card><span>Мои задачи</span><strong>8</strong></Card>
          <Card><span>Новые заявки</span><strong>3</strong></Card>
          <Card><span>Обновления базы знаний</span><strong>12</strong></Card>
        </div>
      </main>
      {children}
    </div>
  )
}

export function PortalLauncher({
  roles,
  username = null,
  roleLabel = null,
  menuVariant = 'card',
  initialMenuOpen = false,
  initialWindows = [],
  onOpenModule,
  onChangeRole,
  children,
}: PortalLauncherProps) {
  const modules = useMemo(
    () => getAllowedLauncherModules(roles),
    [roles],
  )
  const settingsEntry = useMemo(() => getSettingsMenuEntry(roles), [roles])
  const portalSettingsEntry = useMemo(
    () => (showPortalSettingsButton(roles) ? settingsEntry : null),
    [roles, settingsEntry],
  )
  const { theme: colorTheme, toggle: toggleColorTheme } = useAiHubColorTheme()
  const [menuOpen, setMenuOpen] = useState(initialMenuOpen)
  const [openWindows, setOpenWindows] = useState<Set<LauncherModule>>(
    () => new Set(initialWindows.filter((module) => modules.includes(module))),
  )

  const openModule = (module: LauncherModule) => {
    if (module === 'online_chat') {
      const activeRole = roles[0]
      if (activeRole) storeDemoRole(activeRole)
      const qs = activeRole ? `?demo_role=${encodeURIComponent(activeRole)}` : ''
      window.location.assign(`/online-chat${qs}`)
      onOpenModule?.(module)
      return
    }
    setOpenWindows((current) => new Set(current).add(module))
    setMenuOpen(false)
    onOpenModule?.(module)
  }

  const closeModule = (module: LauncherModule) => {
    setOpenWindows((current) => {
      const next = new Set(current)
      next.delete(module)
      return next
    })
  }

  const handleFabClick = () => {
    setMenuOpen((value) => !value)
  }

  return (
    <PortalBackdrop
      roleLabel={roleLabel}
      onChangeRole={onChangeRole}
      settingsEntry={portalSettingsEntry}
      colorTheme={colorTheme}
      onToggleColorTheme={toggleColorTheme}
    >
      {children}

      {openWindows.size > 0 && (
        <div
          className={`portal-module-desktop${
            openWindows.size > 1 ? ' portal-module-desktop--tiled' : ''
          }`}
          data-testid="portal-module-desktop"
        >
          {openWindows.has('sufler') && (
            <ModuleWindow
              module="sufler"
              username={username}
              roleLabel={roleLabel}
              roles={roles}
              settingsEntry={settingsEntry}
              colorTheme={colorTheme}
              tiled={openWindows.size > 1}
              onClose={() => closeModule('sufler')}
              onMinimize={() => closeModule('sufler')}
            />
          )}
          {openWindows.has('assistant') && (
            <ModuleWindow
              module="assistant"
              username={username}
              roleLabel={roleLabel}
              roles={roles}
              settingsEntry={settingsEntry}
              colorTheme={colorTheme}
              tiled={openWindows.size > 1}
              onClose={() => closeModule('assistant')}
              onMinimize={() => closeModule('assistant')}
            />
          )}
        </div>
      )}

      {modules.length > 0 && menuVariant === 'card' && menuOpen && (
        <Card
          className="portal-launcher__menu"
          role="menu"
          aria-label="Выбрать модуль"
          id="portal-launcher-menu"
          data-testid="launcher-menu"
        >
          <div className="portal-launcher__menu-heading">
            <strong>Выбрать модуль</strong>
            <span>Откроется отдельное стартовое окно</span>
          </div>
          <div className="portal-launcher__menu-options">
            {modules.map((module) => (
              <button
                type="button"
                role="menuitem"
                key={module}
                onClick={() => openModule(module)}
              >
                <ModuleGlyph module={module} />
                <span>
                  <strong>{MODULE_LABELS[module]}</strong>
                  <small>{openWindows.has(module) ? 'Уже открыт' : 'Открыть окно'}</small>
                </span>
              </button>
            ))}
          </div>
        </Card>
      )}

      {modules.length > 0 && (
        <div
          className={`portal-launcher__fab portal-launcher__fab--${menuVariant}${
            menuOpen && menuVariant === 'compact' ? ' is-expanded' : ''
          }`}
        >
          {menuVariant === 'compact' && menuOpen && (
            <div
              className="portal-launcher__compact-rail"
              role="menu"
              aria-label="Модули AI"
              id="portal-launcher-menu"
              data-testid="launcher-menu"
            >
              {modules.map((module) => (
                <button
                  key={module}
                  type="button"
                  role="menuitem"
                  className={`portal-launcher__compact-item${
                    openWindows.has(module) ? ' is-active' : ''
                  }`}
                  onClick={() => openModule(module)}
                  title={MODULE_LABELS[module]}
                  data-testid={`launcher-module-${module}`}
                >
                  <span className="portal-launcher__compact-label">
                    {MODULE_LABELS[module]}
                  </span>
                  <span className="portal-launcher__compact-icon" aria-hidden="true">
                    <span>{MODULE_GLYPH[module]}</span>
                  </span>
                </button>
              ))}
            </div>
          )}

          <Fab
            aria-label="Открыть меню Суфлёр и Ассистент"
            aria-expanded={menuOpen}
            aria-controls="portal-launcher-menu"
            badge={menuVariant === 'card' ? modules.length : undefined}
            onClick={handleFabClick}
            data-testid="launcher-button"
            className={menuOpen ? 'is-open' : undefined}
          >
            <span aria-hidden="true">AI</span>
          </Fab>
        </div>
      )}

      {modules.length === 0 && (
        <div className="portal-launcher__empty-modules" role="status">
          <Card>
            <StatusBadge status={settingsEntry ? 'info' : 'warning'}>
              {settingsEntry?.kind === 'reports' ? 'Отчётность I.4' : 'Нет модулей S/A'}
            </StatusBadge>
            <p>
              {settingsEntry
                ? `У роли нет окон Суфлёр/Ассистент. Доступ: «${settingsEntry.label}» через ≡ или кнопку ниже.`
                : 'У выбранной роли нет доступа к Суфлёру и Ассистенту. Выберите другую роль по матрице I.4.'}
            </p>
            {settingsEntry && (
              <Button
                onClick={() => window.location.assign(settingsEntry.href)}
                data-testid="admin-center-link"
              >
                {settingsEntry.label}
              </Button>
            )}
            {onChangeRole && (
              <Button variant="ghost" onClick={onChangeRole}>Сменить роль</Button>
            )}
          </Card>
        </div>
      )}
    </PortalBackdrop>
  )
}
