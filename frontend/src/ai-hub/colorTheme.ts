import { useEffect, useState } from 'react'

/** Classic = current AI Hub blue; emerald = online-chat ARM green palette. */
export type AiHubColorTheme = 'classic' | 'emerald'

export const AI_HUB_COLOR_THEME_KEY = 'ai-hub-color-theme'
export const AI_HUB_COLOR_THEME_EVENT = 'ai-hub-color-theme-change'

export function readAiHubColorTheme(): AiHubColorTheme {
  try {
    return localStorage.getItem(AI_HUB_COLOR_THEME_KEY) === 'emerald'
      ? 'emerald'
      : 'classic'
  } catch {
    return 'classic'
  }
}

export function writeAiHubColorTheme(theme: AiHubColorTheme): void {
  try {
    localStorage.setItem(AI_HUB_COLOR_THEME_KEY, theme)
  } catch {
    /* ignore quota / private mode */
  }
  window.dispatchEvent(
    new CustomEvent<AiHubColorTheme>(AI_HUB_COLOR_THEME_EVENT, { detail: theme }),
  )
}

export function useAiHubColorTheme() {
  const [theme, setTheme] = useState<AiHubColorTheme>(() => readAiHubColorTheme())

  useEffect(() => {
    const sync = (next: AiHubColorTheme) => setTheme(next)
    const onStorage = (event: StorageEvent) => {
      if (event.key === AI_HUB_COLOR_THEME_KEY) {
        sync(event.newValue === 'emerald' ? 'emerald' : 'classic')
      }
    }
    const onCustom = (event: Event) => {
      const detail = (event as CustomEvent<AiHubColorTheme>).detail
      sync(detail === 'emerald' ? 'emerald' : 'classic')
    }
    window.addEventListener('storage', onStorage)
    window.addEventListener(AI_HUB_COLOR_THEME_EVENT, onCustom)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(AI_HUB_COLOR_THEME_EVENT, onCustom)
    }
  }, [])

  const toggle = () => {
    const next: AiHubColorTheme = theme === 'classic' ? 'emerald' : 'classic'
    writeAiHubColorTheme(next)
    setTheme(next)
  }

  return { theme, toggle }
}
