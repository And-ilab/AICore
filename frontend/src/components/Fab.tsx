import { forwardRef, type ButtonHTMLAttributes } from 'react'
import './components.css'

export interface FabProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  badge?: string | number
}

export const Fab = forwardRef<HTMLButtonElement, FabProps>(
  ({ badge, children, className = '', type = 'button', ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={`ui-fab ${className}`.trim()}
      {...props}
    >
      {children}
      {badge !== undefined && <span className="ui-fab__badge">{badge}</span>}
    </button>
  ),
)

Fab.displayName = 'Fab'
