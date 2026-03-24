import {
  useState,
  useEffect,
  useRef,
  useMemo,
  useCallback,
} from 'react'
import type { IChartApi } from 'lightweight-charts'
import PlayerChart, { getRunColour } from '../components/PlayerChart'
import type { RunMarkerSet } from '../components/PlayerChart'
import PlayerPnLPanel from '../components/PlayerPnLPanel'
import MarkerTooltip from '../components/MarkerTooltip'
import { useAuth } from '../context/AuthContext'
import type {
  BacktestRun,
  BacktestSignal,
  ChartCandle,
  PnLPoint,
  RunMarkersResponse,
  MarkerTooltipData,
} from '../types'

// ── API helpers ─────────────────────────────────────────────────────────────

function authHeaders(token: string) {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
}

async function apiPost(url: string, body: unknown, token: string) {
  const res = await fetch(url, {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

async function apiGet(url: string, token: string) {
  const res = await fetch(url, { headers: authHeaders(token) })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

async function apiPatch(url: string, body: unknown, token: string) {
  const res = await fetch(url, {
    method: 'PATCH',
    headers: authHeaders(token),
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

async function apiDelete(url: string, token: string) {
  const res = await fetch(url, {
    method: 'DELETE',
    headers: authHeaders(token),
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

// ── Constants ────────────────────────────────────────────────────────────────

const SUPPORT_OPTIONS = ['LOW', 'MEDIUM', 'HIGH'] as const
const PRESETS: Array<{ label: string; months: number }> = [
  { label: '6M', months: 6 },
  { label: '1Y', months: 12 },
  { label: '2Y', months: 24 },
  { label: '3Y', months: 36 },
]

function monthsAgoDate(months: number): string {
  const d = new Date()
  d.setMonth(d.getMonth() - months)
  return d.toISOString().slice(0, 10)
}

function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

// ── Styling helpers ──────────────────────────────────────────────────────────

const S = {
  page: {
    minHeight: '100vh',
    background: '#0F172A',
    color: '#E5E7EB',
    fontFamily: 'ui-monospace, SFMono-Regular, monospace',
    fontSize: 13,
  } as React.CSSProperties,

  // Two-column layout
  layout: {
    display: 'flex',
    gap: 0,
    minHeight: '100vh',
  } as React.CSSProperties,

  leftPanel: {
    flex: '1 1 70%',
    minWidth: 0,
    overflowY: 'auto' as const,
    padding: '16px 16px 32px',
    borderRight: '1px solid #1F2937',
  } as React.CSSProperties,

  rightPanel: {
    width: 320,
    flexShrink: 0,
    overflowY: 'auto' as const,
    padding: '16px',
    background: '#0A1020',
  } as React.CSSProperties,

  card: {
    background: '#111827',
    border: '1px solid #1F2937',
    borderRadius: 8,
    padding: '12px 16px',
    marginBottom: 12,
  } as React.CSSProperties,

  label: {
    color: '#9CA3AF',
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    display: 'block',
    marginBottom: 4,
  },

  input: {
    background: '#1F2937',
    border: '1px solid #374151',
    borderRadius: 6,
    color: '#E5E7EB',
    padding: '5px 8px',
    fontSize: 13,
    width: '100%',
    outline: 'none',
  } as React.CSSProperties,

  btn: {
    background: '#1F2937',
    border: '1px solid #374151',
    borderRadius: 6,
    color: '#E5E7EB',
    padding: '5px 12px',
    fontSize: 12,
    cursor: 'pointer',
  } as React.CSSProperties,

  btnPrimary: {
    background: '#2563EB',
    border: '1px solid #3B82F6',
    borderRadius: 6,
    color: '#fff',
    padding: '6px 16px',
    fontSize: 13,
    fontWeight: 600,
    cursor: 'pointer',
    width: '100%',
  } as React.CSSProperties,
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function PlayerPage() {
  const { token } = useAuth() as { token: string }

  // Config form state
  const [ticker, setTicker] = useState('')
  const [debouncedTicker, setDebouncedTicker] = useState('')
  const [entryThreshold, setEntryThreshold] = useState(70)
  const [watchThreshold, setWatchThreshold] = useState(55)
  const [minRR, setMinRR] = useState(1.5)
  const [minSupport, setMinSupport] = useState<string>('LOW')
  const [weeklyAligned, setWeeklyAligned] = useState(true)
  const [lookbackYears, setLookbackYears] = useState(3)
  const [runLabel, setRunLabel] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [activePreset, setActivePreset] = useState<string | null>(null)
  const dateRangeActive = dateFrom !== '' && dateTo !== '' && dateFrom < dateTo

  // Run state
  const [isRunning, setIsRunning] = useState(false)
  const [progress, setProgress] = useState({ current: 0, total: 0, pct: 0 })
  const evtSourceRef = useRef<EventSource | null>(null)

  // Data state
  const [runs, setRuns] = useState<BacktestRun[]>([])
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [signals, setSignals] = useState<BacktestSignal[]>([])
  const [candles, setCandles] = useState<ChartCandle[]>([])
  const [runMarkersData, setRunMarkersData] = useState<
    Record<string, RunMarkersResponse>
  >({})
  const [markersVisible, setMarkersVisible] = useState<Record<string, boolean>>({})
  const [markersFetched, setMarkersFetched] = useState<Record<string, boolean>>({})

  // Signal table state
  const [verdictFilter, setVerdictFilter] = useState<'ALL' | 'ENTRY' | 'WATCH'>('ALL')
  const [outcomeFilter, setOutcomeFilter] = useState<'ALL' | 'WIN' | 'LOSS' | 'EXPIRED'>('ALL')
  const [sortKey, setSortKey] = useState<string>('signal_date')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [expandedSignal, setExpandedSignal] = useState<string | null>(null)
  const [highlightedSignal, setHighlightedSignal] = useState<string | null>(null)

  // Chart / tooltip state
  const [chartInstance, setChartInstance] = useState<IChartApi | null>(null)
  const [tooltipData, setTooltipData] = useState<MarkerTooltipData | null>(null)
  const [tooltipPoint, setTooltipPoint] = useState<{ x: number; y: number } | null>(null)
  const [tooltipRect, setTooltipRect] = useState<DOMRect | null>(null)

  // Rename / delete inline state
  const [renameRunId, setRenameRunId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  // Date range error
  const dateError =
    dateFrom !== '' && dateTo !== '' && dateFrom >= dateTo
      ? 'Start date must be before end date'
      : null

  // ── Debounce ticker ──────────────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => setDebouncedTicker(ticker.trim().toUpperCase()), 600)
    return () => clearTimeout(t)
  }, [ticker])

  // ── Auto-generate run label from config ───────────────────────────────────
  useEffect(() => {
    const t = ticker.trim().toUpperCase()
    if (!t) { setRunLabel(''); return }
    const supp = minSupport === 'LOW' ? 'S-LOW' : minSupport === 'MEDIUM' ? 'S-MED' : 'S-HIGH'
    const wa = weeklyAligned ? 'W-ON' : 'W-OFF'
    const range = dateRangeActive ? `${dateFrom}→${dateTo}` : `${lookbackYears}Y`
    setRunLabel(`${t} · E${entryThreshold} · W${watchThreshold} · RR${minRR} · ${supp} · ${wa} · ${range}`)
  }, [ticker, entryThreshold, watchThreshold, minRR, minSupport, weeklyAligned, lookbackYears, dateFrom, dateTo, dateRangeActive])

  // ── Load runs on ticker change ─────────────────────────────────────────────
  const loadRuns = useCallback(async (t: string) => {
    if (!t) { setRuns([]); return }
    try {
      const data: BacktestRun[] = await apiGet(`/api/player/runs/${t}`, token)
      setRuns(data)
    } catch { setRuns([]) }
  }, [token])

  useEffect(() => {
    if (debouncedTicker) loadRuns(debouncedTicker)
    else setRuns([])
  }, [debouncedTicker, loadRuns])

  // ── Load candles on ticker change ────────────────────────────────────────
  const fetchCandles = useCallback(async (t: string) => {
    if (!t) return
    try {
      const data = await apiGet(`/api/player/chart/${t}`, token)
      setCandles(data.candles ?? [])
    } catch { setCandles([]) }
  }, [token])

  useEffect(() => {
    if (debouncedTicker) fetchCandles(debouncedTicker)
  }, [debouncedTicker, fetchCandles])

  // ── Load signals when selectedRunId or verdictFilter changes ─────────────
  const loadSignals = useCallback(async (runId: string, usePnl: boolean) => {
    try {
      const endpoint = usePnl
        ? `/api/player/runs/${runId}/signals/pnl`
        : `/api/player/runs/${runId}/signals`
      const data: BacktestSignal[] = await apiGet(endpoint, token)
      setSignals(data)
    } catch { setSignals([]) }
  }, [token])

  useEffect(() => {
    if (!selectedRunId) { setSignals([]); return }
    const usePnl = verdictFilter === 'ENTRY'
    loadSignals(selectedRunId, usePnl)
  }, [selectedRunId, verdictFilter, loadSignals])

  // ── Fetch markers for a run (lazy, first toggle-on triggers fetch) ─────────
  const fetchMarkers = useCallback(async (runId: string) => {
    if (markersFetched[runId]) return
    try {
      const data: RunMarkersResponse = await apiGet(
        `/api/player/chart/${runId}/markers`,
        token,
      )
      setRunMarkersData((prev) => ({ ...prev, [runId]: data }))
      setMarkersFetched((prev) => ({ ...prev, [runId]: true }))
    } catch {}
  }, [token, markersFetched])

  // ── Chart date range zoom ─────────────────────────────────────────────────
  useEffect(() => {
    if (!chartInstance) return
    if (dateRangeActive) {
      chartInstance.timeScale().setVisibleRange({
        from: dateFrom as any,
        to: dateTo as any,
      })
    } else {
      chartInstance.timeScale().fitContent()
    }
  }, [chartInstance, dateFrom, dateTo, dateRangeActive])

  // ── Start backtest run ────────────────────────────────────────────────────
  const handleRun = async () => {
    const t = ticker.trim().toUpperCase()
    if (!t) return
    setIsRunning(true)
    setProgress({ current: 0, total: 0, pct: 0 })

    try {
      const body: Record<string, unknown> = {
        ticker: t,
        lookback_years: lookbackYears,
        entry_score_threshold: entryThreshold,
        watch_score_threshold: watchThreshold,
        min_rr_ratio: minRR,
        min_support_strength: minSupport,
        require_weekly_aligned: weeklyAligned,
        run_label: runLabel.trim(),
      }
      if (dateRangeActive) {
        body.date_from = dateFrom
        body.date_to = dateTo
      }
      const { run_id } = await apiPost('/api/player/run', body, token)

      // Stream progress over SSE
      const src = new EventSource(
        `/api/player/stream/${run_id}?token=${encodeURIComponent(token)}`,
      )
      evtSourceRef.current = src

      src.addEventListener('progress', (e) => {
        const d = JSON.parse((e as MessageEvent).data)
        setProgress({ current: d.progress, total: d.total, pct: d.pct })
      })

      src.addEventListener('complete', () => {
        src.close()
        evtSourceRef.current = null
        setIsRunning(false)
        loadRuns(t)
      })

      src.addEventListener('error', () => {
        src.close()
        evtSourceRef.current = null
        setIsRunning(false)
      })
    } catch {
      setIsRunning(false)
    }
  }

  // ── Preset buttons ────────────────────────────────────────────────────────
  const applyPreset = (preset: (typeof PRESETS)[number]) => {
    const from = monthsAgoDate(preset.months)
    const to = todayStr()
    setDateFrom(from)
    setDateTo(to)
    setActivePreset(preset.label)
  }

  const clearDateRange = () => {
    setDateFrom('')
    setDateTo('')
    setActivePreset(null)
  }

  // ── Marker visibility toggle ───────────────────────────────────────────────
  const toggleMarkers = useCallback(
    async (runId: string) => {
      const isVisible = markersVisible[runId] ?? false
      if (!isVisible && !markersFetched[runId]) {
        await fetchMarkers(runId)
      }
      setMarkersVisible((prev) => ({ ...prev, [runId]: !isVisible }))
    },
    [markersVisible, markersFetched, fetchMarkers],
  )

  const visibleRunIds = useMemo(
    () => new Set(Object.entries(markersVisible).filter(([, v]) => v).map(([k]) => k)),
    [markersVisible],
  )

  // ── Run index lookup (for colours) ────────────────────────────────────────
  const runIndices = useMemo(() => {
    const m: Record<string, number> = {}
    runs.forEach((r, i) => { m[r.run_id] = i })
    return m
  }, [runs])

  // ── RunMarkerSets for PlayerChart ─────────────────────────────────────────
  const runMarkerSets = useMemo<RunMarkerSet[]>(() => {
    return runs
      .filter((r) => runMarkersData[r.run_id])
      .map((r) => ({
        runId: r.run_id,
        runLabel: r.run_label,
        runIndex: runIndices[r.run_id] ?? 0,
        markers: runMarkersData[r.run_id].markers,
      }))
  }, [runs, runMarkersData, runIndices])

  // ── P&L data for PlayerPnLPanel ───────────────────────────────────────────
  const pnlData = useMemo<Record<string, { fixed: PnLPoint[]; compound: PnLPoint[] }>>(
    () => {
      const out: Record<string, { fixed: PnLPoint[]; compound: PnLPoint[] }> = {}
      for (const [runId, d] of Object.entries(runMarkersData)) {
        out[runId] = {
          fixed: d.pnl_series_fixed ?? d.pnl_series ?? [],
          compound: d.pnl_series_compound ?? [],
        }
      }
      return out
    },
    [runMarkersData],
  )

  const runLabels = useMemo(() => {
    const m: Record<string, string> = {}
    runs.forEach((r) => { m[r.run_id] = r.run_label })
    return m
  }, [runs])

  // ── Best-metric computation ────────────────────────────────────────────────
  const bestWinRate = useMemo(
    () => (runs.length ? Math.max(...runs.map((r) => Number(r.win_rate_entry))) : null),
    [runs],
  )
  const bestWinRateW = useMemo(
    () => (runs.length ? Math.max(...runs.map((r) => Number(r.win_rate_watch))) : null),
    [runs],
  )
  const bestEv = useMemo(
    () => (runs.length ? Math.max(...runs.map((r) => Number(r.expected_value))) : null),
    [runs],
  )
  const bestMae = useMemo(
    () => (runs.length ? Math.min(...runs.map((r) => Number(r.avg_mae))) : null),
    [runs],
  )
  const bestMfe = useMemo(
    () => (runs.length ? Math.max(...runs.map((r) => Number(r.avg_mfe))) : null),
    [runs],
  )
  const bestDays = useMemo(
    () => (runs.length ? Math.min(...runs.map((r) => Number(r.avg_days_to_outcome))) : null),
    [runs],
  )
  const bestFixedPnl = useMemo(
    () => (runs.length ? Math.max(...runs.map((r) => Number(r.fixed_pnl))) : null),
    [runs],
  )
  const bestCompoundPnl = useMemo(
    () => (runs.length ? Math.max(...runs.map((r) => Number(r.compound_pnl))) : null),
    [runs],
  )

  // ── Signals table filtering & sorting ─────────────────────────────────────
  const filteredSignals = useMemo(() => {
    let s = [...signals]
    if (verdictFilter !== 'ALL') s = s.filter((x) => x.verdict === verdictFilter)
    if (outcomeFilter !== 'ALL') s = s.filter((x) => x.outcome === outcomeFilter)
    s.sort((a, b) => {
      const av = (a as any)[sortKey]
      const bv = (b as any)[sortKey]
      const cmp = av < bv ? -1 : av > bv ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
    return s
  }, [signals, verdictFilter, outcomeFilter, sortKey, sortDir])

  const showPnlCols = verdictFilter === 'ENTRY' && signals.some((s) => s.trade_pnl_fixed !== undefined)

  // ── Signal table sort toggle ───────────────────────────────────────────────
  const handleSort = (key: string) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(key); setSortDir('desc') }
  }

  // ── Marker click → scroll + highlight table row ───────────────────────────
  const handleMarkerClick = (signalDate: string, runId: string) => {
    setHighlightedSignal(`${signalDate}::${runId}`)
    setSelectedRunId(runId)
    const key = verdictFilter === 'ENTRY'
    loadSignals(runId, key)
    // Scroll table row into view after render
    setTimeout(() => {
      const row = document.querySelector(
        `[data-sig="${signalDate}::${runId}"]`,
      ) as HTMLElement | null
      row?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    }, 200)
  }

  // ── Signal row click → scroll chart ──────────────────────────────────────
  const handleSignalRowClick = (sig: BacktestSignal) => {
    const key = `${sig.signal_date}::${sig.run_id}`
    setHighlightedSignal(key)
    if (chartInstance) {
      const from = new Date(sig.signal_date)
      from.setDate(from.getDate() - 30)
      const to = new Date(sig.signal_date)
      to.setDate(to.getDate() + 30)
      chartInstance.timeScale().setVisibleRange({
        from: from.toISOString().slice(0, 10) as any,
        to: to.toISOString().slice(0, 10) as any,
      })
    }
  }

  // ── Rename / delete ────────────────────────────────────────────────────────
  const handleRename = async (runId: string) => {
    try {
      await apiPatch(`/api/player/runs/${runId}/label`, { label: renameValue }, token)
      setRuns((prev) =>
        prev.map((r) => (r.run_id === runId ? { ...r, run_label: renameValue } : r)),
      )
    } catch {}
    setRenameRunId(null)
  }

  const handleDelete = async (runId: string) => {
    try {
      await apiDelete(`/api/player/runs/${runId}`, token)
      setRuns((prev) => prev.filter((r) => r.run_id !== runId))
      if (selectedRunId === runId) { setSelectedRunId(null); setSignals([]) }
      setRunMarkersData((prev) => { const n = { ...prev }; delete n[runId]; return n })
      setMarkersVisible((prev) => { const n = { ...prev }; delete n[runId]; return n })
    } catch {}
    setDeleteConfirmId(null)
  }

  // ── Render ─────────────────────────────────────────────────────────────────
  const selectedRun = runs.find((r) => r.run_id === selectedRunId) ?? null

  return (
    <div style={S.page}>
      <div style={S.layout}>
        {/* ── LEFT PANEL (chart + signals) ── */}
        <div style={S.leftPanel}>

          {/* Chart header */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 8,
              flexWrap: 'wrap',
            }}
          >
            <span style={{ color: '#E5E7EB', fontWeight: 700, fontSize: 15, marginRight: 4 }}>
              {debouncedTicker || '—'}
            </span>

            {/* Preset buttons */}
            {PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => applyPreset(p)}
                style={{
                  ...S.btn,
                  background: activePreset === p.label ? '#2563EB' : '#1F2937',
                  borderColor: activePreset === p.label ? '#3B82F6' : '#374151',
                  color: activePreset === p.label ? '#fff' : '#9CA3AF',
                  padding: '3px 8px',
                }}
              >
                {p.label}
              </button>
            ))}

            {/* Date pickers */}
            <input
              type="date"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setActivePreset(null) }}
              style={{
                ...S.input,
                width: 130,
                colorScheme: 'dark',
                background: '#1F2937',
              }}
            />
            <span style={{ color: '#4B5563' }}>→</span>
            <input
              type="date"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setActivePreset(null) }}
              style={{
                ...S.input,
                width: 130,
                colorScheme: 'dark',
                background: '#1F2937',
              }}
            />
            {(dateFrom || dateTo) && (
              <button onClick={clearDateRange} style={{ ...S.btn, padding: '3px 8px', color: '#9CA3AF' }}>
                ✕
              </button>
            )}
            {dateError && (
              <span style={{ color: '#F87171', fontSize: 11 }}>{dateError}</span>
            )}
          </div>

          {/* Progress bar */}
          {isRunning && (
            <div style={{ ...S.card, marginBottom: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ color: '#9CA3AF', fontSize: 11 }}>Running backtest…</span>
                <span style={{ color: '#60A5FA', fontSize: 11 }}>
                  {progress.current} / {progress.total} ({progress.pct}%)
                </span>
              </div>
              <div style={{ background: '#1F2937', borderRadius: 4, height: 6 }}>
                <div
                  style={{
                    background: '#2563EB',
                    height: 6,
                    borderRadius: 4,
                    width: `${progress.pct}%`,
                    transition: 'width 0.3s',
                  }}
                />
              </div>
            </div>
          )}

          {/* Run visibility toggles */}
          {runs.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              {runs.map((r, i) => {
                const colour = getRunColour(i)
                const visible = markersVisible[r.run_id] ?? false
                return (
                  <button
                    key={r.run_id}
                    onClick={() => toggleMarkers(r.run_id)}
                    title={r.run_label}
                    style={{
                      ...S.btn,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      padding: '3px 8px',
                      borderColor: visible ? colour : '#374151',
                      background: visible ? `${colour}18` : '#1F2937',
                    }}
                  >
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        background: visible ? colour : 'transparent',
                        border: `2px solid ${colour}`,
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        maxWidth: 120,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        color: visible ? '#E5E7EB' : '#6B7280',
                        fontSize: 11,
                      }}
                    >
                      {r.run_label}
                    </span>
                  </button>
                )
              })}
            </div>
          )}

          {/* Candlestick chart */}
          {candles.length > 0 && (
            <div
              style={{
                ...S.card,
                padding: 0,
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <PlayerChart
                candles={candles}
                runMarkers={runMarkerSets}
                visibleRunIds={visibleRunIds}
                onMarkerHover={(d, p, r) => {
                  setTooltipData(d)
                  setTooltipPoint(p)
                  setTooltipRect(r)
                }}
                onMarkerClick={handleMarkerClick}
                onChartReady={setChartInstance}
                height={420}
              />
              <MarkerTooltip
                data={tooltipData}
                point={tooltipPoint}
                chartRect={tooltipRect}
              />
            </div>
          )}

          {/* P&L panel */}
          {candles.length > 0 && Object.keys(pnlData).length > 0 && (
            <div style={{ ...S.card, padding: 0, overflow: 'hidden', marginTop: 2 }}>
              <PlayerPnLPanel
                pnlData={pnlData}
                visibleRunIds={visibleRunIds}
                runLabels={runLabels}
                runIndices={runIndices}
                mainChart={chartInstance}
                height={160}
              />
            </div>
          )}

          {/* Signals table section */}
          {selectedRun && (
            <div style={{ marginTop: 12 }}>
              {/* Filters row */}
              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  marginBottom: 8,
                  alignItems: 'center',
                }}
              >
                <span style={{ color: '#6B7280', fontSize: 11 }}>Signals for</span>
                <span
                  style={{
                    color: '#60A5FA',
                    fontSize: 12,
                    fontWeight: 600,
                    maxWidth: 200,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {selectedRun.run_label}
                </span>
                <select
                  value={verdictFilter}
                  onChange={(e) => setVerdictFilter(e.target.value as any)}
                  style={{ ...S.input, width: 'auto' }}
                >
                  <option value="ALL">All verdicts</option>
                  <option value="ENTRY">ENTRY only</option>
                  <option value="WATCH">WATCH only</option>
                </select>
                <select
                  value={outcomeFilter}
                  onChange={(e) => setOutcomeFilter(e.target.value as any)}
                  style={{ ...S.input, width: 'auto' }}
                >
                  <option value="ALL">All outcomes</option>
                  <option value="WIN">WIN</option>
                  <option value="LOSS">LOSS</option>
                  <option value="EXPIRED">EXPIRED</option>
                </select>
              </div>

              {/* P&L summary bar (ENTRY filter only) */}
              {verdictFilter === 'ENTRY' && selectedRun && (
                <div
                  style={{
                    background: '#111827',
                    border: '1px solid #1F2937',
                    borderRadius: 8,
                    padding: '10px 16px',
                    marginBottom: 10,
                    display: 'flex',
                    gap: 24,
                    alignItems: 'center',
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <span style={{ color: '#6B7280', fontSize: 11 }}>
                      {selectedRun.entry_signal_count} ENTRY signals
                    </span>
                    <span style={{ color: '#E5E7EB', marginLeft: 8, fontSize: 12 }}>
                      {Number(selectedRun.win_rate_entry).toFixed(1)}% win rate
                    </span>
                  </div>
                  <div>
                    <span style={{ color: '#6B7280', fontSize: 11 }}>Fixed $1K/trade</span>
                    <span
                      style={{
                        color: Number(selectedRun.fixed_pnl) >= 0 ? '#34D399' : '#F87171',
                        fontWeight: 600,
                        marginLeft: 8,
                        fontSize: 12,
                      }}
                    >
                      {Number(selectedRun.fixed_pnl) >= 0 ? '+' : ''}$
                      {Number(selectedRun.fixed_pnl).toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span style={{ color: '#6B7280', fontSize: 11 }}>Compounding $1K</span>
                    <span
                      style={{
                        color: Number(selectedRun.compound_pnl) >= 0 ? '#34D399' : '#F87171',
                        fontWeight: 600,
                        marginLeft: 8,
                        fontSize: 12,
                      }}
                    >
                      {Number(selectedRun.compound_pnl) >= 0 ? '+' : ''}$
                      {Number(selectedRun.compound_pnl).toFixed(2)}
                    </span>
                    <span style={{ color: '#6B7280', fontSize: 11, marginLeft: 4 }}>
                      → pot ${Number(selectedRun.compound_final_pot).toFixed(2)}
                    </span>
                  </div>
                </div>
              )}

              {/* Signals table */}
              <div
                style={{
                  overflowX: 'auto',
                  border: '1px solid #1F2937',
                  borderRadius: 8,
                }}
              >
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: 12,
                  }}
                >
                  <thead>
                    <tr style={{ background: '#0F172A', color: '#6B7280' }}>
                      {[
                        ['signal_date', 'Date'],
                        ['verdict', 'Verdict'],
                        ['setup_score', 'Score'],
                        ['rr_ratio', 'R:R'],
                        ['support_strength', 'Support'],
                        ['outcome', 'Outcome'],
                        ['return_pct', 'Ret%'],
                        ...(showPnlCols
                          ? [
                              ['trade_pnl_fixed', 'Trade P&L'],
                              ['running_pnl_fixed', 'Running P&L'],
                            ]
                          : []),
                        ['mae', 'MAE'],
                        ['mfe', 'MFE'],
                        ['days_to_outcome', 'Days'],
                      ].map(([key, label]) => (
                        <th
                          key={key}
                          onClick={() => handleSort(key)}
                          style={{
                            padding: '8px 10px',
                            textAlign: 'left',
                            cursor: 'pointer',
                            whiteSpace: 'nowrap',
                            borderBottom: '1px solid #1F2937',
                            userSelect: 'none',
                          }}
                        >
                          {label}
                          {sortKey === key && (
                            <span style={{ marginLeft: 3 }}>
                              {sortDir === 'asc' ? '↑' : '↓'}
                            </span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSignals.length === 0 && (
                      <tr>
                        <td
                          colSpan={showPnlCols ? 14 : 12}
                          style={{
                            padding: 24,
                            textAlign: 'center',
                            color: '#4B5563',
                          }}
                        >
                          No signals match the current filters.
                        </td>
                      </tr>
                    )}
                    {filteredSignals.map((sig) => {
                      const sigKey = `${sig.signal_date}::${sig.run_id}`
                      const isHighlighted = highlightedSignal === sigKey
                      const isExpanded = expandedSignal === sigKey
                      const rowBg =
                        sig.outcome === 'WIN'
                          ? '#0D2818'
                          : sig.outcome === 'LOSS'
                          ? '#2A0D0D'
                          : '#1A1A1A'

                      return (
                        <>
                          <tr
                            key={sigKey}
                            data-sig={sigKey}
                            onClick={() => {
                              handleSignalRowClick(sig)
                              setExpandedSignal(isExpanded ? null : sigKey)
                            }}
                            style={{
                              background: isHighlighted
                                ? `${rowBg} !important`
                                : rowBg,
                              cursor: 'pointer',
                              borderLeft: isHighlighted
                                ? '3px solid #F59E0B'
                                : '3px solid transparent',
                              transition: 'background 0.2s',
                            }}
                          >
                            <td style={{ padding: '6px 10px', color: '#9CA3AF' }}>
                              {sig.signal_date}
                            </td>
                            <td style={{ padding: '6px 10px' }}>
                              <span
                                style={{
                                  background:
                                    sig.verdict === 'ENTRY' ? '#1D4ED820' : '#1F293720',
                                  color:
                                    sig.verdict === 'ENTRY' ? '#60A5FA' : '#9CA3AF',
                                  border: `1px solid ${sig.verdict === 'ENTRY' ? '#3B82F680' : '#37415180'}`,
                                  borderRadius: 4,
                                  padding: '1px 6px',
                                  fontSize: 11,
                                  fontWeight: 600,
                                }}
                              >
                                {sig.verdict}
                              </span>
                            </td>
                            <td style={{ padding: '6px 10px' }}>
                              <span style={{ color: '#E5E7EB' }}>
                                {sig.setup_score}
                              </span>
                              <div
                                style={{
                                  height: 2,
                                  background: '#1F2937',
                                  borderRadius: 1,
                                  marginTop: 2,
                                  width: 40,
                                }}
                              >
                                <div
                                  style={{
                                    height: 2,
                                    borderRadius: 1,
                                    background: '#3B82F6',
                                    width: `${sig.setup_score}%`,
                                  }}
                                />
                              </div>
                            </td>
                            <td style={{ padding: '6px 10px', color: '#E5E7EB' }}>
                              {sig.rr_ratio != null
                                ? `${Number(sig.rr_ratio).toFixed(2)}×`
                                : '—'}
                            </td>
                            <td style={{ padding: '6px 10px', color: '#9CA3AF' }}>
                              {sig.support_strength ?? '—'}
                            </td>
                            <td style={{ padding: '6px 10px' }}>
                              <span
                                style={{
                                  color:
                                    sig.outcome === 'WIN'
                                      ? '#34D399'
                                      : sig.outcome === 'LOSS'
                                      ? '#F87171'
                                      : '#6B7280',
                                  fontWeight: 600,
                                }}
                              >
                                {sig.outcome}
                              </span>
                            </td>
                            <td
                              style={{
                                padding: '6px 10px',
                                color:
                                  Number(sig.return_pct) >= 0 ? '#34D399' : '#F87171',
                              }}
                            >
                              {sig.return_pct != null
                                ? `${Number(sig.return_pct) >= 0 ? '+' : ''}${Number(sig.return_pct).toFixed(2)}%`
                                : '—'}
                            </td>
                            {showPnlCols && (
                              <>
                                <td
                                  style={{
                                    padding: '6px 10px',
                                    color:
                                      (sig.trade_pnl_fixed ?? 0) >= 0
                                        ? '#34D399'
                                        : '#F87171',
                                  }}
                                >
                                  {sig.trade_pnl_fixed != null
                                    ? `${(sig.trade_pnl_fixed ?? 0) >= 0 ? '+' : ''}$${Math.abs(sig.trade_pnl_fixed ?? 0).toFixed(2)}`
                                    : '—'}
                                </td>
                                <td style={{ padding: '6px 10px' }}>
                                  <div
                                    style={{
                                      display: 'flex',
                                      flexDirection: 'column',
                                      gap: 1,
                                    }}
                                  >
                                    <span
                                      style={{
                                        color:
                                          (sig.running_pnl_fixed ?? 0) >= 0
                                            ? '#34D399'
                                            : '#F87171',
                                        fontSize: 11,
                                      }}
                                    >
                                      F: {(sig.running_pnl_fixed ?? 0) >= 0 ? '+' : ''}$
                                      {Number(sig.running_pnl_fixed ?? 0).toFixed(0)}
                                    </span>
                                    <span
                                      style={{
                                        color:
                                          (sig.running_pnl_compound ?? 0) >= 0
                                            ? '#34D399'
                                            : '#F87171',
                                        fontSize: 10,
                                        opacity: 0.8,
                                      }}
                                    >
                                      C: ${Number(sig.running_pot ?? 1000).toFixed(0)}
                                    </span>
                                  </div>
                                </td>
                              </>
                            )}
                            <td style={{ padding: '6px 10px', color: '#9CA3AF' }}>
                              {sig.mae != null ? `${Number(sig.mae).toFixed(2)}%` : '—'}
                            </td>
                            <td style={{ padding: '6px 10px', color: '#9CA3AF' }}>
                              {sig.mfe != null ? `${Number(sig.mfe).toFixed(2)}%` : '—'}
                            </td>
                            <td style={{ padding: '6px 10px', color: '#9CA3AF' }}>
                              {sig.days_to_outcome ?? '—'}
                            </td>
                          </tr>
                          {/* Expanded row with conditions & levels */}
                          {isExpanded && (
                            <tr
                              key={`${sigKey}-exp`}
                              style={{ background: '#0A1020' }}
                            >
                              <td
                                colSpan={showPnlCols ? 14 : 12}
                                style={{ padding: '12px 16px' }}
                              >
                                <div
                                  style={{
                                    display: 'grid',
                                    gridTemplateColumns: '1fr 1fr',
                                    gap: 16,
                                  }}
                                >
                                  {/* Conditions */}
                                  <div>
                                    <div
                                      style={{
                                        color: '#6B7280',
                                        fontSize: 10,
                                        fontWeight: 700,
                                        letterSpacing: '0.08em',
                                        marginBottom: 6,
                                      }}
                                    >
                                      CONDITIONS
                                    </div>
                                    {[
                                      ['Uptrend', sig.uptrend_confirmed],
                                      ['Weekly aligned', sig.weekly_trend_aligned],
                                      ['Near support', sig.near_support],
                                      ['Reversal found', sig.reversal_found],
                                      ['Trigger OK', sig.trigger_ok],
                                      ['4H confirmed', sig.four_h_confirmed],
                                    ].map(([label, val]) => (
                                      <div
                                        key={String(label)}
                                        style={{
                                          display: 'flex',
                                          gap: 8,
                                          marginBottom: 3,
                                        }}
                                      >
                                        <span
                                          style={{
                                            color: val ? '#34D399' : '#F87171',
                                            fontSize: 11,
                                          }}
                                        >
                                          {val ? '✓' : '✗'}
                                        </span>
                                        <span style={{ color: '#9CA3AF', fontSize: 11 }}>
                                          {label as string}
                                        </span>
                                      </div>
                                    ))}
                                  </div>
                                  {/* Levels */}
                                  <div>
                                    <div
                                      style={{
                                        color: '#6B7280',
                                        fontSize: 10,
                                        fontWeight: 700,
                                        letterSpacing: '0.08em',
                                        marginBottom: 6,
                                      }}
                                    >
                                      LEVELS
                                    </div>
                                    {[
                                      ['Entry', sig.entry_price],
                                      ['Stop', sig.stop_loss],
                                      ['Target', sig.target],
                                      ['Exit', sig.exit_price],
                                    ].map(([label, val]) => (
                                      <div
                                        key={String(label)}
                                        style={{
                                          display: 'flex',
                                          justifyContent: 'space-between',
                                          marginBottom: 3,
                                        }}
                                      >
                                        <span style={{ color: '#6B7280', fontSize: 11 }}>
                                          {label as string}
                                        </span>
                                        <span style={{ color: '#E5E7EB', fontSize: 11 }}>
                                          {val != null
                                            ? `$${Number(val).toFixed(2)}`
                                            : '—'}
                                        </span>
                                      </div>
                                    ))}
                                    {sig.outcome_date && (
                                      <div
                                        style={{
                                          display: 'flex',
                                          justifyContent: 'space-between',
                                          marginBottom: 3,
                                        }}
                                      >
                                        <span style={{ color: '#6B7280', fontSize: 11 }}>
                                          Exit date
                                        </span>
                                        <span style={{ color: '#9CA3AF', fontSize: 11 }}>
                                          {sig.outcome_date}
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {!debouncedTicker && (
            <div
              style={{
                marginTop: 60,
                textAlign: 'center',
                color: '#374151',
              }}
            >
              <div style={{ fontSize: 32, marginBottom: 8 }}>📈</div>
              <div style={{ fontSize: 14 }}>
                Enter a ticker in the config panel to begin
              </div>
            </div>
          )}
        </div>

        {/* ── RIGHT PANEL (config + comparison table) ── */}
        <div style={S.rightPanel}>

          {/* Config card */}
          <div style={S.card}>
            <div
              style={{
                color: '#9CA3AF',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.1em',
                marginBottom: 10,
              }}
            >
              CONFIG
            </div>

            {/* Ticker */}
            <div style={{ marginBottom: 10 }}>
              <label style={S.label}>Ticker</label>
              <input
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="e.g. AAPL"
                style={S.input}
              />
            </div>

            {/* Thresholds row */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={S.label}>Entry %</label>
                <input
                  type="number"
                  value={entryThreshold}
                  onChange={(e) => setEntryThreshold(Number(e.target.value))}
                  style={S.input}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={S.label}>Watch %</label>
                <input
                  type="number"
                  value={watchThreshold}
                  onChange={(e) => setWatchThreshold(Number(e.target.value))}
                  style={S.input}
                />
              </div>
            </div>

            {/* Filters row */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={S.label}>Min R:R</label>
                <input
                  type="number"
                  step="0.1"
                  value={minRR}
                  onChange={(e) => setMinRR(Number(e.target.value))}
                  style={S.input}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={S.label}>Min Support</label>
                <select
                  value={minSupport}
                  onChange={(e) => setMinSupport(e.target.value)}
                  style={S.input}
                >
                  {SUPPORT_OPTIONS.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Weekly aligned toggle */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <label style={{ ...S.label, marginBottom: 0, flex: 1 }}>
                Weekly aligned
              </label>
              <button
                onClick={() => setWeeklyAligned((v) => !v)}
                style={{
                  ...S.btn,
                  background: weeklyAligned ? '#065F46' : '#1F2937',
                  borderColor: weeklyAligned ? '#34D399' : '#374151',
                  color: weeklyAligned ? '#34D399' : '#6B7280',
                  padding: '3px 10px',
                  fontSize: 11,
                }}
              >
                {weeklyAligned ? 'ON' : 'OFF'}
              </button>
            </div>

            {/* Lookback (greyed when date range active) */}
            <div style={{ marginBottom: 10, opacity: dateRangeActive ? 0.4 : 1 }}>
              <label style={S.label}>
                Lookback years {dateRangeActive && '(overridden by date range)'}
              </label>
              <input
                type="number"
                value={lookbackYears}
                onChange={(e) => setLookbackYears(Number(e.target.value))}
                disabled={dateRangeActive}
                style={{ ...S.input, cursor: dateRangeActive ? 'not-allowed' : 'text' }}
              />
            </div>

            {/* Run label */}
            <div style={{ marginBottom: 12 }}>
              <label style={S.label}>Run label</label>
              <input
                value={runLabel}
                onChange={(e) => setRunLabel(e.target.value)}
                style={{ ...S.input, fontSize: 11 }}
              />
            </div>

            <button
              onClick={handleRun}
              disabled={!ticker.trim() || isRunning}
              style={{
                ...S.btnPrimary,
                opacity: !ticker.trim() || isRunning ? 0.5 : 1,
                cursor: !ticker.trim() || isRunning ? 'not-allowed' : 'pointer',
              }}
            >
              {isRunning ? 'Running…' : '▶ Run Backtest'}
            </button>
          </div>

          {/* Comparison table */}
          {runs.length > 0 && (
            <div style={S.card}>
              <div
                style={{
                  color: '#9CA3AF',
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  marginBottom: 10,
                }}
              >
                RUNS — {debouncedTicker}
              </div>

              <div style={{ overflowX: 'auto' }}>
                <table
                  style={{
                    width: '100%',
                    borderCollapse: 'collapse',
                    fontSize: 11,
                  }}
                >
                  <thead>
                    <tr style={{ color: '#4B5563' }}>
                      {[
                        'Label',
                        'Sig',
                        'WIN%(E)',
                        'WIN%(W)',
                        'EV',
                        'MAE',
                        'MFE',
                        'Days',
                        'Fixed P&L',
                        'Cmpd P&L',
                        '',
                      ].map((h) => (
                        <th
                          key={h}
                          style={{
                            padding: '4px 6px',
                            textAlign: 'left',
                            borderBottom: '1px solid #1F2937',
                            whiteSpace: 'nowrap',
                            fontWeight: 600,
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run, i) => {
                      const colour = getRunColour(i)
                      const isSelected = selectedRunId === run.run_id
                      const isRenaming = renameRunId === run.run_id
                      const isDeleteConfirm = deleteConfirmId === run.run_id

                      const winRateE = Number(run.win_rate_entry)
                      const winRateW = Number(run.win_rate_watch)
                      const ev = Number(run.expected_value)
                      const mae = Number(run.avg_mae)
                      const mfe = Number(run.avg_mfe)
                      const days = Number(run.avg_days_to_outcome)
                      const fixedPnl = Number(run.fixed_pnl)
                      const compoundPnl = Number(run.compound_pnl)
                      const compoundPot = Number(run.compound_final_pot)

                      const isWinBest = bestWinRate !== null && winRateE === bestWinRate
                      const isWinWBest = bestWinRateW !== null && winRateW === bestWinRateW
                      const isEvBest = bestEv !== null && ev === bestEv
                      const isMaeBest = bestMae !== null && mae === bestMae
                      const isMfeBest = bestMfe !== null && mfe === bestMfe
                      const isDaysBest = bestDays !== null && days === bestDays
                      const isFixedBest = bestFixedPnl !== null && fixedPnl === bestFixedPnl
                      const isCompoundBest =
                        bestCompoundPnl !== null && compoundPnl === bestCompoundPnl

                      return (
                        <tr
                          key={run.run_id}
                          onClick={() =>
                            setSelectedRunId(isSelected ? null : run.run_id)
                          }
                          style={{
                            background: isSelected ? '#0D1F3C' : 'transparent',
                            cursor: 'pointer',
                            borderLeft: `3px solid ${colour}`,
                          }}
                        >
                          {/* Label cell */}
                          <td
                            style={{
                              padding: '6px',
                              maxWidth: 100,
                            }}
                          >
                            {isRenaming ? (
                              <div style={{ display: 'flex', gap: 4 }}>
                                <input
                                  value={renameValue}
                                  onChange={(e) => setRenameValue(e.target.value)}
                                  onClick={(e) => e.stopPropagation()}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleRename(run.run_id)
                                    if (e.key === 'Escape') setRenameRunId(null)
                                  }}
                                  style={{ ...S.input, fontSize: 10, width: 80 }}
                                  autoFocus
                                />
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    handleRename(run.run_id)
                                  }}
                                  style={{ ...S.btn, padding: '2px 4px', fontSize: 10 }}
                                >
                                  ✓
                                </button>
                              </div>
                            ) : (
                              <span
                                style={{
                                  color: '#9CA3AF',
                                  display: 'block',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                  whiteSpace: 'nowrap',
                                }}
                                title={run.run_label}
                              >
                                {run.run_label}
                              </span>
                            )}
                          </td>

                          <td style={{ padding: '6px', color: '#6B7280' }}>
                            {run.total_signals}
                          </td>
                          <td
                            style={{
                              padding: '6px',
                              color: isWinBest ? '#34D399' : '#E5E7EB',
                              fontWeight: isWinBest ? 700 : 400,
                            }}
                          >
                            {winRateE.toFixed(1)}%
                          </td>
                          <td
                            style={{
                              padding: '6px',
                              color: isWinWBest ? '#34D399' : '#E5E7EB',
                              fontWeight: isWinWBest ? 700 : 400,
                            }}
                          >
                            {winRateW.toFixed(1)}%
                          </td>
                          <td
                            style={{
                              padding: '6px',
                              color: isEvBest ? '#34D399' : '#E5E7EB',
                              fontWeight: isEvBest ? 700 : 400,
                            }}
                          >
                            {ev.toFixed(2)}
                          </td>
                          <td
                            style={{
                              padding: '6px',
                              color: isMaeBest ? '#34D399' : '#9CA3AF',
                              fontWeight: isMaeBest ? 700 : 400,
                            }}
                          >
                            {mae.toFixed(2)}%
                          </td>
                          <td
                            style={{
                              padding: '6px',
                              color: isMfeBest ? '#34D399' : '#9CA3AF',
                              fontWeight: isMfeBest ? 700 : 400,
                            }}
                          >
                            {mfe.toFixed(2)}%
                          </td>
                          <td
                            style={{
                              padding: '6px',
                              color: isDaysBest ? '#34D399' : '#6B7280',
                              fontWeight: isDaysBest ? 700 : 400,
                            }}
                          >
                            {days.toFixed(1)}
                          </td>
                          {/* Fixed P&L */}
                          <td style={{ padding: '6px' }}>
                            <span
                              style={{
                                color: fixedPnl >= 0 ? '#34D399' : '#F87171',
                                fontWeight: isFixedBest ? 700 : 600,
                              }}
                            >
                              {fixedPnl >= 0 ? '+' : ''}${fixedPnl.toFixed(0)}
                            </span>
                          </td>
                          {/* Compound P&L */}
                          <td style={{ padding: '6px' }}>
                            <span
                              style={{
                                color: compoundPnl >= 0 ? '#34D399' : '#F87171',
                                fontWeight: isCompoundBest ? 700 : 600,
                              }}
                            >
                              {compoundPnl >= 0 ? '+' : ''}${compoundPnl.toFixed(0)}
                            </span>
                            <span
                              style={{
                                color: '#6B7280',
                                fontSize: 10,
                                marginLeft: 3,
                              }}
                            >
                              (${compoundPot.toFixed(0)})
                            </span>
                          </td>
                          {/* Actions */}
                          <td style={{ padding: '6px' }}>
                            {isDeleteConfirm ? (
                              <div style={{ display: 'flex', gap: 3 }}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    handleDelete(run.run_id)
                                  }}
                                  style={{
                                    ...S.btn,
                                    padding: '1px 5px',
                                    fontSize: 10,
                                    color: '#F87171',
                                    borderColor: '#F87171',
                                  }}
                                >
                                  Del
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setDeleteConfirmId(null)
                                  }}
                                  style={{ ...S.btn, padding: '1px 5px', fontSize: 10 }}
                                >
                                  No
                                </button>
                              </div>
                            ) : (
                              <div style={{ display: 'flex', gap: 4 }}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setRenameRunId(run.run_id)
                                    setRenameValue(run.run_label)
                                  }}
                                  title="Rename"
                                  style={{
                                    ...S.btn,
                                    padding: '1px 5px',
                                    fontSize: 11,
                                    color: '#6B7280',
                                  }}
                                >
                                  ✏
                                </button>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setDeleteConfirmId(run.run_id)
                                  }}
                                  title="Delete"
                                  style={{
                                    ...S.btn,
                                    padding: '1px 5px',
                                    fontSize: 11,
                                    color: '#6B7280',
                                  }}
                                >
                                  🗑
                                </button>
                              </div>
                            )}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {debouncedTicker && runs.length === 0 && !isRunning && (
            <div style={{ color: '#4B5563', fontSize: 12, textAlign: 'center', marginTop: 24 }}>
              No completed runs for {debouncedTicker}.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
