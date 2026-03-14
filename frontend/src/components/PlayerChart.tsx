import { useEffect, useRef } from 'react'
import { createChart, CrosshairMode } from 'lightweight-charts'
import type { IChartApi, ISeriesApi } from 'lightweight-charts'
import type {
  ChartCandle,
  ChartMarker,
  ChartMarkerEntry,
  ChartMarkerExit,
  MarkerTooltipData,
} from '../types'

export const RUN_COLOURS = [
  '#60A5FA',
  '#34D399',
  '#FBBF24',
  '#F87171',
  '#A78BFA',
  '#FB923C',
  '#38BDF8',
  '#4ADE80',
]

export function getRunColour(index: number): string {
  return RUN_COLOURS[index % RUN_COLOURS.length]
}

export interface RunMarkerSet {
  runId: string
  runLabel: string
  runIndex: number
  markers: ChartMarker[]
}

interface Props {
  candles: ChartCandle[]
  runMarkers: RunMarkerSet[]
  visibleRunIds: Set<string>
  onMarkerHover: (
    data: MarkerTooltipData | null,
    point: { x: number; y: number } | null,
    rect: DOMRect | null,
  ) => void
  onMarkerClick: (signalDate: string, runId: string) => void
  onChartReady: (chart: IChartApi) => void
  height?: number
}

function toTime(s: string): any {
  return s
}

function sortByTime<T extends { time: any }>(arr: T[]): T[] {
  return [...arr].sort((a, b) => {
    const at = typeof a.time === 'string' ? a.time : JSON.stringify(a.time)
    const bt = typeof b.time === 'string' ? b.time : JSON.stringify(b.time)
    return at < bt ? -1 : at > bt ? 1 : 0
  })
}

function dedupByTime<T extends { time: any }>(arr: T[]): T[] {
  const seen = new Set<string>()
  return arr.filter((p) => {
    const k = typeof p.time === 'string' ? p.time : JSON.stringify(p.time)
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })
}

function timeToString(t: any): string {
  if (typeof t === 'string') return t
  if (t && typeof t === 'object' && 'year' in t) {
    return `${t.year}-${String(t.month).padStart(2, '0')}-${String(t.day).padStart(2, '0')}`
  }
  return String(t)
}

export default function PlayerChart({
  candles,
  runMarkers,
  visibleRunIds,
  onMarkerHover,
  onMarkerClick,
  onChartReady,
  height = 480,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const markerSeriesRef = useRef<Record<string, ISeriesApi<'Line'>>>({})
  // Keep latest runMarkers in a ref so crosshair/click handlers always see fresh data
  const allMarkersRef = useRef<RunMarkerSet[]>([])
  const visibleRef = useRef<Set<string>>(new Set())

  // ── Initialise chart once ──────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { color: '#111827' } as any,
        textColor: '#9CA3AF',
      },
      grid: {
        vertLines: { color: '#1F2937' },
        horzLines: { color: '#1F2937' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#374151' },
      timeScale: {
        borderColor: '#374151',
        timeVisible: false,
      },
    })
    chartRef.current = chart

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#34D399',
      downColor: '#F87171',
      borderUpColor: '#34D399',
      borderDownColor: '#F87171',
      wickUpColor: '#34D399',
      wickDownColor: '#F87171',
    })
    candleSeriesRef.current = candleSeries

    // Crosshair move → tooltip
    chart.subscribeCrosshairMove((param) => {
      if (!param.point || !containerRef.current) {
        onMarkerHover(null, null, null)
        return
      }
      const rect = containerRef.current.getBoundingClientRect()
      const absPoint = {
        x: rect.left + param.point.x,
        y: rect.top + param.point.y,
      }
      const timeStr = param.time ? timeToString(param.time) : null
      let found: MarkerTooltipData | null = null
      if (timeStr) {
        for (const run of allMarkersRef.current) {
          if (!visibleRef.current.has(run.runId)) continue
          const m = run.markers.find(
            (mk) => mk.time === timeStr && mk.type === 'entry',
          )
          if (m) {
            found = {
              marker: m,
              runId: run.runId,
              runLabel: run.runLabel,
              runColour: getRunColour(run.runIndex),
            }
            break
          }
        }
      }
      onMarkerHover(found, found ? absPoint : null, found ? rect : null)
    })

    // Click → scroll signal table
    chart.subscribeClick((param) => {
      if (!param.time) return
      const timeStr = timeToString(param.time)
      for (const run of allMarkersRef.current) {
        if (!visibleRef.current.has(run.runId)) continue
        const m = run.markers.find(
          (mk) => mk.time === timeStr && mk.type === 'entry',
        )
        if (m) {
          onMarkerClick(timeStr, run.runId)
          break
        }
      }
    })

    onChartReady(chart)

    const resize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      markerSeriesRef.current = {}
    }
  }, [height]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Load candles ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!candleSeriesRef.current || candles.length === 0) return
    const sorted = [...candles].sort((a, b) => (a.time < b.time ? -1 : 1))
    candleSeriesRef.current.setData(
      sorted.map((c) => ({
        time: toTime(c.time),
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    )
    chartRef.current?.timeScale().fitContent()
  }, [candles])

  // ── Rebuild marker series when runMarkers or visibility changes ────────
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    allMarkersRef.current = runMarkers
    visibleRef.current = visibleRunIds

    // Remove old series
    for (const series of Object.values(markerSeriesRef.current)) {
      try { chart.removeSeries(series) } catch (_) {}
    }
    markerSeriesRef.current = {}

    for (const run of runMarkers) {
      const visible = visibleRunIds.has(run.runId)
      const colour = getRunColour(run.runIndex)

      // Invisible host series — must have data so markers aren't silently dropped
      const lineSeries = chart.addLineSeries({
        color: 'transparent',
        lineWidth: 0 as any,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: false,
      })

      // Seed with full OHLCV history so every trading day is valid for a marker
      if (candles.length > 0) {
        lineSeries.setData(
          dedupByTime(
            sortByTime(candles.map((c) => ({ time: toTime(c.time), value: 0 }))),
          ),
        )
      }

      if (visible && run.markers.length > 0) {
        const lwMarkers = run.markers.map((m): any => {
          if (m.type === 'entry') {
            const entry = m as ChartMarkerEntry
            const isEntry = entry.verdict === 'ENTRY'
            return {
              time: toTime(m.time),
              position: 'belowBar',
              color: isEntry ? colour : colour + '80',
              shape: 'arrowUp',
              text: isEntry ? String(entry.score) : '',
              size: isEntry ? 1 : 0.7,
            }
          } else {
            const exit = m as ChartMarkerExit
            const exitColour =
              exit.outcome === 'WIN'
                ? '#34D399'
                : exit.outcome === 'LOSS'
                ? '#F87171'
                : '#6B7280'
            const shape: any =
              exit.outcome === 'WIN'
                ? 'circle'
                : exit.outcome === 'LOSS'
                ? 'square'
                : 'arrowDown'
            const text =
              exit.outcome === 'WIN' ? '✓' : exit.outcome === 'LOSS' ? '✗' : '–'
            return {
              time: toTime(m.time),
              position: 'aboveBar',
              color: exitColour,
              shape,
              text,
              size: 0.8,
            }
          }
        })

        // Sort ascending and deduplicate by (time, shape) before setMarkers
        const sorted = [...lwMarkers].sort((a: any, b: any) =>
          a.time < b.time ? -1 : a.time > b.time ? 1 : 0,
        )
        const seenKeys = new Set<string>()
        const deduped = sorted.filter((mk: any) => {
          const key = `${mk.time}-${mk.shape}`
          if (seenKeys.has(key)) return false
          seenKeys.add(key)
          return true
        })
        lineSeries.setMarkers(deduped)
      }

      markerSeriesRef.current[run.runId] = lineSeries
    }
  }, [runMarkers, visibleRunIds, candles])

  return <div ref={containerRef} style={{ width: '100%' }} />
}
