import { useEffect, useState } from 'react'
import {
  loadOcrModelChoice,
  publicModelLabel,
  saveOcrModelChoice,
  type ModelOption,
} from '../admin/api/modelRegistry'

export function OcrModelPicker() {
  const [models, setModels] = useState<ModelOption[]>([])
  const [selected, setSelected] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [hidden, setHidden] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const payload = await loadOcrModelChoice()
        if (cancelled) return
        setModels(payload.models)
        setSelected(payload.selected_model)
      } catch (loadError) {
        if (cancelled) return
        const message = loadError instanceof Error ? loadError.message : ''
        if (message === 'permission_denied' || message === 'authentication_required') {
          setHidden(true)
          return
        }
        setError(message || 'Не удалось загрузить модели')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const onChange = async (modelId: string) => {
    const previous = selected
    setSelected(modelId)
    setBusy(true)
    setError('')
    try {
      const payload = await saveOcrModelChoice(modelId)
      setModels(payload.models)
      setSelected(payload.selected_model)
    } catch (saveError) {
      setSelected(previous)
      setError(saveError instanceof Error ? saveError.message : 'Не удалось сохранить модель')
    } finally {
      setBusy(false)
    }
  }

  if (hidden) return null

  const known = models.some((model) => model.id === selected)

  return (
    <label className="ocr-docs__model" data-testid="ocr-model">
      <span>Модель</span>
      <select
        aria-label="Модель OCR"
        data-testid="ocr-model-select"
        value={selected}
        disabled={busy || models.length === 0}
        onChange={(event) => void onChange(event.target.value)}
      >
        {!known && selected ? (
          <option value={selected}>{publicModelLabel(selected, selected)}</option>
        ) : null}
        {models.length === 0 ? <option value="">Загрузка…</option> : null}
        {models.map((model) => (
          <option key={model.id} value={model.id} disabled={model.available === false}>
            {publicModelLabel(model.id, model.label)}
          </option>
        ))}
      </select>
      {error ? <small role="alert">{error}</small> : null}
    </label>
  )
}
