import type { CSSProperties, JSX } from 'react'

/** Nesting ("вложение") — a group node that only groups other nodes and can
 * never be chosen as a closing topic. */
export function TopicGroupIcon({ size = 14, color = 'currentColor', style }: {
  size?: number
  color?: string
  style?: CSSProperties
}): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={style}
    >
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2.5h8a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
    </svg>
  )
}

/** Topic ("тема") — a leaf node that can be chosen as the dialog closing
 * topic. */
export function TopicLeafIcon({ size = 14, color = 'currentColor', style }: {
  size?: number
  color?: string
  style?: CSSProperties
}): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={style}
    >
      <path d="M12 3.5 20 8v8l-8 4.5L4 16V8l8-4.5z" />
      <circle cx="12" cy="12" r="2.4" />
    </svg>
  )
}

export function TrashIcon({ size = 14, color = 'currentColor', style }: {
  size?: number
  color?: string
  style?: CSSProperties
}): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      style={style}
    >
      <path d="M4 7h16" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
      <path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  )
}
