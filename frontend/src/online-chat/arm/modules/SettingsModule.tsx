import { useEffect, useState, type ReactNode } from 'react'
import {
  fetchAssignmentSettings,
  updateAssignmentSettings,
  type AssignmentMode,
} from '../../api/onlineChatApi'
import { Button, Row, Text } from '../primitives'
import { ArmModuleFrame } from './ArmModuleFrame'
import type { ArmModuleProps, ArmUiSettings } from './types'

export const ARM_UI_SETTINGS_KEY = 'arm-ui-settings-v1'
export const ARM_UI_SETTINGS_EVENT = 'arm-ui-settings-changed'

const DEFAULT_SETTINGS: ArmUiSettings = {
  soundEnabled: true,
  desktopNotify: false,
  compactQueue: false,
  autoExpandSummary: true,
  fontScale: 'md',
}

export function loadArmUiSettings(): ArmUiSettings {
  try {
    const raw = localStorage.getItem(ARM_UI_SETTINGS_KEY)
    if (!raw) return DEFAULT_SETTINGS
    const parsed = JSON.parse(raw) as Partial<ArmUiSettings>
    return {
      ...DEFAULT_SETTINGS,
      ...parsed,
      // Enter-to-send is fixed product behavior — ignore legacy localStorage overrides.
    }
  } catch {
    return DEFAULT_SETTINGS
  }
}

export function armFontScaleFactor(scale: ArmUiSettings['fontScale']): number {
  if (scale === 'sm') return 0.9
  if (scale === 'lg') return 1.12
  return 1
}

function persistSettings(settings: ArmUiSettings) {
  try {
    localStorage.setItem(ARM_UI_SETTINGS_KEY, JSON.stringify(settings))
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(ARM_UI_SETTINGS_EVENT, { detail: settings }))
}

export function SettingsModule({ t, scheme, onBack }: ArmModuleProps) {
  const [settings, setSettings] = useState<ArmUiSettings>(() => loadArmUiSettings())
  const [saved, setSaved] = useState(false)
  const [assignmentMode, setAssignmentMode] = useState<AssignmentMode>('strict_auto')
  const [assignmentSaving, setAssignmentSaving] = useState(false)
  const [assignmentNotice, setAssignmentNotice] = useState('')

  useEffect(() => {
    persistSettings(settings)
  }, [settings])

  useEffect(() => {
    void fetchAssignmentSettings()
      .then((result) => setAssignmentMode(result.mode))
      .catch(() => {})
  }, [])

  const patch = <K extends keyof ArmUiSettings>(key: K, value: ArmUiSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }))
    setSaved(true)
    window.setTimeout(() => setSaved(false), 1200)
  }

  const saveAssignmentMode = (mode: AssignmentMode) => {
    setAssignmentMode(mode)
    setAssignmentSaving(true)
    void updateAssignmentSettings(mode)
      .then(() => {
        setAssignmentNotice('Режим распределения сохранён')
        window.setTimeout(() => setAssignmentNotice(''), 1500)
      })
      .catch(() => setAssignmentNotice('Не удалось сохранить режим'))
      .finally(() => setAssignmentSaving(false))
  }

  return (
    <ArmModuleFrame
      t={t}
      scheme={scheme}
      title="Настройки АРМ"
      subtitle="Персональные параметры рабочего места оператора"
      onBack={onBack}
      actions={saved ? <Text style={{ fontSize: 12, color: scheme.accentControl }}>Сохранено</Text> : undefined}
    >
      <div style={{ padding: 16, maxWidth: 720, display: 'flex', flexDirection: 'column', gap: 14 }}>
        <Section t={t} title="Распределение диалогов">
          <Row style={{ gap: 8, flexWrap: 'wrap' }}>
            <Button
              size="sm"
              variant={assignmentMode === 'strict_auto' ? 'primary' : 'secondary'}
              disabled={assignmentSaving}
              onClick={() => saveAssignmentMode('strict_auto')}
            >
              Авто
            </Button>
            <Button
              size="sm"
              variant={assignmentMode === 'manual_plus_auto' ? 'primary' : 'secondary'}
              disabled={assignmentSaving}
              onClick={() => saveAssignmentMode('manual_plus_auto')}
            >
              Авто + Ручной
            </Button>
          </Row>
          {assignmentNotice ? (
            <Text style={{ fontSize: 12, color: scheme.accentControl, marginTop: 8 }}>
              {assignmentNotice}
            </Text>
          ) : null}
        </Section>

        <Section t={t} title="Уведомления">
          <Toggle
            label="Звук нового сообщения клиента"
            checked={settings.soundEnabled}
            onChange={(v) => patch('soundEnabled', v)}
          />
          <Toggle
            label="Desktop-уведомления браузера"
            checked={settings.desktopNotify}
            onChange={(v) => {
              patch('desktopNotify', v)
              if (v && 'Notification' in window && Notification.permission === 'default') {
                void Notification.requestPermission()
              }
            }}
          />
        </Section>

        <Section t={t} title="Очередь и диалоги">
          <Toggle
            label="Компактные карточки очереди"
            checked={settings.compactQueue}
            onChange={(v) => patch('compactQueue', v)}
          />
          <Toggle
            label="Автораскрывать summary клиента"
            checked={settings.autoExpandSummary}
            onChange={(v) => patch('autoExpandSummary', v)}
          />
          <Text style={{ fontSize: 12, color: t.text.secondary, lineHeight: 1.45 }}>
            Enter отправляет ответ клиенту, Shift+Enter — новая строка. Пробел включает и выключает голосовой ввод, D отменяет запись. Это поведение зафиксировано для всех ролей.
          </Text>
        </Section>

        <Section t={t} title="Отображение">
          <Text style={{ fontSize: 12, color: t.text.secondary, marginBottom: 8 }}>
            Масштаб текста интерфейса АРМ
          </Text>
          <Row style={{ gap: 8 }}>
            {([
              ['sm', 'Меньше'],
              ['md', 'Обычный'],
              ['lg', 'Крупнее'],
            ] as const).map(([id, label]) => (
              <Button
                key={id}
                size="sm"
                variant={settings.fontScale === id ? 'primary' : 'secondary'}
                onClick={() => patch('fontScale', id)}
              >
                {label}
              </Button>
            ))}
          </Row>
        </Section>

        <Section t={t} title="Сброс">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setSettings(DEFAULT_SETTINGS)
              setSaved(true)
            }}
          >
            Вернуть настройки по умолчанию
          </Button>
        </Section>
      </div>
    </ArmModuleFrame>
  )
}

function Section({
  t,
  title,
  children,
}: {
  t: ArmModuleProps['t']
  title: string
  children: ReactNode
}) {
  return (
    <section
      style={{
        padding: 14,
        borderRadius: 10,
        border: `1px solid ${t.stroke.secondary}`,
        background: t.bg.editor,
      }}
    >
      <Text weight="semibold" style={{ marginBottom: 10 }}>{title}</Text>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{children}</div>
    </section>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 12,
        cursor: 'pointer',
      }}
    >
      <Text style={{ fontSize: 13, lineHeight: 1.35 }}>{label}</Text>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 16, height: 16, accentColor: 'var(--arm-accent-control)' }}
      />
    </label>
  )
}
