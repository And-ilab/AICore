export interface SuflerHintCitation {
  article_id: number
  chunk_index: number
  title: string
  permalink: string
}

export interface SuflerHint {
  rank: number
  text: string
  /** Fuller KB article shown when the operator opens ⋯ on a knowledge-base hint. */
  detail_text?: string
  operator_tip?: string
  source_type?: 'scenario' | 'knowledge_base'
  relevance_score: number
  relevance_percent: number
  citations: SuflerHintCitation[]
}

export interface SuggestResponse {
  query: string
  profile: string
  kb_id: string
  kb_slugs?: string[]
  hints: SuflerHint[]
  citations_enabled: boolean
  blocked_reason: string | null
  min_relevance: number
  latency_ms: {
    qu: number
    rag: number
    llm: number
    total: number
  }
  request_id: string
  gateway_model?: string
  scenario?: {
    code: string
    title: string
    path: string[]
    node_id: string
    next_clarify: string
    paused?: boolean
    completed?: boolean
    return_phrase?: string
    steps?: Array<{ node_id: string; label: string }>
    upcoming?: Array<{ node_id: string; label: string }>
    choices?: Array<{ label: string; reply: string }>
  } | null
  suggested_scenario?: {
    code: string
    title: string
    confidence: number
  } | null
}

function csrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

function emptySuggestResponse(query: string): SuggestResponse {
  return {
    query,
    profile: 'sufler_cc',
    kb_id: 'cc_production',
    hints: [],
    citations_enabled: true,
    blocked_reason: 'no_relevant_knowledge',
    min_relevance: 0.2,
    latency_ms: { qu: 0, rag: 0, llm: 0, total: 0 },
    request_id: '',
    scenario: null,
    suggested_scenario: null,
  }
}

function friendlySuggestError(raw: string, status: number): string {
  const code = (raw || '').toLowerCase()
  if (
    status === 401
    || status === 403
    || status >= 500
    || code.includes('authentication_required')
    || code.includes('permission_denied')
    || code.includes('no_relevant_knowledge')
    || code.includes('sufler_unavailable')
    || !raw
    || raw === 'validation_error'
    || /^[a-z0-9_]+$/i.test(raw)
  ) {
    return 'В базе нет информации по этой реплике'
  }
  return raw
}

async function postSuggestOnce(
  text: string,
  limit: number,
  options?: {
    clientHistory?: string
    dialogContext?: string
    kbSlugs?: string[]
    channel?: 'telephony' | 'online_chat'
    mode?: 'consultation' | 'service'
    sessionId?: string
  },
): Promise<Response> {
  return fetch('/api/v1/sufler/suggest', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({
      text,
      limit,
      client_history: options?.clientHistory ?? '',
      dialog_context: options?.dialogContext ?? '',
      ...(options && 'kbSlugs' in options ? { kb_slugs: options.kbSlugs ?? [] } : {}),
      ...(options?.channel ? { channel: options.channel } : {}),
      ...(options?.mode ? { mode: options.mode } : {}),
      ...(options?.sessionId ? { session_id: options.sessionId } : {}),
    }),
  })
}

export async function requestSuflerSuggest(
  text: string,
  limit = 5,
  options?: {
    clientHistory?: string
    dialogContext?: string
    kbSlugs?: string[]
    channel?: 'telephony' | 'online_chat'
    mode?: 'consultation' | 'service'
    sessionId?: string
  },
): Promise<SuggestResponse> {
  // Online-chat ARM is often opened without a prior admin/login bootstrap.
  try {
    const { ensureDevSession } = await import('../../auth/ensureDevSession')
    await ensureDevSession()
  } catch {
    /* ignore — suggest will surface a friendly error if auth still missing */
  }
  const safeLimit = Math.min(5, Math.max(1, Math.round(limit) || 5))
  const parseBody = async (response: Response) =>
    (await response.json().catch(() => ({}))) as {
      error?: string
      details?: { request?: string[] }
    } & Partial<SuggestResponse>

  let response: Response
  try {
    response = await postSuggestOnce(text, safeLimit, options)
  } catch {
    return emptySuggestResponse(text)
  }
  if (!response.ok && (response.status === 401 || response.status === 403 || response.status >= 500)) {
    try {
      const { ensureDevSession, ensureCsrfToken } = await import('../../auth/ensureDevSession')
      await ensureDevSession()
      await ensureCsrfToken(true)
      response = await postSuggestOnce(text, safeLimit, options)
    } catch {
      return emptySuggestResponse(text)
    }
  }
  const body = await parseBody(response)
  if (!response.ok) {
    return emptySuggestResponse(text)
  }
  if (!Array.isArray(body.hints)) {
    return emptySuggestResponse(text)
  }
  return body as SuggestResponse
}

export async function enterSuflerScenario(
  code: string,
  options?: {
    sessionId?: string
    channel?: 'telephony' | 'online_chat'
  },
): Promise<SuggestResponse> {
  try {
    const { ensureDevSession } = await import('../../auth/ensureDevSession')
    await ensureDevSession()
  } catch {
    /* ignore */
  }
  const response = await fetch('/api/v1/sufler/scenario/enter', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({
      code,
      ...(options?.sessionId ? { session_id: options.sessionId } : {}),
      ...(options?.channel ? { channel: options.channel } : {}),
    }),
  })
  const body = await response.json().catch(() => ({} as { error?: string }))
  if (!response.ok) {
    throw new Error(friendlySuggestError(String(body.error || ''), response.status))
  }
  return body as SuggestResponse
}

export async function clearSuflerScenario(sessionId: string): Promise<void> {
  try {
    const { ensureDevSession } = await import('../../auth/ensureDevSession')
    await ensureDevSession()
  } catch {
    /* ignore */
  }
  await fetch('/api/v1/sufler/scenario/clear', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ session_id: sessionId }),
  }).catch(() => {})
}

export async function exitSuflerScenario(
  sessionId: string,
): Promise<Pick<SuggestResponse, 'scenario' | 'suggested_scenario'>> {
  try {
    const { ensureDevSession } = await import('../../auth/ensureDevSession')
    await ensureDevSession()
  } catch {
    /* ignore */
  }
  const response = await fetch('/api/v1/sufler/scenario/exit', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({ session_id: sessionId }),
  })
  const body = await response.json().catch(() => ({} as { error?: string }))
  if (!response.ok) {
    throw new Error(friendlySuggestError(String(body.error || ''), response.status))
  }
  return body as Pick<SuggestResponse, 'scenario' | 'suggested_scenario'>
}

export async function resumeSuflerScenario(
  sessionId: string,
  mode: 'start' | 'checkpoint' | 'step',
  options?: {
    channel?: 'telephony' | 'online_chat'
    nodeId?: string
    dialogContext?: string
  },
): Promise<SuggestResponse> {
  try {
    const { ensureDevSession } = await import('../../auth/ensureDevSession')
    await ensureDevSession()
  } catch {
    /* ignore */
  }
  const response = await fetch('/api/v1/sufler/scenario/resume', {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': csrfToken(),
    },
    body: JSON.stringify({
      session_id: sessionId,
      mode,
      ...(options?.channel ? { channel: options.channel } : {}),
      ...(options?.nodeId ? { node_id: options.nodeId } : {}),
      ...(options?.dialogContext ? { dialog_context: options.dialogContext } : {}),
    }),
  })
  const body = await response.json().catch(() => ({} as { error?: string }))
  if (!response.ok) {
    throw new Error(friendlySuggestError(String(body.error || ''), response.status))
  }
  return body as SuggestResponse
}
