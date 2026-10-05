import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Button, Card, HintCard, StatusBadge } from '../../components'
import {
  previewQuQuery,
  type QuPreviewResult,
} from './api/quPreview'
import {
  createQuExample,
  deleteQuExample,
  listQuDocuments,
  listQuExamples,
  reviewQuExample,
  type QuDocumentOption,
  type QuExample,
} from './api/quAdmin'

type QuTab = 'dataset' | 'moderation' | 'preview'

function readTabFromUrl(): QuTab {
  const tab = new URLSearchParams(window.location.search).get('tab')
  if (tab === 'moderation' || tab === 'dataset' || tab === 'preview') {
    return tab
  }
  return 'dataset'
}

function setTabInUrl(tab: QuTab) {
  const url = new URL(window.location.href)
  if (tab === 'dataset') {
    url.searchParams.delete('tab')
  } else {
    url.searchParams.set('tab', tab)
  }
  window.history.replaceState({}, '', `${url.pathname}${url.search}`)
}

function sourceLabel(source: string): string {
  if (source === 'dialog') return 'Диалог'
  if (source === 'asr_qa') return 'QA ASR'
  return 'Вручную'
}

function channelLabel(channel: string): string {
  if (channel === 'telephony' || channel === 'phone') return 'Телефония'
  if (channel === 'chat' || channel === 'online_chat' || channel === 'widget') return 'Онлайн-чат'
  return channel || '—'
}

function readPreviewQueryFromUrl(): string {
  return new URLSearchParams(window.location.search).get('q') || ''
}

function setPreviewQueryInUrl(query: string) {
  const url = new URL(window.location.href)
  const trimmed = query.trim()
  if (trimmed) {
    url.searchParams.set('q', trimmed)
  } else {
    url.searchParams.delete('q')
  }
  window.history.replaceState({}, '', `${url.pathname}${url.search}`)
}

export function QuPreviewScreen({
  canEdit = true,
  initialTab,
}: {
  canEdit?: boolean
  initialTab?: QuTab
}) {
  const [tab, setTab] = useState<QuTab>(() => initialTab ?? readTabFromUrl())
  const [previewQuery, setPreviewQuery] = useState(readPreviewQueryFromUrl)
  const [autoRunPreview, setAutoRunPreview] = useState(
    () => Boolean(readPreviewQueryFromUrl().trim()) && (initialTab ?? readTabFromUrl()) === 'preview',
  )

  const switchTab = (next: QuTab, query?: string) => {
    setTab(next)
    setTabInUrl(next)
    if (query != null) {
      setPreviewQuery(query)
      setPreviewQueryInUrl(query)
      setAutoRunPreview(next === 'preview' && Boolean(query.trim()))
    }
  }

  return (
    <div className="qu-admin" data-testid="qu-admin-screen">
      <div className="qu-admin__tabs" role="tablist" aria-label="Модуль понимания">
        <button type="button" className={tab === 'dataset' ? 'is-active' : ''} onClick={() => switchTab('dataset')}>
          Обучающая выборка
        </button>
        <button type="button" className={tab === 'moderation' ? 'is-active' : ''} onClick={() => switchTab('moderation')}>
          На модерации
        </button>
        <button type="button" className={tab === 'preview' ? 'is-active' : ''} onClick={() => switchTab('preview')}>
          Предпросмотр
        </button>
      </div>
      {tab === 'dataset' ? (
        <DatasetTab canEdit={canEdit} onPreview={(query) => switchTab('preview', query)} />
      ) : null}
      {tab === 'moderation' ? (
        <ModerationTab canEdit={canEdit} onPreview={(query) => switchTab('preview', query)} />
      ) : null}
      {tab === 'preview' ? (
        <PreviewTab
          query={previewQuery}
          onQueryChange={setPreviewQuery}
          autoRun={autoRunPreview}
          onAutoRunConsumed={() => setAutoRunPreview(false)}
        />
      ) : null}
    </div>
  )
}

function DatasetTab({
  canEdit,
  onPreview,
}: {
  canEdit: boolean
  onPreview: (query: string) => void
}) {
  const [items, setItems] = useState<QuExample[]>([])
  const [documents, setDocuments] = useState<QuDocumentOption[]>([])
  const [question, setQuestion] = useState('')
  const [intentId, setIntentId] = useState('')
  const [articleId, setArticleId] = useState('')
  const [synonyms, setSynonyms] = useState('')
  const [locale, setLocale] = useState('ru')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async () => {
    const [list, docs] = await Promise.all([
      listQuExamples('active'),
      listQuDocuments(),
    ])
    setItems(list.items)
    setDocuments(docs)
  }

  useEffect(() => {
    void load().catch((requestError: unknown) => {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить выборку')
    })
  }, [])

  const selectedDoc = documents.find((item) => String(item.article_id) === articleId)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canEdit || busy) return
    setBusy(true)
    setError('')
    try {
      await createQuExample({
        question,
        intent_id: intentId,
        article_id: articleId ? Number(articleId) : null,
        article_title: selectedDoc?.title || '',
        synonyms,
        locale,
      })
      setQuestion('')
      setIntentId('')
      setArticleId('')
      setSynonyms('')
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось сохранить эталон')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (item: QuExample) => {
    if (!canEdit) return
    setBusy(true)
    setError('')
    try {
      await deleteQuExample(item.id)
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось удалить эталон')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="qu-admin__stack">
      <div className="qu-admin__grid">
        <Card>
        <header>
          <div>
            <h2>Типовой запрос</h2>
          </div>
        </header>
        <form className="qu-admin__form" onSubmit={(event) => void submit(event)}>
          <label>
            <span>Запрос</span>
            <textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              rows={3}
              required
              disabled={!canEdit}
            />
          </label>
          <label>
            <span>Тема</span>
            <input
              value={intentId}
              onChange={(event) => setIntentId(event.target.value)}
              disabled={!canEdit}
            />
          </label>
          <label>
            <span>Документ КБ</span>
            <select value={articleId} onChange={(event) => setArticleId(event.target.value)} disabled={!canEdit}>
              <option value="">Не выбран</option>
              {documents.map((doc) => (
                <option key={doc.article_id} value={doc.article_id}>
                  {doc.title} · {doc.kb_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Синонимы</span>
            <input
              value={synonyms}
              onChange={(event) => setSynonyms(event.target.value)}
              disabled={!canEdit}
            />
          </label>
          <label>
            <span>Язык</span>
            <select value={locale} onChange={(event) => setLocale(event.target.value)} disabled={!canEdit}>
              <option value="ru">ru</option>
              <option value="en">en</option>
            </select>
          </label>
          {error ? <p className="qu-admin__error">{error}</p> : null}
          <Button type="submit" disabled={!canEdit || busy || !question.trim()}>
            {busy ? 'Сохранение…' : 'Добавить'}
          </Button>
        </form>
      </Card>
      <Card>
        <header>
          <div>
            <h2>Сохранённые запросы</h2>
          </div>
        </header>
        <div className="qu-admin__table-wrap">
          <table>
            <thead>
              <tr>
                <th>Запрос</th>
                <th>Тема</th>
                <th>Документ</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td>{item.question}</td>
                  <td>{item.intent_id || '—'}</td>
                  <td>{item.article_title || item.article_id || '—'}</td>
                  <td>
                    <div className="qu-admin__actions">
                      <Button
                        variant="ghost"
                        disabled={busy}
                        onClick={() => onPreview(item.question)}
                      >
                        Предпросмотр
                      </Button>
                      <Button variant="ghost" disabled={!canEdit || busy} onClick={() => void remove(item)}>
                        Удалить
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {items.length === 0 ? (
                <tr>
                  <td colSpan={4}>Пока нет типовых запросов.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </Card>
      </div>
    </div>
  )
}

function ModerationTab({
  canEdit,
  onPreview,
}: {
  canEdit: boolean
  onPreview: (query: string) => void
}) {
  const [items, setItems] = useState<QuExample[]>([])
  const [documents, setDocuments] = useState<QuDocumentOption[]>([])
  const [drafts, setDrafts] = useState<Record<number, { intent_id: string; article_id: string; admin_comment: string }>>({})
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)

  const load = async () => {
    const [list, docs] = await Promise.all([
      listQuExamples('pending_review'),
      listQuDocuments(),
    ])
    setItems(list.items)
    setDocuments(docs)
    setDrafts((current) => {
      const next = { ...current }
      for (const item of list.items) {
        if (!next[item.id]) {
          next[item.id] = {
            intent_id: item.intent_id,
            article_id: item.article_id ? String(item.article_id) : '',
            admin_comment: item.admin_comment,
          }
        }
      }
      return next
    })
  }

  useEffect(() => {
    void load().catch((requestError: unknown) => {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось загрузить очередь')
    })
  }, [])

  const review = async (item: QuExample, action: 'approve' | 'reject') => {
    if (!canEdit) return
    const draft = drafts[item.id] || { intent_id: '', article_id: '', admin_comment: '' }
    setBusyId(item.id)
    setError('')
    try {
      const selected = documents.find((doc) => String(doc.article_id) === draft.article_id)
      await reviewQuExample(item.id, {
        action,
        intent_id: draft.intent_id,
        article_id: draft.article_id ? Number(draft.article_id) : null,
        article_title: selected?.title || item.article_title,
        admin_comment: draft.admin_comment,
      })
      if (action === 'approve') {
        onPreview(item.question)
        return
      }
      await load()
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Не удалось обработать эталон')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="qu-admin__stack">
      {error ? <p className="qu-admin__error">{error}</p> : null}
      {items.map((item) => {
        const draft = drafts[item.id] || { intent_id: item.intent_id, article_id: '', admin_comment: item.admin_comment }
        return (
          <Card key={item.id}>
            <header>
              <div>
                <h2>{item.question}</h2>
                <p>
                  {sourceLabel(item.source)} · {channelLabel(item.channel)} · {item.operator_name || 'оператор не указан'}
                  {item.relevance_percent != null ? ` · ${item.relevance_percent}%` : ''}
                </p>
              </div>
            </header>
            {item.original_hint ? <p className="qu-admin__hint">Исходная подсказка: {item.original_hint}</p> : null}
            <div className="qu-admin__form">
              <label>
                <span>Тема</span>
                <input
                  value={draft.intent_id}
                  disabled={!canEdit}
                  onChange={(event) => setDrafts((current) => ({
                    ...current,
                    [item.id]: { ...draft, intent_id: event.target.value },
                  }))}
                />
              </label>
              <label>
                <span>Документ КБ</span>
                <select
                  value={draft.article_id}
                  disabled={!canEdit}
                  onChange={(event) => setDrafts((current) => ({
                    ...current,
                    [item.id]: { ...draft, article_id: event.target.value },
                  }))}
                >
                  <option value="">Не выбран</option>
                  {documents.map((doc) => (
                    <option key={doc.article_id} value={doc.article_id}>
                      {doc.title} · {doc.kb_name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                <span>Комментарий админа БЗ</span>
                <textarea
                  rows={2}
                  value={draft.admin_comment}
                  disabled={!canEdit}
                  onChange={(event) => setDrafts((current) => ({
                    ...current,
                    [item.id]: { ...draft, admin_comment: event.target.value },
                  }))}
                />
              </label>
              <div className="qu-admin__actions">
                <Button
                  disabled={!canEdit || busyId === item.id}
                  onClick={() => void review(item, 'approve')}
                >
                  Утвердить и проверить
                </Button>
                <Button
                  variant="ghost"
                  disabled={!canEdit || busyId === item.id}
                  onClick={() => void review(item, 'reject')}
                >
                  Отклонить
                </Button>
              </div>
            </div>
          </Card>
        )
      })}
      {items.length === 0 ? (
        <Card>
          <p>Очередь модерации пуста.</p>
        </Card>
      ) : null}
    </div>
  )
}

function PreviewTab({
  query,
  onQueryChange,
  autoRun,
  onAutoRunConsumed,
}: {
  query: string
  onQueryChange: (value: string) => void
  autoRun: boolean
  onAutoRunConsumed: () => void
}) {
  const [result, setResult] = useState<QuPreviewResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const runPreview = async (value: string) => {
    if (!value.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      setResult(await previewQuQuery(value.trim()))
    } catch (requestError) {
      setResult(null)
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Не удалось выполнить предпросмотр',
      )
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!autoRun || !query.trim()) return
    onAutoRunConsumed()
    void runPreview(query)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once when arriving from moderation
  }, [autoRun, query])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    await runPreview(query)
  }

  const empty = useMemo(() => result && result.documents.length === 0, [result])

  return (
    <div className="qu-preview" data-testid="qu-preview-form">
      <Card className="qu-preview__query-card">
        <header>
          <div>
            <h2>Тестовый запрос</h2>
            <p>Поиск по всем базам знаний: файлы ассистента, ручные КБ и СУЗ.</p>
          </div>
        </header>
        <form onSubmit={(event) => void submit(event)}>
          <label>
            <span>Запрос пользователя</span>
            <textarea
              aria-label="Запрос пользователя"
              value={query}
              rows={4}
              onChange={(event) => onQueryChange(event.target.value)}
            />
          </label>
          <div className="qu-preview__actions">
            <span>Индекс: <strong>все базы знаний</strong></span>
            <Button type="submit" disabled={!query.trim() || loading}>
              {loading ? 'Поиск…' : 'Предпросмотр'}
            </Button>
          </div>
        </form>
      </Card>

      {error && (
        <Card className="qu-preview__error" role="alert">
          <strong>Предпросмотр недоступен</strong>
          <span>{error}</span>
        </Card>
      )}

      {result?.hint?.text ? (
        <Card className="qu-preview__hint-card">
          <header>
            <div>
              <h2>Подсказка оператору</h2>
            </div>
            <StatusBadge status="success">{result.hint.relevance_percent}%</StatusBadge>
          </header>
          <HintCard
            title={result.hint.title}
            relevance={`${result.hint.relevance_percent}%`}
            relevancePercent={result.hint.relevance_percent}
            suzLink={
              result.hint.permalink
                ? { title: result.hint.title, href: result.hint.permalink }
                : null
            }
            defaultExpanded
          >
            {result.hint.text}
          </HintCard>
        </Card>
      ) : null}

      {result && (
        <Card className="qu-preview__results">
          <header>
            <div>
              <h2>Найденные документы</h2>
            </div>
            <StatusBadge status="neutral">
              Мин. порог {result.min_relevance_percent}%
            </StatusBadge>
          </header>
          {empty ? (
            <p className="qu-preview__empty">
              В активных базах знаний нет документов для этого запроса.
            </p>
          ) : (
            <div className="qu-preview__table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Документ</th>
                    <th scope="col">Релевантность</th>
                    <th scope="col">Совпавший пример</th>
                  </tr>
                </thead>
                <tbody>
                  {result.documents.map((document) => (
                    <tr key={`${document.article_id}-${document.chunk_index}`}>
                      <td>
                        <span className="qu-preview__rank">{document.rank}</span>
                        {document.permalink ? (
                          <a href={document.permalink} target="_blank" rel="noreferrer">
                            {document.title}
                          </a>
                        ) : document.title}
                        <small>
                          {document.kb_slug ? `${document.kb_slug} · ` : ''}
                          {document.snippet}
                        </small>
                      </td>
                      <td>
                        <StatusBadge
                          status={document.meets_min_relevance ? 'success' : 'warning'}
                        >
                          {document.relevance_percent}%
                        </StatusBadge>
                      </td>
                      <td>{document.matched_example}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
