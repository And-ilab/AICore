import { ensureDevSession } from '../../auth/ensureDevSession'

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function transcribeUtterance(
  audio: Blob,
  speaker: 'client' | 'operator',
): Promise<string> {
  try {
    await ensureDevSession()
  } catch {
    /* suggest/transcribe will surface auth errors */
  }
  const body = new FormData()
  body.append('speaker', speaker)
  body.append('audio', audio, 'utterance.wav')
  const response = await fetch('/api/v1/sufler/transcribe', {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-CSRFToken': csrfToken() },
    body,
  })
  const payload = (await response.json().catch(() => ({}))) as {
    text?: string
    details?: { request?: string[] }
    error?: string
  }
  if (!response.ok) {
    throw new Error(
      payload.details?.request?.[0]
      || payload.error
      || `Transcribe failed (${response.status})`,
    )
  }
  return String(payload.text || '').trim()
}
