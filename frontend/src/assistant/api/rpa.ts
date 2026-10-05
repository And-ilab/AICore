export interface RpaScenario {
  id: number
  name: string
  code: string
  description: string
  active: boolean
}

export interface RpaLaunchResult {
  id: number
  scenario_id: number
  scenario_name: string
  scenario_code: string
  status: string
  status_label: string
  detail: string
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

export async function fetchRpaWhitelist(): Promise<RpaScenario[]> {
  const response = await fetch('/api/v1/assistant/rpa/scenarios/', {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(await parseError(response))
  const body = (await response.json()) as { items: RpaScenario[] }
  return body.items || []
}

export async function confirmRpaLaunch(scenarioId: number): Promise<RpaLaunchResult> {
  const response = await fetch('/api/v1/assistant/rpa/launch/', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ scenario_id: scenarioId, confirm: true }),
  })
  if (!response.ok) throw new Error(await parseError(response))
  return (await response.json()) as RpaLaunchResult
}
