import type { SuflerScenarioProgress } from './hooks/useSuflerTranscript'

interface ScenarioPathWidgetProps {
  scenario: SuflerScenarioProgress
  onReturn?: () => void
  onReturnToStep?: (nodeId: string) => void
}

type PathStep = {
  node_id: string
  label: string
  kind: 'done' | 'current' | 'upcoming'
}

function walkedSteps(scenario: SuflerScenarioProgress) {
  if (scenario.steps?.length) return scenario.steps
  return scenario.path.map((label, index) => ({
    node_id: index === scenario.path.length - 1 ? scenario.node_id : '',
    label,
  }))
}

function displaySteps(scenario: SuflerScenarioProgress): PathStep[] {
  const walked = walkedSteps(scenario)
  const currentIndex = Math.max(0, walked.length - 1)
  const upcoming = scenario.completed ? [] : scenario.upcoming ?? []
  return [
    ...walked.map((step, index) => ({
      ...step,
      kind: (index === currentIndex ? 'current' : 'done') as PathStep['kind'],
    })),
    ...upcoming.map((step) => ({
      ...step,
      kind: 'upcoming' as const,
    })),
  ]
}

export function ScenarioPathWidget({
  scenario,
  onReturn,
  onReturnToStep,
}: ScenarioPathWidgetProps) {
  const steps = displaySteps(scenario)
  if (!steps.length) return null

  const currentIndex = Math.max(
    0,
    steps.findIndex((step) => step.kind === 'current'),
  )
  const mode = scenario.completed ? 'completed' : scenario.paused ? 'paused' : 'active'
  const badge =
    mode === 'completed' ? 'Сценарий окончен' : mode === 'paused' ? 'Вернуться к диалогу' : 'В сценарии'
  const current = steps[currentIndex]

  return (
    <aside
      className={`sufler-path-widget sufler-path-widget--${mode}`}
      aria-label="Текущий путь сценария"
      data-testid="sufler-scenario-path-widget"
    >
      <header>
        <h2>{mode === 'paused' ? 'Вернуться к диалогу' : 'Текущий путь'}</h2>
        <span className="sufler-path-widget__badge">{badge}</span>
      </header>
      <p className="sufler-path-widget__meta">
        {scenario.code} · шаг {currentIndex + 1} из {steps.length}
      </p>
      <ol>
        {steps.map((step, index) => {
          const clickable = mode === 'paused' && step.kind !== 'upcoming' && Boolean(step.node_id)
          const className = [
            step.kind === 'current' ? 'is-current' : '',
            step.kind === 'done' ? 'is-done' : '',
            step.kind === 'upcoming' ? 'is-upcoming' : '',
            clickable ? 'is-clickable' : '',
          ]
            .filter(Boolean)
            .join(' ')
          const content = (
            <>
              <span>{index + 1}</span>
              {step.label}
            </>
          )
          return (
            <li key={`${step.kind}-${step.node_id || step.label}-${index}`} className={className || undefined}>
              {clickable ? (
                <button
                  type="button"
                  onClick={() => onReturnToStep?.(step.node_id)}
                  data-testid={`sufler-scenario-step-${index}`}
                >
                  {content}
                </button>
              ) : (
                content
              )}
            </li>
          )
        })}
      </ol>
      {mode === 'completed' ? (
        <section className="sufler-path-widget__done" role="status">
          <small>Сценарий окончен</small>
          <strong>{current?.label}</strong>
          <span>Диалог по этой ветке закрыт</span>
        </section>
      ) : mode === 'paused' ? (
        <section className="sufler-path-widget__return" data-testid="sufler-scenario-return">
          <small>Остановились на шаге</small>
          <strong>{current?.label}</strong>
          {scenario.return_phrase ? <p>{scenario.return_phrase}</p> : null}
          <button
            type="button"
            onClick={() => {
              if (current?.node_id) onReturnToStep?.(current.node_id)
              else onReturn?.()
            }}
            data-testid="sufler-scenario-return-button"
          >
            Вернуться
          </button>
        </section>
      ) : (
        <section>
          <small>Активный шаг</small>
          <strong>{current?.label}</strong>
          {current?.node_id ? <span>ID: {current.node_id}</span> : null}
        </section>
      )}
    </aside>
  )
}
