import { useEffect, useState } from 'react'

interface AuthContextResponse {
  authenticated: boolean
  username: string | null
  first_name?: string | null
  last_name?: string | null
  display_name?: string | null
  roles: string[]
  tabs: string[]
}

export interface PortalAuthState {
  status: 'loading' | 'ready' | 'unavailable'
  authenticated: boolean
  username: string | null
  displayName: string | null
  firstName: string | null
  lastName: string | null
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

function anonymousState(): PortalAuthState {
  const fallbackRoles = devRoles()
  return {
    status: 'ready',
    authenticated: false,
    username: fallbackRoles.length ? 'Development user' : null,
    displayName: null,
    firstName: null,
    lastName: null,
    roles: fallbackRoles,
    tabs: [],
  }
}

export function usePortalAuth(): PortalAuthState {
  const [state, setState] = useState<PortalAuthState>({
    status: 'loading',
    authenticated: false,
    username: null,
    displayName: null,
    firstName: null,
    lastName: null,
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
        if (response.status === 401) {
          setState(anonymousState())
          return null
        }
        if (!response.ok) {
          throw new Error(`Auth context failed: ${response.status}`)
        }
        return (await response.json()) as AuthContextResponse
      })
      .then((payload) => {
        if (!payload) return
        const fallbackRoles = payload.authenticated ? [] : devRoles()
        setState({
          status: 'ready',
          authenticated: payload.authenticated,
          username: payload.authenticated
            ? payload.username
            : fallbackRoles.length
              ? 'Development user'
              : null,
          displayName: payload.authenticated
            ? (payload.display_name || payload.username)
            : null,
          firstName: payload.authenticated ? (payload.first_name || null) : null,
          lastName: payload.authenticated ? (payload.last_name || null) : null,
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
          authenticated: false,
          username: fallbackRoles.length ? 'Development user' : null,
          displayName: null,
          firstName: null,
          lastName: null,
          roles: fallbackRoles,
          tabs: [],
        })
      })
    return () => controller.abort()
  }, [])

  return state
}
