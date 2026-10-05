/** Shown when a real question has nothing suitable in the knowledge base. */
export const NO_SUZ_HINT_MESSAGE = 'В базе нет информации по этой реплике'

export function emptySuflerHintMessage(
  blocked: string | null | undefined,
  hasHints: boolean,
): string {
  if (hasHints) return ''
  if (blocked === 'no_hint_needed' || blocked === 'service_mode') return ''
  return NO_SUZ_HINT_MESSAGE
}
