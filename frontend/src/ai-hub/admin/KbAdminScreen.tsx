import { useCallback, useEffect, useRef, useState, type DragEvent, type FormEvent } from 'react'
import {
  ensureDevSession,
  isAuthErrorMessage,
  resetDevSessionCache,
} from '../../auth/ensureDevSession'
import { Button, Card, StatusBadge } from '../../components'
import {
  AssistantAdminApiError,
  createAssistantKb,
  deleteAssistantKb,
  deleteAssistantKbDocument,
  getAssistantKb,
  listAssistantKbs,
  reindexAssistantKb,
  startAssistantKbCrawl,
  uploadAssistantKbDocument,
  type AssistantCrawlJob,
  type AssistantKb,
  type AssistantKbDocument,
} from './api/assistantAdmin'
import {
  deleteKnowledgeBase,
  deleteKnowledgeDocument,
  getKnowledgeBase,
  KnowledgeBaseApiError,
  listKnowledgeBases,
  reindexKnowledgeBase,
  uploadKnowledgeDocument,
  type KnowledgeBase,
  type KnowledgeBaseDocument,
  type KnowledgeBaseStatus,
  type WebhookStatus,
} from './api/kbAdmin'

interface KbAdminScreenProps {
  canEdit?: boolean
  demoKb?: UnifiedKb
}
type KbKind = 'cc' | 'assistant'
type UnifiedKey = `${KbKind}:${number}`

interface UnifiedDocument {
  id: number
  filename: string
  size_bytes: number
  status: string
  index_percent: number
  source_label: string
  readonly?: boolean
  url?: string
  status_message?: string
}

interface UnifiedKb {
  key: UnifiedKey
  kind: KbKind
  id: number
  name: string
  description: string
  source: string
  source_label: string
  module_label: string
  status: KnowledgeBaseStatus | string
  status_message: string
  document_count: number
  index_percent: number
  webhook_status: WebhookStatus | string
  webhook_label: string
  readonly?: boolean
  documents?: UnifiedDocument[]
  start_url?: string
  crawl_depth?: number
  max_pages?: number
  ignore_robots?: boolean
  allowed_hosts?: string[]
  latest_job?: AssistantCrawlJob | null
}

function statusBadge(status: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (status === 'ready') return 'success'
  if (status === 'indexing' || status === 'crawling' || status === 'queued') return 'info'
  if (status === 'error' || status === 'failed') return 'danger'
  if (status === 'idle') return 'warning'
  return 'neutral'
}

function statusLabel(status: string): string {
  if (status === 'ready') return 'Индекс актуален'
  if (status === 'indexing' || status === 'crawling') return 'Индексация…'
  if (status === 'queued') return 'В очереди'
  if (status === 'error' || status === 'failed') return 'Ошибка индекса'
  return 'Ожидает индексации'
}

function webhookBadge(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'OK') return 'success'
  if (status === 'ERROR') return 'danger'
  return 'neutral'
}

function sourceBadge(source: string): 'info' | 'neutral' {
  return source === 'suz_bitrix' || source === 'website' ? 'info' : 'neutral'
}

function docPercent(status: string, indexPercent?: number): number {
  if (typeof indexPercent === 'number') return indexPercent
  if (status === 'indexed' || status === 'ready') return 100
  return 0
}

function indexFromDocs(documents: UnifiedDocument[], status: string, documentCount: number): number {
  if (!documents.length) return status === 'ready' && documentCount ? 100 : 0
  return Math.round(documents.reduce((sum, doc) => sum + doc.index_percent, 0) / documents.length)
}

function fromCcKb(kb: KnowledgeBase): UnifiedKb {
  const isSuz = kb.source === 'suz_bitrix'
  const documents = (kb.documents ?? []).map((doc: KnowledgeBaseDocument) => ({
    id: doc.id,
    filename: doc.filename,
    size_bytes: doc.size_bytes,
    status: doc.status,
    index_percent: docPercent(doc.status, doc.index_percent),
    source_label: kb.source_label || (isSuz ? 'СУЗ Битрикс' : 'Ручная загрузка'),
    readonly: Boolean(isSuz),
  }))
  return {
    key: `cc:${kb.id}`,
    kind: 'cc',
    id: kb.id,
    name: kb.name,
    description: kb.description || '',
    source: kb.source,
    source_label: kb.source_label || (isSuz ? 'СУЗ Битрикс' : 'Ручная загрузка'),
    module_label: 'КЦ',
    status: kb.status,
    status_message: kb.status_message || '',
    document_count: kb.document_count,
    index_percent: typeof kb.index_percent === 'number'
      ? kb.index_percent
      : indexFromDocs(documents, kb.status, kb.document_count),
    webhook_status: kb.webhook_status || 'IDLE',
    webhook_label: kb.webhook_label || '—',
    readonly: Boolean(kb.readonly || isSuz),
    documents: kb.documents ? documents : undefined,
  }
}

function fromAssistantKb(kb: AssistantKb): UnifiedKb {
  const isWebsite = kb.source === 'website'
  const documents = (kb.documents ?? []).map((doc: AssistantKbDocument) => ({
    id: doc.id,
    filename: doc.filename,
    size_bytes: doc.size_bytes,
    status: doc.status,
    index_percent: docPercent(doc.status, doc.index_percent),
    source_label: doc.source_label || (isWebsite ? 'Сайт' : 'Ручная загрузка'),
    readonly: Boolean(doc.readonly || isWebsite),
    url: doc.url || doc.permalink,
    status_message: doc.status_message || '',
  }))
  return {
    key: `assistant:${kb.id}`,
    kind: 'assistant',
    id: kb.id,
    name: kb.name,
    description: kb.description || '',
    source: kb.source || 'manual',
    source_label: kb.source_label || (isWebsite ? 'Сайт' : 'Ручная загрузка'),
    module_label: 'Ассистент',
    status: kb.status,
    status_message: kb.status_message || '',
    document_count: kb.document_count,
    index_percent: typeof kb.index_percent === 'number'
      ? kb.index_percent
      : indexFromDocs(documents, String(kb.status), kb.document_count),
    webhook_status: 'IDLE',
    webhook_label: '—',
    readonly: false,
    documents: kb.documents ? documents : undefined,
    start_url: kb.start_url || '',
    crawl_depth: kb.crawl_depth ?? 1,
    max_pages: kb.max_pages ?? 15,
    ignore_robots: Boolean(kb.ignore_robots),
    allowed_hosts: kb.allowed_hosts || [],
    latest_job: kb.latest_job ?? null,
  }
}

function formatKbError(error: unknown, fallback: string): string {
  const code = error instanceof Error ? error.message : ''
  if (
    error instanceof KnowledgeBaseApiError
    || error instanceof AssistantAdminApiError
    || isAuthErrorMessage(code)
  ) {
    if (code === 'authentication_required' || /401/.test(code)) {
      return 'Сессия Django истекла. Нажмите «Повторить» — вход выполнится автоматически.'
    }
    if (code === 'csrf_failed' || /csrf/i.test(code)) {
      return 'Сбой CSRF-токена после входа. Нажмите «Повторить».'
    }
    if (code === 'permission_denied') {
      return 'Недостаточно прав для этой операции.'
    }
    if (error instanceof KnowledgeBaseApiError || error instanceof AssistantAdminApiError) {
      return code
    }
  }
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function makeKey(kind: KbKind, id: number): UnifiedKey {
  return `${kind}:${id}`
}

function crawlNeedsPoll(job?: AssistantCrawlJob | null): boolean {
  return Boolean(job && ['queued', 'crawling', 'indexing'].includes(String(job.status)))
}

function kbNeedsPoll(kb: UnifiedKb | null): boolean {
  if (!kb) return false
  if (kb.status === 'indexing' || crawlNeedsPoll(kb.latest_job)) return true
  return (kb.documents ?? []).some(
    (doc) => doc.status === 'uploaded' || (doc.index_percent > 0 && doc.index_percent < 100),
  )
}

function IndexBar({
  percent,
  flash,
  compact,
}: {
  percent: number
  flash?: boolean
  compact?: boolean
}) {
  const value = Math.max(0, Math.min(100, percent))
  return (
    <div
      className={`kb-admin__bar${compact ? ' kb-admin__bar--compact' : ''}${flash ? ' is-complete' : ''}${value > 0 && value < 100 ? ' is-active' : ''}`}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={value}
      data-testid="kb-index-bar"
    >
      <span className="kb-admin__bar-fill" style={{ width: `${value}%` }} />
      <strong>{value}%</strong>
    </div>
  )
}

export function KbAdminScreen({ canEdit = true, demoKb }: KbAdminScreenProps) {
  const [items, setItems] = useState<UnifiedKb[]>(demoKb ? [demoKb] : [])
  const [selectedKey, setSelectedKey] = useState<UnifiedKey | null>(demoKb?.key ?? null)
  const [selected, setSelected] = useState<UnifiedKb | null>(demoKb ?? null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [createSource, setCreateSource] = useState<'manual' | 'website'>('manual')
  const [startUrl, setStartUrl] = useState('')
  const [allowedHosts, setAllowedHosts] = useState('')
  const [crawlDepth, setCrawlDepth] = useState('1')
  const [maxPages, setMaxPages] = useState('15')
  const [ignoreRobots, setIgnoreRobots] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(!demoKb)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const [pendingNames, setPendingNames] = useState<string[]>([])
  const [flashReady, setFlashReady] = useState(false)
  const [flashDocIds, setFlashDocIds] = useState<number[]>([])
  const fileInputRef = useRef<HTMLInputElement>(null)
  const selectedKeyRef = useRef<UnifiedKey | null>(null)
  const prevIndexRef = useRef(0)
  const prevDocIndexRef = useRef<Record<number, number>>({})

  useEffect(() => {
    selectedKeyRef.current = selectedKey
  }, [selectedKey])

  const loadDetail = useCallback(async (key: UnifiedKey): Promise<UnifiedKb> => {
    const [kind, rawId] = key.split(':') as [KbKind, string]
    const id = Number(rawId)
    if (kind === 'assistant') {
      return fromAssistantKb(await getAssistantKb(id))
    }
    return fromCcKb(await getKnowledgeBase(id))
  }, [])

  const refreshList = useCallback(async (preferKey?: UnifiedKey | null) => {
    const [ccResult, assistantResult] = await Promise.allSettled([
      listKnowledgeBases(),
      listAssistantKbs(),
    ])
    const ccItems = ccResult.status === 'fulfilled' ? ccResult.value : []
    const assistantItems = assistantResult.status === 'fulfilled' ? assistantResult.value : []
    if (ccResult.status === 'rejected' && assistantResult.status === 'rejected') {
      throw ccResult.reason
    }
    const next = [
      ...assistantItems.map(fromAssistantKb),
      ...ccItems.map(fromCcKb),
    ].sort((a, b) => a.name.localeCompare(b.name, 'ru'))
    setItems(next)
    const targetKey = preferKey ?? selectedKeyRef.current ?? next[0]?.key ?? null
    setSelectedKey(targetKey)
    if (targetKey == null) {
      setSelected(null)
      return null
    }
    const detail = await loadDetail(targetKey)
    setSelected(detail)
    setItems((current) =>
      current.map((item) => (item.key === detail.key
        ? {
            ...item,
            status: detail.status,
            status_message: detail.status_message,
            document_count: detail.document_count,
            index_percent: detail.index_percent,
            source_label: detail.source_label,
            webhook_status: detail.webhook_status,
            webhook_label: detail.webhook_label,
            latest_job: detail.latest_job,
          }
        : item)),
    )
    return detail
  }, [loadDetail])

  const loadInitial = useCallback(async (forceRelogin = false) => {
    setLoading(true)
    setError('')
    try {
      if (forceRelogin) resetDevSessionCache()
      let ok = await ensureDevSession(forceRelogin)
      if (!ok) {
        resetDevSessionCache()
        ok = await ensureDevSession(true)
      }
      if (!ok) {
        setError(
          'Нет сессии Django. Нажмите «Повторить». Проверьте, что API на :8001 запущен.',
        )
        return
      }
      await refreshList()
    } catch (requestError) {
      const message = formatKbError(requestError, 'Не удалось загрузить базы знаний')
      if (isAuthErrorMessage(message) || isAuthErrorMessage(String(requestError))) {
        resetDevSessionCache()
        const ok = await ensureDevSession(true)
        if (ok) {
          try {
            await refreshList()
            setError('')
            return
          } catch (retryError) {
            setError(formatKbError(retryError, 'Не удалось загрузить базы знаний'))
            return
          }
        }
      }
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [refreshList])

  useEffect(() => {
    if (demoKb) {
      setLoading(false)
      return
    }
    void loadInitial(false)
  }, [demoKb, loadInitial])

  const applyDetail = useCallback((detail: UnifiedKb) => {
    const prevIndex = prevIndexRef.current
    const prevDocs = prevDocIndexRef.current
    const nextDocs: Record<number, number> = {}
    const completed: number[] = []
    for (const doc of detail.documents ?? []) {
      nextDocs[doc.id] = doc.index_percent
      if (doc.index_percent >= 100 && (prevDocs[doc.id] ?? 0) < 100) {
        completed.push(doc.id)
      }
    }
    prevIndexRef.current = detail.index_percent
    prevDocIndexRef.current = nextDocs
    if (detail.index_percent >= 100 && prevIndex < 100) {
      setFlashReady(true)
      window.setTimeout(() => setFlashReady(false), 1800)
      setNotice('Индексация завершена. Документы доступны для поиска.')
    }
    if (completed.length) {
      setFlashDocIds((current) => [...current, ...completed])
      window.setTimeout(() => {
        setFlashDocIds((current) => current.filter((id) => !completed.includes(id)))
      }, 1800)
    }
    setSelected(detail)
    setItems((current) =>
      current.map((item) =>
        item.key === detail.key
          ? {
              ...item,
              status: detail.status,
              status_message: detail.status_message,
              document_count: detail.document_count,
              index_percent: detail.index_percent,
              latest_job: detail.latest_job,
            }
          : item,
      ),
    )
  }, [])

  const pollKey = selected?.key ?? null
  const shouldPoll = !demoKb && kbNeedsPoll(selected)

  useEffect(() => {
    if (!pollKey || !shouldPoll) return
    let cancelled = false
    const tick = async () => {
      try {
        const detail = await loadDetail(pollKey)
        if (!cancelled) applyDetail(detail)
      } catch {
        /* keep polling */
      }
    }
    void tick()
    const timer = window.setInterval(() => { void tick() }, 800)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [pollKey, shouldPoll, loadDetail, applyDetail])

  const runKbAction = async (action: () => Promise<void>, fallback: string) => {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await action()
    } catch (requestError) {
      const message = formatKbError(requestError, fallback)
      const raw = requestError instanceof Error ? requestError.message : ''
      if (isAuthErrorMessage(message) || isAuthErrorMessage(raw)) {
        resetDevSessionCache()
        const ok = await ensureDevSession()
        if (ok) {
          try {
            await action()
            return
          } catch (retryError) {
            setError(formatKbError(retryError, fallback))
            return
          }
        }
      }
      setError(message)
    } finally {
      setBusy(false)
    }
  }

  const selectKb = async (key: UnifiedKey) => {
    setSelectedKey(key)
    setNotice('')
    await runKbAction(async () => {
      setSelected(await loadDetail(key))
    }, 'Не удалось открыть базу знаний')
  }

  const createKb = async (event: FormEvent) => {
    event.preventDefault()
    if (!canEdit || !name.trim() || busy) return
    if (createSource === 'website' && !startUrl.trim()) return
    const nextName = name.trim()
    const nextDescription = description.trim()
    const hosts = allowedHosts.split(/[,;\s]+/).map((item) => item.trim()).filter(Boolean)
    await runKbAction(async () => {
      const created = await createAssistantKb({
        name: nextName,
        description: nextDescription,
        source: createSource,
        start_url: createSource === 'website' ? startUrl.trim() : undefined,
        depth: Number(crawlDepth) || 1,
        max_pages: Number(maxPages) || 15,
        ignore_robots: ignoreRobots,
        allowed_hosts: createSource === 'website' ? hosts : undefined,
      })
      setName('')
      setDescription('')
      setStartUrl('')
      setAllowedHosts('')
      setCreateSource('manual')
      setShowCreate(false)
      await refreshList(makeKey('assistant', created.id))
      setNotice(`БЗ «${created.name}» создана (появится в чате).`)
    }, 'Не удалось создать базу знаний')
  }

  const onStartCrawl = async () => {
    if (!canEdit || !selected || selected.kind !== 'assistant' || busy) return
    const current = selected
    const hosts = current.allowed_hosts?.length
      ? current.allowed_hosts
      : allowedHosts.split(/[,;\s]+/).map((item) => item.trim()).filter(Boolean)
    await runKbAction(async () => {
      const result = await startAssistantKbCrawl(current.id, {
        start_url: current.start_url || startUrl.trim(),
        depth: current.crawl_depth ?? (Number(crawlDepth) || 1),
        max_pages: current.max_pages ?? (Number(maxPages) || 15),
        ignore_robots: current.ignore_robots ?? ignoreRobots,
        allowed_hosts: hosts,
      })
      applyDetail(fromAssistantKb(result.knowledge_base))
      setNotice('Обход сайта запущен. Статус обновляется сам.')
    }, 'Не удалось запустить обход сайта')
  }

  const uploadFiles = async (files: FileList | File[] | null | undefined) => {
    if (!canEdit || !selected || selected.readonly || busy) return
    const list = files ? [...files] : []
    if (!list.length) return
    const current = selected
    setPendingNames(list.map((file) => file.name))
    await runKbAction(async () => {
      if (current.kind === 'assistant') {
        for (const file of list) {
          const result = await uploadAssistantKbDocument(current.id, file, { reindex: false })
          applyDetail(fromAssistantKb(result.knowledge_base))
          setPendingNames((names) => names.filter((item) => item !== file.name))
        }
        applyDetail(fromAssistantKb(await reindexAssistantKb(current.id)))
      } else {
        for (const file of list) {
          const result = await uploadKnowledgeDocument(current.id, file)
          applyDetail(fromCcKb(result.knowledge_base))
          setPendingNames((names) => names.filter((item) => item !== file.name))
        }
      }
      setPendingNames([])
      setNotice(
        list.length === 1
          ? `Файл «${list[0].name}» загружен. Индексация идёт — проценты ниже обновляются сами.`
          : `Загружено файлов: ${list.length}. Индексация идёт — проценты ниже обновляются сами.`,
      )
    }, 'Не удалось загрузить документ')
    setPendingNames([])
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const onReindex = async () => {
    if (!canEdit || !selected || selected.readonly || busy) return
    const current = selected
    await runKbAction(async () => {
      if (current.kind === 'assistant') {
        applyDetail(fromAssistantKb(await reindexAssistantKb(current.id)))
      } else {
        applyDetail(fromCcKb(await reindexKnowledgeBase(current.id)))
      }
      setNotice('Переиндексация запущена. Полоска процентов обновляется сама.')
    }, 'Не удалось выполнить переиндексацию')
  }

  const onDeleteKb = async () => {
    if (!canEdit || !selected || selected.readonly || busy) return
    const current = selected
    await runKbAction(async () => {
      if (current.kind === 'assistant') {
        await deleteAssistantKb(current.id)
      } else {
        await deleteKnowledgeBase(current.id)
      }
      await refreshList()
      setNotice('База знаний удалена.')
    }, 'Не удалось удалить базу знаний')
  }

  const onDeleteDocument = async (documentId: number) => {
    if (!canEdit || !selected || selected.readonly || busy) return
    const current = selected
    await runKbAction(async () => {
      if (current.kind === 'assistant') {
        setSelected(fromAssistantKb(await deleteAssistantKbDocument(current.id, documentId)))
      } else {
        setSelected(fromCcKb(await deleteKnowledgeDocument(current.id, documentId)))
      }
      await refreshList(current.key)
    }, 'Не удалось удалить документ')
  }

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragOver(false)
    void uploadFiles(event.dataTransfer.files)
  }

  if (loading) {
    return <Card className="kb-admin-loading">Загрузка баз знаний…</Card>
  }

  const webhookStatus = selected?.webhook_status ?? 'IDLE'
  const webhookLabel = selected?.webhook_label ?? '—'
  const indexPercent = selected?.index_percent ?? 0
  const isSuz = Boolean(selected?.readonly || selected?.source === 'suz_bitrix')
  const isWebsite = selected?.source === 'website'
  const crawlJob = selected?.latest_job ?? null

  return (
    <div className="kb-admin" data-testid="kb-admin-screen">
      {error && (
        <Card className="kb-admin__error" role="alert" data-testid="kb-admin-error">
          <div className="kb-admin__error-main">
            <strong>Уведомление</strong>
            <span>{error}</span>
          </div>
          <div className="kb-admin__error-actions">
            <Button type="button" variant="ghost" onClick={() => void loadInitial(true)}>
              Повторить
            </Button>
            <Button type="button" variant="ghost" onClick={() => setError('')}>
              Скрыть
            </Button>
          </div>
        </Card>
      )}
      {notice && !error && (
        <Card className="kb-admin__notice" role="status" data-testid="kb-admin-notice">
          <span>{notice}</span>
          <Button type="button" variant="ghost" onClick={() => setNotice('')}>
            Закрыть
          </Button>
        </Card>
      )}
      <div className="kb-admin__layout">
        <Card className="kb-admin__list">
          <header>
            <div>
              <h2>Базы знаний</h2>
              <p>Ассистент, КЦ и СУЗ Битрикс — один список</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              disabled={busy || loading}
              onClick={() => void loadInitial(true)}
              data-testid="kb-refresh-list"
            >
              Обновить
            </Button>
          </header>
          <div className="kb-admin__create-bar">
            <Button
              type="button"
              disabled={!canEdit || busy}
              onClick={() => setShowCreate((value) => !value)}
              data-testid="kb-create-toggle"
            >
              + Создать БЗ
            </Button>
          </div>
          {showCreate && (
            <form className="kb-admin__create" onSubmit={(event) => void createKb(event)}>
              <label>
                <span>Источник</span>
                <select
                  value={createSource}
                  disabled={!canEdit || busy}
                  onChange={(event) => setCreateSource(event.target.value as 'manual' | 'website')}
                  data-testid="kb-create-source"
                >
                  <option value="manual">Файлы</option>
                  <option value="website">Сайт</option>
                </select>
              </label>
              <label>
                <span>Название</span>
                <input
                  value={name}
                  disabled={!canEdit || busy}
                  placeholder="Например: HR policies"
                  onChange={(event) => setName(event.target.value)}
                  data-testid="kb-create-name"
                />
              </label>
              <label>
                <span>Описание</span>
                <input
                  value={description}
                  disabled={!canEdit || busy}
                  placeholder="Краткое описание"
                  onChange={(event) => setDescription(event.target.value)}
                />
              </label>
              {createSource === 'website' && (
                <>
                  <label>
                    <span>URL сайта</span>
                    <input
                      value={startUrl}
                      disabled={!canEdit || busy}
                      placeholder="https://www.belarusbank.by"
                      onChange={(event) => {
                        const next = event.target.value
                        setStartUrl(next)
                        try {
                          const host = new URL(next).hostname.replace(/^www\./i, '')
                          if (host && !allowedHosts.trim()) setAllowedHosts(host)
                        } catch {
                          /* keep hosts as typed */
                        }
                      }}
                      data-testid="kb-create-start-url"
                    />
                  </label>
                  <label>
                    <span>Разрешённые домены</span>
                    <input
                      value={allowedHosts}
                      disabled={!canEdit || busy}
                      placeholder="belarusbank.by"
                      onChange={(event) => setAllowedHosts(event.target.value)}
                      data-testid="kb-create-allowed-hosts"
                    />
                  </label>
                  <label>
                    <span>Глубина</span>
                    <input
                      type="number"
                      min={0}
                      max={10}
                      value={crawlDepth}
                      disabled={!canEdit || busy}
                      onChange={(event) => setCrawlDepth(event.target.value)}
                    />
                    <small>Сколько кликов от главной: 0 — только она, 1 — ещё страницы со ссылок на ней.</small>
                  </label>
                  <label>
                    <span>Макс. страниц</span>
                    <input
                      type="number"
                      min={1}
                      max={200}
                      value={maxPages}
                      disabled={!canEdit || busy}
                      onChange={(event) => setMaxPages(event.target.value)}
                    />
                    <small>Сколько страниц максимум положить в базу. 15 — мало для большого сайта.</small>
                  </label>
                  <label className="kb-admin__check">
                    <input
                      type="checkbox"
                      checked={ignoreRobots}
                      disabled={!canEdit || busy}
                      onChange={(event) => setIgnoreRobots(event.target.checked)}
                      data-testid="kb-create-ignore-robots"
                    />
                    <span title="Сайт просит роботов не заходить на часть ссылок. Галочка — зайти всё равно.">
                      не слушать robots.txt
                    </span>
                  </label>
                </>
              )}
              <Button
                type="submit"
                disabled={!canEdit || busy || !name.trim() || (createSource === 'website' && !startUrl.trim())}
                data-testid="kb-create-submit"
              >
                Создать
              </Button>
            </form>
          )}
          <ul className="kb-admin__kb-list" data-testid="kb-list">
            {items.map((item) => (
              <li key={item.key}>
                <button
                  type="button"
                  className={item.key === selectedKey ? 'is-active' : undefined}
                  onClick={() => void selectKb(item.key)}
                  data-testid={`kb-item-${item.key}`}
                >
                  <span className="kb-admin__kb-meta">
                    <strong>{item.name}</strong>
                    <span className="kb-admin__kb-tags">
                      <StatusBadge status="neutral">{item.module_label}</StatusBadge>
                      <StatusBadge status={sourceBadge(item.source)}>
                        {item.source_label}
                      </StatusBadge>
                    </span>
                  </span>
                  <IndexBar percent={item.index_percent} compact flash={item.key === selectedKey && flashReady} />
                </button>
              </li>
            ))}
            {!items.length && (
              <li className="kb-admin__empty">
                <p>Список пуст или не загрузился с сервера.</p>
                <Button type="button" variant="secondary" disabled={busy || loading} onClick={() => void loadInitial(true)}>
                  Обновить список
                </Button>
              </li>
            )}
          </ul>
        </Card>
        <Card className="kb-admin__detail">
          {selected ? (
            <>
              <header>
                <div>
                  <h2>{selected.name}</h2>
                  <p>
                    {selected.description
                      || (isSuz
                        ? 'Статьи из интеграции СУЗ Битрикс (webhook).'
                        : isWebsite
                          ? 'Страницы сайта в индексе ассистента.'
                          : selected.kind === 'assistant'
                            ? 'Документы для ИИ-чата ассистента.'
                            : 'Документы для индекса суфлёра КЦ.')}
                  </p>
                </div>
                <span className="kb-admin__kb-tags">
                  <StatusBadge status="neutral">{selected.module_label}</StatusBadge>
                  <StatusBadge status={sourceBadge(selected.source)}>
                    {selected.source_label}
                  </StatusBadge>
                </span>
              </header>
              <section className="kb-admin__detail-stats admin-stats" aria-label="Статус выбранной БЗ">
                <Card className={flashReady ? 'is-index-ready' : undefined}>
                  <span>Индекс</span>
                  <strong data-testid="kb-stat-index">{indexPercent}%</strong>
                  <IndexBar percent={indexPercent} flash={flashReady} />
                  <small>{statusLabel(String(selected.status))}</small>
                </Card>
                <Card>
                  <span>{isWebsite ? 'Страниц' : 'Документов'}</span>
                  <strong data-testid="kb-stat-docs">{selected.document_count}</strong>
                  <small>В выбранной БЗ</small>
                </Card>
                <Card>
                  <span>Webhook СУЗ</span>
                  <strong data-testid="kb-stat-webhook">
                    <StatusBadge status={webhookBadge(String(webhookStatus))}>
                      {webhookLabel}
                    </StatusBadge>
                  </strong>
                  <small>{isSuz ? 'Интеграция Битрикс' : 'для СУЗ-БЗ'}</small>
                </Card>
              </section>
              {isWebsite && (
                <div className="kb-admin__suz-note" data-testid="kb-website-source">
                  <strong>Источник: сайт</strong>
                  <p>
                    Обход того же домена: {selected.start_url || 'URL не задан'}.
                    Глубина {selected.crawl_depth ?? 1} (кликов от главной), не больше {selected.max_pages ?? 15} страниц.
                    Разрешённые хосты: {(selected.allowed_hosts ?? []).join(', ') || '—'}.
                  </p>
                  {crawlJob && (
                    <div className="kb-admin__crawl-card" data-testid="kb-crawl-status">
                      <StatusBadge status={statusBadge(String(crawlJob.status))}>
                        {crawlJob.status}
                      </StatusBadge>
                      <span>страниц {crawlJob.pages_ok}</span>
                      <span>4xx {crawlJob.pages_4xx}</span>
                      <span>5xx {crawlJob.pages_5xx}</span>
                      {crawlJob.elapsed_seconds != null && (
                        <span>{crawlJob.elapsed_seconds} с</span>
                      )}
                      <small>{crawlJob.status_message}</small>
                    </div>
                  )}
                  <div className="kb-admin__actions">
                    <Button
                      disabled={!canEdit || busy || crawlNeedsPoll(crawlJob)}
                      onClick={() => void onStartCrawl()}
                      data-testid="kb-crawl-start"
                    >
                      Запустить обход
                    </Button>
                    <Button variant="ghost" disabled={!canEdit || busy} onClick={() => void onDeleteKb()}>
                      Удалить БЗ
                    </Button>
                  </div>
                </div>
              )}
              {isSuz ? (
                <div className="kb-admin__suz-note" data-testid="kb-suz-readonly">
                  <strong>Источник: СУЗ Битрикс</strong>
                  <p>
                    Документы поступают через webhook. Ручная загрузка недоступна.
                    БЗ ассистента (те, что в выпадашке чата) — в этом же списке слева с меткой «Ассистент».
                  </p>
                </div>
              ) : isWebsite ? null : (
                <div
                  className={`kb-admin__dropzone${dragOver ? ' is-dragover' : ''}`}
                  data-testid="kb-upload-zone"
                  onDragEnter={(event) => { event.preventDefault(); setDragOver(true) }}
                  onDragOver={(event) => { event.preventDefault(); setDragOver(true) }}
                  onDragLeave={(event) => { event.preventDefault(); setDragOver(false) }}
                  onDrop={onDrop}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.doc,.docx,.txt,.rtf,.xlsx,.pptx,.png,.jpg,.jpeg"
                    multiple
                    hidden
                    disabled={!canEdit || busy}
                    onChange={(event) => void uploadFiles(event.target.files)}
                    data-testid="kb-upload-input"
                  />
                  <strong>Ручная загрузка документов</strong>
                  <p>
                    {selected.kind === 'assistant'
                      ? 'Файлы попадут в чат ассистента (выпадающий список БЗ).'
                      : 'Файлы попадут в индекс КЦ / суфлёра.'}
                  </p>
                  <div className="kb-admin__actions">
                    <div>
                      <Button disabled={!canEdit || busy} onClick={() => fileInputRef.current?.click()} data-testid="kb-upload-button">
                        Загрузить файлы
                      </Button>
                      <Button
                        variant="secondary"
                        disabled={!canEdit || busy || !(selected.documents ?? []).length}
                        onClick={() => void onReindex()}
                        data-testid="kb-reindex-button"
                      >
                        Переиндексировать
                      </Button>
                    </div>
                    <Button variant="ghost" disabled={!canEdit || busy} onClick={() => void onDeleteKb()}>
                      Удалить БЗ
                    </Button>
                  </div>
                </div>
              )}
              {(selected.status === 'indexing' || crawlNeedsPoll(crawlJob) || pendingNames.length > 0) && (
                <div className="kb-admin__progress" data-testid="kb-indexing">
                  <IndexBar percent={indexPercent} flash={flashReady} />
                  <p className="kb-admin__status-msg kb-admin__status-msg--indexing">
                    {selected.status_message || 'Индексация выполняется…'}
                  </p>
                </div>
              )}
              {selected.status_message && selected.status !== 'indexing' && !pendingNames.length && (
                <p className="kb-admin__status-msg">{selected.status_message}</p>
              )}
              <div className="kb-admin__table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{isWebsite ? 'Страница' : 'Документ'}</th>
                      <th scope="col">Источник</th>
                      <th scope="col">%</th>
                      {!isSuz && !isWebsite && <th scope="col">Действия</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {(selected.documents ?? []).map((document) => (
                      <tr key={document.id}>
                        <td>
                          <strong>{document.filename}</strong>
                          {document.url && <small>{document.url}</small>}
                          {document.status_message && (
                            <small>{document.status_message}</small>
                          )}
                        </td>
                        <td>
                          <StatusBadge status="neutral">{document.source_label}</StatusBadge>
                        </td>
                        <td>
                          <IndexBar
                            percent={document.index_percent}
                            compact
                            flash={flashDocIds.includes(document.id)}
                          />
                        </td>
                        {!isSuz && !isWebsite && (
                          <td>
                            <Button
                              variant="ghost"
                              disabled={!canEdit || busy || document.readonly}
                              onClick={() => void onDeleteDocument(document.id)}
                            >
                              Удалить
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                    {!(selected.documents ?? []).length && (
                      <tr>
                        <td colSpan={isSuz || isWebsite ? 3 : 4} className="kb-admin__empty">
                          {isWebsite
                            ? 'Страниц пока нет — запустите обход сайта.'
                            : isSuz
                              ? 'Статей из СУЗ пока нет — ожидается webhook Битрикс.'
                              : 'Документов пока нет — загрузите PDF или DOCX в зону выше.'}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="kb-admin__empty-detail">
              <h2>Выберите или создайте базу знаний</h2>
              <p>Ассистент (чат), КЦ и СУЗ Битрикс — в одном списке.</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
