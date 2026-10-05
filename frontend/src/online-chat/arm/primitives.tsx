import type { CSSProperties, KeyboardEvent, MouseEvent, ReactNode } from 'react'

export function Row({
  children,
  style,
  gap,
  wrap,
}: {
  children?: ReactNode
  style?: CSSProperties
  gap?: number
  wrap?: boolean
}) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'row',
        alignItems: 'center',
        gap: gap ?? style?.gap,
        flexWrap: wrap ? 'wrap' : style?.flexWrap,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function Stack({
  children,
  style,
  gap,
}: {
  children?: ReactNode
  style?: CSSProperties
  gap?: number
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: gap ?? 8, ...style }}>{children}</div>
  )
}

export function Text({
  children,
  style,
  weight,
  tone,
  id,
}: {
  children?: ReactNode
  style?: CSSProperties
  weight?: 'semibold' | 'normal'
  tone?: 'secondary'
  id?: string
}) {
  return (
    <div
      id={id}
      style={{
        display: 'block',
        fontWeight: weight === 'semibold' ? 600 : 400,
        color: tone === 'secondary' ? 'var(--arm-t-secondary)' : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function H3({ children, style }: { children?: ReactNode; style?: CSSProperties }) {
  return <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, ...style }}>{children}</h3>
}

export function Spacer() {
  return <div style={{ flex: 1, minWidth: 8 }} />
}

export function Divider({ style }: { style?: CSSProperties }) {
  return <div style={{ height: 1, background: 'var(--arm-stroke-secondary)', ...style }} />
}

export function Pill({
  children,
  tone = 'neutral',
  size = 'md',
  active,
  onClick,
  title,
}: {
  children?: ReactNode
  tone?: 'info' | 'warning' | 'neutral' | 'success'
  size?: 'sm' | 'md'
  active?: boolean
  onClick?: () => void
  title?: string
}) {
  const tones: Record<string, CSSProperties> = {
    info: { background: '#E3F2FD', color: '#1565C0', borderColor: '#90CAF9' },
    warning: { background: '#FFF3E0', color: '#E65100', borderColor: '#FFCC80' },
    success: { background: '#E8F5E9', color: '#2E7D32', borderColor: '#A5D6A7' },
    neutral: { background: '#ECEFF1', color: '#546E7A', borderColor: '#CFD8DC' },
  }
  const t = tones[tone] ?? tones.neutral
  const Comp = onClick ? 'button' : 'span'
  return (
    <Comp
      type={onClick ? 'button' : undefined}
      title={title}
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: size === 'sm' ? '1px 6px' : '2px 8px',
        borderRadius: 999,
        border: `1px solid ${active ? 'var(--arm-accent)' : t.borderColor}`,
        background: active ? 'var(--arm-accent-control)' : t.background,
        color: active ? 'var(--arm-on-accent)' : t.color,
        fontSize: size === 'sm' ? 10 : 11,
        fontWeight: 600,
        fontFamily: 'inherit',
        cursor: onClick ? 'pointer' : 'default',
        lineHeight: 1.3,
        whiteSpace: 'nowrap',
      }}
    >
      {children}
    </Comp>
  )
}

export function Button({
  children,
  variant = 'primary',
  size,
  style,
  disabled,
  onClick,
  type = 'button',
  title,
}: {
  children?: ReactNode
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm'
  style?: CSSProperties
  disabled?: boolean
  onClick?: (event: MouseEvent<HTMLButtonElement>) => void
  type?: 'button' | 'submit'
  title?: string
}) {
  const base: CSSProperties = {
    fontFamily: 'inherit',
    fontSize: size === 'sm' ? 11 : 13,
    lineHeight: 1.3,
    padding: size === 'sm' ? '4px 10px' : '6px 12px',
    borderRadius: 6,
    border: '1px solid transparent',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.55 : 1,
  }
  const variants: Record<string, CSSProperties> = {
    primary: {
      background: 'var(--arm-accent-control)',
      borderColor: 'var(--arm-accent-control)',
      color: 'var(--arm-on-accent)',
    },
    secondary: {
      background: 'var(--arm-fill-secondary)',
      borderColor: 'var(--arm-stroke-secondary)',
      color: 'var(--arm-t-secondary)',
    },
    ghost: {
      background: 'transparent',
      borderColor: 'transparent',
      color: 'var(--arm-t-secondary)',
    },
  }
  return (
    <button type={type} title={title} disabled={disabled} onClick={onClick} style={{ ...base, ...variants[variant], ...style }}>
      {children}
    </button>
  )
}

export function IconButton({
  children,
  title,
  onClick,
  disabled,
  active,
  'aria-label': ariaLabel,
  style,
}: {
  children?: ReactNode
  title?: string
  onClick?: () => void
  disabled?: boolean
  active?: boolean
  'aria-label'?: string
  style?: CSSProperties
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={ariaLabel ?? title}
      disabled={disabled}
      onClick={onClick}
      style={{
        width: 34,
        height: 34,
        border: `1px solid ${active ? 'var(--arm-accent, #0B6B3A)' : 'var(--arm-stroke-secondary)'}`,
        borderRadius: 8,
        background: active ? 'var(--arm-fill-tertiary, #E7F0EB)' : 'var(--arm-fill-secondary)',
        color: 'var(--arm-t-primary)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.45 : 1,
        fontFamily: 'inherit',
        fontSize: 14,
        lineHeight: 1,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        ...style,
      }}
    >
      {children}
    </button>
  )
}

export function Select({
  value,
  onChange,
  options,
  disabled,
  style,
}: {
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
  style?: CSSProperties
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      style={{
        width: '100%',
        padding: '6px 8px',
        borderRadius: 6,
        border: '1px solid var(--arm-stroke-secondary)',
        background: 'var(--arm-bg-elevated)',
        color: 'var(--arm-t-primary)',
        fontFamily: 'inherit',
        fontSize: 13,
        opacity: disabled ? 0.55 : 1,
        cursor: disabled ? 'not-allowed' : undefined,
        ...style,
      }}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  )
}

export function TextArea({
  value,
  onChange,
  placeholder,
  rows,
  disabled,
  style,
  onKeyDown,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  rows?: number
  disabled?: boolean
  style?: CSSProperties
  onKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={onKeyDown}
      placeholder={placeholder}
      rows={rows}
      disabled={disabled}
      style={{
        width: '100%',
        minHeight: 72,
        padding: '10px 12px',
        borderRadius: 8,
        border: '1px solid var(--arm-stroke-secondary)',
        background: 'var(--arm-fill-secondary)',
        color: 'var(--arm-t-primary)',
        fontFamily: 'inherit',
        fontSize: 13,
        resize: 'vertical',
        ...style,
      }}
    />
  )
}

export function Callout({
  children,
  tone = 'info',
  title,
  style,
  className,
}: {
  children?: ReactNode
  tone?: 'info' | 'warning' | 'success' | 'danger'
  title?: string
  style?: CSSProperties
  className?: string
}) {
  const tones: Record<string, CSSProperties> = {
    info: { background: '#E3F2FD', borderColor: '#90CAF9', color: '#0D47A1' },
    warning: { background: '#FFF8E1', borderColor: '#FFE082', color: '#F57F17' },
    success: { background: '#E8F5E9', borderColor: '#A5D6A7', color: '#1B5E20' },
    danger: { background: '#FFEBEE', borderColor: '#EF9A9A', color: '#B71C1C' },
  }
  return (
    <div
      className={className}
      style={{ padding: 10, borderRadius: 8, border: '1px solid', ...tones[tone], ...style }}
    >
      {title ? <div style={{ fontWeight: 600, marginBottom: 4, fontSize: 12 }}>{title}</div> : null}
      {children}
    </div>
  )
}

export function Card({ children, style }: { children?: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{ borderRadius: 8, border: '1px solid var(--arm-stroke-secondary)', background: 'var(--arm-bg-elevated)', overflow: 'hidden', ...style }}>
      {children}
    </div>
  )
}

export function CardHeader({
  children,
  trailing,
  style,
}: {
  children?: ReactNode
  trailing?: ReactNode
  style?: CSSProperties
}) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 8,
        padding: '10px 12px 0',
        fontWeight: 600,
        fontSize: 13,
        ...style,
      }}
    >
      <span>{children}</span>
      {trailing}
    </div>
  )
}

export function CardBody({ children }: { children?: ReactNode }) {
  return <div style={{ padding: 12 }}>{children}</div>
}

export function Link({
  href,
  children,
  style,
}: {
  href: string
  children?: ReactNode
  style?: CSSProperties
}) {
  return (
    <a href={href} target="_blank" rel="noreferrer" style={{ color: 'inherit', ...style }}>
      {children}
    </a>
  )
}

export function Grid({
  children,
  columns,
  style,
}: {
  children?: ReactNode
  columns?: number
  style?: CSSProperties
}) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${columns ?? 2}, minmax(0, 1fr))`, ...style }}>
      {children}
    </div>
  )
}
