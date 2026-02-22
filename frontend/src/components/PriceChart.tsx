import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import {
  createChart,
  ColorType,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type Time,
  type LogicalRange,
} from 'lightweight-charts'
import type { PriceBar } from '../types'

// ─── Time range options ───────────────────────────────────────────────────────

const TIME_RANGES = [
  { label: '1M',  days: 30   },
  { label: '6M',  days: 180  },
  { label: '1Y',  days: 365  },
  { label: '2Y',  days: 730  },
  { label: '5Y',  days: 1825 },
  { label: '6Y',  days: 2190 },
] as const

// ─── Indicator state ──────────────────────────────────────────────────────────

interface IndicatorState {
  sma20:  boolean
  sma50:  boolean
  sma200: boolean
  ema9:   boolean
  ema21:  boolean
  bb:     boolean
  volume: boolean
  rsi:    boolean
  macd:   boolean
}

const DEFAULT_IND: IndicatorState = {
  sma20: true, sma50: true, sma200: true,
  ema9: false, ema21: false,
  bb: true, volume: true,
  rsi: false, macd: false,
}

// ─── Math helpers ─────────────────────────────────────────────────────────────

function toTime(date: string): Time { return date as Time }

function sma(values: number[], w: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < w - 1) return null
    return values.slice(i - w + 1, i + 1).reduce((a, b) => a + b, 0) / w
  })
}

function stddev(values: number[], means: (number | null)[], w: number): (number | null)[] {
  return values.map((_, i) => {
    if (i < w - 1 || means[i] == null) return null
    const m = means[i]!
    const v = values.slice(i - w + 1, i + 1).reduce((a, b) => a + (b - m) ** 2, 0) / w
    return Math.sqrt(v)
  })
}

function ema(values: number[], period: number): (number | null)[] {
  const result: (number | null)[] = new Array(values.length).fill(null)
  if (values.length < period) return result
  const k = 2 / (period + 1)
  result[period - 1] = values.slice(0, period).reduce((a, b) => a + b, 0) / period
  for (let i = period; i < values.length; i++) {
    result[i] = values[i] * k + result[i - 1]! * (1 - k)
  }
  return result
}

function computeRSI(closes: number[], period = 14): (number | null)[] {
  const result: (number | null)[] = new Array(closes.length).fill(null)
  if (closes.length <= period) return result
  const changes = closes.slice(1).map((v, i) => v - closes[i])
  let avgG = changes.slice(0, period).reduce((a, c) => a + Math.max(0, c), 0) / period
  let avgL = changes.slice(0, period).reduce((a, c) => a + Math.max(0, -c), 0) / period
  result[period] = 100 - 100 / (1 + (avgL === 0 ? Infinity : avgG / avgL))
  for (let i = period; i < changes.length; i++) {
    avgG = (avgG * (period - 1) + Math.max(0,  changes[i])) / period
    avgL = (avgL * (period - 1) + Math.max(0, -changes[i])) / period
    result[i + 1] = 100 - 100 / (1 + (avgL === 0 ? Infinity : avgG / avgL))
  }
  return result
}

function computeMACD(closes: number[]) {
  const e12 = ema(closes, 12)
  const e26 = ema(closes, 26)
  const macdLine: (number | null)[] = closes.map((_, i) =>
    e12[i] != null && e26[i] != null ? e12[i]! - e26[i]! : null
  )
  const start = macdLine.findIndex(v => v != null)
  const signalLine: (number | null)[] = new Array(closes.length).fill(null)
  const histogram:  (number | null)[] = new Array(closes.length).fill(null)
  if (start >= 0) {
    const sig = ema(macdLine.slice(start) as number[], 9)
    sig.forEach((s, i) => {
      const idx = start + i
      signalLine[idx] = s
      if (s != null && macdLine[idx] != null) histogram[idx] = macdLine[idx]! - s
    })
  }
  return { macdLine, signalLine, histogram }
}

// ─── Shared chart theme ───────────────────────────────────────────────────────

const THEME = {
  layout: {
    background: { type: ColorType.Solid, color: '#030712' },
    textColor: '#d1d5db',
    fontSize: 13,
    fontFamily: "'Inter', 'system-ui', sans-serif",
  },
  grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
  rightPriceScale: { borderColor: '#374151', textColor: '#d1d5db' },
  timeScale: { borderColor: '#374151', timeVisible: true, secondsVisible: false },
} as const

// ─── Shared sub-pane data setter ──────────────────────────────────────────────

function setLineData(
  ref: React.MutableRefObject<ISeriesApi<'Line'> | null>,
  arr: (number | null)[],
  prices: PriceBar[],
) {
  ref.current?.setData(
    arr
      .map((v, i) => v != null ? { time: toTime(prices[i].date), value: v } : null)
      .filter((x): x is { time: Time; value: number } => x !== null)
  )
}

// ─── Reusable hook: build an entire chart instance ────────────────────────────

function useChartInstance(
  containerRef: React.RefObject<HTMLDivElement>,
  prices: PriceBar[],
  ind: IndicatorState,
) {
  const chartRef      = useRef<IChartApi | null>(null)
  const candleRef     = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const sma20R        = useRef<ISeriesApi<'Line'> | null>(null)
  const sma50R        = useRef<ISeriesApi<'Line'> | null>(null)
  const sma200R       = useRef<ISeriesApi<'Line'> | null>(null)
  const ema9R         = useRef<ISeriesApi<'Line'> | null>(null)
  const ema21R        = useRef<ISeriesApi<'Line'> | null>(null)
  const bbUpR         = useRef<ISeriesApi<'Line'> | null>(null)
  const bbLoR         = useRef<ISeriesApi<'Line'> | null>(null)
  const volR          = useRef<ISeriesApi<'Histogram'> | null>(null)

  const rsiContRef    = useRef<HTMLDivElement>(null)
  const rsiChartRef   = useRef<IChartApi | null>(null)
  const rsiSeriesRef  = useRef<ISeriesApi<'Line'> | null>(null)
  const rsiSyncRef    = useRef<((r: LogicalRange | null) => void) | null>(null)

  const macdContRef   = useRef<HTMLDivElement>(null)
  const macdChartRef  = useRef<IChartApi | null>(null)
  const macdLineRef   = useRef<ISeriesApi<'Line'> | null>(null)
  const macdSignalRef = useRef<ISeriesApi<'Line'> | null>(null)
  const macdHistRef   = useRef<ISeriesApi<'Histogram'> | null>(null)
  const macdSyncRef   = useRef<((r: LogicalRange | null) => void) | null>(null)

  // Create main chart
  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      ...THEME, autoSize: true,
      rightPriceScale: { ...THEME.rightPriceScale, scaleMargins: { top: 0.08, bottom: 0.22 } },
    })
    candleRef.current  = chart.addCandlestickSeries({
      upColor: '#22c55e', downColor: '#ef4444',
      borderUpColor: '#22c55e', borderDownColor: '#ef4444',
      wickUpColor: '#22c55e', wickDownColor: '#ef4444',
    })
    sma20R.current  = chart.addLineSeries({ color: '#60a5fa', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
    sma50R.current  = chart.addLineSeries({ color: '#f97316', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
    sma200R.current = chart.addLineSeries({ color: '#f87171', lineWidth: 2, priceLineVisible: false, lastValueVisible: false })
    ema9R.current   = chart.addLineSeries({ color: '#a78bfa', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    ema21R.current  = chart.addLineSeries({ color: '#fb923c', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
    bbUpR.current   = chart.addLineSeries({ color: '#4b5563', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
    bbLoR.current   = chart.addLineSeries({ color: '#4b5563', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
    volR.current    = chart.addHistogramSeries({ priceScaleId: '', priceFormat: { type: 'volume' } })
    chart.priceScale('').applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } })
    chartRef.current = chart
    return () => { chart.remove(); chartRef.current = null }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Update main chart data
  useEffect(() => {
    if (!prices.length || !candleRef.current || !chartRef.current) return
    const closes = prices.map(p => p.close)

    const ld = (arr: (number | null)[], ref: React.MutableRefObject<ISeriesApi<'Line'> | null>, active: boolean) => {
      if (!ref.current) return
      if (!active) { ref.current.setData([]); return }
      setLineData(ref, arr, prices)
    }

    candleRef.current.setData(prices.map(p => ({
      time: toTime(p.date), open: p.open, high: p.high, low: p.low, close: p.close,
    })))

    const m20   = sma(closes, 20)
    const m50   = sma(closes, 50)
    const m200  = sma(closes, 200)
    const std20 = stddev(closes, m20, 20)
    const bbUp  = m20.map((m, i) => m != null && std20[i] != null ? m + 2 * std20[i]! : null)
    const bbLo  = m20.map((m, i) => m != null && std20[i] != null ? m - 2 * std20[i]! : null)

    ld(m20,  sma20R,  ind.sma20)
    ld(m50,  sma50R,  ind.sma50)
    ld(m200, sma200R, ind.sma200)
    ld(ema(closes, 9),  ema9R,  ind.ema9)
    ld(ema(closes, 21), ema21R, ind.ema21)
    ld(bbUp, bbUpR, ind.bb)
    ld(bbLo, bbLoR, ind.bb)

    if (volR.current) {
      if (!ind.volume) {
        volR.current.setData([])
      } else {
        volR.current.setData(prices.map(p => ({
          time: toTime(p.date), value: p.volume,
          color: p.close >= p.open ? '#166534' : '#7f1d1d',
        })))
      }
    }
    chartRef.current.timeScale().fitContent()
  }, [prices, ind])

  // RSI lifecycle
  useEffect(() => {
    if (!ind.rsi || !rsiContRef.current || !chartRef.current) return
    const rsiChart = createChart(rsiContRef.current, {
      ...THEME, autoSize: true,
      rightPriceScale: { ...THEME.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { ...THEME.timeScale, visible: false },
    })
    const ob = rsiChart.addLineSeries({ color: '#ef444460', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
    const os = rsiChart.addLineSeries({ color: '#22c55e60', lineWidth: 1, lineStyle: LineStyle.Dashed, priceLineVisible: false, lastValueVisible: false })
    rsiSeriesRef.current = rsiChart.addLineSeries({ color: '#a78bfa', lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
    if (prices.length > 0) {
      const flat = (v: number) => prices.map(p => ({ time: toTime(p.date), value: v }))
      ob.setData(flat(70)); os.setData(flat(30))
      setLineData(rsiSeriesRef, computeRSI(prices.map(p => p.close)), prices)
    }
    rsiChartRef.current = rsiChart
    const handler = (range: LogicalRange | null) => { if (range) rsiChart.timeScale().setVisibleLogicalRange(range) }
    rsiSyncRef.current = handler
    chartRef.current.timeScale().subscribeVisibleLogicalRangeChange(handler)
    return () => {
      chartRef.current?.timeScale().unsubscribeVisibleLogicalRangeChange(handler)
      rsiSyncRef.current = null
      rsiChart.remove(); rsiChartRef.current = null; rsiSeriesRef.current = null
    }
  }, [ind.rsi]) // eslint-disable-line react-hooks/exhaustive-deps

  // RSI data update
  useEffect(() => {
    if (!ind.rsi || !rsiSeriesRef.current || !prices.length) return
    setLineData(rsiSeriesRef, computeRSI(prices.map(p => p.close)), prices)
    rsiChartRef.current?.timeScale().fitContent()
  }, [prices, ind.rsi])

  // MACD lifecycle
  useEffect(() => {
    if (!ind.macd || !macdContRef.current || !chartRef.current) return
    const macdChart = createChart(macdContRef.current, {
      ...THEME, autoSize: true,
      rightPriceScale: { ...THEME.rightPriceScale, scaleMargins: { top: 0.1, bottom: 0.1 } },
      timeScale: { ...THEME.timeScale, visible: false },
    })
    macdLineRef.current   = macdChart.addLineSeries({ color: '#60a5fa', lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
    macdSignalRef.current = macdChart.addLineSeries({ color: '#f97316', lineWidth: 2, priceLineVisible: false, lastValueVisible: true })
    macdHistRef.current   = macdChart.addHistogramSeries({ color: '#6b7280', priceFormat: { type: 'price', precision: 4, minMove: 0.0001 }, priceLineVisible: false, lastValueVisible: false })
    if (prices.length > 0) {
      const { macdLine, signalLine, histogram } = computeMACD(prices.map(p => p.close))
      setLineData(macdLineRef, macdLine, prices)
      setLineData(macdSignalRef, signalLine, prices)
      macdHistRef.current?.setData(
        histogram.map((v, i) => v != null ? { time: toTime(prices[i].date), value: v, color: v >= 0 ? '#166534' : '#7f1d1d' } : null)
          .filter((x): x is { time: Time; value: number; color: string } => x !== null)
      )
    }
    macdChartRef.current = macdChart
    const handler = (range: LogicalRange | null) => { if (range) macdChart.timeScale().setVisibleLogicalRange(range) }
    macdSyncRef.current = handler
    chartRef.current.timeScale().subscribeVisibleLogicalRangeChange(handler)
    return () => {
      chartRef.current?.timeScale().unsubscribeVisibleLogicalRangeChange(handler)
      macdSyncRef.current = null
      macdChart.remove(); macdChartRef.current = null
      macdLineRef.current = null; macdSignalRef.current = null; macdHistRef.current = null
    }
  }, [ind.macd]) // eslint-disable-line react-hooks/exhaustive-deps

  // MACD data update
  useEffect(() => {
    if (!ind.macd || !macdLineRef.current || !prices.length) return
    const { macdLine, signalLine, histogram } = computeMACD(prices.map(p => p.close))
    setLineData(macdLineRef, macdLine, prices)
    setLineData(macdSignalRef, signalLine, prices)
    macdHistRef.current?.setData(
      histogram.map((v, i) => v != null ? { time: toTime(prices[i].date), value: v, color: v >= 0 ? '#166534' : '#7f1d1d' } : null)
        .filter((x): x is { time: Time; value: number; color: string } => x !== null)
    )
    macdChartRef.current?.timeScale().fitContent()
  }, [prices, ind.macd])

  return { rsiContRef, macdContRef }
}

// ─── Shared toolbar ───────────────────────────────────────────────────────────

function ToggleBtn({ label, color, active, onClick }: { label: string; color: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${active ? 'bg-white/10 border-white/20 text-gray-100' : 'bg-transparent border-white/5 text-gray-600 hover:text-gray-400 hover:border-white/10'}`}>
      <span className="w-3 h-0.5 rounded-full inline-block" style={{ backgroundColor: active ? color : '#4b5563' }} />
      {label}
    </button>
  )
}

function PaneToggleBtn({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-all ${active ? 'bg-blue-500/20 border-blue-500/40 text-blue-300' : 'bg-transparent border-white/5 text-gray-600 hover:text-gray-400 hover:border-white/10'}`}>
      {label}
    </button>
  )
}

function ChartToolbar({
  ind, toggle, days, onDaysChange, rightSlot,
}: {
  ind: IndicatorState
  toggle: (k: keyof IndicatorState) => void
  days: number
  onDaysChange: (d: number) => void
  rightSlot?: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5 px-4 py-3 border-b border-white/10 shrink-0">
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[10px] text-gray-600 uppercase tracking-widest mr-1">Overlays</span>
        <ToggleBtn label="SMA 20"  color="#60a5fa" active={ind.sma20}  onClick={() => toggle('sma20')}  />
        <ToggleBtn label="SMA 50"  color="#f97316" active={ind.sma50}  onClick={() => toggle('sma50')}  />
        <ToggleBtn label="SMA 200" color="#f87171" active={ind.sma200} onClick={() => toggle('sma200')} />
        <ToggleBtn label="EMA 9"   color="#a78bfa" active={ind.ema9}   onClick={() => toggle('ema9')}   />
        <ToggleBtn label="EMA 21"  color="#fb923c" active={ind.ema21}  onClick={() => toggle('ema21')}  />
        <ToggleBtn label="BB"      color="#6b7280" active={ind.bb}     onClick={() => toggle('bb')}     />
        <ToggleBtn label="Volume"  color="#374151" active={ind.volume} onClick={() => toggle('volume')} />
      </div>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] text-gray-600 uppercase tracking-widest mr-1">Panes</span>
          <PaneToggleBtn label="RSI"  active={ind.rsi}  onClick={() => toggle('rsi')}  />
          <PaneToggleBtn label="MACD" active={ind.macd} onClick={() => toggle('macd')} />
        </div>
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-0.5 bg-white/5 rounded-lg p-0.5">
            {TIME_RANGES.map(({ label, days: d }) => (
              <button key={label} onClick={() => onDaysChange(d)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${d === days ? 'bg-white/15 text-white' : 'text-gray-500 hover:text-gray-300'}`}>
                {label}
              </button>
            ))}
          </div>
          {rightSlot}
        </div>
      </div>
    </div>
  )
}

// ─── Expand / Compress icons ──────────────────────────────────────────────────

function ExpandIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 15 15" fill="none">
      <path d="M1.5 1.5H5.5M1.5 1.5V5.5M1.5 1.5L5.5 5.5M13.5 1.5H9.5M13.5 1.5V5.5M13.5 1.5L9.5 5.5M1.5 13.5H5.5M1.5 13.5V9.5M1.5 13.5L5.5 9.5M13.5 13.5H9.5M13.5 13.5V9.5M13.5 13.5L9.5 9.5"
        stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  )
}

// ─── Fullscreen sub-window (portal) ──────────────────────────────────────────

function ChartModal({
  prices, ind, toggle, days, onDaysChange, onClose, ticker,
}: {
  prices: PriceBar[]
  ind: IndicatorState
  toggle: (k: keyof IndicatorState) => void
  days: number
  onDaysChange: (d: number) => void
  onClose: () => void
  ticker?: string
}) {
  const mainRef = useRef<HTMLDivElement>(null)
  const { rsiContRef, macdContRef } = useChartInstance(mainRef, prices, ind)

  // Escape key + scroll lock
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return createPortal(
    <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 sm:p-6">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Floating window */}
      <div className="relative w-full h-full max-w-[96vw] max-h-[92vh] bg-[#030712] rounded-2xl border border-white/10 shadow-2xl shadow-black/50 flex flex-col overflow-hidden">

        {/* Title bar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 shrink-0 bg-white/[0.02]">
          <div className="flex items-center gap-2.5">
            <div className="flex gap-1.5">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
              <div className="w-3 h-3 rounded-full bg-green-500/80" />
            </div>
            <span className="text-sm font-medium text-gray-300">
              {ticker ? `${ticker} — Chart` : 'Chart'}
            </span>
          </div>
          <button
            onClick={onClose}
            title="Close (Esc)"
            className="text-gray-500 hover:text-gray-200 hover:bg-white/10 w-7 h-7 flex items-center justify-center rounded-md transition-all text-base leading-none"
          >
            ✕
          </button>
        </div>

        {/* Toolbar */}
        <ChartToolbar ind={ind} toggle={toggle} days={days} onDaysChange={onDaysChange} />

        {/* Main chart — flex-1 works because parent has a fixed height */}
        <div ref={mainRef} className="w-full flex-1 min-h-0" />

        {/* RSI sub-pane */}
        {ind.rsi && (
          <div className="border-t border-white/10 shrink-0">
            <div className="flex items-center gap-2 px-4 py-1.5 border-b border-white/5">
              <span className="text-[10px] text-gray-500 uppercase tracking-widest">RSI 14</span>
              <span className="text-[10px] text-red-400">— 70</span>
              <span className="text-[10px] text-green-400">— 30</span>
            </div>
            <div ref={rsiContRef} className="w-full h-36" />
          </div>
        )}

        {/* MACD sub-pane */}
        {ind.macd && (
          <div className="border-t border-white/10 shrink-0">
            <div className="flex items-center gap-3 px-4 py-1.5 border-b border-white/5">
              <span className="text-[10px] text-gray-500 uppercase tracking-widest">MACD 12/26/9</span>
              <span className="text-[10px] text-blue-400">— MACD</span>
              <span className="text-[10px] text-orange-400">— Signal</span>
            </div>
            <div ref={macdContRef} className="w-full h-36" />
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface PriceChartProps {
  prices:       PriceBar[]
  days:         number
  onDaysChange: (days: number) => void
  ticker?:      string
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function PriceChart({ prices, days, onDaysChange, ticker }: PriceChartProps) {
  const [ind, setInd] = useState<IndicatorState>(DEFAULT_IND)
  const [fullscreen, setFullscreen] = useState(false)
  const toggle = (key: keyof IndicatorState) =>
    setInd(prev => ({ ...prev, [key]: !prev[key] }))

  const mainRef = useRef<HTMLDivElement>(null)
  const { rsiContRef, macdContRef } = useChartInstance(mainRef, prices, ind)

  const expandBtn = (
    <button
      onClick={() => setFullscreen(true)}
      title="Open in sub-window"
      className="p-1.5 rounded-md text-gray-500 hover:text-gray-200 hover:bg-white/10 border border-white/5 hover:border-white/15 transition-all"
    >
      <ExpandIcon />
    </button>
  )

  return (
    <>
      <div className="glass overflow-hidden animate-fade-in">
        <ChartToolbar
          ind={ind} toggle={toggle} days={days} onDaysChange={onDaysChange}
          rightSlot={expandBtn}
        />

        <div ref={mainRef} className="w-full h-[480px]" />

        {ind.rsi && (
          <div className="border-t border-white/10">
            <div className="flex items-center gap-2 px-4 py-1.5 border-b border-white/5">
              <span className="text-[10px] text-gray-500 uppercase tracking-widest">RSI 14</span>
              <span className="text-[10px] text-red-400">— 70</span>
              <span className="text-[10px] text-green-400">— 30</span>
            </div>
            <div ref={rsiContRef} className="w-full h-32" />
          </div>
        )}

        {ind.macd && (
          <div className="border-t border-white/10">
            <div className="flex items-center gap-3 px-4 py-1.5 border-b border-white/5">
              <span className="text-[10px] text-gray-500 uppercase tracking-widest">MACD 12/26/9</span>
              <span className="text-[10px] text-blue-400">— MACD</span>
              <span className="text-[10px] text-orange-400">— Signal</span>
            </div>
            <div ref={macdContRef} className="w-full h-36" />
          </div>
        )}
      </div>

      {/* Sub-window portal — renders on document.body, bypasses all stacking contexts */}
      {fullscreen && (
        <ChartModal
          prices={prices}
          ind={ind}
          toggle={toggle}
          days={days}
          onDaysChange={onDaysChange}
          onClose={() => setFullscreen(false)}
          ticker={ticker}
        />
      )}
    </>
  )
}
