import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react'
import {
  ArmOperatorView,
  getSchemePalette,
  type OperatorPresence,
} from './arm/ArmOperatorView'
import { ARM_THEME_DARK, ARM_THEME_LIGHT, type ThemeKind } from './arm/theme'
import {
  ARM_UI_SETTINGS_EVENT,
  armFontScaleFactor,
  loadArmUiSettings,
  type ArmUiSettings,
} from './arm/modules'
import {
  operatorsApi,
  type OperatorPresence as PersistedPresence,
} from './api/managementApi'
import './ChatArmApp.css'

export interface ChatArmAppProps {
  operatorName?: string
  /** Logged-in actor (supervisor) when observing another operator's ARM. */
  actorName?: string
  demoMode?: boolean
  initialPresence?: OperatorPresence
  themeKind?: ThemeKind
  statsDrawerOpen?: boolean
  onStatsDrawerOpenChange?: (open: boolean) => void
  armRole?: 'operator' | 'supervisor' | 'admin'
  viewOnly?: boolean
  allowTransferInView?: boolean
}

function mapApiPresence(presence: string): OperatorPresence | null {
  const supported = new Set<OperatorPresence>([
    'online',
    'break',
    'lunch',
    'training',
    'meeting',
    'offline',
  ])
  if (supported.has(presence as OperatorPresence)) {
    return presence as OperatorPresence
  }
  if (presence === 'tech_issue') return 'tech_break'
  if (presence === 'busy') return 'offline_queue'
  return null
}

/** Emerald ARM: light mockup by default, optional dark toggle. */
export function ChatArmApp({
  initialPresence = 'online',
  operatorName = 'Иванов И.И.',
  actorName = '',
  themeKind = 'light',
  statsDrawerOpen,
  onStatsDrawerOpenChange,
  armRole = 'operator',
  viewOnly = false,
  allowTransferInView = false,
}: ChatArmAppProps) {
  const t = themeKind === 'light' ? ARM_THEME_LIGHT : ARM_THEME_DARK
  const scheme = useMemo(() => getSchemePalette(t, 'belarusbank_emerald'), [t])

  const [selectedQueue, setSelectedQueue] = useState('1')
  const [reply, setReply] = useState('')
  const [suflerSuggestionText, setSuflerSuggestionText] = useState('')
  const [toast, setToast] = useState<string | null>(null)
  const [presence, setPresence] = useState<OperatorPresence>(initialPresence)
  const [viewMode, setViewMode] = useState<'active' | 'colleague'>(viewOnly ? 'colleague' : 'active')
  const [closeTopic, setCloseTopic] = useState<string>('')
  const [uiSettings, setUiSettings] = useState<ArmUiSettings>(() => loadArmUiSettings())

  useEffect(() => {
    const sync = () => setUiSettings(loadArmUiSettings())
    const onCustom = () => sync()
    window.addEventListener(ARM_UI_SETTINGS_EVENT, onCustom)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(ARM_UI_SETTINGS_EVENT, onCustom)
      window.removeEventListener('storage', sync)
    }
  }, [])

  useEffect(() => {
    if (viewOnly) setViewMode('colleague')
  }, [viewOnly])

  const syncOperatorProfile = useCallback(() => {
    if (viewOnly) return
    void operatorsApi.list().then((operators) => {
      const profile = operators.find((item) => item.name === operatorName)
      if (!profile) return
      const mapped = mapApiPresence(profile.presence)
      if (mapped) {
        setPresence((prev) => (prev === mapped ? prev : mapped))
      }
    }).catch(() => undefined)
  }, [operatorName, viewOnly])

  useEffect(() => {
    syncOperatorProfile()
    if (viewOnly) return
    const timer = window.setInterval(syncOperatorProfile, 2500)
    return () => window.clearInterval(timer)
  }, [syncOperatorProfile, viewOnly])

  const persistPresence = (next: OperatorPresence) => {
    if (viewOnly) return
    setPresence(next)
    const mapped: PersistedPresence =
      next === 'tech_break'
        ? 'tech_issue'
        : next === 'offline_queue'
          ? 'busy'
          : next === 'invisible'
            ? 'offline'
            : next
    void operatorsApi.list()
      .then((operators) => {
        const profile = operators.find((item) => item.name === operatorName)
        return profile ? operatorsApi.setPresence(profile.id, mapped) : undefined
      })
      .catch(() => setToast('Статус сохранён только локально: профиль оператора не найден.'))
  }

  const fontScale = armFontScaleFactor(uiSettings.fontScale)

  const cssVars = {
    '--arm-accent': scheme.accent,
    '--arm-accent-weak': scheme.accentWeak,
    '--arm-accent-control': scheme.accentControl,
    '--arm-header-bg': scheme.headerBg,
    '--arm-panel-bg': scheme.panelBg,
    '--arm-badge': scheme.badge,
    '--arm-on-accent': t.text.onAccent,
    '--arm-fill-secondary': t.fill.secondary,
    '--arm-fill-tertiary': t.fill.tertiary,
    '--arm-fill-quaternary': t.fill.quaternary,
    '--arm-stroke-secondary': t.stroke.secondary,
    '--arm-stroke-tertiary': t.stroke.tertiary,
    '--arm-t-primary': t.text.primary,
    '--arm-t-secondary': t.text.secondary,
    '--arm-t-tertiary': t.text.tertiary,
    '--arm-bg-elevated': t.bg.elevated,
    '--arm-bg-editor': t.bg.editor,
    '--arm-font-scale': String(fontScale),
  } as CSSProperties

  return (
    <main
      className="chat-arm-page"
      data-testid="chat-arm-app"
      data-scheme="belarusbank_emerald"
      data-theme={themeKind}
      style={{
        ...cssVars,
        background: scheme.panelBg,
        color: t.text.primary,
        fontSize: `${14 * fontScale}px`,
      }}
    >
      <div
        className="chat-arm-page__frame"
        style={{
          border: `1px solid ${scheme.accentWeak}`,
          background: scheme.panelBg,
        }}
      >
        <ArmOperatorView
          t={t}
          scheme={scheme}
          selectedQueue={selectedQueue}
          onSelectQueue={setSelectedQueue}
          reply={reply}
          suflerSuggestionText={suflerSuggestionText}
          onReplyChange={(value) => {
            setReply(value)
            if (!value) setSuflerSuggestionText('')
          }}
          onInsertSufler={(answerText) => {
            setReply(answerText)
            setSuflerSuggestionText(answerText)
            setToast('Подсказка суфлёра вставлена в черновик ответа.')
          }}
          toast={toast}
          onClearToast={() => setToast(null)}
          presence={presence}
          onPresenceChange={persistPresence}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          closeTopic={closeTopic}
          onCloseTopicChange={setCloseTopic}
          operatorName={operatorName}
          statsDrawerOpen={statsDrawerOpen}
          onStatsDrawerOpenChange={onStatsDrawerOpenChange}
          armRole={armRole}
          viewOnly={viewOnly}
          allowTransferInView={allowTransferInView}
          actorName={actorName || (viewOnly ? '' : operatorName)}
        />
      </div>
    </main>
  )
}
