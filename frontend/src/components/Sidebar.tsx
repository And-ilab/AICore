import { forwardRef, type HTMLAttributes } from 'react'
import './components.css'

export interface SidebarItem {
  label: string
  href: string
  active?: boolean
}

export interface SidebarProps extends HTMLAttributes<HTMLElement> {
  items: SidebarItem[]
  logoSrc?: string
  logoAlt?: string
}

export const Sidebar = forwardRef<HTMLElement, SidebarProps>(
  (
    {
      items,
      logoSrc = '/assets/belarusbank-logo.png',
      logoAlt = 'Беларусбанк',
      className = '',
      ...props
    },
    ref,
  ) => (
    <aside ref={ref} className={`ui-sidebar ${className}`.trim()} {...props}>
      <img className="ui-sidebar__logo" src={logoSrc} alt={logoAlt} />
      <nav className="ui-sidebar__nav" aria-label="Основная навигация">
        {items.map((item) => (
          <a
            key={`${item.href}-${item.label}`}
            className="ui-sidebar__link"
            href={item.href}
            aria-current={item.active ? 'page' : undefined}
          >
            {item.label}
          </a>
        ))}
      </nav>
    </aside>
  ),
)

Sidebar.displayName = 'Sidebar'
