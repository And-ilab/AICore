/** Keep a finished sentence when the model hits the token cap mid-phrase. */
export function finishLastSentence(text: string): string {
  const trimmed = text.replace(/[\s\u00a0]+$/u, '')
  if (!trimmed) return text
  if (/[.!?…]["»”)\]']*$/u.test(trimmed)) return trimmed

  let last = -1
  for (const mark of ['.', '!', '?', '…']) {
    const index = trimmed.lastIndexOf(mark)
    if (index > last) last = index
  }
  if (last < 20) return trimmed

  let end = last + 1
  while (end < trimmed.length && /["»”)\]']/.test(trimmed[end] || '')) {
    end += 1
  }
  const leftover = trimmed.slice(end).trim()
  if (!leftover) return trimmed
  return trimmed.slice(0, end).trimEnd()
}
