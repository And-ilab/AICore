import { forwardRef, type HTMLAttributes } from 'react'
import './components.css'

export type StatusBadgeStatus = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

export interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  status?: StatusBadgeStatus
}

export const StatusBadge = forwardRef<HTMLSpanElement, StatusBadgeProps>(
  ({ status = 'neutral', className = '', ...props }, ref) => (
    <span
      ref={ref}
      className={`ui-status ui-status--${status} ${className}`.trim()}
      {...props}
    />
  ),
)

StatusBadge.displayName = 'StatusBadge'
