import { useEffect, useRef } from 'react'
import { createChart, LineStyle } from 'lightweight-charts'
import type { IChartApi } from 'lightweight-charts'
import type { PnLPoint } from '../types'

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

interface Props {
  pnlData: Record<string, { fixed: PnLPoint[]; compound: PnLPoint[] }>
  visibleRunIds: Set<string>
  runLabels: Record<string, string>
  runIndices: Record<string, number>
  mainChart: IChartApi | null
  height?: number
}

function sortByTime<T extends { time: string }>(arr: T[]): T[] {
  return [...arr].sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0))
}

function dedupByTime<T extends { time: string }>(arr: T[]): T[] {
  const seen = new Set<string>()
  return arr.filter((p) => {
    if (seen.has(p.time)) return false
    seen.add(p.time)
    return true
  })
}

export default function PlayerPnLPanel({
  pnlData,
  visibleRunIds,
  runLabels: _runLabels,
  runIndices,
  mainChart,
  height = 160,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<Record<string, { fixed: any; compound: any }>>({})
  const zeroRef = useRef<any>(null)
  const syncingFromMainRef = useRef(false)
  const syncingFromPnlRef = useRef(false)

  // Create chart once
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
      leftPriceScale: { visible: false },
      rightPriceScale: {
        visible: true,
        borderColor: '#374151',
      },
      timeScale: { visible: false },
      crosshair: { mode: 0 as any },
    })
    chartRef.current = chart

    // Dashed zero reference line
    const zeroSeries = chart.addLineSeries({
      color: '#4B5563',
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      lastValueVisible: false,
      priceLineVisible: false,
    })
    zeroRef.current = zeroSeries

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
      seriesRef.current = {}
      zeroRef.current = null
    }
  }, [height])

  // Bidirectional time-scale sync with main chart
  useEffect(() => {
    if (!chartRef.current || !mainChart) return
    const pnlChart = chartRef.current

    const unsubMain = mainChart
      .timeScale()
      .subscribeVisibleLogicalRangeChange((range) => {
        if (!range) return
        if (syncingFromPnlRef.current) {
          syncingFromPnlRef.current = false
          return
        }
        syncingFromMainRef.current = true
        pnlChart.timeScale().setVisibleLogicalRange(range)
      })

    const unsubPnl = pnlChart
      .timeScale()
      .subscribeVisibleLogicalRangeChange((range) => {
        if (!range) return
        if (syncingFromMainRef.current) {
          syncingFromMainRef.current = false
          return
        }
        syncingFromPnlRef.current = true
        mainChart.timeScale().setVisibleLogicalRange(range)
      })

    return () => {
      unsubMain()
      unsubPnl()
    }
  }, [mainChart])

  // Rebuild run series when data or visibility changes
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    // Remove all existing run series
    for (const { fixed, compound } of Object.values(seriesRef.current)) {
      try { chart.removeSeries(fixed) } catch (_) {}
      try { chart.removeSeries(compound) } catch (_) {}
    }
    seriesRef.current = {}

    // Collect all outcome times for zero line
    const allTimes = new Set<string>()
    for (const [runId, { fixed }] of Object.entries(pnlData)) {
      if (visibleRunIds.has(runId)) {
        fixed.forEach((p) => allTimes.add(p.time))
      }
    }
    const sortedTimes = [...allTimes].sort()
    if (zeroRef.current && sortedTimes.length > 0) {
      zeroRef.current.setData(
        dedupByTime(sortedTimes.map((t) => ({ time: t as any, value: 0 }))),
      )
    }

    // Add two series per visible run (solid Fixed, dashed Compound)
    for (const [runId, data] of Object.entries(pnlData)) {
      if (!visibleRunIds.has(runId)) continue
      const idx = runIndices[runId] ?? 0
      const colour = getRunColour(idx)

      const fixedSeries = chart.addLineSeries({
        color: colour,
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        lastValueVisible: true,
        priceLineVisible: false,
        title: 'Fixed',
      })
      const compoundSeries = chart.addLineSeries({
        color: colour,
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
        lastValueVisible: true,
        priceLineVisible: false,
        title: 'Cmpd',
      })

      if (data.fixed.length > 0) {
        fixedSeries.setData(
          dedupByTime(sortByTime(data.fixed)).map((p) => ({
            time: p.time as any,
            value: p.value,
          })),
        )
      }
      if (data.compound.length > 0) {
        compoundSeries.setData(
          dedupByTime(sortByTime(data.compound)).map((p) => ({
            time: p.time as any,
            value: p.value,
          })),
        )
      }

      seriesRef.current[runId] = { fixed: fixedSeries, compound: compoundSeries }
    }
  }, [pnlData, visibleRunIds, runIndices])

  return (
    <div>
      {/* Panel header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '6px 12px',
          borderTop: '1px solid #1F2937',
          borderBottom: '1px solid #1F2937',
          background: '#0F172A',
        }}
      >
        <span
          style={{
            color: '#9CA3AF',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
          }}
        >
          Cumulative P&amp;L (ENTRY only)
        </span>
        <div style={{ display: 'flex', gap: 12, fontSize: 10, color: '#6B7280' }}>
          <span>── Fixed $1K</span>
          <span>╌╌ Compound</span>
        </div>
      </div>
      <div ref={containerRef} />
    </div>
  )
}
