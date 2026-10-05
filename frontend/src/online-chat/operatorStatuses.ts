/** II.5 / FR-CHAT-11 operator presence — 9 statuses from canvas online-chat. */

export type OperatorPresence =
  | 'online'
  | 'invisible'
  | 'break'
  | 'lunch'
  | 'tech_break'
  | 'training'
  | 'meeting'
  | 'offline_queue'
  | 'offline'

export type OperatorStatusTone = 'success' | 'warning' | 'neutral' | 'info'

export interface OperatorStatusDef {
  id: OperatorPresence
  label: string
  tone: OperatorStatusTone
  /** When false, operator does not receive new waiting-queue assignments. */
  acceptsNewDialogs: boolean
}

export const OPERATOR_STATUSES: readonly OperatorStatusDef[] = [
  { id: 'online', label: 'в сети', tone: 'success', acceptsNewDialogs: true },
  { id: 'invisible', label: 'невидимка', tone: 'neutral', acceptsNewDialogs: false },
  { id: 'break', label: 'перерыв', tone: 'warning', acceptsNewDialogs: false },
  { id: 'lunch', label: 'обед', tone: 'warning', acceptsNewDialogs: false },
  { id: 'tech_break', label: 'техперерыв', tone: 'warning', acceptsNewDialogs: false },
  { id: 'training', label: 'обучение', tone: 'info', acceptsNewDialogs: false },
  { id: 'meeting', label: 'встреча', tone: 'info', acceptsNewDialogs: false },
  { id: 'offline_queue', label: 'офлайн-обращения', tone: 'info', acceptsNewDialogs: true },
  { id: 'offline', label: 'не в сети', tone: 'neutral', acceptsNewDialogs: false },
] as const

export function operatorStatusById(id: string): OperatorStatusDef | undefined {
  return OPERATOR_STATUSES.find((status) => status.id === id)
}

export function isOperatorPresence(value: string): value is OperatorPresence {
  return OPERATOR_STATUSES.some((status) => status.id === value)
}
