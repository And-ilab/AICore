import { useEffect, useMemo, useState } from 'react'
import { operatorsApi, type ChatOperator } from '../../api/managementApi'
import { Button, Pill, Row, Text } from '../primitives'
import { ArmModuleFrame, ModuleEmpty, presenceColor } from './ArmModuleFrame'
import { COLLEAGUE_DIALOG_DEMO, DEMO_CONTACTS } from './demoData'
import type { ArmModuleProps, PresenceTone } from './types'

type Colleague = {
  id: string
  name: string
  department: string
  presence: PresenceTone
  activeDialogs: number
}

function mapPresence(presence: string): PresenceTone {
  if (presence === 'online') return 'online'
  if (presence === 'busy' || presence === 'meeting' || presence === 'training') return 'busy'
  if (presence === 'break' || presence === 'lunch' || presence === 'tech_issue') return 'away'
  return 'offline'
}

function presenceLabel(presence: PresenceTone): string {
  if (presence === 'online') return 'в сети'
  if (presence === 'busy') return 'занят'
  if (presence === 'away') return 'отошёл'
  return 'не в сети'
}

/**
 * Separate module for UC-O8 / FR-CHAT-14:
 * 1) pick an operator
 * 2) inspect their dialogs in view-only mode
 */
export function ColleagueDialogsModule({
  t,
  scheme,
  operatorName,
  armRole,
  onBack,
}: ArmModuleProps) {
  const [colleagues, setColleagues] = useState<Colleague[]>(
    DEMO_CONTACTS.map((c) => ({
      id: c.id,
      name: c.name,
      department: c.department,
      presence: c.presence,
      activeDialogs: c.activeDialogs ?? 0,
    })),
  )
  const [query, setQuery] = useState('')
  const [selectedName, setSelectedName] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    void operatorsApi
      .list()
      .then((list) => {
        if (cancelled || !list.length) return
        const mapped = list
          .filter((item) => item.is_active !== false && item.name !== operatorName)
          .map((item: ChatOperator) => ({
            id: String(item.id),
            name: item.name,
            department:
              item.department_name
              || (typeof item.department === 'object' && item.department
                ? item.department.name
                : 'Без отдела'),
            presence: mapPresence(item.presence),
            activeDialogs: item.active_dialogs ?? 0,
          }))
        if (mapped.length) {
          setColleagues(mapped)
          setSelectedName((prev) => prev ?? mapped[0]?.name ?? null)
        }
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [operatorName])

  useEffect(() => {
    if (!selectedName && colleagues[0]) setSelectedName(colleagues[0].name)
  }, [colleagues, selectedName])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return colleagues
    return colleagues.filter(
      (item) =>
        item.name.toLowerCase().includes(q)
        || item.department.toLowerCase().includes(q),
    )
  }, [colleagues, query])

  const selected = colleagues.find((item) => item.name === selectedName) ?? null
  const dialogs =
    (selected && (COLLEAGUE_DIALOG_DEMO[selected.name] ?? []))
    || []

  const openViewArm = () => {
    if (!selected) return
    const params = new URLSearchParams({ mode: 'view', operator: selected.name })
    if (armRole === 'supervisor') params.set('transfer', '1')
    window.location.assign(`/online-chat/operators?${params.toString()}`)
  }

  return (
    <ArmModuleFrame
      t={t}
      scheme={scheme}
      title="Диалоги коллег"
      onBack={onBack}
      bodyStyle={{ overflow: 'hidden', display: 'flex' }}
      actions={
        selected ? (
          <Button variant="primary" size="sm" onClick={openViewArm}>
            Открыть АРМ просмотра
          </Button>
        ) : undefined
      }
    >
      <aside
        style={{
          width: 300,
          flexShrink: 0,
          borderRight: `1px solid ${t.stroke.secondary}`,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          background: t.bg.editor,
        }}
      >
        <div style={{ padding: 12 }}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск оператора"
            style={{
              width: '100%',
              padding: '8px 10px',
              borderRadius: 8,
              border: `1px solid ${t.stroke.secondary}`,
              background: t.bg.elevated,
              color: t.text.primary,
              fontFamily: 'inherit',
              fontSize: 13,
            }}
          />
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 12px' }}>
          {filtered.map((item) => {
            const active = item.name === selectedName
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedName(item.name)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  padding: '10px 12px',
                  marginBottom: 4,
                  borderRadius: 8,
                  border: `1px solid ${active ? scheme.accent : 'transparent'}`,
                  background: active ? t.fill.tertiary : 'transparent',
                  cursor: 'pointer',
                  fontFamily: 'inherit',
                  color: t.text.primary,
                }}
              >
                <Row style={{ gap: 8, alignItems: 'center' }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: 999,
                      background: presenceColor(item.presence),
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <Text weight="semibold" style={{ fontSize: 13 }}>{item.name}</Text>
                    <Text style={{ fontSize: 11, color: t.text.secondary }}>
                      {item.department} · {presenceLabel(item.presence)}
                    </Text>
                  </div>
                  <Pill size="sm">{item.activeDialogs || dialogsFor(item.name).length}</Pill>
                </Row>
              </button>
            )
          })}
        </div>
      </aside>

      <section style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {!selected ? (
          <ModuleEmpty t={t} title="Выберите оператора" hint="Список слева — сотрудники смены." />
        ) : (
          <>
            <div
              style={{
                padding: '14px 16px',
                borderBottom: `1px solid ${t.stroke.secondary}`,
                flexShrink: 0,
              }}
            >
              <Row style={{ justifyContent: 'space-between', gap: 12, alignItems: 'center' }}>
                <div>
                  <Text weight="semibold" style={{ fontSize: 16 }}>
                    Просмотр · {selected.name}
                  </Text>
                  <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 2 }}>
                    {selected.department} · режим только чтения, ответы недоступны
                  </Text>
                </div>
                <Pill tone="warning" size="sm">read-only</Pill>
              </Row>
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: 12 }}>
              {dialogs.length === 0 ? (
                <ModuleEmpty
                  t={t}
                  title="Нет активных диалогов"
                  hint="У оператора сейчас пустая очередь. Можно открыть полный АРМ просмотра."
                />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {dialogs.map((dialog) => (
                    <div
                      key={`${selected.name}-${dialog.client}`}
                      style={{
                        padding: 14,
                        borderRadius: 10,
                        border: `1px solid ${t.stroke.secondary}`,
                        background: t.bg.editor,
                      }}
                    >
                      <Row style={{ justifyContent: 'space-between', gap: 8 }}>
                        <Text weight="semibold">{dialog.client}</Text>
                        <Row style={{ gap: 6 }}>
                          {dialog.urgent ? <Pill tone="warning" size="sm">срочно</Pill> : null}
                          <Pill size="sm">{dialog.wait}</Pill>
                        </Row>
                      </Row>
                      <Text style={{ fontSize: 12, color: t.text.secondary, marginTop: 4 }}>
                        {dialog.channel}
                      </Text>
                      <Text style={{ fontSize: 13, marginTop: 8, lineHeight: 1.4 }}>
                        {dialog.preview}
                      </Text>
                      <Row style={{ marginTop: 10, gap: 8 }}>
                        <Button variant="secondary" size="sm" onClick={openViewArm}>
                          Открыть в АРМ просмотра
                        </Button>
                      </Row>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </section>
    </ArmModuleFrame>
  )
}

function dialogsFor(name: string) {
  return COLLEAGUE_DIALOG_DEMO[name] ?? []
}
