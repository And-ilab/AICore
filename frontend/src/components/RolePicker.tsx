import { useMemo } from 'react'
import { DEMO_ROLE_CATALOG, type DemoRoleDefinition } from '../auth/demoRoles'
import {
  getAllowedLauncherModules,
  getSettingsMenuEntry,
  type LauncherModule,
} from './portalLauncherAccess'
import { Card } from './Card'
import { StatusBadge } from './StatusBadge'
import './RolePicker.css'

export interface RolePickerProps {
  selectedCode?: string | null
  onSelect: (role: DemoRoleDefinition) => void
  title?: string
  subtitle?: string
}

const MODULE_BADGE: Record<LauncherModule, string> = {
  sufler: 'Суфлёр',
  assistant: 'Ассистент',
  online_chat: 'Онлайн-чат',
}

export function RolePicker({
  selectedCode = null,
  onSelect,
  title = 'Выбор тестовой роли',
  subtitle = 'Матрица ролей I.4 · Суфлёр / Ассистент / Онлайн-чат / настройки',
}: RolePickerProps) {
  const groups = useMemo(() => {
    const map = new Map<string, DemoRoleDefinition[]>()
    for (const role of DEMO_ROLE_CATALOG) {
      const list = map.get(role.group) ?? []
      list.push(role)
      map.set(role.group, list)
    }
    return [...map.entries()]
  }, [])

  return (
    <div className="role-picker" data-testid="role-picker" role="dialog" aria-label={title}>
      <Card className="role-picker__card">
        <header className="role-picker__header">
          <StatusBadge status="info">I.4 · демо</StatusBadge>
          <h1>{title}</h1>
          <p>{subtitle}</p>
        </header>

        <div className="role-picker__groups">
          {groups.map(([group, roles]) => (
            <section key={group} className="role-picker__group">
              <h2>{group}</h2>
              <ul className="role-picker__list">
                {roles.map((role) => {
                  const modules = getAllowedLauncherModules([role.code])
                  const settings = getSettingsMenuEntry([role.code])
                  const selected = selectedCode === role.code
                  return (
                    <li key={role.code}>
                      <button
                        type="button"
                        className={`role-picker__option${selected ? ' is-selected' : ''}`}
                        onClick={() => onSelect(role)}
                        aria-pressed={selected}
                        data-testid={`role-option-${role.code}`}
                      >
                        <span className="role-picker__option-main">
                          <span className="role-picker__num">{role.number}</span>
                          <span className="role-picker__label">{role.label}</span>
                        </span>
                        <span className="role-picker__modules" aria-label="Доступные модули">
                          {modules.map((module) => (
                            <span
                              key={module}
                              className={`role-picker__module role-picker__module--${module}`}
                            >
                              {MODULE_BADGE[module]}
                            </span>
                          ))}
                          {settings && (
                            <span
                              className={`role-picker__module role-picker__module--${
                                settings.kind === 'reports' ? 'reports' : 'settings'
                              }`}
                            >
                              {settings.kind === 'reports' ? 'Отчёты' : 'Настройки'}
                            </span>
                          )}
                          {modules.length === 0 && !settings && (
                            <span className="role-picker__module role-picker__module--none">нет S/A</span>
                          )}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
      </Card>
    </div>
  )
}
