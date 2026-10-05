import { useCallback, useRef, useState } from 'react'
import { transcribeUtterance } from '../api/transcribe'

export type DualSpeaker = 'client' | 'operator'

interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  start: () => void
  stop: () => void
  abort?: () => void
  onresult: ((event: SpeechRecognitionEventLike) => void) | null
  onerror: ((event: { error?: string }) => void) | null
  onend: (() => void) | null
  onspeechstart: (() => void) | null
  onspeechend: (() => void) | null
  onaudiostart: (() => void) | null
  onsoundstart: (() => void) | null
}

interface SpeechRecognitionEventLike {
  resultIndex: number
  results: ArrayLike<{
    isFinal: boolean
    0: { transcript: string }
  }>
}

type SpeechRecognitionCtor = new () => SpeechRecognitionLike

function speechCtor(): SpeechRecognitionCtor | null {
  const holder = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor
    webkitSpeechRecognition?: SpeechRecognitionCtor
  }
  return holder.SpeechRecognition || holder.webkitSpeechRecognition || null
}

function rms(samples: Float32Array): number {
  let sum = 0
  for (let index = 0; index < samples.length; index += 1) {
    const value = samples[index]
    sum += value * value
  }
  return Math.sqrt(sum / Math.max(1, samples.length))
}

function downsample(input: Float32Array, inRate: number, outRate: number): Float32Array {
  if (inRate === outRate) return input
  const ratio = inRate / outRate
  const length = Math.max(1, Math.floor(input.length / ratio))
  const output = new Float32Array(length)
  for (let index = 0; index < length; index += 1) {
    output[index] = input[Math.min(input.length - 1, Math.floor(index * ratio))]
  }
  return output
}

function encodeWav(float32: Float32Array, sampleRate: number): Blob {
  const pcm = new Int16Array(float32.length)
  for (let index = 0; index < float32.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, float32[index]))
    pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
  }
  const buffer = new ArrayBuffer(44 + pcm.length * 2)
  const view = new DataView(buffer)
  const write = (offset: number, text: string) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index))
    }
  }
  write(0, 'RIFF')
  view.setUint32(4, 36 + pcm.length * 2, true)
  write(8, 'WAVE')
  write(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true)
  view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true)
  view.setUint16(34, 16, true)
  write(36, 'data')
  view.setUint32(40, pcm.length * 2, true)
  new Int16Array(buffer, 44).set(pcm)
  return new Blob([buffer], { type: 'audio/wav' })
}

function mixMono(buffer: AudioBuffer): Float32Array {
  const left = buffer.getChannelData(0)
  if (buffer.numberOfChannels < 2) return new Float32Array(left)
  const right = buffer.getChannelData(1)
  const mixed = new Float32Array(left.length)
  for (let index = 0; index < left.length; index += 1) {
    mixed[index] = (left[index] + right[index]) * 0.5
  }
  return mixed
}

function attachPcmUtterances(
  context: AudioContext,
  stream: MediaStream,
  recordingRef: { current: boolean },
  onLevel: (level: number) => void,
  onWav: (wav: Blob) => void,
  speakThreshold = 0.02,
): { processor: ScriptProcessorNode; stop: () => void } {
  const source = context.createMediaStreamSource(stream)
  const processor = context.createScriptProcessor(4096, 2, 1)
  const sink = context.createGain()
  sink.gain.value = 0
  source.connect(processor)
  processor.connect(sink)
  sink.connect(context.destination)
  const chunks: Float32Array[] = []
  let speaking = false
  let silenceMs = 0
  processor.onaudioprocess = (event) => {
    if (!recordingRef.current) return
    const input = mixMono(event.inputBuffer)
    const level = rms(input)
    onLevel(level)
    if (level >= speakThreshold) {
      speaking = true
      silenceMs = 0
      chunks.push(input)
    } else if (speaking) {
      silenceMs += (input.length / event.inputBuffer.sampleRate) * 1000
      chunks.push(input)
      if (silenceMs >= 700) {
        speaking = false
        silenceMs = 0
        const mergedLength = chunks.reduce((sum, item) => sum + item.length, 0)
        const merged = new Float32Array(mergedLength)
        let offset = 0
        for (const item of chunks) {
          merged.set(item, offset)
          offset += item.length
        }
        chunks.length = 0
        const rate = event.inputBuffer.sampleRate
        const pcm = downsample(merged, rate, 16000)
        if (pcm.length < 16000 * 0.35) return
        onWav(encodeWav(pcm, 16000))
      }
    }
  }
  return {
    processor,
    stop: () => {
      processor.disconnect()
      source.disconnect()
      sink.disconnect()
    },
  }
}

export interface LiveDualAsrState {
  recording: boolean
  paused: boolean
  micLevel: number
  systemLevel: number
  micSpeaker: DualSpeaker
  systemSpeaker: DualSpeaker
  status: string
  caption: string
  systemCaption: string
  error: string
  systemCapture: boolean
}

function isInsecureRemoteOrigin(): boolean {
  if (window.isSecureContext) return false
  const host = window.location.hostname
  return host !== 'localhost' && host !== '127.0.0.1'
}

export function useLiveDualAsr(
  onUtterance: (speaker: DualSpeaker, text: string, isFinal: boolean) => void,
) {
  const [state, setState] = useState<LiveDualAsrState>({
    recording: false,
    paused: false,
    micLevel: 0,
    systemLevel: 0,
    micSpeaker: 'client',
    systemSpeaker: 'operator',
    status: '',
    caption: '',
    systemCaption: '',
    error: '',
    systemCapture: false,
  })
  const recordingRef = useRef(false)
  const pausedRef = useRef(false)
  const micSpeakerRef = useRef<DualSpeaker>('client')
  const systemSpeakerRef = useRef<DualSpeaker>('operator')
  const onUtteranceRef = useRef(onUtterance)
  onUtteranceRef.current = onUtterance
  const cleanupRef = useRef<(() => void) | null>(null)
  const systemCleanupRef = useRef<(() => void) | null>(null)
  const finalizeTimerRef = useRef<number | null>(null)
  const lastInterimRef = useRef('')
  const lastBrowserSpeechAtRef = useRef(0)
  const levelPulseRef = useRef(0)
  const hearingRef = useRef(false)

  const setPartial = useCallback((patch: Partial<LiveDualAsrState>) => {
    setState((current) => ({ ...current, ...patch }))
  }, [])

  const swapSpeakers = useCallback(() => {
    setState((current) => {
      const micSpeaker = current.micSpeaker === 'client' ? 'operator' : 'client'
      const systemSpeaker = micSpeaker === 'client' ? 'operator' : 'client'
      micSpeakerRef.current = micSpeaker
      systemSpeakerRef.current = systemSpeaker
      return { ...current, micSpeaker, systemSpeaker }
    })
  }, [])

  const stop = useCallback(() => {
    recordingRef.current = false
    pausedRef.current = false
    if (finalizeTimerRef.current != null) {
      window.clearTimeout(finalizeTimerRef.current)
      finalizeTimerRef.current = null
    }
    hearingRef.current = false
    window.cancelAnimationFrame(levelPulseRef.current)
    systemCleanupRef.current?.()
    systemCleanupRef.current = null
    cleanupRef.current?.()
    cleanupRef.current = null
    setPartial({
      recording: false,
      paused: false,
      micLevel: 0,
      systemLevel: 0,
      caption: '',
      systemCaption: '',
      systemCapture: false,
      status: 'Запись остановлена',
    })
  }, [setPartial])

  const start = useCallback(async () => {
    if (recordingRef.current) return
    const insecure = isInsecureRemoteOrigin()
    const Recognition = speechCtor()
    const emitHeard = (text: string, isFinal: boolean) => {
      const cleaned = text.trim()
      if (!cleaned || pausedRef.current) return
      setPartial({ caption: cleaned })
      onUtteranceRef.current(micSpeakerRef.current, cleaned, isFinal)
    }

    // SpeechRecognition starts on click; getUserMedia only drives the level meter.
    if (Recognition) {
      recordingRef.current = true
      const recognition = new Recognition()
      recognition.lang = 'ru-RU'
      recognition.continuous = true
      recognition.interimResults = true
      recognition.onresult = (event) => {
        lastBrowserSpeechAtRef.current = Date.now()
        let finalChunk = ''
        let interim = ''
        for (let index = event.resultIndex; index < event.results.length; index += 1) {
          const piece = String(event.results[index]?.[0]?.transcript || '')
          if (event.results[index].isFinal) finalChunk += piece
          else interim += piece
        }
        const finalText = finalChunk.trim()
        const interimText = interim.trim()
        if (finalText) {
          lastInterimRef.current = ''
          if (finalizeTimerRef.current != null) {
            window.clearTimeout(finalizeTimerRef.current)
            finalizeTimerRef.current = null
          }
          emitHeard(finalText, true)
          return
        }
        if (!interimText) return
        lastInterimRef.current = interimText
        emitHeard(interimText, false)
        if (finalizeTimerRef.current != null) {
          window.clearTimeout(finalizeTimerRef.current)
        }
        finalizeTimerRef.current = window.setTimeout(() => {
          const pending = lastInterimRef.current.trim()
          if (pending) emitHeard(pending, true)
          lastInterimRef.current = ''
        }, 1200)
      }
      recognition.onerror = (event) => {
        if (event.error === 'no-speech' || event.error === 'aborted') return
        setPartial({
          error: '',
          status:
            event.error === 'network' || event.error === 'service-not-allowed' || insecure
              ? `Chrome не отдаёт текст по HTTP (${window.location.host}). Введите реплику в поле.`
              : `Микрофон: ${event.error || 'ошибка распознавания'}`,
        })
      }
      recognition.onend = () => {
        if (!recordingRef.current) return
        window.setTimeout(() => {
          if (!recordingRef.current) return
          try {
            recognition.start()
          } catch {
            /* already started */
          }
        }, 250)
      }
      try {
        recognition.start()
      } catch {
        recordingRef.current = false
        setPartial({ error: 'Не удалось запустить распознавание микрофона' })
        return
      }
      pausedRef.current = false
      setPartial({
        recording: true,
        paused: false,
        error: '',
        caption: '',
        micLevel: 0,
        systemCapture: false,
        status: 'Говорите в микрофон — полоска прыгает от голоса. После паузы текст должен появиться в ленте.',
      })

      let micStream: MediaStream | null = null
      let micContext: AudioContext | null = null
      let micCapture: { stop: () => void } | null = null
      void navigator.mediaDevices
        .getUserMedia({ audio: true, video: false })
        .then((stream) => {
          if (!recordingRef.current) {
            stream.getTracks().forEach((track) => track.stop())
            return
          }
          micStream = stream
          micContext = new AudioContext()
          void micContext.resume()
          micCapture = attachPcmUtterances(
            micContext,
            stream,
            recordingRef,
            (level) => setState((current) => ({ ...current, micLevel: level })),
            (wav) => {
              // Chrome may expose SpeechRecognition but never return text
              // (common in local/Docker HTTP environments). In that case,
              // use the backend STT for the same microphone utterance.
              if (Date.now() - lastBrowserSpeechAtRef.current < 2000) return
              if (pausedRef.current) return
              const speaker = micSpeakerRef.current
              void transcribeUtterance(wav, speaker)
                .then((text) => {
                  const cleaned = text.trim()
                  if (!cleaned) return
                  setPartial({ caption: cleaned })
                  onUtteranceRef.current(speaker, cleaned, true)
                })
                .catch(() => {
                  setPartial({
                    status: 'Не удалось распознать реплику. Повторите её или введите текст вручную.',
                  })
                })
            },
          )
        })
        .catch(() => {
          setPartial({
            error: 'Нет доступа к микрофону. Разрешите его в браузере и нажмите «Начать имитацию» снова.',
          })
        })

      cleanupRef.current = () => {
        try {
          recognition.onend = null
          recognition.stop()
        } catch {
          /* already stopped */
        }
        micCapture?.stop()
        micStream?.getTracks().forEach((track) => track.stop())
        void micContext?.close()
        systemCleanupRef.current?.()
        systemCleanupRef.current = null
      }
      return
    }

    recordingRef.current = true
    let micStream: MediaStream
    try {
      micStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
        video: false,
      })
    } catch {
      setPartial({ error: 'Нет доступа к микрофону. Разрешите его в браузере.' })
      recordingRef.current = false
      return
    }

    pausedRef.current = false
    setPartial({
      recording: true,
      paused: false,
      error: '',
      caption: '',
      status: 'В этом браузере нет Chrome Speech Recognition. Введите реплику в поле или говорите паузами для локального STT.',
      systemCapture: false,
    })

    const micContext = new AudioContext()
    void micContext.resume()
    const micCapture = attachPcmUtterances(
      micContext,
      micStream,
      recordingRef,
      (level) => setState((current) => ({ ...current, micLevel: level })),
      (wav) => {
        if (pausedRef.current) return
        const speaker = micSpeakerRef.current
        void transcribeUtterance(wav, speaker)
          .then((text) => {
            if (text) onUtteranceRef.current(speaker, text, true)
          })
          .catch(() => {
            /* manual input still available */
          })
      },
    )

    cleanupRef.current = () => {
      micCapture.stop()
      micStream.getTracks().forEach((track) => track.stop())
      void micContext.close()
      systemCleanupRef.current?.()
      systemCleanupRef.current = null
    }
  }, [setPartial])

  const enableSystemAudio = useCallback(async () => {
    if (!recordingRef.current || systemCleanupRef.current) return
    let systemStream: MediaStream
    try {
      systemStream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      })
    } catch {
      setPartial({
        status:
          'Системный звук не выбран. В Chrome в окне шаринга отметьте «Также системный звук».',
      })
      return
    }
    const audioTracks = systemStream.getAudioTracks()
    if (!audioTracks.length) {
      systemStream.getTracks().forEach((track) => track.stop())
      setPartial({
        status:
          'Нет дорожки звука. Выберите вкладку или экран и включите «Также системный звук».',
      })
      return
    }
    const systemContext = new AudioContext({ sampleRate: 16000 })
    void systemContext.resume()
    const systemCapture = attachPcmUtterances(
      systemContext,
      systemStream,
      recordingRef,
      (level) => setState((current) => ({ ...current, systemLevel: level })),
      (wav) => {
        if (pausedRef.current) return
        const speaker: DualSpeaker = 'operator'
        setPartial({ status: 'Распознаю реплику оператора…', error: '' })
        void transcribeUtterance(wav, speaker)
          .then((text) => {
            if (!text) return
            onUtteranceRef.current(speaker, text, true)
            setPartial({
              systemCaption: text,
              status: `Оператор: ${text}`,
              error: '',
            })
          })
          .catch((error: unknown) => {
            const message =
              error instanceof Error ? error.message : 'Системный звук не распознан'
            if (message.includes('could not recognize')) {
              setPartial({ status: 'Оператор говорил, но фразу не разобрали. Повторите громче.' })
              return
            }
            setPartial({ error: message })
          })
      },
      0.006,
    )
    const preview = document.createElement('video')
    preview.muted = true
    preview.playsInline = true
    preview.autoplay = true
    preview.setAttribute('aria-hidden', 'true')
    preview.style.cssText =
      'position:fixed;width:1px;height:1px;opacity:0;pointer-events:none;left:-20px;top:-20px'
    preview.srcObject = systemStream
    document.body.appendChild(preview)
    void preview.play().catch(() => {
      /* capture still runs without visible preview */
    })
    const releasePreview = () => {
      preview.srcObject = null
      preview.remove()
    }
    const releaseSystem = () => {
      if (!systemCleanupRef.current) return
      systemCleanupRef.current = null
      releasePreview()
      systemCapture.stop()
      systemStream.getTracks().forEach((track) => track.stop())
      void systemContext.close()
      setPartial({
        systemCapture: false,
        systemLevel: 0,
        systemCaption: '',
        status: recordingRef.current
          ? 'Системный звук отключён. Микрофон продолжает писать клиента.'
          : 'Запись остановлена',
      })
    }
    systemStream.getTracks().forEach((track) => {
      track.addEventListener('ended', releaseSystem)
    })
    setPartial({
      systemCapture: true,
      error: '',
      systemCaption: '',
      status: 'Два канала сразу: микрофон — клиент, системный звук — оператор. Реплики оператора появятся в ленте.',
    })
    systemCleanupRef.current = () => {
      systemStream.getTracks().forEach((track) => {
        track.removeEventListener('ended', releaseSystem)
      })
      releasePreview()
      systemCapture.stop()
      systemStream.getTracks().forEach((track) => track.stop())
      void systemContext.close()
    }
  }, [setPartial])

  const pause = useCallback(() => {
    if (!recordingRef.current || pausedRef.current) return
    pausedRef.current = true
    setPartial({
      paused: true,
      status: 'Распознавание на паузе',
    })
  }, [setPartial])

  const resume = useCallback(() => {
    if (!recordingRef.current || !pausedRef.current) return
    pausedRef.current = false
    setPartial({
      paused: false,
      status: 'Распознавание продолжено',
    })
  }, [setPartial])

  return { ...state, start, stop, pause, resume, swapSpeakers, enableSystemAudio }
}
