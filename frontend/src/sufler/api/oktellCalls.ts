export type OktellListenLeg = {
  speaker: 'client' | 'operator' | string
  dial: string
  sip_user: string
  status: string
}

export type OktellCallEvent = {
  type?: string
  speaker?: 'client' | 'operator'
  text?: string
  is_final?: boolean
  turn_id?: string
  hints?: unknown[]
  blocked_reason?: string | null
}

export type OktellLiveCall = {
  CallerID: string
  CalledID: string
  Idchain: string
  op_name: string
  call_type: string
  state: string
  listen_mode: string
  created_at?: number
  legs: OktellListenLeg[]
  sufler_ws: string
  events?: OktellCallEvent[]
  previous_question?: string
  previous_asked_at?: string
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export async function ensureOktellListen(kbSlugs?: string[]): Promise<OktellLiveCall | null> {
  const response = await fetch('/api/v1/telephony/oktell/listen-now', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify(kbSlugs === undefined ? {} : { kb_slugs: kbSlugs }),
  })
  if (!response.ok) return null
  const body = (await response.json()) as { call?: OktellLiveCall }
  return body.call ?? null
}

export async function fetchOktellCalls(): Promise<OktellLiveCall[]> {
  const response = await fetch('/api/v1/telephony/oktell/calls', {
    credentials: 'include',
  })
  if (response.status === 401 || response.status === 403) {
    return []
  }
  if (!response.ok) {
    return []
  }
  const body = (await response.json()) as { calls?: OktellLiveCall[] }
  return Array.isArray(body.calls) ? body.calls : []
}

export async function fetchOktellCall(idchain: string): Promise<OktellLiveCall | null> {
  if (!idchain) return null
  const response = await fetch(
    `/api/v1/telephony/oktell/calls/${encodeURIComponent(idchain)}`,
    { credentials: 'include' },
  )
  if (!response.ok) return null
  const body = (await response.json()) as { call?: OktellLiveCall }
  return body.call ?? null
}
