import { useEffect, useState } from 'react'

interface AuthContextResponse {
  authenticated: boolean
  username: string | null
  roles: string[]
  tabs: string[]
}

export interface PortalAuthState {
  status: 'loading' | 'ready' | 'unavailable'
  username: string | null
  roles: string[]
  tabs: string[]
}

const DEFAULT_DEV_ROLES = [
  'software_administrator',
  'contact_center_analyst',
  'contact_center_online_chat_operator',
  'contact_center_module_administrator',
]

function devRoles(): string[] {
  if (!import.meta.env.DEV && import.meta.env.VITE_SUFLER_DEMO !== '1') {
    return []
  }
  const configured = String(import.meta.env.VITE_DEV_RBAC_ROLES ?? '')
    .split(',')
    .map((role) => role.trim())
    .filter(Boolean)
  return configured.length ? configured : DEFAULT_DEV_ROLES
}

export function usePortalAuth(): PortalAuthState {
  const [state, setState] = useState<PortalAuthState>({
    status: 'loading',
    username: null,
    roles: [],
    tabs: [],
  })

  useEffect(() => {
    const controller = new AbortController()
    void fetch('/api/auth/me/', {
      credentials: 'include',
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Auth context failed: ${response.status}`)
        }
        return (await response.json()) as AuthContextResponse
      })
      .then((payload) => {
        const fallbackRoles = payload.authenticated ? [] : devRoles()
        setState({
          status: 'ready',
          username: payload.authenticated
            ? payload.username
            : fallbackRoles.length
              ? 'Development user'
              : null,
          roles: payload.authenticated ? payload.roles : fallbackRoles,
          tabs: payload.authenticated ? payload.tabs : [],
        })
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') {
          return
        }
        const fallbackRoles = devRoles()
        setState({
          status: fallbackRoles.length ? 'ready' : 'unavailable',
          username: fallbackRoles.length ? 'Development user' : null,
          roles: fallbackRoles,
          tabs: [],
        })
      })
    return () => controller.abort()
  }, [])

  return state
}
