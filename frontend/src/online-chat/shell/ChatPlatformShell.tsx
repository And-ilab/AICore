import type { CSSProperties, ReactNode } from 'react'
import { ARM_THEME_DARK, ARM_THEME_LIGHT, type ThemeKind } from '../arm/theme'
import './ChatPlatformShell.css'

interface ChatPlatformShellProps {
  children: ReactNode
  currentPath: string
  displayName?: string | null
  jobTitle?: string | null
  showArm?: boolean
  showOperators?: boolean
  showSupervisor?: boolean
  showAdmin?: boolean
  showSimulator?: boolean
  /** Nav label for /online-chat: «Чаты». */
  armNavLabel?: string
  /** Keep simulator operate session when clicking brand / «Чаты». */
  armHref?: string
  operatorsHref?: string
  themeKind?: ThemeKind
  onToggleTheme?: () => void
  showMenuButton?: boolean
  menuOpen?: boolean
  onMenuToggle?: () => void
  photoUrl?: string | null
  onPhotoChange?: (dataUrl: string) => void
  photoError?: string | null
}

export function ChatPlatformShell({
  children,
  currentPath,
  displayName,
  jobTitle,
  showArm = true,
  showOperators = false,
  showSupervisor = false,
  showAdmin = false,
  showSimulator = false,
  armNavLabel = 'Чаты',
  armHref = '/online-chat',
  operatorsHref = '/online-chat/operators',
  themeKind = 'light',
  onToggleTheme,
  showMenuButton = false,
  menuOpen = false,
  onMenuToggle,
  photoUrl,
  onPhotoChange,
  photoError,
}: ChatPlatformShellProps) {
  const routes = [
    { href: armHref, label: armNavLabel, access: 'arm' as const },
    { href: operatorsHref, label: 'Операторы', access: 'operators' as const },
    { href: '/online-chat/supervisor', label: 'Супервизор', access: 'supervisor' as const },
    { href: '/online-chat/admin', label: 'Управление', access: 'admin' as const },
    {
      href: '/online-chat/simulator',
      label: 'Симулятор',
      access: 'simulator' as const,
      testOnly: true,
    },
  ]
  const t = themeKind === 'light' ? ARM_THEME_LIGHT : ARM_THEME_DARK
  const style = {
    '--arm-accent': t.accent.primary,
    '--arm-accent-control': t.accent.control,
    '--arm-accent-weak': t.fill.tertiary,
    '--arm-header-bg': '#006b3c',
    '--arm-panel-bg': t.fill.secondary,
    '--arm-on-accent': t.text.onAccent,
    '--arm-fill-secondary': t.fill.secondary,
    '--arm-fill-tertiary': t.fill.tertiary,
    '--arm-fill-quaternary': t.fill.quaternary,
    '--arm-stroke-secondary': t.stroke.secondary,
    '--arm-stroke-tertiary': t.stroke.tertiary,
    '--arm-t-primary': t.text.primary,
    '--arm-t-secondary': t.text.secondary,
    '--arm-t-tertiary': t.text.tertiary,
    '--arm-bg-elevated': t.bg.elevated,
    '--arm-bg-editor': t.bg.editor,
  } as CSSProperties

  const visible = (access: (typeof routes)[number]['access']) =>
    (access === 'arm' && showArm)
    || (access === 'operators' && showOperators)
    || (access === 'supervisor' && showSupervisor)
    || (access === 'admin' && showAdmin)
    || (access === 'simulator' && showSimulator)

  const userLine = [displayName, jobTitle].filter(Boolean).join(' · ')

  return (
    <div className="chat-platform-shell" style={style} data-theme={themeKind}>
      <header className="chat-platform-shell__header">
        <div className="chat-platform-shell__lead">
          {showMenuButton && (
            <button
              type="button"
              className={`chat-platform-shell__menu${menuOpen ? ' is-open' : ''}`}
              aria-expanded={menuOpen}
              aria-label={menuOpen ? 'Скрыть меню' : 'Открыть меню'}
              title={menuOpen ? 'Скрыть меню' : 'Меню'}
              onClick={onMenuToggle}
            >
              <span aria-hidden="true" />
              <span aria-hidden="true" />
              <span aria-hidden="true" />
            </button>
          )}
          <a className="chat-platform-shell__brand" href={armHref} aria-label="Онлайн-чат — главная">
            <img
              className="chat-platform-shell__mark"
              src="/assets/belarusbank-logo.png"
              alt="Беларусбанк"
            />
            <span>
              <strong>Онлайн-чат</strong>
              <small>Беларусбанк</small>
            </span>
          </a>
          {onToggleTheme && (
            <button
              type="button"
              className="chat-platform-shell__theme"
              title={themeKind === 'light' ? 'Включить тёмную тему' : 'Включить светлую тему'}
              aria-label={themeKind === 'light' ? 'Тёмная тема' : 'Светлая тема'}
              onClick={onToggleTheme}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
                <circle cx="12" cy="12" r="4.2" stroke="currentColor" strokeWidth="1.8" />
                <path
                  d="M12 3v1.6M12 19.4V21M4.6 12H3M21 12h-1.6M6.2 6.2l1.1 1.1M16.7 16.7l1.1 1.1M6.2 17.8l1.1-1.1M16.7 7.3l1.1-1.1"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                />
              </svg>
            </button>
          )}
        </div>
        <nav className="chat-platform-shell__nav" aria-label="Разделы онлайн-чата">
          {routes.filter(({ access }) => visible(access)).map((route) => {
            const active = route.access === 'arm'
              ? currentPath === '/online-chat' && !currentPath.endsWith('/operators')
              : currentPath === route.href || (route.access === 'operators' && currentPath === '/online-chat/operators')
            return (
              <a
                key={`${route.access}:${route.href}`}
                href={route.href}
                className={[
                  active ? 'is-active' : '',
                  'testOnly' in route && route.testOnly ? 'is-test-only' : '',
                ].filter(Boolean).join(' ') || undefined}
                aria-current={active ? 'page' : undefined}
                title={'testOnly' in route && route.testOnly ? 'Тестовый раздел (только для проверки)' : undefined}
              >
                <span>{route.label}</span>
                {'testOnly' in route && route.testOnly ? (
                  <span className="chat-platform-shell__test-badge">тест</span>
                ) : null}
              </a>
            )
          })}
        </nav>
        <div className="chat-platform-shell__user" title={userLine || undefined}>
          <label
            className={`chat-platform-shell__avatar${onPhotoChange ? ' is-editable' : ''}`}
            title={onPhotoChange ? 'Загрузить фото' : (displayName || 'Аватар')}
          >
            {photoUrl ? (
              <img src={photoUrl} alt="" />
            ) : (
              <svg viewBox="0 0 40 40" width="36" height="36" aria-hidden>
                <circle cx="20" cy="20" r="20" fill="#ffffff33" />
                <circle cx="20" cy="13" r="9" fill="#ffffffaa" />
                <path d="M3 40c2.2-12 9.5-17.5 17-17.5S34.8 28 37 40" fill="#ffffffaa" />
              </svg>
            )}
            {onPhotoChange ? (
              <input
                type="file"
                accept="image/*"
                aria-label="Загрузить фото аватара"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  const reader = new FileReader()
                  reader.onload = () => onPhotoChange(String(reader.result || ''))
                  reader.readAsDataURL(file)
                }}
              />
            ) : null}
          </label>
          <div className="chat-platform-shell__user-text">
            {displayName && <strong>{displayName}</strong>}
            {jobTitle && <small>{jobTitle}</small>}
            {photoError ? <small className="chat-platform-shell__photo-error">{photoError}</small> : null}
            {!displayName && !jobTitle && 'Пользователь'}
          </div>
        </div>
      </header>
      <div className="chat-platform-shell__content">{children}</div>
    </div>
  )
}
