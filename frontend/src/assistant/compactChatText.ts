/** Drop markdown noise, source dumps, and a trailing empty list step. */
export function compactChatText(text: string) {
  let out = text.replace(/\r\n/g, '\n')
  out = out.replace(/\*\*([^*]+)\*\*/g, '$1')
  out = out.replace(/\*([^*\n]+)\*/g, '$1')
  out = out.replace(/\*\*/g, '')
  const lines = out.split('\n').filter((line) => {
    const trimmed = line.trim()
    if (!trimmed) return false
    if (/^источники\s*[:(\[]/i.test(trimmed)) return false
    if (/^источники\s*\(\d+\)/i.test(trimmed)) return false
    if (/^[-–—•]\s*\[\d+\]/.test(trimmed)) return false
    if (/^\[\d+\]\s+\S/.test(trimmed) && /(бз:|источник|\.txt|\.doc|\.pdf)/i.test(trimmed)) {
      return false
    }
    if (/по предоставленн\w*\s+фрагмент/i.test(trimmed)) return false
    if (/в базе знаний найдено/i.test(trimmed)) return false
    if (/^фрагменты базы знаний/i.test(trimmed)) return false
    return true
  })
  while (lines.length) {
    const last = lines[lines.length - 1]?.trim() ?? ''
    if (/^(?:\d+[\.)]|[-–—•])\s*$/.test(last)) {
      lines.pop()
      continue
    }
    break
  }
  return lines
    .join('\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{2,}/g, '\n')
    .trim()
}
