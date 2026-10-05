import { useEffect, useState, type ReactNode } from 'react'
import { operatorsApi } from '../api/managementApi'
import { ChatPlatformShell } from './ChatPlatformShell'
import type { ThemeKind } from '../arm/theme'

type ShellProps = React.ComponentProps<typeof ChatPlatformShell>

/**
 * Loads operator avatar for the shell header and persists uploads
 * to the current OperatorProfile (source of truth for the client widget).
 */
export function ChatPlatformShellWithAvatar({
  displayName,
  photoUrl: photoUrlProp,
  onPhotoChange: onPhotoChangeProp,
  ...rest
}: ShellProps & { children: ReactNode; themeKind?: ThemeKind }) {
  const storageKey = displayName ? `oc-avatar:${displayName}` : null
  const [photoUrl, setPhotoUrl] = useState<string | null>(() => {
    if (photoUrlProp) return photoUrlProp
    if (!storageKey) return null
    try {
      return localStorage.getItem(storageKey)
    } catch {
      return null
    }
  })
  const [uploadError, setUploadError] = useState<string | null>(null)

  useEffect(() => {
    if (photoUrlProp) {
      setPhotoUrl(photoUrlProp)
      return
    }
    let cancelled = false
    void operatorsApi
      .me(displayName || undefined)
      .then((profile) => {
        if (cancelled) return
        if (profile.photo_url) {
          setPhotoUrl(profile.photo_url)
          if (storageKey) {
            try {
              localStorage.setItem(storageKey, profile.photo_url)
            } catch {
              /* quota */
            }
          }
          return
        }
        if (storageKey) {
          try {
            const cached = localStorage.getItem(storageKey)
            if (cached) setPhotoUrl(cached)
          } catch {
            /* ignore */
          }
        }
      })
      .catch(() => {
        if (cancelled || !storageKey) return
        try {
          const cached = localStorage.getItem(storageKey)
          if (cached) setPhotoUrl(cached)
        } catch {
          /* ignore */
        }
      })
    return () => {
      cancelled = true
    }
  }, [displayName, photoUrlProp, storageKey])

  const onPhotoChange = (dataUrl: string) => {
    setPhotoUrl(dataUrl)
    setUploadError(null)
    if (storageKey) {
      try {
        localStorage.setItem(storageKey, dataUrl)
      } catch {
        /* quota */
      }
    }
    onPhotoChangeProp?.(dataUrl)
    void operatorsApi
      .updateMyPhoto(dataUrl, displayName || undefined)
      .then((profile) => {
        if (profile.photo_url) setPhotoUrl(profile.photo_url)
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : 'Не удалось сохранить фото'
        setUploadError(message)
      })
  }

  return (
    <ChatPlatformShell
      {...rest}
      displayName={displayName}
      photoUrl={photoUrl}
      onPhotoChange={onPhotoChange}
      photoError={uploadError}
    />
  )
}
