import { forwardRef, type HTMLAttributes } from 'react'
import './components.css'

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  padded?: boolean
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ padded = true, className = '', ...props }, ref) => (
    <div
      ref={ref}
      className={`ui-card ${padded ? 'ui-card--padded' : ''} ${className}`.trim()}
      {...props}
    />
  ),
)

Card.displayName = 'Card'
