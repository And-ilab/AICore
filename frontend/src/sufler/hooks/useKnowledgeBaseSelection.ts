import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  fetchAssistantKnowledgeBases,
  type AssistantKbOption,
} from '../../assistant/api/knowledgeBases'
import { ensureDevSession } from '../../auth/ensureDevSession'

export type KbCatalogStatus = 'loading' | 'ready' | 'error'

export function useKnowledgeBaseSelection() {
  const [catalog, setCatalog] = useState<AssistantKbOption[]>([])
  const [status, setStatus] = useState<KbCatalogStatus>('loading')
  const [selected, setSelected] = useState<Record<string, boolean>>({})
  const slugsRef = useRef<string[] | undefined>(undefined)

  const slugs = useMemo(
    () =>
      catalog
        .filter((kb) => selected[kb.id])
        .map((kb) => kb.slug),
    [catalog, selected],
  )

  slugsRef.current = status === 'ready' ? slugs : undefined

  useEffect(() => {
    let cancelled = false
    setStatus('loading')
    void (async () => {
      try {
        await ensureDevSession()
        const items = await fetchAssistantKnowledgeBases()
        if (cancelled) return
        setCatalog(items)
        setSelected(Object.fromEntries(items.map((kb) => [kb.id, true])))
        setStatus('ready')
      } catch {
        if (cancelled) return
        setCatalog([])
        setSelected({})
        setStatus('error')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const allSelected =
    catalog.length > 0 && catalog.every((kb) => selected[kb.id])
  const someSelected = catalog.some((kb) => selected[kb.id])

  const toggleAll = (checked: boolean) => {
    setSelected(Object.fromEntries(catalog.map((kb) => [kb.id, checked])))
  }

  const getKbSlugs = useCallback(() => slugsRef.current, [])

  return {
    catalog,
    status,
    selected,
    setSelected,
    slugs,
    allSelected,
    someSelected,
    toggleAll,
    getKbSlugs,
  }
}
