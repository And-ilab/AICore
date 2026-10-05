import type { CSSProperties, JSX } from 'react'
import type { ArmTheme } from './theme'

export type SummaryTopicKey =
  | 'cards'
  | 'payments'
  | 'mobile'
  | 'credits'
  | 'mortgage'
  | 'deposits'
  | 'business'
  | 'security'
  | 'tech'
  | 'other'

export type SummaryTopicMeta = {
  key: SummaryTopicKey
  label: string
  /** Soft chip background / accent — works on light and dark ARM themes. */
  light: { bg: string; fg: string; border: string }
  dark: { bg: string; fg: string; border: string }
}

const TOPIC_META: SummaryTopicMeta[] = [
  {
    key: 'cards',
    label: 'Карты и счета',
    light: { bg: '#E8F1FB', fg: '#0C4DA2', border: '#B7CFE8' },
    dark: { bg: '#1A2F4A', fg: '#8FB8E8', border: '#2A4A6E' },
  },
  {
    key: 'payments',
    label: 'Платежи и переводы',
    light: { bg: '#E8F7F0', fg: '#0B6B3A', border: '#B5DCC7' },
    dark: { bg: '#163528', fg: '#7FCF9F', border: '#27543C' },
  },
  {
    key: 'mobile',
    label: 'Мобильный банк',
    light: { bg: '#F3EAFB', fg: '#6B2FA0', border: '#D4BBE8' },
    dark: { bg: '#2C1F3D', fg: '#C9A6E8', border: '#4A3560' },
  },
  {
    key: 'credits',
    label: 'Кредиты',
    light: { bg: '#FFF3E0', fg: '#A05A00', border: '#E8C89A' },
    dark: { bg: '#3A2A14', fg: '#E0B06A', border: '#5A4320' },
  },
  {
    key: 'mortgage',
    label: 'Ипотека',
    light: { bg: '#EDE7F6', fg: '#4527A0', border: '#C5B6E0' },
    dark: { bg: '#241C3A', fg: '#B39DDB', border: '#3C2F5A' },
  },
  {
    key: 'deposits',
    label: 'Вклады',
    light: { bg: '#E0F7FA', fg: '#006064', border: '#A9D5DB' },
    dark: { bg: '#143236', fg: '#80CBC4', border: '#2A5054' },
  },
  {
    key: 'business',
    label: 'Юрлица',
    light: { bg: '#ECEFF1', fg: '#37474F', border: '#C1CCD1' },
    dark: { bg: '#243038', fg: '#B0BEC5', border: '#3A4A54' },
  },
  {
    key: 'security',
    label: 'Блокировка / безопасность',
    light: { bg: '#FFEBEE', fg: '#B71C1C', border: '#E8B4B8' },
    dark: { bg: '#3A1C1C', fg: '#EF9A9A', border: '#5A3030' },
  },
  {
    key: 'tech',
    label: 'Техническая поддержка',
    light: { bg: '#E3F2FD', fg: '#1565C0', border: '#A9C8E0' },
    dark: { bg: '#1A2C3A', fg: '#90CAF9', border: '#2E4A60' },
  },
  {
    key: 'other',
    label: 'Прочее',
    light: { bg: '#F5F5F5', fg: '#616161', border: '#D0D0D0' },
    dark: { bg: '#2A2A2A', fg: '#BDBDBD', border: '#444444' },
  },
]

const KEYWORD_TO_KEY: Array<{ key: SummaryTopicKey; patterns: RegExp[] }> = [
  { key: 'security', patterns: [/блок/i, /безопас/i, /мошен/i, /пин/i, /pin/i] },
  { key: 'mortgage', patterns: [/ипотек/i, /квартир/i, /жил/i] },
  { key: 'credits', patterns: [/кредит/i, /овердрафт/i, /заём/i, /заем/i] },
  { key: 'deposits', patterns: [/вклад/i, /депозит/i] },
  { key: 'payments', patterns: [/платеж/i, /перевод/i, /еріп/i, /ерип/i, /реквизит/i] },
  { key: 'mobile', patterns: [/мобильн/i, /м-банк/i, /приложение/i, /интернет-банк/i] },
  { key: 'business', patterns: [/юрлиц/i, /бизнес/i, /р\/с/i, /расчётн/i, /расчетн/i] },
  { key: 'tech', patterns: [/техн/i, /ошибк/i, /сбой/i, /поддержк/i] },
  { key: 'cards', patterns: [/карт/i, /сч[её]т/i, /atm/i, /лимит/i, /банкомат/i] },
]

export function resolveTopicKey(topic: string): SummaryTopicKey {
  const normalized = (topic || '').trim()
  if (!normalized || normalized === 'без темы') return 'other'
  const exact = TOPIC_META.find(
    (item) => item.label.toLowerCase() === normalized.toLowerCase(),
  )
  if (exact) return exact.key
  for (const rule of KEYWORD_TO_KEY) {
    if (rule.patterns.some((re) => re.test(normalized))) return rule.key
  }
  return 'other'
}

export function topicMeta(key: SummaryTopicKey): SummaryTopicMeta {
  return TOPIC_META.find((item) => item.key === key) ?? TOPIC_META[TOPIC_META.length - 1]!
}

export function topicColors(t: ArmTheme, key: SummaryTopicKey) {
  const meta = topicMeta(key)
  return t.kind === 'light' ? meta.light : meta.dark
}

function TopicIconSvg({
  topicKey,
  color,
}: {
  topicKey: SummaryTopicKey
  color: string
}): JSX.Element {
  const common = {
    width: 14,
    height: 14,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: color,
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }

  switch (topicKey) {
    case 'cards':
      return (
        <svg {...common}>
          <rect x="2" y="5" width="20" height="14" rx="2" />
          <path d="M2 10h20" />
          <path d="M6 15h4" />
        </svg>
      )
    case 'payments':
      return (
        <svg {...common}>
          <path d="M7 7h11l-3-3" />
          <path d="M17 7v0" />
          <path d="M17 17H6l3 3" />
          <path d="M7 17V7" />
          <path d="M17 7v10" />
        </svg>
      )
    case 'mobile':
      return (
        <svg {...common}>
          <rect x="7" y="2" width="10" height="20" rx="2" />
          <path d="M11 18h2" />
        </svg>
      )
    case 'credits':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v10" />
          <path d="M9.5 9.5c.6-1 1.7-1.5 2.7-1.5 1.5 0 2.8 1 2.8 2.4 0 2.6-5 2.2-5 5 0 1.2 1.1 2.1 2.5 2.1 1.1 0 2-.5 2.5-1.3" />
        </svg>
      )
    case 'mortgage':
      return (
        <svg {...common}>
          <path d="M3 11.5 12 4l9 7.5" />
          <path d="M6 10.5V20h12v-9.5" />
          <path d="M10 20v-5h4v5" />
        </svg>
      )
    case 'deposits':
      return (
        <svg {...common}>
          <path d="M12 3v3" />
          <path d="M8 8c0-2 1.8-3.5 4-3.5s4 1.5 4 3.5c0 4-8 3.5-8 8 0 2 1.8 3.5 4 3.5s4-1.5 4-3.5" />
          <path d="M8 21h8" />
        </svg>
      )
    case 'business':
      return (
        <svg {...common}>
          <rect x="3" y="7" width="18" height="13" rx="1.5" />
          <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <path d="M3 12h18" />
        </svg>
      )
    case 'security':
      return (
        <svg {...common}>
          <path d="M12 3 5 6v5c0 5 3.5 8.5 7 9.5 3.5-1 7-4.5 7-9.5V6l-7-3z" />
          <path d="M9.5 12.5 11 14l3.5-3.5" />
        </svg>
      )
    case 'tech':
      return (
        <svg {...common}>
          <path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.5-2.5 2.5-2.5z" />
        </svg>
      )
    default:
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="9" />
          <path d="M9.5 9.5a2.5 2.5 0 1 1 3.7 2.2c-.8.5-1.2 1-1.2 2" />
          <path d="M12 17h.01" />
        </svg>
      )
  }
}

export function TopicChip({
  t,
  topic,
  size = 'md',
  selected = false,
  onClick,
  disabled = false,
}: {
  t: ArmTheme
  topic: string
  size?: 'sm' | 'md'
  selected?: boolean
  onClick?: () => void
  disabled?: boolean
}): JSX.Element {
  const key = resolveTopicKey(topic)
  const colors = topicColors(t, key)
  const pad = size === 'sm' ? '2px 7px' : '4px 10px'
  const fontSize = size === 'sm' ? 11 : 12
  const interactive = typeof onClick === 'function'
  const style: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 5,
    padding: pad,
    borderRadius: 999,
    background: colors.bg,
    color: colors.fg,
    border: selected ? `1.5px solid ${colors.fg}` : `1px solid ${colors.border}`,
    boxShadow: selected ? `0 0 0 2px ${colors.bg}` : 'none',
    fontSize,
    fontWeight: selected ? 700 : 600,
    lineHeight: 1.3,
    maxWidth: '100%',
    cursor: disabled ? 'not-allowed' : interactive ? 'pointer' : 'default',
    opacity: disabled ? 0.55 : 1,
    fontFamily: 'inherit',
  }
  const content = (
    <>
      <TopicIconSvg topicKey={key} color={colors.fg} />
      <span
        style={{
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {topic || 'Прочее'}
      </span>
    </>
  )
  if (interactive) {
    return (
      <button
        type="button"
        title={topic}
        disabled={disabled}
        aria-pressed={selected}
        onClick={(event) => {
          event.stopPropagation()
          onClick()
        }}
        style={style}
      >
        {content}
      </button>
    )
  }
  return (
    <span style={style} title={topic}>
      {content}
    </span>
  )
}
