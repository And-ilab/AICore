/**
 * Local/dev bootstrap: establish Django session via mock_ldap so admin APIs
 * (KB upload/create, …) do not fail with authentication_required / CSRF 403.
 *
 * Why this exists: the SPA on Vite (:5173) is separate from Django session auth.
 * Role picker is UI-only; mutating /api/admin/* needs a real session cookie + CSRF.
 */

let inFlight: Promise<boolean> | null = null
/** Password that last succeeded — avoid retrying wrong ones after first DEV login. */
let workingPassword: string | null = null

function isDevRuntime(): boolean {
  // Vite DEV, explicit demo, or TEST prod image built with mock-login args.
  return Boolean(
    import.meta.env.DEV
    || import.meta.env.VITE_ALLOW_DEV_LOGIN === '1'
    || import.meta.env.VITE_DEV_AUTH_PASSWORD
    || import.meta.env.VITE_SUFLER_DEMO === '1',
  )
}

export function readCsrfToken(): string {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function fetchAuthMe(): Promise<{ authenticated: boolean }> {
  const response = await fetch('/api/auth/me/', { credentials: 'include' })
  if (!response.ok) return { authenticated: false }
  return (await response.json()) as { authenticated: boolean }
}

async function tryLogin(username: string, password: string): Promise<boolean> {
  const response = await fetch('/api/auth/login/', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  if (!response.ok) return false
  const body = (await response.json()) as { ok?: boolean; authenticated?: boolean }
  return Boolean(body.ok || body.authenticated)
}

function candidatePasswords(): string[] {
  const configured = String(
    import.meta.env.VITE_DEV_AUTH_PASSWORD ?? '',
  ).trim()
  // Order: last-known-good, then VITE_*, then infra/.env.example placeholder,
  // then Django settings default. infra/.env often keeps the placeholder.
  const passwords = [
    workingPassword ?? '',
    configured,
    // Local infra/.env default used in this repo.
    'SuflerDevPass123',
    'replace-with-dev-only-password',
    'dev-only-password',
  ].filter(Boolean)
  return [...new Set(passwords)]
}

function candidateUsernames(): string[] {
  const configured = String(import.meta.env.VITE_DEV_AUTH_USER ?? '').trim()
  return [...new Set([configured, 'dev-role-01', 'dev-role-02'].filter(Boolean))]
}

async function loginDevUser(): Promise<boolean> {
  for (const username of candidateUsernames()) {
    for (const password of candidatePasswords()) {
      if (await tryLogin(username, password).catch(() => false)) {
        workingPassword = password
        return true
      }
    }
  }
  return false
}

/** Drop cached in-flight promise so the next call re-checks / re-logins. */
export function resetDevSessionCache(): void {
  inFlight = null
}

/**
 * Guarantee a readable csrftoken cookie. Django rotates CSRF on login;
 * pass forceRefresh after login so a pre-login cookie is not reused.
 */
export async function ensureCsrfToken(forceRefresh = false): Promise<string> {
  if (!forceRefresh) {
    const existing = readCsrfToken()
    if (existing) return existing
  }
  await fetchAuthMe().catch(() => ({ authenticated: false }))
  let token = readCsrfToken()
  if (!token) {
    await fetch('/api/auth/me/', { credentials: 'include' }).catch(() => null)
    token = readCsrfToken()
  }
  return token
}

async function ensureDevSessionOnce(forceRelogin = false): Promise<boolean> {
  // Always re-check /me/ — also refreshes csrftoken after login rotation.
  let me = forceRelogin
    ? { authenticated: false }
    : await fetchAuthMe().catch(() => ({ authenticated: false }))
  let justLoggedIn = false
  if (!me.authenticated) {
    if (!isDevRuntime()) return false
    const loggedIn = await loginDevUser().catch(() => false)
    if (!loggedIn) return false
    justLoggedIn = true
    me = await fetchAuthMe().catch(() => ({ authenticated: false }))
    if (!me.authenticated) return false
  }

  const csrf = await ensureCsrfToken(justLoggedIn || forceRelogin)
  return Boolean(csrf)
}

/** Returns true when the browser has an authenticated Django session + CSRF cookie. */
export async function ensureDevSession(forceRelogin = false): Promise<boolean> {
  if (inFlight && !forceRelogin) return inFlight

  inFlight = ensureDevSessionOnce(forceRelogin)

  try {
    return await inFlight
  } catch {
    return false
  } finally {
    // Only coalesce concurrent callers; never keep a sticky "logged in" cache.
    inFlight = null
  }
}

export function isAuthErrorMessage(message: string): boolean {
  return /authentication_required|permission_denied|csrf|403 Forbidden|401/i.test(
    message,
  )
}

export function isCsrfErrorMessage(message: string): boolean {
  return /csrf|CSRF verification failed/i.test(message)
}
