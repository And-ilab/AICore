import type { ScenarioGraph, ScenarioNode } from './api/scenarios'

export interface ScenarioValidation {
  errors: string[]
  warnings: string[]
}

export function scenarioStartNode(graph: ScenarioGraph): ScenarioNode | undefined {
  return graph.nodes.find((node) => node.type === 'start') ?? graph.nodes[0]
}

export function reachableScenarioNodes(graph: ScenarioGraph): ScenarioNode[] {
  const start = scenarioStartNode(graph)
  if (!start) return []

  const byId = new Map(graph.nodes.map((node) => [node.id, node]))
  const visited = new Set<string>()
  const ordered: ScenarioNode[] = []
  const queue = [start.id]

  while (queue.length) {
    const id = queue.shift()
    if (!id || visited.has(id)) continue
    const node = byId.get(id)
    if (!node) continue
    visited.add(id)
    ordered.push(node)
    node.edges.forEach((edge) => {
      if (!visited.has(edge.to)) queue.push(edge.to)
    })
  }
  return ordered
}

export function createScenarioNode(graph: ScenarioGraph): ScenarioNode {
  const used = new Set(graph.nodes.map((node) => node.id))
  let index = graph.nodes.length + 1
  while (used.has(`step_${index}`)) index += 1
  return {
    id: `step_${index}`,
    type: 'answer',
    label: `Шаг ${index}`,
    hint_text: '',
    clarify_text: '',
    examples: [],
    intent_id: '',
    edges: [],
  }
}

export function duplicateScenarioNode(graph: ScenarioGraph, source: ScenarioNode): ScenarioNode {
  const copy = createScenarioNode(graph)
  return {
    ...source,
    id: copy.id,
    label: `${source.label} — копия`,
    edges: source.edges.map((edge) => ({ ...edge, keywords: [...edge.keywords] })),
    examples: [...source.examples],
  }
}

export function removeScenarioNode(graph: ScenarioGraph, nodeId: string): ScenarioGraph {
  return {
    nodes: graph.nodes
      .filter((node) => node.id !== nodeId)
      .map((node) => ({
        ...node,
        edges: node.edges.filter((edge) => edge.to !== nodeId),
      })),
  }
}

export function updateClientVariant(
  graph: ScenarioGraph,
  nodeId: string,
  edgeIndex: number,
  text: string,
): ScenarioGraph {
  const source = graph.nodes.find((node) => node.id === nodeId)
  const edge = source?.edges[edgeIndex]
  if (!source || !edge) return graph
  const previous = edge.label.trim()
  const next = text.trim()

  return {
    nodes: graph.nodes.map((node) => {
      if (node.id === nodeId) {
        return {
          ...node,
          edges: node.edges.map((item, index) =>
            index === edgeIndex
              ? { ...item, label: text, keywords: next ? [next] : [] }
              : item,
          ),
        }
      }
      if (node.id !== edge.to) return node
      const examples = node.examples.filter((example) => example !== previous)
      return {
        ...node,
        examples: next && !examples.includes(next) ? [...examples, next] : examples,
      }
    }),
  }
}

export function updateClientReply(
  graph: ScenarioGraph,
  nodeId: string,
  edgeIndex: number,
  reply: string,
): ScenarioGraph {
  const source = graph.nodes.find((node) => node.id === nodeId)
  const edge = source?.edges[edgeIndex]
  if (!source || !edge) return graph
  const previous = (edge.reply ?? '').trim()
  const next = reply.trim()

  return {
    nodes: graph.nodes.map((node) => {
      if (node.id === nodeId) {
        return {
          ...node,
          edges: node.edges.map((item, index) => index === edgeIndex
            ? {
                ...item,
                reply,
                keywords: next ? [next] : item.keywords,
              }
            : item),
        }
      }
      if (node.id !== edge.to) return node
      const examples = node.examples.filter((example) => example !== previous)
      return {
        ...node,
        examples: next && !examples.includes(next) ? [...examples, next] : examples,
      }
    }),
  }
}

export function updateClientVariantTarget(
  graph: ScenarioGraph,
  nodeId: string,
  edgeIndex: number,
  targetId: string,
): ScenarioGraph {
  const source = graph.nodes.find((node) => node.id === nodeId)
  const edge = source?.edges[edgeIndex]
  if (!source || !edge) return graph
  if (edge.to === targetId) return graph
  const example = edge.label.trim()

  return {
    nodes: graph.nodes.map((node) => {
      if (node.id === nodeId) {
        return {
          ...node,
          edges: node.edges.map((item, index) =>
            index === edgeIndex ? { ...item, to: targetId } : item,
          ),
        }
      }
      if (!example) return node
      if (node.id === edge.to) {
        return { ...node, examples: node.examples.filter((item) => item !== example) }
      }
      if (node.id === targetId && !node.examples.includes(example)) {
        return { ...node, examples: [...node.examples, example] }
      }
      return node
    }),
  }
}

export function validateScenario(
  title: string,
  rootQuestion: string,
  graph: ScenarioGraph,
): ScenarioValidation {
  const errors: string[] = []
  const warnings: string[] = []
  const ids = new Set(graph.nodes.map((node) => node.id))

  if (!title.trim()) errors.push('Укажите название сценария.')
  if (!rootQuestion.trim()) errors.push('Укажите стартовую реплику клиента.')
  if (!graph.nodes.length) errors.push('Добавьте хотя бы один шаг.')
  if (graph.nodes.length && !graph.nodes.some((node) => node.type === 'start')) {
    errors.push('Добавьте шаг с типом «Начало сценария».')
  }

  graph.nodes.forEach((node, index) => {
    const name = node.label.trim() || `Шаг ${index + 1}`
    if (!node.label.trim()) errors.push(`${name}: укажите название.`)
    if (!node.clarify_text.trim() && !node.hint_text.trim() && node.type !== 'end') {
      errors.push(`${name}: добавьте вопрос клиенту или ответ оператора.`)
    }
    node.edges.forEach((edge, edgeIndex) => {
      if (!ids.has(edge.to)) {
        errors.push(`${name}, вариант ${edgeIndex + 1}: выберите существующий следующий шаг.`)
      }
      if (!edge.label.trim() && !edge.keywords.length) {
        errors.push(`${name}, вариант ${edgeIndex + 1}: опишите ответ клиента.`)
      }
      if (!(edge.reply ?? edge.label).trim()) {
        errors.push(`${name}, вариант ${edgeIndex + 1}: укажите естественную реплику клиента.`)
      }
    })
  })

  const reachable = new Set(reachableScenarioNodes(graph).map((node) => node.id))
  graph.nodes.forEach((node) => {
    if (!reachable.has(node.id)) warnings.push(`Шаг «${node.label || node.id}» недоступен от начала.`)
  })
  return { errors, warnings }
}
