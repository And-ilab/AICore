import { useState } from 'react'
import { Button, Card } from '../components'
import {
  createUserSkill,
  deleteUserSkill,
  updateUserSkill,
  type AssistantSkill,
} from './api/skills'

interface MySkillsPanelProps {
  skills: AssistantSkill[]
  demoMode?: boolean
  onClose: () => void
  onChange: (skills: AssistantSkill[]) => void
}

export function MySkillsPanel({
  skills,
  demoMode = false,
  onClose,
  onChange,
}: MySkillsPanelProps) {
  const mine = skills.filter((item) => item.scope === 'user')
  const [selectedId, setSelectedId] = useState<number | null>(mine[0]?.id ?? null)
  const selected = mine.find((item) => item.id === selectedId) ?? null
  const [name, setName] = useState(selected?.name ?? '')
  const [alias, setAlias] = useState(selected?.alias ?? '')
  const [instruction, setInstruction] = useState(selected?.instruction ?? '')
  const [needsAttachment, setNeedsAttachment] = useState(selected?.needs_attachment ?? false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const apply = (item: AssistantSkill | null) => {
    setSelectedId(item?.id ?? null)
    setName(item?.name ?? '')
    setAlias(item?.alias ?? '')
    setInstruction(item?.instruction ?? '')
    setNeedsAttachment(item?.needs_attachment ?? false)
  }

  const replace = (next: AssistantSkill) => {
    onChange(skills.filter((item) => item.id !== next.id).concat(next))
    apply(next)
  }

  const createLocal = () => {
    const created: AssistantSkill = {
      id: -1000 - Date.now(),
      code: '',
      scope: 'user',
      owner_id: 0,
      name: 'Мой навык',
      alias: `moy-${Date.now().toString(36)}`,
      instruction: 'Как отвечать на мои запросы.',
      needs_attachment: false,
      enabled: true,
      department_scope: '',
    }
    onChange([...skills, created])
    apply(created)
  }

  const onCreate = async () => {
    setBusy(true)
    setError('')
    try {
      if (demoMode) {
        createLocal()
        return
      }
      const created = await createUserSkill({
        name: 'Мой навык',
        alias: `moy-${Date.now().toString(36)}`,
        instruction: 'Как отвечать на мои запросы.',
      })
      onChange([...skills, created])
      apply(created)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось создать')
    } finally {
      setBusy(false)
    }
  }

  const onSave = async () => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      if (demoMode || selected.id < 0) {
        replace({
          ...selected,
          name,
          alias: alias.replace(/^\//, ''),
          instruction,
          needs_attachment: needsAttachment,
        })
        return
      }
      replace(
        await updateUserSkill(selected.id, {
          name,
          alias: alias.replace(/^\//, ''),
          instruction,
          needs_attachment: needsAttachment,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось сохранить')
    } finally {
      setBusy(false)
    }
  }

  const onDelete = async () => {
    if (!selected) return
    setBusy(true)
    setError('')
    try {
      if (!demoMode && selected.id > 0) {
        await deleteUserSkill(selected.id)
      }
      const next = skills.filter((item) => item.id !== selected.id)
      onChange(next)
      apply(next.find((item) => item.scope === 'user') ?? null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Не удалось удалить')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="asst-my-skills" data-testid="asst-my-skills-panel">
      <header className="asst-my-skills__header">
        <h2>Мои навыки</h2>
        <Button type="button" variant="ghost" onClick={onClose} data-testid="asst-my-skills-close">
          Закрыть
        </Button>
      </header>
      {error ? (
        <p className="asst-composer__attach-error" role="alert">{error}</p>
      ) : null}
      <div className="asst-my-skills__layout">
        <aside>
          <Button
            type="button"
            variant="secondary"
            disabled={busy}
            onClick={() => void onCreate()}
            data-testid="asst-my-skill-add"
          >
            Создать
          </Button>
          <ul data-testid="asst-my-skill-list">
            {mine.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={item.id === selectedId ? 'is-active' : undefined}
                  onClick={() => apply(item)}
                  data-testid={`asst-my-skill-${item.id}`}
                >
                  {item.name}
                  <small>/{item.alias}</small>
                </button>
              </li>
            ))}
            {!mine.length ? <li>Пока нет личных навыков.</li> : null}
          </ul>
        </aside>
        <Card className="asst-my-skills__form">
          {!selected ? (
            <p>Создайте навык — он будет доступен во всех ваших диалогах.</p>
          ) : (
            <>
              <label>
                Название
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  data-testid="asst-my-skill-name"
                />
              </label>
              <label>
                /алиас
                <input
                  value={alias}
                  onChange={(event) => setAlias(event.target.value)}
                  data-testid="asst-my-skill-alias"
                />
              </label>
              <label>
                Инструкция
                <textarea
                  rows={6}
                  value={instruction}
                  onChange={(event) => setInstruction(event.target.value)}
                  data-testid="asst-my-skill-instruction"
                />
              </label>
              <label className="asst-my-skills__check">
                <input
                  type="checkbox"
                  checked={needsAttachment}
                  onChange={(event) => setNeedsAttachment(event.target.checked)}
                  data-testid="asst-my-skill-attach"
                />
                Нужно вложение
              </label>
              <div className="asst-my-skills__actions">
                <Button
                  type="button"
                  disabled={busy}
                  onClick={() => void onSave()}
                  data-testid="asst-my-skill-save"
                >
                  Сохранить
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void onDelete()}
                  data-testid="asst-my-skill-delete"
                >
                  Удалить
                </Button>
              </div>
            </>
          )}
        </Card>
      </div>
    </div>
  )
}
