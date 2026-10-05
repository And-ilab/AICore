import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { BarChartView, DataTable, PieChartView } from './charts'
import {
  CHANNEL_OPTIONS,
  CLOSE_TOPICS,
  SUFLER_REPORT_IDS,
  type ReportViewMode,
} from './demoData'
import {
  CcReportsApiError,
  downloadCcExport,
  fetchBuilderTemplates,
  fetchCcCatalog,
  previewBuilder,
  saveBuilderTemplate,
  triggerBrowserDownload,
  type CatalogPayload,
  type CatalogReportMeta,
} from './api/ccReports'
import { fieldLabel, localizeCell, metricLabel, summaryLabel } from './labels'

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function toneForIndex(index: number): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  const tones = ['success', 'info', 'warning', 'danger', 'neutral'] as const
  return tones[index % tones.length]
}

function rowsToTable(
  rows: Record<string, unknown>[],
  columns?: { key: string; label: string }[],
): { headers: string[]; rows: string[][] } {
  if (!rows.length) return { headers: ['Нет данных'], rows: [['За выбранный период записей нет']] }
  const keys = columns?.length
    ? columns.map((item) => item.key)
    : Object.keys(rows[0]).filter(
        (key) => !['dialog_id', 'id', 'role', 'choice', 'outcome', 'channel_label', 'label', 'is_total', 'is_section'].includes(key),
      )
  const headerFor = (key: string) => {
    const fromColumn = columns?.find((item) => item.key === key)?.label
    if (fromColumn) return fromColumn
    if (key === 'operator') return 'Оператор'
    return fieldLabel(key)
  }
  return {
    headers: keys.map(headerFor),
    rows: rows.map((row) =>
      keys.map((key) => {
        if (key === 'operator') {
          const name = localizeCell(row[key])
          const role = String(row.role || '')
          if (role === 'supervisor') return `${name} · Супервизор`
          if (role === 'admin') return `${name} · Админ`
          return name
        }
        if (key === 'share_pct' || key === 'pct_10s' || key === 'pct_20s' || key === 'pct_30s' || key === 'pct_40s') {
          const raw = row[key]
          if (raw === null || raw === undefined || raw === '') return '—'
          const num = Number(raw)
          if (Number.isFinite(num)) return `${num.toFixed(2)}%`
        }
        return localizeCell(row[key])
      }),
    ),
  }
}

function downloadCsv(filename: string, headers: string[], rows: string[][]) {
  const csv = [headers, ...rows]
    .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
  triggerBrowserDownload(blob, filename.endsWith('.csv') ? filename : `${filename}.csv`)
}

const TOPIC_REPORTS = new Set<string>([])

const STATUS_REPORTS = new Set<string>([])

const GROUP_BY_OPTIONS: Record<string, Array<{ value: string; label: string }>> = {
  relevance: [
    { value: 'none', label: 'Без группировки' },
    { value: 'channel', label: 'По каналу' },
    { value: 'topic', label: 'По тематике' },
  ],
}

function chartCaption(reportId: string, viewMode: ReportViewMode): string {
  if (viewMode === 'table') return ''
  if (reportId === 'usefulness') return 'Количество отметок оператора по полезности подсказок'
  if (reportId === 'relevance') return 'Средняя релевантность подсказок суфлёра'
  if (reportId === 'chat-offline') return 'Распределение необработанных и отказных обращений'
  if (reportId === 'chat_history') return 'Распределение диалогов по статусам'
  if (reportId === 'chat-ratings') return 'Количество оценок клиентов по звёздам'
  if (reportId === 'chat-topics' || reportId === 'topics') {
    return 'Число закрытых диалогов по тематикам. «За прошлый период» — предыдущий интервал той же длины, что выбран в фильтре дат'
  }
  if (reportId === 'chat-operators') return 'Число диалогов по операторам'
  if (reportId === 'chat-period') return 'Число обращений по каналам'
  if (reportId === 'chat-sla') return 'Распределение времени первого ответа'
  if (reportId === 'correctness') return 'Доля отметок по корректности подсказок, %'
  return 'Значения по выбранному отчёту'
}

function ReportChartView({
  viewMode,
  reportId,
  chart,
  selectedLabel,
  table,
  onPieSelect,
}: {
  viewMode: ReportViewMode
  reportId: string
  chart: { label: string; value: number; pct?: number }[]
  selectedLabel: string
  table: { headers: string[]; rows: string[][] }
  onPieSelect?: (label: string) => void
}) {
  const pieData = chart.map((item, index) => ({
    label: item.label,
    value: item.value,
    pct: item.pct,
    tone: toneForIndex(index),
  }))
  const barCategories = chart.map((item) => item.label)
  const barSeries = [{ name: selectedLabel, data: chart.map((item) => item.value) }]
  const caption = chartCaption(reportId, viewMode)

  if (viewMode === 'table') {
    return <DataTable headers={table.headers} rows={table.rows} />
  }
  if (!chart.length) {
    return <DataTable headers={table.headers} rows={table.rows} />
  }
  return (
    <>
      {caption ? <p className="rpt-chart-caption">{caption}</p> : null}
      {viewMode === 'pie' ? <PieChartView data={pieData} onSelect={onPieSelect} /> : null}
      {viewMode === 'bar' ? (
        <BarChartView
          categories={barCategories}
          series={barSeries}
          valueSuffix={reportId === 'relevance' || reportId === 'correctness' ? '%' : ''}
        />
      ) : null}
    </>
  )
}

export function CcReportsScreen({
  initialPanel = 'reports',
  domain = 'chat',
  initialReport,
  scope,
}: {
  initialPanel?: 'reports' | 'builder'
  domain?: 'chat' | 'sufler' | 'all'
  initialReport?: string
  scope?: 'chat' | 'sufler'
} = {}) {
  const sufler = scope === 'sufler' || domain === 'sufler'
  const channelOptions = CHANNEL_OPTIONS.filter((item) => item.value !== 'phone')
  const [panel, setPanel] = useState<'reports' | 'builder'>(initialPanel)
  const [catalogMeta, setCatalogMeta] = useState<CatalogReportMeta[]>([])
  const [reportType, setReportType] = useState(() => {
    const fromUrl = new URLSearchParams(window.location.search).get('report') || ''
    const fallback = initialReport || (sufler ? 'usefulness' : 'chat-topics')
    if (sufler && fromUrl && !SUFLER_REPORT_IDS.has(fromUrl)) {
      return fallback
    }
    return fromUrl || fallback
  })
  const [viewMode, setViewMode] = useState<ReportViewMode>('bar')
  const [filtersOpen, setFiltersOpen] = useState(true)
  const [periodFrom, setPeriodFrom] = useState(isoDaysAgo(13))
  const [periodTo, setPeriodTo] = useState(todayIso())
  const [channel, setChannel] = useState('all')
  const [topic, setTopic] = useState('all')
  const [dialogueStatus, setDialogueStatus] = useState('all')
  const [groupBy, setGroupBy] = useState('channel')
  const [payload, setPayload] = useState<CatalogPayload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [exportBusy, setExportBusy] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const [savedTemplates, setSavedTemplates] = useState<
    Array<{ id: string; name: string; metrics: string[]; view_mode: string }>
  >([])
  const debounceRef = useRef<number | null>(null)
  const catalogMetaRef = useRef<CatalogReportMeta[]>([])

  const topicEnabled = TOPIC_REPORTS.has(reportType)
  const statusEnabled = STATUS_REPORTS.has(reportType)
  const groupOptions = GROUP_BY_OPTIONS[reportType] || []
  const groupByEnabled = groupOptions.length > 0

  useEffect(() => {
    catalogMetaRef.current = catalogMeta
  }, [catalogMeta])

  const reportChoices = useMemo(() => {
    const base =
      catalogMeta.length > 0
        ? catalogMeta
        : [{ id: reportType, label: reportType, fr: '', default_view: 'table' as const }]
    const templates = savedTemplates.map((item) => ({
      id: `saved:${item.id}`,
      label: `★ ${item.name}`,
      fr: 'custom',
      default_view: (item.view_mode as ReportViewMode) || 'table',
      description: undefined as string | undefined,
    }))
    return [...base, ...templates]
  }, [catalogMeta, reportType, savedTemplates])

  const selected = useMemo(() => {
    const fromChoices = reportChoices.find((item) => item.id === reportType)
    if (fromChoices) return fromChoices
    return (
      catalogMeta.find((item) => item.id === reportType)
      || payload?.report
      || {
        id: reportType,
        fr: '',
        label: reportType,
        default_view: 'table' as const,
        description: undefined as string | undefined,
      }
    )
  }, [catalogMeta, payload, reportChoices, reportType])

  useEffect(() => {
    if (!groupByEnabled) return
    const options = GROUP_BY_OPTIONS[reportType] || []
    if (!options.some((item) => item.value === groupBy)) {
      setGroupBy(options[0]?.value || 'none')
    }
  }, [groupBy, groupByEnabled, reportType])

  useEffect(() => {
    void fetchBuilderTemplates()
      .then((data) => setSavedTemplates([...(data.templates || []), ...(data.saved || [])]))
      .catch(() => setSavedTemplates([]))
  }, [panel])

  const topicChoices = useMemo(() => {
    const fromRows = new Set<string>()
    for (const row of payload?.rows || []) {
      const value = String((row as Record<string, unknown>).topic || '').trim()
      if (value) fromRows.add(value)
    }
    if (fromRows.size) return Array.from(fromRows).sort((a, b) => a.localeCompare(b, 'ru'))
    return [...CLOSE_TOPICS]
  }, [payload])

  const loadReport = useCallback(async () => {
    setError(null)
    setLoading(true)
    try {
      if (reportType.startsWith('saved:')) {
        const templateId = reportType.slice('saved:'.length)
        const template = savedTemplates.find((item) => item.id === templateId)
        if (!template) {
          setError('Сохранённый шаблон не найден')
          setPayload(null)
          return
        }
        const data = await previewBuilder({
          name: template.name,
          metrics: template.metrics,
          view_mode: (template.view_mode as ReportViewMode) || 'table',
          date_from: periodFrom,
          date_to: periodTo,
        })
        const rows = (data.rows || []).map((row) => ({
          metric: metricLabel(row.metric),
          value: row.value,
          unit: row.unit || '—',
        }))
        setPayload({
          report: {
            id: reportType,
            fr: 'custom',
            label: template.name,
            default_view: (template.view_mode as ReportViewMode) || 'table',
          },
          catalog: catalogMetaRef.current,
          rows,
          chart: (data.chart || []).map((item) => ({
            label: metricLabel(item.label),
            value: item.value,
          })),
          summary: {},
          filters: { date_from: periodFrom, date_to: periodTo, channel: 'online_chat' },
          stub: false,
          source: 'builder',
          alerts: [],
        })
        const nextView = (template.view_mode || 'table') as ReportViewMode
        if (nextView === 'table' || nextView === 'pie' || nextView === 'bar') {
          setViewMode((current) => (current === nextView ? current : nextView))
        }
        return
      }

      const messenger = channel === 'all' || channel === 'phone' ? '' : channel
      const data = sufler
        ? await fetchCcCatalog({
            date_from: periodFrom,
            date_to: periodTo,
            report: reportType,
            scope: 'sufler',
            group_by: reportType === 'relevance' && groupByEnabled ? groupBy : '',
          })
        : await fetchCcCatalog({
            date_from: periodFrom,
            date_to: periodTo,
            channel: 'online_chat',
            report: reportType,
            messenger,
            topic: topicEnabled && topic !== 'all' ? topic : '',
            status: statusEnabled && dialogueStatus !== 'all' ? dialogueStatus : '',
            group_by: reportType === 'relevance' && groupByEnabled ? groupBy : '',
          })
      setPayload(data)
      const nextCatalog = data.catalog || []
      const prevIds = catalogMetaRef.current.map((item) => item.id).join('|')
      const nextIds = nextCatalog.map((item) => item.id).join('|')
      if (prevIds !== nextIds) {
        setCatalogMeta(nextCatalog)
      }
      const nextView = (data.report.default_view || 'table') as ReportViewMode
      if (nextView === 'table' || nextView === 'pie' || nextView === 'bar') {
        setViewMode((current) => (current === nextView ? current : nextView))
      }
    } catch (err) {
      const message =
        err instanceof CcReportsApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Не удалось загрузить отчёт'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [
    channel,
    dialogueStatus,
    groupBy,
    groupByEnabled,
    periodFrom,
    periodTo,
    reportType,
    savedTemplates,
    statusEnabled,
    sufler,
    topic,
    topicEnabled,
  ])

  useEffect(() => {
    if (panel !== 'reports') return undefined
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      void loadReport()
    }, 300)
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [panel, loadReport])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (reportType) {
      url.searchParams.set('report', reportType)
      window.history.replaceState({}, '', `${url.pathname}${url.search}`)
    }
  }, [reportType])

  const table = useMemo(
    () => rowsToTable((payload?.rows || []) as Record<string, unknown>[], payload?.columns),
    [payload],
  )
  const chart = payload?.chart || []

  const exportCurrentCsv = () => {
    downloadCsv(`${selected.label}.csv`, table.headers, table.rows)
  }

  const exportServer = async (format: 'xlsx' | 'pdf') => {
    setExportBusy(true)
    setError(null)
    try {
      const { blob, filename } = await downloadCcExport(
        sufler
          ? {
              date_from: periodFrom,
              date_to: periodTo,
              report: reportType,
              scope: 'sufler',
            }
          : {
              date_from: periodFrom,
              date_to: periodTo,
              channel: 'online_chat',
              report: reportType,
            },
        format,
      )
      triggerBrowserDownload(blob, filename)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка экспорта')
    } finally {
      setExportBusy(false)
    }
  }

  const chartBlock = (
    <ReportChartView
      viewMode={viewMode}
      reportId={reportType}
      chart={chart}
      selectedLabel={selected.label}
      table={table}
      onPieSelect={
        sufler && reportType === 'usefulness'
          ? (label) => {
              if (label.includes('Не воспользовался')) {
                setReportType('errors')
              }
            }
          : undefined
      }
    />
  )

  if (panel === 'builder') {
    return <BuilderPanel onBack={() => setPanel('reports')} />
  }

  return (
    <div className="rpt-body" data-testid={sufler ? 'sufler-reports-screen' : 'cc-reports-screen'}>
      <div className="rpt-brand">
        <img
          className="rpt-brand__logo"
          src="/assets/belarusbank-wordmark-green.png"
          alt="Беларусбанк"
        />
        <div className="rpt-brand__titles">
          <strong>{sufler ? 'Аналитика суфлёра' : 'Аналитика контакт-центра'}</strong>
          <span>Беларусбанк</span>
        </div>
      </div>
      {sufler ? null : (
        <div className="rpt-row rpt-row--end">
          <button type="button" className="rpt-pill is-active" onClick={() => setPanel('reports')}>
            Готовые отчёты
          </button>
          <button type="button" className="rpt-pill" onClick={() => setPanel('builder')}>
            Конструктор
          </button>
        </div>
      )}

      <div className="rpt-card">
        <div className="rpt-card__head">
          <span>Фильтры отчёта</span>
          <button
            type="button"
            className="rpt-btn rpt-btn--ghost"
            onClick={() => setFiltersOpen((open) => !open)}
          >
            {filtersOpen ? 'Свернуть' : 'Настроить фильтры'}
          </button>
        </div>
        {filtersOpen ? (
          <div className="rpt-card__body">
            <div className="rpt-grid-2">
              <label className="rpt-field">
                Тип отчёта
                <select
                  value={reportType}
                  onChange={(event) => setReportType(event.target.value)}
                >
                  {reportChoices.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              {sufler ? null : (
                <label className="rpt-field">
                  Канал чата
                  <select value={channel} onChange={(e) => setChannel(e.target.value)}>
                    {channelOptions.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="rpt-field">
                Период с
                <input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
              </label>
              <label className="rpt-field">
                Период по
                <input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
              </label>
              {sufler ? null : (
                <>
                  <label className={`rpt-field${topicEnabled ? '' : ' is-disabled'}`}>
                    Тематика закрытия
                    <select
                      value={topic}
                      disabled={!topicEnabled}
                      onChange={(e) => setTopic(e.target.value)}
                    >
                      <option value="all">Все тематики</option>
                      {topicChoices.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className={`rpt-field${statusEnabled ? '' : ' is-disabled'}`}>
                    Статусы
                    <select
                      value={dialogueStatus}
                      disabled={!statusEnabled}
                      onChange={(e) => setDialogueStatus(e.target.value)}
                    >
                      <option value="all">Все</option>
                      <option value="closed">Закрыт</option>
                      <option value="active">В работе</option>
                      <option value="waiting">В очереди</option>
                      <option value="offline">Офлайн</option>
                      <option value="lost">Потерянный</option>
                      <option value="rejected">Отказ клиента</option>
                    </select>
                  </label>
                </>
              )}
              <label className={`rpt-field${groupByEnabled ? '' : ' is-disabled'}`}>
                Группировка
                <select
                  value={groupByEnabled ? groupBy : ''}
                  disabled={!groupByEnabled}
                  onChange={(e) => setGroupBy(e.target.value)}
                >
                  {groupByEnabled ? (
                    groupOptions.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))
                  ) : (
                    <option value="">Не применяется к этому отчёту</option>
                  )}
                </select>
              </label>
            </div>
            {'description' in selected && selected.description ? (
              <p className="rpt-muted" style={{ margin: '8px 0 0' }}>{selected.description}</p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="rpt-row">
        <span className="rpt-muted">Представление:</span>
        {(['table', 'pie', 'bar'] as ReportViewMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            className={`rpt-pill${viewMode === mode ? ' is-active' : ''}`}
            onClick={() => setViewMode(mode)}
          >
            {mode === 'table' ? 'Таблица' : mode === 'pie' ? 'Круговая' : 'Столбчатая'}
          </button>
        ))}
        <span className="rpt-spacer" />
        <button
          type="button"
          className="rpt-btn rpt-btn--ghost"
          onClick={() => setFullscreen(true)}
          title="На весь экран"
        >
          ⛶
        </button>
        <button type="button" className="rpt-btn" onClick={exportCurrentCsv}>
          CSV
        </button>
        <button
          type="button"
          className="rpt-btn"
          disabled={exportBusy}
          onClick={() => void exportServer('xlsx')}
        >
          Экспорт xlsx
        </button>
        <button
          type="button"
          className="rpt-btn"
          disabled={exportBusy}
          onClick={() => void exportServer('pdf')}
        >
          Экспорт pdf
        </button>
      </div>

      {error ? (
        <div className="rpt-card">
          <div className="rpt-card__body" style={{ color: '#c62828' }}>
            {error}
          </div>
        </div>
      ) : null}

      <div className="rpt-stats">
        {Object.entries(payload?.summary || {})
          .filter(([key]) => !['report_id', 'note', 'period', 'rows', 'distribution', 'by_outcome', 'p95_first_response_sec', 'p95_ms'].includes(key))
          .slice(0, 6)
          .map(([key, value]) => (
            <div key={key} className="rpt-stat rpt-stat--info">
              <span>{summaryLabel(key)}</span>
              <strong>{localizeCell(value)}</strong>
            </div>
          ))}
      </div>

      <div className="rpt-card">
        <div className="rpt-card__head">
          <span>{selected.label}</span>
        </div>
        <div className="rpt-card__body">
          {loading && !payload ? <p className="rpt-muted">Загрузка данных…</p> : null}
          {payload || !loading ? chartBlock : null}
        </div>
      </div>

      {fullscreen ? (
        <div className="rpt-view-fullscreen">
          <div className="rpt-row" style={{ marginBottom: 12 }}>
            <strong>{selected.label}</strong>
            <span className="rpt-spacer" />
            <button type="button" className="rpt-btn" onClick={() => setFullscreen(false)}>
              Закрыть
            </button>
          </div>
          <div className="rpt-card">
            <div className="rpt-card__body">
              {loading && !payload ? <p className="rpt-muted">Загрузка…</p> : chartBlock}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  )
}

function BuilderPanel({ onBack }: { onBack: () => void }) {
  const [metrics, setMetrics] = useState([
    'sla_pct',
    'useful_pct',
    'relevance_avg',
    'incorrect_llm',
  ])
  const [templateName, setTemplateName] = useState('Качество сервиса и суфлёра')
  const [viewMode, setViewMode] = useState<'table' | 'bar' | 'pie'>('bar')
  const [periodFrom, setPeriodFrom] = useState(isoDaysAgo(6))
  const [periodTo, setPeriodTo] = useState(todayIso())
  const [catalog, setCatalog] = useState<{ id: string; label: string }[]>([])
  const [preview, setPreview] = useState<{
    rows: { metric: string; value: number; unit: string }[]
    chart: { label: string; value: number }[]
    message?: string
  } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [saveNotice, setSaveNotice] = useState<string | null>(null)
  const debounceRef = useRef<number | null>(null)

  useEffect(() => {
    void fetchBuilderTemplates()
      .then((data) => setCatalog(data.metric_catalog || []))
      .catch(() => setCatalog([]))
  }, [])

  const runPreview = useCallback(async () => {
    if (!metrics.length) {
      setPreview({ rows: [], chart: [], message: 'Добавьте хотя бы один показатель.' })
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await previewBuilder({
        name: templateName,
        metrics,
        view_mode: viewMode,
        date_from: periodFrom,
        date_to: periodTo,
      })
      setPreview(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка предпросмотра')
    } finally {
      setLoading(false)
    }
  }, [metrics, periodFrom, periodTo, templateName, viewMode])

  useEffect(() => {
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(() => {
      void runPreview()
    }, 250)
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [runPreview])

  const saveTemplate = async () => {
    setSaveNotice(null)
    setError(null)
    try {
      await saveBuilderTemplate({
        name: templateName.trim() || 'Качество сервиса и суфлёра',
        metrics,
        view_mode: viewMode,
        date_from: periodFrom,
        date_to: periodTo,
        filters: { channel: 'online_chat' },
      })
      setSaveNotice('Шаблон сохранён. Он появится в «Готовых отчётах» в списке типов отчёта.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить шаблон')
    }
  }

  return (
    <div className="rpt-body">
      <div className="rpt-row rpt-row--end">
        <button type="button" className="rpt-pill" onClick={onBack}>
          Готовые отчёты
        </button>
        <button type="button" className="rpt-pill is-active">
          Конструктор
        </button>
      </div>

      <div className="rpt-builder-grid">
        <div style={{ display: 'grid', gap: 16 }}>
          <div className="rpt-card">
            <div className="rpt-card__head">Период и шаблон</div>
            <div className="rpt-card__body" style={{ display: 'grid', gap: 10 }}>
              <label className="rpt-field">
                Название
                <input value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
              </label>
              <div className="rpt-grid-2">
                <label className="rpt-field">
                  С
                  <input type="date" value={periodFrom} onChange={(e) => setPeriodFrom(e.target.value)} />
                </label>
                <label className="rpt-field">
                  По
                  <input type="date" value={periodTo} onChange={(e) => setPeriodTo(e.target.value)} />
                </label>
              </div>
              <label className="rpt-field">
                Вид
                <select value={viewMode} onChange={(e) => setViewMode(e.target.value as typeof viewMode)}>
                  <option value="table">Таблица</option>
                  <option value="bar">Столбчатая</option>
                  <option value="pie">Круговая</option>
                </select>
              </label>
            </div>
          </div>

          <div className="rpt-card">
            <div className="rpt-card__head">
              <span>Показатели</span>
              <button
                type="button"
                className="rpt-btn rpt-btn--ghost"
                onClick={() => setMetrics((prev) => [...prev, catalog[0]?.id || 'dialogs_total'])}
              >
                + Поле
              </button>
            </div>
            <div className="rpt-card__body rpt-metric-list">
              {metrics.map((metric, index) => (
                <div key={`${metric}-${index}`} className="rpt-inline-selects">
                  <select
                    value={metric}
                    onChange={(e) =>
                      setMetrics((prev) =>
                        prev.map((item, i) => (i === index ? e.target.value : item)),
                      )
                    }
                  >
                    {(catalog.length
                      ? catalog
                      : [
                          { id: 'dialogs_total', label: 'Число диалогов' },
                          { id: 'sla_pct', label: 'Соблюдение SLA первого ответа, %' },
                          { id: 'csat', label: 'Средняя оценка клиента' },
                          { id: 'useful_pct', label: 'Полезность суфлёра, %' },
                          { id: 'aht_sec', label: 'Среднее время обработки, с' },
                        ]
                    ).map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="rpt-btn rpt-btn--ghost"
                    onClick={() => setMetrics((prev) => prev.filter((_, i) => i !== index))}
                  >
                    Удалить
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div className="rpt-row">
            <button type="button" className="rpt-btn" onClick={() => void saveTemplate()}>
              Сохранить шаблон
            </button>
          </div>
          {saveNotice ? <div className="rpt-notice">{saveNotice}</div> : null}
          {error ? <p style={{ color: '#c62828' }}>{error}</p> : null}
        </div>

        <div className="rpt-card">
          <div className="rpt-card__head">Предпросмотр конструктора</div>
          <div className="rpt-card__body" style={{ display: 'grid', gap: 14 }}>
            {loading ? <p className="rpt-muted">Считаем…</p> : null}
            {preview?.message ? <p className="rpt-muted">{preview.message}</p> : null}
            <div className="rpt-stats" style={{ gridTemplateColumns: 'repeat(2, 1fr)' }}>
              {(preview?.rows || []).map((row) => (
                <div key={row.metric} className="rpt-stat rpt-stat--info">
                  <span>{metricLabel(row.metric, catalog)}</span>
                  <strong>
                    {localizeCell(row.value)}
                    {row.unit ? ` ${row.unit}` : ''}
                  </strong>
                </div>
              ))}
            </div>
            {viewMode === 'bar' && preview?.chart?.length ? (
              <>
                <p className="rpt-chart-caption">
                  Сравнение показателей в процентах за выбранный период
                </p>
                <BarChartView
                  categories={preview.chart.map((item) => metricLabel(item.label, catalog))}
                  series={[{ name: 'Значение', data: preview.chart.map((item) => item.value) }]}
                  valueSuffix="%"
                />
              </>
            ) : null}
            {viewMode === 'pie' && preview?.chart?.length ? (
              <PieChartView
                data={preview.chart.map((item, index) => ({
                  label: metricLabel(item.label, catalog),
                  value: item.value,
                  tone: toneForIndex(index),
                }))}
              />
            ) : null}
            <DataTable
              headers={['Показатель', 'Значение', 'Ед.']}
              rows={(preview?.rows || []).map((row) => [
                metricLabel(row.metric, catalog),
                localizeCell(row.value),
                row.unit || '—',
              ])}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
