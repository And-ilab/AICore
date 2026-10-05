import { Button } from '../../components'
import type {
  ScenarioChannel,
  ScenarioDetail,
  ScenarioEdge,
  ScenarioNode,
} from './api/scenarios'

interface ScenarioWorkspaceProps {
  detail: ScenarioDetail
  path: ScenarioNode[]
  canEdit: boolean
  issueNodeIds: Set<string>
  onDetailChange: (patch: Partial<ScenarioDetail>) => void
  onNodeChange: (nodeId: string, patch: Partial<ScenarioNode>) => void
  onEdgeChange: (nodeId: string, index: number, patch: Partial<ScenarioEdge>) => void
  onReplyChange: (nodeId: string, index: number, reply: string) => void
  onAddEdge: (nodeId: string) => void
  onRemoveEdge: (nodeId: string, index: number) => void
  onOpenBranch: (pathIndex: number, targetId: string) => void
  onCreateBranch: (pathIndex: number, nodeId: string, edgeIndex: number) => void
  onSelectPathStep: (pathIndex: number) => void
  onDuplicateNode: (nodeId: string) => void
  onDeleteNode: (nodeId: string) => void
}

function stepRole(node: ScenarioNode, index: number): string {
  if (node.type === 'start') return 'Вход в сценарий'
  if (!node.edges.length) return 'Завершение ветки'
  return `Шаг ${index + 1}`
}

export function ScenarioWorkspace({
  detail,
  path,
  canEdit,
  issueNodeIds,
  onDetailChange,
  onNodeChange,
  onEdgeChange,
  onReplyChange,
  onAddEdge,
  onRemoveEdge,
  onOpenBranch,
  onCreateBranch,
  onSelectPathStep,
  onDuplicateNode,
  onDeleteNode,
}: ScenarioWorkspaceProps) {
  const byId = new Map(detail.graph.nodes.map((node) => [node.id, node]))

  return (
    <div className="scr-flow-editor">
      <section className="scr-basics" aria-label="Основные настройки сценария">
        <label>
          <span>Название сценария</span>
          <input
            value={detail.title}
            disabled={!canEdit}
            onChange={(event) => onDetailChange({ title: event.target.value })}
          />
        </label>
        <label className="scr-basics__root">
          <span>Главная входная реплика клиента</span>
          <input
            value={detail.root_question}
            disabled={!canEdit}
            placeholder="Например: Хочу открыть счёт ребёнку"
            onChange={(event) => onDetailChange({ root_question: event.target.value })}
          />
        </label>
        <label>
          <span>Каналы</span>
          <select
            value={detail.channels}
            disabled={!canEdit}
            onChange={(event) => onDetailChange({ channels: event.target.value as ScenarioChannel })}
          >
            <option value="both">Телефония и чат</option>
            <option value="telephony">Телефония</option>
            <option value="online_chat">Онлайн-чат</option>
          </select>
        </label>
      </section>

      <nav className="scr-flow-path" aria-label="Текущая ветка">
        <span>Текущая ветка:</span>
        {path.map((node, index) => (
          <button type="button" key={node.id} onClick={() => onSelectPathStep(index)}>
            {index ? '→ ' : ''}{node.label || stepRole(node, index)}
          </button>
        ))}
      </nav>

      <div className="scr-flow-steps">
        {path.map((node, pathIndex) => (
          <article
            className={`scr-flow-step${issueNodeIds.has(node.id) ? ' has-error' : ''}`}
            key={node.id}
            id={`scenario-step-${node.id}`}
          >
            <header className="scr-flow-step__head">
              <div>
                <small>{stepRole(node, pathIndex)}</small>
                <input
                  aria-label={`Название шага ${pathIndex + 1}`}
                  value={node.label}
                  disabled={!canEdit}
                  placeholder="Короткое название шага"
                  onChange={(event) => onNodeChange(node.id, { label: event.target.value })}
                />
              </div>
              <div className="scr-flow-step__actions">
                <button type="button" disabled={!canEdit} onClick={() => onDuplicateNode(node.id)}>Дублировать</button>
                {node.type !== 'start' ? (
                  <button type="button" className="is-danger" disabled={!canEdit} onClick={() => onDeleteNode(node.id)}>Удалить</button>
                ) : null}
              </div>
            </header>

            <div className="scr-flow-step__sequence">
              <section className="scr-conversation-block scr-conversation-block--client">
                <header><span>1</span><div><h3>Когда запускается этот шаг</h3><p>Примеры фраз клиента, которые приводят сюда.</p></div></header>
                <textarea
                  rows={3}
                  value={node.examples.join('\n')}
                  disabled={!canEdit}
                  placeholder={'Например: хочу открыть счёт\nНужен счёт ребёнку'}
                  onChange={(event) => onNodeChange(node.id, {
                    examples: event.target.value.split('\n').map((line) => line.trim()).filter(Boolean),
                  })}
                />
              </section>

              <section className="scr-conversation-block scr-conversation-block--operator">
                <header><span>2</span><div><h3>Что говорит оператор</h3><p>Готовая подсказка. Можно оставить пустой и сразу задать вопрос.</p></div></header>
                <textarea
                  rows={4}
                  value={node.hint_text}
                  disabled={!canEdit}
                  placeholder="Готовый ответ оператору"
                  onChange={(event) => onNodeChange(node.id, { hint_text: event.target.value })}
                />
              </section>

              <section className="scr-conversation-block scr-conversation-block--question">
                <header>
                  <span>3</span>
                  <div><h3>Что спрашивает оператор</h3><p>Включите вопрос, если после него клиент выбирает продолжение.</p></div>
                  <label className="scr-question-toggle">
                    <input
                      type="checkbox"
                      checked={Boolean(node.clarify_text)}
                      disabled={!canEdit}
                      onChange={(event) => onNodeChange(node.id, {
                        clarify_text: event.target.checked ? 'Уточните, пожалуйста: ' : '',
                      })}
                    />
                    <span>Задать вопрос</span>
                  </label>
                </header>
                {node.clarify_text ? (
                  <textarea
                    rows={3}
                    value={node.clarify_text}
                    disabled={!canEdit}
                    placeholder="Например: С карточкой или без карточки?"
                    onChange={(event) => onNodeChange(node.id, { clarify_text: event.target.value })}
                  />
                ) : (
                  <div className="scr-question-off">Вопрос не задан. После ответа оператора ветка может завершиться.</div>
                )}
              </section>

              <section className="scr-conversation-block scr-conversation-block--choices">
                <header><span>4</span><div><h3>Что может ответить клиент</h3><p>Добавьте один или несколько естественных ответов и настройте продолжение.</p></div></header>
                <div className="scr-choice-list">
                  {node.edges.map((edge, edgeIndex) => {
                    const target = byId.get(edge.to)
                    return (
                      <div className="scr-choice-card" key={`${node.id}-${edgeIndex}`}>
                        <div className="scr-choice-card__number">{edgeIndex + 1}</div>
                        <label className="scr-choice-card__reply">
                          <span>Ответ клиента</span>
                          <input
                            value={edge.reply ?? edge.label}
                            disabled={!canEdit}
                            placeholder="Например: Да, документ ребёнка есть"
                            onChange={(event) => onReplyChange(node.id, edgeIndex, event.target.value)}
                          />
                        </label>
                        <div className="scr-choice-card__next">
                          <span>Что будет дальше</span>
                          {target ? (
                            <button
                              type="button"
                              className="scr-next-step"
                              onClick={() => onOpenBranch(pathIndex, target.id)}
                            >
                              <small>Продолжение</small>
                              <strong>{target.label || 'Шаг без названия'}</strong>
                              <b>Открыть ниже ↓</b>
                            </button>
                          ) : (
                            <Button
                              variant="ghost"
                              disabled={!canEdit || !(edge.reply ?? edge.label).trim()}
                              onClick={() => onCreateBranch(pathIndex, node.id, edgeIndex)}
                            >
                              + Создать продолжение
                            </Button>
                          )}
                        </div>
                        <details className="scr-choice-card__technical">
                          <summary>Настройки перехода</summary>
                          <label>
                            <span>Название ветки</span>
                            <input
                              value={edge.label}
                              disabled={!canEdit}
                              onChange={(event) => onEdgeChange(node.id, edgeIndex, { label: event.target.value })}
                            />
                          </label>
                          <label>
                            <span>Связать с существующим шагом</span>
                            <select
                              value={edge.to}
                              disabled={!canEdit}
                              onChange={(event) => onEdgeChange(node.id, edgeIndex, { to: event.target.value })}
                            >
                              <option value="">Продолжение ещё не создано</option>
                              {detail.graph.nodes.filter((item) => item.id !== node.id).map((item) => (
                                <option value={item.id} key={item.id}>{item.label || item.id}</option>
                              ))}
                            </select>
                          </label>
                          <label className="scr-choice-fallback">
                            <input
                              type="checkbox"
                              checked={Boolean(edge.is_fallback)}
                              disabled={!canEdit}
                              onChange={(event) => onEdgeChange(node.id, edgeIndex, { is_fallback: event.target.checked })}
                            />
                            <span>Другой / не подходит</span>
                          </label>
                        </details>
                        <button type="button" className="scr-choice-card__remove" disabled={!canEdit} onClick={() => onRemoveEdge(node.id, edgeIndex)}>Удалить вариант</button>
                      </div>
                    )
                  })}
                  {!node.edges.length ? (
                    <div className="scr-choice-empty">
                      <strong>Это завершение ветки</strong>
                      <p>Если разговор должен продолжиться, добавьте вариант ответа клиента.</p>
                    </div>
                  ) : null}
                </div>
                <Button variant="ghost" disabled={!canEdit} onClick={() => onAddEdge(node.id)}>+ Добавить вариант ответа</Button>
              </section>
            </div>
          </article>
        ))}
      </div>

      <details className="scr-system-prompt">
        <summary>Системная инструкция сценария</summary>
        <textarea
          rows={5}
          value={detail.system_prompt}
          disabled={!canEdit}
          onChange={(event) => onDetailChange({ system_prompt: event.target.value })}
        />
      </details>
    </div>
  )
}

export function ScenarioTestPreview({ code, onOpenTest }: { code: string; onOpenTest?: (code: string) => void }) {
  return (
    <section className="scr-preview">
      <div>
        <strong>Проверить разговор</strong>
        <p>Пройдите настроенные шаги от имени клиента.</p>
      </div>
      <Button variant="ghost" onClick={() => onOpenTest?.(code)}>Открыть тест</Button>
    </section>
  )
}
