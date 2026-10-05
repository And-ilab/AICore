import { useCallback, useEffect, useState } from 'react'
import { Button, StatusBadge } from '../../components'
import {
  createDialogScenario,
  getDialogScenario,
  listDialogScenarios,
  saveDialogScenario,
  type ScenarioChannel,
  type ScenarioDetail,
  type ScenarioEdge,
  type ScenarioGraph,
  type ScenarioListItem,
  type ScenarioNode,
} from './api/scenarios'
import {
  createScenarioNode,
  duplicateScenarioNode,
  removeScenarioNode,
  updateClientReply,
  validateScenario,
} from './scenarioGraphAdapter'
import { ScenarioTestPreview, ScenarioWorkspace } from './ScenarioEditorWorkspace'
import './ScenarioEditor.css'

interface ScenarioEditorScreenProps {
  canEdit: boolean
  initialCode?: string
  onBack?: () => void
  onOpenTest?: (code: string) => void
  onScenarioCreated?: (code: string) => void
}

interface NewScenarioForm {
  title: string
  rootQuestion: string
  channels: ScenarioChannel
}

export function ScenarioEditorScreen({
  canEdit,
  initialCode = '',
  onBack,
  onOpenTest,
  onScenarioCreated,
}: ScenarioEditorScreenProps) {
  const [items, setItems] = useState<ScenarioListItem[]>([])
  const [selected, setSelected] = useState(initialCode)
  const [detail, setDetail] = useState<ScenarioDetail | null>(null)
  const [pathIds, setPathIds] = useState<string[]>([])
  const [message, setMessage] = useState('')
  const [publishIssues, setPublishIssues] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newForm, setNewForm] = useState<NewScenarioForm>({
    title: '',
    rootQuestion: '',
    channels: 'both',
  })

  const loadList = useCallback(async () => {
    try {
      const payload = await listDialogScenarios()
      setItems(payload.items)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось загрузить сценарии')
    }
  }, [])

  useEffect(() => { void loadList() }, [loadList])
  useEffect(() => {
    setSelected(initialCode)
    if (initialCode === 'new') {
      setDetail(null)
      setPathIds([])
      setMessage('')
    }
  }, [initialCode])

  useEffect(() => {
    if (!selected || selected === 'new') {
      if (selected !== 'new') setDetail(null)
      return
    }
    let cancelled = false
    void getDialogScenario(selected)
      .then((payload) => {
        if (cancelled) return
        const start = payload.graph.nodes.find((node) => node.type === 'start') ?? payload.graph.nodes[0]
        setDetail(payload)
        setPathIds(start ? [start.id] : [])
        setPublishIssues([])
        setMessage('')
      })
      .catch((error: unknown) => {
        if (!cancelled) setMessage(error instanceof Error ? error.message : 'Не удалось открыть сценарий')
      })
    return () => { cancelled = true }
  }, [selected])

  const nodes = detail?.graph.nodes ?? []
  const path = pathIds.map((id) => nodes.find((node) => node.id === id)).filter((node): node is ScenarioNode => Boolean(node))
  const issueNodeIds = new Set<string>()
  publishIssues.forEach((issue) => {
    nodes.forEach((node) => {
      if (issue.includes(`«${node.label || node.id}»`) || issue.startsWith(`${node.label}:`)) {
        issueNodeIds.add(node.id)
      }
    })
  })

  const updateGraph = (graph: ScenarioGraph) => {
    setDetail((current) => current ? { ...current, graph } : current)
    setPublishIssues([])
  }

  const patchNode = (nodeId: string, patch: Partial<ScenarioNode>) => {
    updateGraph({ nodes: nodes.map((node) => node.id === nodeId ? { ...node, ...patch } : node) })
  }

  const patchEdge = (nodeId: string, edgeIndex: number, patch: Partial<ScenarioEdge>) => {
    updateGraph({
      nodes: nodes.map((node) => node.id === nodeId
        ? { ...node, edges: node.edges.map((edge, index) => index === edgeIndex ? { ...edge, ...patch } : edge) }
        : node),
    })
  }

  const handleSave = async (publish: boolean) => {
    if (!detail || !canEdit) return
    if (publish) {
      const validation = validateScenario(detail.title, detail.root_question, detail.graph)
      const issues = [...validation.errors, ...validation.warnings]
      setPublishIssues(issues)
      if (validation.errors.length) {
        setMessage('Исправьте обязательные поля перед публикацией.')
        return
      }
    }
    setSaving(true)
    setMessage('')
    try {
      const saved = await saveDialogScenario(detail.code, {
        title: detail.title,
        root_question: detail.root_question,
        channels: detail.channels,
        graph: detail.graph,
        system_prompt: detail.system_prompt,
        publish,
      })
      setDetail(saved)
      setMessage(publish ? 'Сценарий опубликован.' : 'Черновик сохранён.')
      setPublishIssues([])
      await loadList()
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось сохранить')
    } finally {
      setSaving(false)
    }
  }

  const handleCreate = async () => {
    if (!canEdit || !newForm.title.trim() || !newForm.rootQuestion.trim()) return
    let next = items.length + 1
    const codes = new Set(items.map((item) => item.code))
    while (codes.has(`CC-SCR-${String(next).padStart(3, '0')}`)) next += 1
    const code = `CC-SCR-${String(next).padStart(3, '0')}`
    setCreating(true)
    setMessage('')
    try {
      const created = await createDialogScenario({
        code,
        title: newForm.title.trim(),
        root_question: newForm.rootQuestion.trim(),
        channels: newForm.channels,
        graph: {
          nodes: [{
            id: 'start',
            type: 'start',
            label: 'Начало разговора',
            hint_text: '',
            clarify_text: '',
            examples: [newForm.rootQuestion.trim()],
            intent_id: code,
            edges: [],
          }],
        },
      })
      setSelected(created.code)
      setDetail(created)
      setPathIds(['start'])
      setNewForm({ title: '', rootQuestion: '', channels: 'both' })
      await loadList()
      onScenarioCreated?.(created.code)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Не удалось создать сценарий')
    } finally {
      setCreating(false)
    }
  }

  const createContinuation = (pathIndex: number, nodeId: string, edgeIndex: number) => {
    if (!detail) return
    const source = nodes.find((node) => node.id === nodeId)
    const edge = source?.edges[edgeIndex]
    if (!source || !edge) return
    const node = {
      ...createScenarioNode(detail.graph),
      label: edge.label && !/^Вариант \d+$/.test(edge.label) ? edge.label : 'Следующий шаг',
      examples: (edge.reply ?? '').trim() ? [(edge.reply ?? '').trim()] : [],
    }
    const nextNodes = [...nodes, node].map((item) => item.id === nodeId
      ? {
          ...item,
          edges: item.edges.map((itemEdge, index) => index === edgeIndex
            ? { ...itemEdge, to: node.id }
            : itemEdge),
        }
      : item)
    updateGraph({ nodes: nextNodes })
    setPathIds((current) => [...current.slice(0, pathIndex + 1), node.id])
    window.requestAnimationFrame(() => document.getElementById(`scenario-step-${node.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
  }

  if (selected === 'new') {
    return (
      <div className="scr-editor" data-testid="scenario-editor">
        <header className="scr-editor__head">
          <div className="scr-editor__identity">
            {onBack ? <button type="button" onClick={onBack}>← Все сценарии</button> : null}
            <div><span>НОВЫЙ СЦЕНАРИЙ</span><h2>Сначала настройте вход в разговор</h2></div>
          </div>
        </header>
        <section className="scr-create">
          <header>
            <span>Шаг 1 из 2</span>
            <h2>Основные данные</h2>
            <p>После создания вы сразу добавите вопрос оператора, варианты клиента и продолжения.</p>
          </header>
          <div className="scr-create__fields">
            <label>
              <span>Название сценария *</span>
              <input
                autoFocus
                value={newForm.title}
                placeholder="Например: Открытие счёта ребёнку"
                onChange={(event) => setNewForm((current) => ({ ...current, title: event.target.value }))}
              />
              <small>Короткое название для каталога.</small>
            </label>
            <label>
              <span>Что говорит клиент в начале *</span>
              <textarea
                rows={3}
                value={newForm.rootQuestion}
                placeholder="Например: Хочу открыть счёт сыну"
                onChange={(event) => setNewForm((current) => ({ ...current, rootQuestion: event.target.value }))}
              />
              <small>По этой реплике суфлёр распознает сценарий.</small>
            </label>
            <label>
              <span>Где работает сценарий</span>
              <select value={newForm.channels} onChange={(event) => setNewForm((current) => ({ ...current, channels: event.target.value as ScenarioChannel }))}>
                <option value="both">Телефония и чат</option>
                <option value="telephony">Только телефония</option>
                <option value="online_chat">Только онлайн-чат</option>
              </select>
            </label>
          </div>
          <footer>
            <Button variant="ghost" onClick={onBack}>Отмена</Button>
            <Button
              disabled={creating || !newForm.title.trim() || !newForm.rootQuestion.trim()}
              onClick={() => void handleCreate()}
            >
              {creating ? 'Создаём…' : 'Создать и настроить шаги →'}
            </Button>
          </footer>
        </section>
        {message ? <p className="scr-editor__message">{message}</p> : null}
      </div>
    )
  }

  if (!selected || !detail || !path.length) {
    return (
      <section className="scr-editor-empty" data-testid="scenario-editor">
        <h2>Сначала выберите сценарий</h2>
        <p>Откройте каталог и нажмите на нужную карточку.</p>
        {onBack ? <Button onClick={onBack}>Перейти к каталогу</Button> : null}
        {message ? <p>{message}</p> : null}
      </section>
    )
  }

  return (
    <div className="scr-editor" data-testid="scenario-editor">
      <header className="scr-editor__head">
        <div className="scr-editor__identity">
          {onBack ? <button type="button" onClick={onBack}>← Все сценарии</button> : null}
          <div><span>{detail.code}</span><h2>{detail.title}</h2></div>
          <StatusBadge status={detail.status === 'production' ? 'success' : 'warning'}>
            {detail.status === 'production' ? 'Опубликован' : 'Черновик'}
          </StatusBadge>
        </div>
        <div className="scr-editor__head-actions">
          {onOpenTest ? <Button variant="ghost" onClick={() => onOpenTest(detail.code)}>Тестировать</Button> : null}
          <Button variant="secondary" disabled={!canEdit || saving} onClick={() => void handleSave(false)}>Сохранить</Button>
          <Button disabled={!canEdit || saving} onClick={() => void handleSave(true)}>Опубликовать</Button>
        </div>
      </header>

      {publishIssues.length ? (
        <section className="scr-validation" aria-live="polite">
          <strong>Что нужно исправить</strong>
          <ul>{publishIssues.map((issue) => <li key={issue}>{issue}</li>)}</ul>
        </section>
      ) : null}

      <ScenarioWorkspace
        detail={detail}
        path={path}
        canEdit={canEdit}
        issueNodeIds={issueNodeIds}
        onDetailChange={(patch) => {
          setDetail((current) => current ? { ...current, ...patch } : current)
          setPublishIssues([])
        }}
        onNodeChange={patchNode}
        onEdgeChange={patchEdge}
        onReplyChange={(nodeId, edgeIndex, reply) => updateGraph(updateClientReply(detail.graph, nodeId, edgeIndex, reply))}
        onAddEdge={(nodeId) => {
          const node = nodes.find((item) => item.id === nodeId)
          if (!node) return
          patchNode(nodeId, {
            edges: [...node.edges, {
              to: '',
              label: `Вариант ${node.edges.length + 1}`,
              reply: '',
              keywords: [],
              is_fallback: false,
            }],
          })
        }}
        onRemoveEdge={(nodeId, edgeIndex) => {
          const node = nodes.find((item) => item.id === nodeId)
          if (node) patchNode(nodeId, { edges: node.edges.filter((_, index) => index !== edgeIndex) })
        }}
        onOpenBranch={(pathIndex, targetId) => {
          setPathIds((current) => [...current.slice(0, pathIndex + 1), targetId])
          window.requestAnimationFrame(() => document.getElementById(`scenario-step-${targetId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
        }}
        onCreateBranch={createContinuation}
        onSelectPathStep={(pathIndex) => {
          const target = path[pathIndex]
          setPathIds((current) => current.slice(0, pathIndex + 1))
          window.requestAnimationFrame(() => document.getElementById(`scenario-step-${target.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }))
        }}
        onDuplicateNode={(nodeId) => {
          const source = nodes.find((node) => node.id === nodeId)
          if (!source) return
          const copy = duplicateScenarioNode(detail.graph, source)
          updateGraph({ nodes: [...nodes, copy] })
          setPathIds([copy.id])
        }}
        onDeleteNode={(nodeId) => {
          const pathIndex = pathIds.indexOf(nodeId)
          updateGraph(removeScenarioNode(detail.graph, nodeId))
          setPathIds((current) => current.slice(0, Math.max(1, pathIndex)))
        }}
      />
      <ScenarioTestPreview code={detail.code} onOpenTest={onOpenTest} />
      {message ? <p className="scr-editor__message" aria-live="polite">{message}</p> : null}
    </div>
  )
}
