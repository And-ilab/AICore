import { useEffect, useState } from 'react'
import { fetchOktellCall, fetchOktellCalls, type OktellLiveCall } from '../api/oktellCalls'

function pickLatest(calls: OktellLiveCall[]): OktellLiveCall | null {
  const live = calls.filter((item) => item.state !== 'stopped')
  if (!live.length) return null
  return [...live].sort((a, b) => (b.created_at ?? 0) - (a.created_at ?? 0))[0]
}

function pickCall(calls: OktellLiveCall[], preferredId: string): OktellLiveCall | null {
  const latest = pickLatest(calls)
  if (preferredId) {
    return calls.find((item) => item.Idchain === preferredId && item.state !== 'stopped') ?? latest
  }
  return latest
}

export function useOktellActiveCall(preferredId = 'live') {
  const [call, setCall] = useState<OktellLiveCall | null>(null)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      const [calls, preferred] = await Promise.all([
        fetchOktellCalls(),
        preferredId ? fetchOktellCall(preferredId) : Promise.resolve(null),
      ])
      if (cancelled) return
      const merged = preferred
        ? [preferred, ...calls.filter((item) => item.Idchain !== preferred.Idchain)]
        : calls
      setCall((prev) => {
        const next = pickCall(merged, preferredId)
        if (
          prev &&
          next &&
          prev.Idchain === next.Idchain &&
          prev.state === next.state &&
          (prev.events?.length ?? 0) === (next.events?.length ?? 0)
        ) {
          return prev
        }
        return next
      })
    }
    void load()
    const timer = window.setInterval(() => {
      void load()
    }, 1000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [preferredId])

  return call
}
