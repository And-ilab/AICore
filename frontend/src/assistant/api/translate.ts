export interface Translation {
  direction: 'ru-en' | 'en-ru'
  source_label: string
  target_label: string
  source: string
  text: string
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function parseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      details?: { request?: string[] }
      error?: string
    }
    return payload.details?.request?.[0] || payload.error || `Ошибка ${response.status}`
  } catch {
    return `Ошибка ${response.status}`
  }
}

export async function translateText(
  text: string,
  direction: 'ru-en' | 'en-ru',
): Promise<Translation> {
  const response = await fetch('/api/v1/assistant/translate/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ text, direction }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as Translation
}
