import type { StatusBadgeStatus } from './StatusBadge'

/** II.3.2 / canvas: ≥90 green, 85–89 amber-strong, 80–84 amber-light, <80 neutral. */
export type RelevanceTier = 'high' | 'mediumStrong' | 'mediumLight' | 'low'

export type HintFeedbackChoice = 'used' | 'not_used' | 'partial'

export const HINT_FEEDBACK_OPTIONS: readonly {
  id: HintFeedbackChoice
  label: string
}[] = [
  { id: 'used', label: 'Воспользовался' },
  { id: 'not_used', label: 'Не воспользовался' },
  { id: 'partial', label: 'Неполный ответ' },
] as const

export function parseRelevancePercent(relevance: number | string | undefined): number | null {
  if (relevance == null) return null
  if (typeof relevance === 'number' && Number.isFinite(relevance)) return relevance
  const match = String(relevance).match(/(\d+(?:\.\d+)?)/)
  return match ? Number(match[1]) : null
}

export function relevanceTierFromPercent(pct: number): RelevanceTier {
  if (pct >= 90) return 'high'
  if (pct >= 85) return 'mediumStrong'
  if (pct >= 80) return 'mediumLight'
  return 'low'
}

export function relevanceStatusFromPercent(pct: number): StatusBadgeStatus {
  const tier = relevanceTierFromPercent(pct)
  if (tier === 'high') return 'success'
  if (tier === 'low') return 'neutral'
  return 'warning'
}
