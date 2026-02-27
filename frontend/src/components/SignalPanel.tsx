import { useState } from 'react'
import type { AnalysisResponse } from '../types'

interface SignalPanelProps {
  analysis: AnalysisResponse
}

const TOOLTIPS: Record<string, string> = {
  RSI:             'Relative Strength Index — above 70 is overbought, below 30 is oversold',
  MACD:            'Moving Average Convergence Divergence — measures momentum and trend direction',
  'Bollinger Bands': 'Price position within Bollinger Bands — squeeze indicates low volatility breakout incoming',
  Volume:          'Current volume vs 20-day average — high ratio signals strong conviction',
  Support:         'Nearest price floor based on recent swing lows',
  Resistance:      'Nearest price ceiling based on recent swing highs',
  Candlestick:     'Recent candlestick patterns detected on the daily chart',
  Trend:           'Overall trend signal based on SMA 20 / 50 / 200 alignment',
}

function strengthVariant(s: string): 'green' | 'yellow' | 'gray' {
  if (s === 'HIGH') return 'green'
  if (s === 'MEDIUM') return 'yellow'
  return 'gray'
}

function weeklyTrendVariant(
  weeklyTrend: string,
  dailyTrend: string,
): 'green' | 'red' | 'yellow' | 'gray' {
  const w = (weeklyTrend ?? '').toUpperCase()
  const d = (dailyTrend  ?? '').toUpperCase()
  if (w === 'BULLISH') return 'green'
  if (w === 'BEARISH') return d.includes('BULLISH') ? 'yellow' : 'red'
  return 'gray'
}

function signalVariant(signal: string): 'green' | 'red' | 'yellow' | 'gray' {
  const s = (signal ?? '').toUpperCase()
  if (['BULLISH', 'RISING', 'HIGH', 'ABOVE', 'STRONG'].some(k => s.includes(k))) return 'green'
  if (['BEARISH', 'FALLING', 'OVERBOUGHT', 'BELOW', 'WEAK'].some(k => s.includes(k))) return 'red'
  if (s.includes('OVERSOLD')) return 'yellow'
  return 'gray'
}

function macdVariant(crossover: string): 'green' | 'red' | 'gray' {
  const s = (crossover ?? '').toLowerCase()
  if (s.includes('bullish')) return 'green'
  if (s.includes('bearish')) return 'red'
  return 'gray'
}

const VARIANT_STYLES = {
  green:  'bg-green-500/15 text-green-300 border-green-500/25',
  red:    'bg-red-500/15 text-red-300 border-red-500/25',
  yellow: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/25',
  gray:   'bg-white/5 text-gray-400 border-white/10',
}

const SIGNAL_ICONS = {
  green:  '↑',
  red:    '↓',
  yellow: '⚠',
  gray:   '→',
}

function Badge({
  label,
  variant,
  showIcon = false,
}: {
  label: string
  variant: 'green' | 'red' | 'yellow' | 'gray'
  showIcon?: boolean
}) {
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border font-medium ${VARIANT_STYLES[variant]}`}>
      {showIcon && <span>{SIGNAL_ICONS[variant]}</span>}
      {label || '—'}
    </span>
  )
}

function fmt(n: number | null, decimals = 2): string {
  return n == null ? '—' : n.toFixed(decimals)
}

function fmtPct(n: number | null): string {
  return n == null ? '—' : `${n.toFixed(1)}%`
}

function fmtPrice(n: number | null): string {
  return n == null ? '—' : `$${n.toFixed(2)}`
}

function Cell({
  label,
  children,
  extra,
}: {
  label: string
  children: React.ReactNode
  extra?: React.ReactNode
}) {
  return (
    <div
      className="glass-hover p-4 flex flex-col gap-2 cursor-default"
      title={TOOLTIPS[label]}
    >
      <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">{label}</span>
      <div className="flex flex-wrap items-center gap-1.5 text-sm text-gray-100">
        {children}
      </div>
      {extra}
    </div>
  )
}

function ExpandableLevels({
  levels,
  color,
}: {
  levels: { price: number; strength: string }[]
  color: 'green' | 'red'
}) {
  const [open, setOpen] = useState(false)
  if (levels.length === 0) return null
  return (
    <div className="border-t border-white/5 pt-1 mt-0.5">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
        className="flex items-center gap-1 text-[10px] text-gray-600 hover:text-gray-400 transition-colors"
      >
        <svg
          className={`w-2.5 h-2.5 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M19 9l-7 7-7-7" />
        </svg>
        {open ? 'fewer levels' : `+${levels.length} more`}
      </button>
      {open && (
        <div className="mt-1.5 flex flex-col gap-1">
          {levels.map((lvl, i) => (
            <div key={i} className="flex items-center justify-between">
              <span className={`text-xs font-mono ${color === 'green' ? 'text-green-400/70' : 'text-red-400/70'}`}>
                ${lvl.price.toFixed(2)}
              </span>
              <Badge label={lvl.strength} variant={strengthVariant(lvl.strength)} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function SignalPanel({ analysis }: SignalPanelProps) {
  const { momentum, volatility, volume, support_resistance, candlestick, trend } = analysis

  const additionalSupports    = (support_resistance.swing_lows  ?? []).slice(1, 5)
  const additionalResistances = (support_resistance.swing_highs ?? []).slice(1, 5)

  const candlestickPatterns = candlestick.length > 0
    ? candlestick.map((c) => c.pattern).join(', ')
    : 'none'

  const obvArrow = (volume.obv_trend ?? '').toUpperCase() === 'RISING' ? '↑'
    : (volume.obv_trend ?? '').toUpperCase() === 'FALLING' ? '↓'
    : '→'

  const macdLabel = momentum.macd_crossover && momentum.macd_crossover !== 'none'
    ? momentum.macd_crossover
    : `hist ${fmt(momentum.macd_histogram, 3)}`

  const trendVariant = signalVariant(trend.signal)

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 animate-fade-in">
      <Cell label="RSI">
        <span className="font-mono font-semibold">{fmt(momentum.rsi, 1)}</span>
        <Badge label={momentum.rsi_signal} variant={signalVariant(momentum.rsi_signal)} showIcon />
      </Cell>

      <Cell label="MACD">
        <Badge label={macdLabel} variant={macdVariant(momentum.macd_crossover)} showIcon />
        <span className="text-xs text-gray-500">{momentum.signal}</span>
      </Cell>

      <Cell label="Bollinger Bands">
        <span className="font-mono font-semibold">{fmtPct(volatility.bb_position)}</span>
        <Badge label={volatility.signal} variant={signalVariant(volatility.signal)} />
        {volatility.bb_squeeze && <Badge label="Squeeze" variant="yellow" />}
      </Cell>

      <Cell label="Volume">
        <span className="font-mono font-semibold">{fmt(volume.volume_ratio, 2)}×</span>
        <span className="text-gray-400 font-mono">OBV {obvArrow}</span>
        <Badge label={volume.volume_signal} variant={signalVariant(volume.volume_signal)} />
      </Cell>

      <Cell
        label="Support"
        extra={<ExpandableLevels levels={additionalSupports} color="green" />}
      >
        <span className="font-mono font-semibold text-green-400">{fmtPrice(support_resistance.nearest_support)}</span>
        <Badge label={support_resistance.support_strength ?? 'LOW'} variant={strengthVariant(support_resistance.support_strength ?? 'LOW')} />
        <span className="text-xs text-gray-500">
          {fmtPct(support_resistance.distance_to_support_pct)} away
        </span>
      </Cell>

      <Cell
        label="Resistance"
        extra={<ExpandableLevels levels={additionalResistances} color="red" />}
      >
        <span className="font-mono font-semibold text-red-400">{fmtPrice(support_resistance.nearest_resistance)}</span>
        <Badge label={support_resistance.resistance_strength ?? 'LOW'} variant={strengthVariant(support_resistance.resistance_strength ?? 'LOW')} />
        <span className="text-xs text-gray-500">
          {fmtPct(support_resistance.distance_to_resistance_pct)} away
        </span>
      </Cell>

      <Cell label="Candlestick">
        <span className="text-xs text-gray-300 capitalize">{candlestickPatterns}</span>
      </Cell>

      <Cell
        label="Trend"
        extra={
          analysis.weekly_trend ? (
            <div className="border-t border-white/5 pt-1.5 mt-0.5 flex items-center gap-1.5">
              <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider flex-shrink-0">
                W
              </span>
              <Badge
                label={analysis.weekly_trend.weekly_trend}
                variant={weeklyTrendVariant(analysis.weekly_trend.weekly_trend, trend.signal)}
                showIcon
              />
              <span className="text-[10px] text-gray-600 font-mono capitalize">
                {analysis.weekly_trend.weekly_trend_strength.toLowerCase()}
              </span>
            </div>
          ) : null
        }
      >
        <Badge label={trend.signal} variant={trendVariant} showIcon />
        <span className="text-xs text-gray-500 font-mono">@ ${analysis.price.toFixed(2)}</span>
      </Cell>
    </div>
  )
}
