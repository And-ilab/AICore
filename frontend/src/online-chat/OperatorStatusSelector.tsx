import {
  OPERATOR_STATUSES,
  type OperatorPresence,
} from './operatorStatuses'

export interface OperatorStatusSelectorProps {
  value: OperatorPresence
  onChange: (next: OperatorPresence) => void
  disabled?: boolean
}

export function OperatorStatusSelector({
  value,
  onChange,
  disabled = false,
}: OperatorStatusSelectorProps) {
  return (
    <div
      className="chat-arm__statuses"
      role="radiogroup"
      aria-label="Статус оператора"
      data-testid="operator-status-selector"
    >
      {OPERATOR_STATUSES.map((status) => {
        const active = value === status.id
        return (
          <button
            key={status.id}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            className={`chat-arm__status chat-arm__status--${status.tone} ${
              active ? 'chat-arm__status--active' : ''
            }`}
            data-testid={`operator-status-${status.id}`}
            data-status={status.id}
            title={status.label}
            onClick={() => onChange(status.id)}
          >
            {status.label}
          </button>
        )
      })}
    </div>
  )
}
