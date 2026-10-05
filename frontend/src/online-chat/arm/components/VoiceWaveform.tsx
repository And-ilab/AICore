import { useEffect, useRef } from 'react'

const BAR_COUNT = 28

export function VoiceWaveform({
  analyser,
  active,
  width = 148,
  height = 32,
}: {
  analyser: AnalyserNode | null
  active: boolean
  width?: number
  height?: number
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const peaksRef = useRef<Float32Array>(new Float32Array(BAR_COUNT))

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !analyser || !active) return

    const context = canvas.getContext('2d')
    if (!context) return

    const samples = new Uint8Array(analyser.fftSize)
    let frame = 0

    const draw = () => {
      const ratio = window.devicePixelRatio || 1
      const nextWidth = Math.floor(width * ratio)
      const nextHeight = Math.floor(height * ratio)
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth
        canvas.height = nextHeight
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0)
      context.clearRect(0, 0, width, height)

      analyser.getByteTimeDomainData(samples)
      const peaks = peaksRef.current
      const gap = 2
      const barWidth = Math.max(2, (width - gap * (BAR_COUNT - 1)) / BAR_COUNT)
      const midY = height / 2
      const slice = Math.max(1, Math.floor(samples.length / BAR_COUNT))

      for (let index = 0; index < BAR_COUNT; index += 1) {
        const start = index * slice
        const end = Math.min(samples.length, start + slice)
        let peak = 0
        for (let offset = start; offset < end; offset += 1) {
          const amplitude = Math.abs(samples[offset] - 128) / 128
          if (amplitude > peak) peak = amplitude
        }
        const target = 0.1 + peak * 0.9
        peaks[index] += (target - peaks[index]) * 0.45
        const barHeight = Math.max(3, peaks[index] * (height - 4))
        const x = index * (barWidth + gap)
        const y = midY - barHeight / 2
        const gradient = context.createLinearGradient(x, y, x, y + barHeight)
        gradient.addColorStop(0, '#8EE0B4')
        gradient.addColorStop(0.5, '#2E9A63')
        gradient.addColorStop(1, '#007A43')
        context.fillStyle = gradient
        context.beginPath()
        const radius = Math.min(2, barWidth / 2)
        if (typeof context.roundRect === 'function') {
          context.roundRect(x, y, barWidth, barHeight, radius)
        } else {
          context.rect(x, y, barWidth, barHeight)
        }
        context.fill()
      }

      frame = window.requestAnimationFrame(draw)
    }

    frame = window.requestAnimationFrame(draw)
    return () => {
      window.cancelAnimationFrame(frame)
      peaksRef.current = new Float32Array(BAR_COUNT)
    }
  }, [analyser, active, height, width])

  return (
    <canvas
      ref={canvasRef}
      className="voice-input__waveform-canvas"
      width={width}
      height={height}
      aria-hidden
    />
  )
}
