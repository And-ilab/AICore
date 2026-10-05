import { useEffect, useRef } from 'react'
import {
  appendVoiceTranscript,
  useVoiceTextInput,
} from '../../hooks/useVoiceTextInput'
import { VoiceWaveform } from './VoiceWaveform'
import './VoiceInput.css'

const SPACE_ARM_MS = 400

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function isComposerTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && !!target.closest('[data-chat-composer="true"]')
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.closest('[data-voice-input="true"]')) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (tag === 'INPUT') {
    const type = (target as HTMLInputElement).type
    return type !== 'button' && type !== 'submit' && type !== 'checkbox' && type !== 'radio'
  }
  return false
}

function isOtherControl(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false
  if (target.closest('[data-voice-input="true"]')) return false
  const tag = target.tagName
  return tag === 'BUTTON' || tag === 'A' || target.getAttribute('role') === 'button'
}

function isCancelKey(event: KeyboardEvent): boolean {
  return event.code === 'KeyD' || event.key === 'd' || event.key === 'D'
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 15a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path
        d="M19 11a7 7 0 0 1-14 0M12 18v3"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden>
      <rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M6 6l12 12M18 6L6 18"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function VoiceInputButton({
  disabled,
  currentText,
  onTranscript,
  onError,
  onRecordingChange,
}: {
  disabled?: boolean
  currentText: string
  onTranscript: (nextText: string) => void
  onError?: (message: string) => void
  onRecordingChange?: (recording: boolean) => void
}) {
  const currentTextRef = useRef(currentText)
  currentTextRef.current = currentText
  const disabledRef = useRef(!!disabled)
  disabledRef.current = !!disabled
  const baseTextRef = useRef(currentText)
  const allowDraftRef = useRef(false)

  const applySessionText = (sessionText: string) => {
    if (!allowDraftRef.current) return
    onTranscript(appendVoiceTranscript(baseTextRef.current, sessionText))
  }

  const restoreBaseText = () => {
    allowDraftRef.current = false
    onTranscript(baseTextRef.current)
  }

  const captureBaseText = () => {
    baseTextRef.current = currentTextRef.current
    allowDraftRef.current = true
  }

  const voice = useVoiceTextInput({
    enabled: !disabled,
    onDraft: applySessionText,
    onTranscript: applySessionText,
    onCancel: restoreBaseText,
    onError,
  })

  const recordingRef = useRef(voice.recording)
  recordingRef.current = voice.recording
  const processingRef = useRef(voice.processing)
  processingRef.current = voice.processing
  const startRef = useRef(voice.startRecording)
  startRef.current = voice.startRecording
  const stopRef = useRef(voice.stopRecording)
  stopRef.current = voice.stopRecording
  const cancelRef = useRef(voice.cancelRecording)
  cancelRef.current = voice.cancelRecording
  const spaceArmedRef = useRef(true)
  const ignoreSpaceUntilRef = useRef(0)

  const beginRecording = () => {
    captureBaseText()
    void startRef.current()
  }

  useEffect(() => {
    onRecordingChange?.(voice.recording)
  }, [onRecordingChange, voice.recording])

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (isCancelKey(event)) {
        if (!recordingRef.current) return
        if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return
        event.preventDefault()
        cancelRef.current()
        return
      }

      if (event.code !== 'Space' && event.key !== ' ') return
      if (event.repeat || event.ctrlKey || event.metaKey || event.altKey) return
      if (processingRef.current) return
      if (!spaceArmedRef.current) return
      if (Date.now() < ignoreSpaceUntilRef.current) return

      if (recordingRef.current) {
        event.preventDefault()
        spaceArmedRef.current = false
        void stopRef.current()
        return
      }

      if (disabledRef.current) return
      if (isOtherControl(event.target)) return
      if (isEditableTarget(event.target)) {
        const inComposer = isComposerTarget(event.target)
        if (!inComposer || currentTextRef.current.trim().length > 0) return
      }
      event.preventDefault()
      spaceArmedRef.current = false
      ignoreSpaceUntilRef.current = Date.now() + SPACE_ARM_MS
      beginRecording()
    }

    const onKeyUp = (event: KeyboardEvent) => {
      if (event.code !== 'Space' && event.key !== ' ') return
      spaceArmedRef.current = true
    }

    window.addEventListener('keydown', onKeyDown, true)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown, true)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [])

  const title = voice.recording
    ? 'Остановить голосовой ввод'
    : voice.processing
      ? 'Распознаём речь…'
      : 'Голосовой ввод (пробел)'

  return (
    <div className="voice-input" data-voice-input="true">
      {voice.recording ? (
        <div className="voice-input__stage" role="status">
          <VoiceWaveform analyser={voice.analyser} active={voice.recording} />
          <span className="voice-input__timer">{formatElapsed(voice.elapsedMs)}</span>
          <button
            type="button"
            className="voice-input__button voice-input__button--cancel"
            title="Отменить голосовой ввод (D)"
            aria-label="Отменить голосовой ввод"
            data-testid="voice-input-cancel"
            onClick={() => voice.cancelRecording()}
          >
            <CloseIcon />
          </button>
        </div>
      ) : null}
      <button
        type="button"
        className={
          voice.recording
            ? 'voice-input__button voice-input__button--recording'
            : voice.processing
              ? 'voice-input__button voice-input__button--processing'
              : 'voice-input__button'
        }
        title={title}
        aria-label={title}
        aria-pressed={voice.recording}
        disabled={disabled || voice.processing}
        onClick={() => {
          if (!voice.recording && !voice.processing) {
            captureBaseText()
          }
          voice.toggleRecording()
        }}
        data-testid="voice-input-button"
      >
        {voice.processing ? <span className="voice-input__spinner" /> : voice.recording ? <StopIcon /> : <MicIcon />}
      </button>
    </div>
  )
}
