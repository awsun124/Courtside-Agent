import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, requestJson } from './api'
import { windowDays } from './format'
import type { DataMode, HistoryItem, HistoryResponse, LatestResponse } from './types'

export function useBriefing() {
  const [mode, setMode] = useState<DataMode>(() => new URLSearchParams(window.location.search).get('mode') === 'sample' ? 'sample' : 'live')
  const [data, setData] = useState<LatestResponse | null>(null)
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [days, setDays] = useState(7)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [historyError, setHistoryError] = useState(false)
  const [retryUntil, setRetryUntil] = useState(0)
  const [now, setNow] = useState(Date.now())
  const currentMode = useRef(mode)
  const readController = useRef<AbortController | null>(null)
  const refreshController = useRef<AbortController | null>(null)

  const load = useCallback(async (selectedMode: DataMode, signal: AbortSignal, showLoading = true) => {
    if (showLoading) { setLoading(true); setError(null) }
    const results = await Promise.allSettled([
      requestJson<LatestResponse>(`/api/briefings/latest?mode=${selectedMode}`, { signal }),
      requestJson<HistoryResponse>(`/api/briefings?mode=${selectedMode}&limit=4`, { signal }),
    ])
    if (signal.aborted || currentMode.current !== selectedMode) return
    const [latest, past] = results
    if (latest.status === 'fulfilled' && latest.value.status?.data_mode === selectedMode &&
        (!latest.value.briefing || latest.value.briefing.data_mode === selectedMode)) {
      setData(latest.value)
      if (showLoading && latest.value.briefing) setDays(windowDays(latest.value.briefing.window_start, latest.value.briefing.as_of))
    } else {
      setError(latest.status === 'rejected' ? latest.reason.message : 'The API returned the wrong data mode.')
    }
    if (past.status === 'fulfilled' && past.value.data_mode === selectedMode) {
      setHistory(past.value.briefings)
      setHistoryError(false)
    } else setHistoryError(true)
    setLoading(false)
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    readController.current = controller
    void load(mode, controller.signal)
    return () => controller.abort()
  }, [mode, load])

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => { window.clearInterval(timer); refreshController.current?.abort() }
  }, [])

  const lastAttempt = data?.status.last_attempt
  const serverRunning = lastAttempt?.status === 'running' && Date.parse(lastAttempt.lease_until) > now
  const sourceCooldown = mode === 'live' && lastAttempt && lastAttempt.requests_used > 0 ? Date.parse(lastAttempt.started_at) + 30 * 60 * 1000 : 0
  const retrySeconds = Math.max(0, Math.ceil((Math.max(retryUntil, sourceCooldown) - now) / 1000))

  useEffect(() => {
    if (!serverRunning) return
    let controller = new AbortController()
    const timer = window.setInterval(() => {
      controller.abort()
      controller = new AbortController()
      void load(mode, controller.signal, false)
    }, 3000)
    return () => { window.clearInterval(timer); controller.abort() }
  }, [serverRunning, mode, load])

  function changeMode(next: DataMode) {
    if (next === mode || refreshing) return
    readController.current?.abort()
    currentMode.current = next
    setData(null)
    setHistory([])
    setDays(7)
    setError(null)
    setRetryUntil(0)
    setLoading(true)
    setMode(next)
    const url = new URL(window.location.href)
    if (next === 'sample') url.searchParams.set('mode', 'sample')
    else url.searchParams.delete('mode')
    window.history.replaceState(null, '', url)
  }

  function reload() {
    readController.current?.abort()
    const controller = new AbortController()
    readController.current = controller
    void load(mode, controller.signal)
  }

  async function refresh() {
    if (mode === 'live' && data?.status.schedule?.enabled) return
    if (refreshing || serverRunning || loading || retrySeconds > 0) return
    const controller = new AbortController()
    refreshController.current = controller
    setRefreshing(true)
    setError(null)
    try {
      const response = await requestJson<LatestResponse>('/api/refresh', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, days, max_requests: 3 }), signal: controller.signal,
      })
      if (controller.signal.aborted) return
      if (response.status.data_mode !== mode || response.briefing?.data_mode !== mode) throw new ApiError('The API returned the wrong data mode.')
      setData(response)
      const history = await requestJson<HistoryResponse>(`/api/briefings?mode=${mode}&limit=4`, { signal: controller.signal }).catch(() => null)
      if (controller.signal.aborted) return
      if (history) { setHistory(history.briefings); setHistoryError(false) }
      else setHistoryError(true)
    } catch (error) {
      if (controller.signal.aborted) return
      setError(error instanceof Error ? error.message : 'Could not refresh the briefing.')
      if (error instanceof ApiError && error.retryAfter > 0) setRetryUntil(Date.now() + error.retryAfter * 1000)
      await load(mode, controller.signal, false)
    } finally {
      if (!controller.signal.aborted) setRefreshing(false)
    }
  }

  return { mode, changeMode, data, history, historyError, days, setDays, loading, refreshing: refreshing || serverRunning,
    error, refresh, reload, retrySeconds, now }
}
