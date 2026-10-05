export interface SandboxSnippet {
  kind: 'sql' | 'code'
  label: string
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

export async function fetchSqlAccess(): Promise<{ name: string; object_name: string }[]> {
  const response = await fetch('/api/v1/assistant/sql/access/', {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(await parseError(response))
  const body = (await response.json()) as { items: { name: string; object_name: string }[] }
  return body.items || []
}

export async function submitSandboxSnippet(
  kind: 'sql' | 'code',
  text: string,
): Promise<SandboxSnippet> {
  const response = await fetch('/api/v1/assistant/sandbox/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ kind, text }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as SandboxSnippet
}
