import type { JSX } from 'react'
import { Card, CardBody, Stack, Text } from './primitives'
import { TopicChip } from './summaryTopics'
import type { ArmTheme } from './theme'

export type SummaryDialogBlock = {
  date_label: string
  topic: string
  essence?: string
  channel?: string
  operator_name?: string
  /** @deprecated transcript lines are no longer shown */
  lines?: Array<{ speaker: string; text: string }>
}

export type SummaryHistoryData = {
  summary: string
  detailedSummary: string
  preview: string
  topics?: string[]
  blocks?: SummaryDialogBlock[]
  isFirst?: boolean
}

export const EMPTY_SUMMARY_HISTORY: SummaryHistoryData = {
  summary: 'История обращений пока не загружена.',
  detailedSummary: 'Откройте диалог клиента, чтобы загрузить единую историю и summary.',
  preview: 'Нет данных',
  topics: [],
  blocks: [],
}

function neutralCardSurface(t: ArmTheme, isExpanded: boolean): { background: string; border: string } {
  return {
    background: isExpanded ? t.bg.elevated : t.fill.tertiary,
    border: t.stroke.secondary,
  }
}

export function historyToSummary(input: {
  items?: unknown[]
  summary?: string
  detailedSummary?: string
  topics?: string[]
  blocks?: SummaryDialogBlock[]
  isFirst?: boolean
  previousCount?: number
}): SummaryHistoryData {
  const itemsCount = input.items?.length ?? 0
  const blocks = input.blocks ?? []
  const previousCount = typeof input.previousCount === 'number'
    ? input.previousCount
    : blocks.length > 0
      ? blocks.length
      : Math.max(0, itemsCount - 1)
  // Source of truth: other dialogs / detailed blocks — never the summary wording.
  const reallyFirst = previousCount <= 0 && blocks.length === 0
  let summary = (input.summary || '').trim()
  if (!summary) {
    summary = reallyFirst
      ? 'Первое обращение клиента.'
      : `Клиент обращался ранее (${Math.max(previousCount, blocks.length)}).`
  } else if (!reallyFirst && /^первое обращение клиента\.?$/i.test(summary)) {
    summary = `Клиент обращался ранее (${Math.max(previousCount, blocks.length)}).`
  }
  return {
    summary,
    detailedSummary: (input.detailedSummary || '').trim() || summary,
    preview: summary,
    topics: input.topics ?? [],
    blocks,
    isFirst: reallyFirst,
  }
}

function ShortSummaryBody({
  t,
  data,
}: {
  t: ArmTheme
  data: SummaryHistoryData
}): JSX.Element {
  if (data.isFirst) {
    return (
      <Text style={{ fontSize: 12, lineHeight: 1.55, color: t.text.primary }}>
        Первое обращение клиента — предыдущей истории нет.
      </Text>
    )
  }
  return (
    <Text style={{ fontSize: 12, lineHeight: 1.55, color: t.text.primary }}>
      {data.summary}
    </Text>
  )
}

function MetaTable({
  t,
  channel,
  operatorName,
}: {
  t: ArmTheme
  channel?: string
  operatorName?: string
}): JSX.Element {
  const rows = [
    { label: 'Канал', value: channel || '—' },
    { label: 'Оператор', value: operatorName || '—' },
  ]
  return (
    <div
      style={{
        marginTop: 10,
        borderRadius: 8,
        border: `1px solid ${t.stroke.tertiary}`,
        overflow: 'hidden',
      }}
    >
      {rows.map((row, index) => (
        <div
          key={row.label}
          style={{
            display: 'grid',
            gridTemplateColumns: '96px 1fr',
            gap: 8,
            padding: '6px 10px',
            background: index % 2 === 0 ? t.fill.secondary : t.bg.elevated,
            borderTop: index === 0 ? 'none' : `1px solid ${t.stroke.tertiary}`,
            fontSize: 11,
            lineHeight: 1.4,
          }}
        >
          <span style={{ color: t.text.tertiary, fontWeight: 600 }}>{row.label}</span>
          <span style={{ color: t.text.primary }}>{row.value}</span>
        </div>
      ))}
    </div>
  )
}

function DetailedBlocks({
  t,
  blocks,
  fallback,
}: {
  t: ArmTheme
  blocks: SummaryDialogBlock[]
  fallback: string
}): JSX.Element {
  if (!blocks.length) {
    return (
      <Text style={{ fontSize: 12, lineHeight: 1.55, color: t.text.primary, whiteSpace: 'pre-line' }}>
        {fallback}
      </Text>
    )
  }
  return (
    <Stack gap={10}>
      {blocks.map((block, index) => (
        <div
          key={`${block.date_label}-${index}`}
          style={{
            borderRadius: 10,
            border: `1px solid ${t.stroke.tertiary}`,
            background: t.fill.secondary,
            padding: '10px 12px',
          }}
        >
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
              alignItems: 'center',
              marginBottom: 8,
            }}
          >
            <span
              style={{
                fontSize: 11,
                fontWeight: 700,
                color: t.text.secondary,
                letterSpacing: 0.2,
              }}
            >
              {block.date_label}
            </span>
            <TopicChip t={t} topic={block.topic} size="sm" />
          </div>
          <Text style={{ fontSize: 12, lineHeight: 1.55, color: t.text.primary }}>
            {block.essence || 'Нет краткого описания сути обращения.'}
          </Text>
          <MetaTable t={t} channel={block.channel} operatorName={block.operator_name} />
        </div>
      ))}
    </Stack>
  )
}

export function ClientSummaryCard({
  t,
  data,
  isExpanded,
  onToggle,
}: {
  t: ArmTheme
  data: SummaryHistoryData
  isExpanded: boolean
  onToggle: () => void
  scheme?: unknown
  disabled?: boolean
}): JSX.Element {
  const surface = neutralCardSurface(t, isExpanded)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Summary клиента"
      aria-expanded={isExpanded}
      style={{ marginTop: 8, outline: 'none', cursor: 'pointer' }}
      onClick={() => onToggle()}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onToggle()
        }
      }}
    >
      <Card
        style={{
          background: surface.background,
          border: `1px solid ${surface.border}`,
        }}
      >
        <CardBody>
          {isExpanded ? (
            <Stack gap={10}>
              <Text weight="semibold" style={{ fontSize: 11, fontWeight: 700, color: t.text.secondary }}>
                Краткий summary
              </Text>
              <ShortSummaryBody t={t} data={data} />
              <div style={{ height: 1, background: t.stroke.tertiary }} />
              <Text weight="semibold" style={{ fontSize: 11, fontWeight: 700, color: t.text.secondary }}>
                Детальный summary
              </Text>
              <DetailedBlocks t={t} blocks={data.blocks ?? []} fallback={data.detailedSummary} />
            </Stack>
          ) : (
            <Text style={{ fontSize: 12, lineHeight: 1.45, color: t.text.secondary }}>
              {data.preview}
            </Text>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

/** Read-only expanded summary (history module) — same visual language as ARM card. */
export function ClientSummaryPanel({
  t,
  data,
}: {
  t: ArmTheme
  data: SummaryHistoryData
}): JSX.Element {
  return (
    <Stack gap={10}>
      <Text weight="semibold" style={{ fontSize: 11, fontWeight: 700, color: t.text.secondary }}>
        Краткий summary
      </Text>
      <ShortSummaryBody t={t} data={data} />
      <div style={{ height: 1, background: t.stroke.tertiary }} />
      <Text weight="semibold" style={{ fontSize: 11, fontWeight: 700, color: t.text.secondary }}>
        Детальный summary
      </Text>
      <DetailedBlocks t={t} blocks={data.blocks ?? []} fallback={data.detailedSummary} />
    </Stack>
  )
}
