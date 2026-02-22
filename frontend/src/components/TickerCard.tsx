import type { TickerInfo } from '../types'

interface TickerCardProps {
  info: TickerInfo
  price: number
  dayChange: number
  dayChangePct: number
}

function fmtMarketCap(n: number | null): string {
  if (n == null) return '—'
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`
  return `$${n.toFixed(0)}`
}

export default function TickerCard({ info, price, dayChange, dayChangePct }: TickerCardProps) {
  const positive = dayChange >= 0
  const changeColor = positive ? 'text-green-400' : 'text-red-400'
  const changeBg    = positive ? 'bg-green-500/10 border-green-500/20' : 'bg-red-500/10 border-red-500/20'
  const arrow       = positive ? '▲' : '▼'

  return (
    <div className="glass animate-fade-in px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
      {/* Left: company identity */}
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold tracking-tight text-white">
            {info.symbol}
          </span>
          {info.sector && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-500/25 text-blue-300 font-medium">
              {info.sector}
            </span>
          )}
        </div>
        <span className="text-sm text-gray-400">{info.company_name ?? '—'}</span>
      </div>

      {/* Right: price + change + market cap */}
      <div className="flex items-center gap-4 sm:gap-6">
        <div className="flex flex-col items-end gap-1">
          <span className="text-2xl font-bold tabular-nums text-white">
            ${price.toFixed(2)}
          </span>
          <span className={`text-xs px-2 py-0.5 rounded border font-mono font-medium ${changeColor} ${changeBg}`}>
            {arrow} ${Math.abs(dayChange).toFixed(2)} ({Math.abs(dayChangePct).toFixed(2)}%)
          </span>
        </div>

        {info.market_cap != null && (
          <div className="hidden sm:flex flex-col items-end gap-1 border-l border-white/10 pl-5">
            <span className="text-xs text-gray-500 uppercase tracking-wider">Mkt Cap</span>
            <span className="text-sm font-semibold text-gray-200">{fmtMarketCap(info.market_cap)}</span>
          </div>
        )}
      </div>
    </div>
  )
}
