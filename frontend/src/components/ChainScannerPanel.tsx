import { useEffect, useState } from 'react'
import { chainScan, getCachedSignals, openOptionTrade } from '../api/client'
import type { ChainSignal, ChainScanResponse, PricedStrategy } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

type SortKey = 'conviction' | 'edge_pct' | 'iv_rank'

const IV_REGIME_STYLE: Record<string, string> = {
  LOW: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  NORMAL: 'bg-white/5 text-gray-400 border-white/10',
  ELEVATED: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  HIGH: 'bg-red-500/15 text-red-300 border-red-500/30',
}

const DIRECTION_STYLE: Record<string, string> = {
  BUY: 'bg-green-500/15 text-green-400 border-green-500/30',
  SELL: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
}

function convictionColor(c: number): string {
  if (c >= 80) return 'text-green-300'
  if (c >= 60) return 'text-green-400'
  if (c >= 30) return 'text-yellow-400'
  return 'text-gray-500'
}

function convictionGlow(c: number): string {
  return c >= 80 ? 'drop-shadow-[0_0_4px_rgba(134,239,172,0.4)]' : ''
}

function fmt(n: number | null | undefined, prefix = '$') {
  if (n == null) return '—'
  return `${prefix}${n.toFixed(2)}`
}

// ── Priced strategy section ──────────────────────────────────────────────────

function PricedStrategySection({ ps }: { ps: PricedStrategy }) {
  const [showLegs, setShowLegs] = useState(false)

  return (
    <div className="border-t border-white/6 pt-3 mt-1 flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Priced Strategy</span>
        <span className="text-xs font-mono text-gray-500">{ps.strategy.replace(/_/g, ' ')}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${ps.is_credit ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-blue-500/10 text-blue-400 border-blue-500/20'}`}>
          {ps.is_credit ? 'CREDIT' : 'DEBIT'}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-sm">
        <div>
          <p className="text-xs text-gray-500 mb-0.5">{ps.is_credit ? 'Credit recv.' : 'Debit paid'}</p>
          <p className="font-mono text-white">{fmt(ps.entry)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">{ps.is_credit ? 'Take-profit' : 'Target exit'}</p>
          <p className="font-mono text-green-400">{fmt(ps.exit_target)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Option stop</p>
          <p className="font-mono text-red-400">{fmt(ps.option_stop)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">R:R</p>
          <p className="font-mono text-white">{ps.risk_reward}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Max profit</p>
          <p className="font-mono text-green-300">{ps.max_profit != null ? fmt(ps.max_profit) : 'Unlimited'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Max loss</p>
          <p className="font-mono text-red-300">{ps.max_loss != null ? fmt(ps.max_loss) : 'Unlimited'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">P(profit)</p>
          <p className="font-mono text-white">{ps.prob_profit.toFixed(1)}%</p>
        </div>
        {ps.spread_width != null && (
          <div>
            <p className="text-xs text-gray-500 mb-0.5">Spread width</p>
            <p className="font-mono text-gray-300">{fmt(ps.spread_width)}</p>
          </div>
        )}
      </div>

      {/* Net Greeks */}
      <div className="flex gap-4 text-xs font-mono text-gray-500">
        <span>{'\u0394'} {ps.net_delta > 0 ? '+' : ''}{ps.net_delta.toFixed(3)}</span>
        <span>{'\u0398'} ${ps.net_theta.toFixed(3)}/d</span>
        <span>{'\u03BD'} {ps.net_vega.toFixed(3)}</span>
        <span>{'\u0393'} {ps.net_gamma.toFixed(4)}</span>
      </div>

      {/* Legs */}
      {ps.legs.length > 0 && (
        <div>
          <button
            onClick={() => setShowLegs((s) => !s)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showLegs ? '\u25B2 Hide legs' : `\u25BC Show ${ps.legs.length} leg${ps.legs.length > 1 ? 's' : ''}`}
          </button>
          {showLegs && (
            <div className="mt-2 rounded-lg border border-white/8 overflow-hidden">
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="border-b border-white/8 text-gray-500">
                    <th className="text-left px-3 py-1.5">Action</th>
                    <th className="text-left px-3 py-1.5">Type</th>
                    <th className="text-right px-3 py-1.5">Strike</th>
                    <th className="text-right px-3 py-1.5">Price</th>
                    <th className="text-right px-3 py-1.5">IV</th>
                    <th className="text-right px-3 py-1.5">{'\u0394'}</th>
                  </tr>
                </thead>
                <tbody>
                  {ps.legs.map((leg, i) => (
                    <tr key={i} className="border-b border-white/5 last:border-0">
                      <td className={`px-3 py-1.5 font-semibold ${leg.action === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                        {leg.action.toUpperCase()}
                      </td>
                      <td className="px-3 py-1.5 text-gray-300">{leg.option_type.toUpperCase()}</td>
                      <td className="px-3 py-1.5 text-right text-gray-200">${leg.strike.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-gray-200">${leg.price.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-gray-400">{(leg.iv * 100).toFixed(1)}%</td>
                      <td className="px-3 py-1.5 text-right text-gray-400">{leg.delta > 0 ? '+' : ''}{leg.delta.toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Signal card ──────────────────────────────────────────────────────────────

function SignalCard({ signal }: { signal: ChainSignal }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/3 p-4 flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-sm font-bold text-white font-mono">{signal.ticker}</span>
        <span className="font-mono text-sm text-gray-300">${signal.strike.toFixed(2)}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${signal.option_type === 'call' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
          {signal.option_type.toUpperCase()}
        </span>
        <span className="text-xs text-gray-500 font-mono">{signal.expiry} · {signal.dte}d</span>
        <span className="ml-auto text-xs text-gray-500 font-mono">spot ${signal.spot.toFixed(2)}</span>
      </div>

      {/* IV context row */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`px-2 py-0.5 rounded-md border text-xs font-medium ${IV_REGIME_STYLE[signal.iv_regime] ?? 'bg-white/5 text-gray-400 border-white/10'}`}>
          {signal.iv_regime}
        </span>
        <span className="text-xs text-gray-500">
          IV rank <span className="font-mono text-gray-300">{signal.iv_rank.toFixed(1)}</span>
        </span>
        <span className="text-xs text-gray-500">
          IV %ile <span className="font-mono text-gray-300">{signal.iv_percentile.toFixed(1)}</span>
        </span>
        <span className="text-xs text-gray-500">
          IV <span className="font-mono text-gray-300">{(signal.chain_iv * 100).toFixed(1)}%</span>
        </span>
        <span className="text-xs text-gray-500">
          GARCH <span className="font-mono text-gray-300">{(signal.garch_vol * 100).toFixed(1)}%</span>
        </span>
      </div>

      {/* Edge + direction + conviction row */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`px-2 py-0.5 rounded-md border text-xs font-mono ${DIRECTION_STYLE[signal.direction] ?? 'bg-white/5 text-gray-400 border-white/10'}`}>
          {signal.direction}
        </span>
        <span className={`text-sm font-mono ${signal.edge_pct > 0 ? 'text-green-400' : signal.edge_pct < 0 ? 'text-red-400' : 'text-gray-400'}`}>
          edge {signal.edge_pct > 0 ? '+' : ''}{signal.edge_pct.toFixed(1)}%
        </span>
        <span className={`text-sm font-mono font-semibold ${convictionColor(signal.conviction)} ${convictionGlow(signal.conviction)}`}>
          conviction {signal.conviction.toFixed(0)}
        </span>
        <span className="text-xs text-gray-500 font-mono">
          mid ${signal.mid.toFixed(2)} · theo ${signal.theo_price.toFixed(2)}
        </span>
      </div>

      {/* Greeks row */}
      <div className="flex gap-4 text-xs font-mono text-gray-500 border-t border-white/6 pt-2">
        <span>{'\u0394'} {signal.delta > 0 ? '+' : ''}{signal.delta.toFixed(3)}</span>
        <span>{'\u0393'} {signal.gamma.toFixed(4)}</span>
        <span>{'\u0398'} ${signal.theta.toFixed(3)}/d</span>
        <span>{'\u03BD'} {signal.vega.toFixed(3)}</span>
        <span className="text-gray-600">OI {signal.open_interest.toLocaleString()}</span>
        <span className="text-gray-600">spread {signal.bid_ask_spread_pct.toFixed(1)}%</span>
      </div>

      {/* Recommended strategy */}
      {signal.recommended_strategy && (
        <div className="border-t border-white/6 pt-3 mt-1 flex flex-col gap-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Strategy</span>
            <span className="text-sm font-medium text-white">{signal.recommended_strategy.label}</span>
            <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${signal.recommended_strategy.risk_profile === 'defined' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'}`}>
              {signal.recommended_strategy.risk_profile}
            </span>
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono border bg-white/5 text-gray-400 border-white/10">
              {signal.recommended_strategy.edge_source.replace(/_/g, ' ')}
            </span>
          </div>
          <p className="text-xs text-gray-400 leading-relaxed">{signal.recommended_strategy.rationale}</p>
        </div>
      )}

      {/* Priced strategy */}
      {signal.priced_strategy && (
        <>
          <PricedStrategySection ps={signal.priced_strategy} />
          <LogTradeButton signal={signal} ps={signal.priced_strategy} />
        </>
      )}
    </div>
  )
}

function LogTradeButton({ signal, ps }: { signal: ChainSignal; ps: PricedStrategy }) {
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  async function handleLog() {
    setSaving(true)
    try {
      await openOptionTrade({
        ticker: signal.ticker,
        strategy: ps.strategy,
        is_credit: ps.is_credit,
        legs: ps.legs,
        entry_premium: ps.entry,
        exit_target: ps.exit_target,
        option_stop: ps.option_stop,
        max_profit: ps.max_profit,
        max_loss: ps.max_loss,
        spread_width: ps.spread_width ?? null,
        expiry: signal.expiry,
        dte_at_open: signal.dte,
        chain_iv: signal.chain_iv,
        iv_rank: signal.iv_rank,
        iv_regime: signal.iv_regime,
        conviction: signal.conviction,
      })
      setSaved(true)
    } catch {
      // silently ignore
    } finally {
      setSaving(false)
    }
  }

  if (saved) {
    return (
      <div className="text-xs text-green-400 font-medium mt-1">Trade logged</div>
    )
  }

  return (
    <button
      onClick={handleLog}
      disabled={saving}
      className="mt-1 px-3 py-1.5 rounded-lg border border-green-500/30 bg-green-500/10 text-green-400 text-xs font-medium hover:bg-green-500/20 disabled:opacity-40 transition-colors"
    >
      {saving ? 'Logging\u2026' : 'Log Trade'}
    </button>
  )
}

// ── Main panel ───────────────────────────────────────────────────────────────

export default function ChainScannerPanel() {
  const [input, setInput] = useState('')
  const [priceStrategies, setPriceStrategies] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [data, setData] = useState<ChainScanResponse | null>(null)
  const [sortBy, setSortBy] = useState<SortKey>('conviction')
  const [lastScan, setLastScan] = useState<string | null>(null)

  // Load cached signals on mount
  useEffect(() => {
    getCachedSignals()
      .then((cached) => {
        if (cached.signals.length > 0) {
          const signals = cached.signals.map((row) => ({
            ticker: String(row.ticker ?? ''),
            strike: Number(row.strike ?? 0),
            expiry: String(row.expiry ?? ''),
            option_type: (row.option_type ?? 'call') as 'call' | 'put',
            dte: Number(row.dte ?? 0),
            spot: Number(row.spot ?? 0),
            bid: Number(row.bid ?? 0),
            ask: Number(row.ask ?? 0),
            mid: Number(row.mid ?? 0),
            open_interest: Number(row.open_interest ?? 0),
            bid_ask_spread_pct: Number(row.bid_ask_spread_pct ?? 0),
            chain_iv: Number(row.chain_iv ?? 0),
            iv_rank: Number(row.iv_rank ?? 0),
            iv_percentile: Number(row.iv_percentile ?? 0),
            iv_regime: (row.iv_regime ?? 'NORMAL') as ChainSignal['iv_regime'],
            garch_vol: Number(row.garch_vol ?? 0),
            theo_price: Number(row.theo_price ?? 0),
            edge_pct: Number(row.edge_pct ?? 0),
            direction: (row.direction ?? 'BUY') as 'BUY' | 'SELL',
            delta: Number(row.delta ?? 0),
            gamma: Number(row.gamma ?? 0),
            theta: Number(row.theta ?? 0),
            vega: Number(row.vega ?? 0),
            conviction: Number(row.conviction ?? 0),
          })) as ChainSignal[]
          setData({ signals, total: cached.total, tickers_scanned: 0 })
          setLastScan(cached.last_scan)
        }
      })
      .catch(() => {})
  }, [])

  async function handleScan(useWatchlist = false) {
    const tickers = useWatchlist
      ? []
      : input
          .toUpperCase()
          .split(/[\s,]+/)
          .map((t) => t.trim())
          .filter(Boolean)

    if (!useWatchlist && tickers.length === 0) return

    setLoading(true)
    setError(null)
    setData(null)
    setLastScan(null)
    try {
      const result = await chainScan(tickers, { top: 20, price: priceStrategies })
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chain scan failed')
    } finally {
      setLoading(false)
    }
  }

  const sorted = data
    ? [...data.signals].sort((a, b) => {
        if (sortBy === 'conviction') return b.conviction - a.conviction
        if (sortBy === 'edge_pct') return Math.abs(b.edge_pct) - Math.abs(a.edge_pct)
        return b.iv_rank - a.iv_rank
      })
    : []

  return (
    <div className="flex flex-col gap-6">
      {/* Input row */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleScan()}
          placeholder="AAPL, NVDA, SPY …"
          className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 font-mono"
        />
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer select-none self-center">
          <input
            type="checkbox"
            checked={priceStrategies}
            onChange={(e) => setPriceStrategies(e.target.checked)}
            className="accent-blue-500"
          />
          Price strategies
        </label>
        <button
          onClick={() => handleScan(false)}
          disabled={loading || !input.trim()}
          className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium text-white transition-colors"
        >
          {loading ? 'Scanning\u2026' : 'Scan'}
        </button>
        <button
          onClick={() => handleScan(true)}
          disabled={loading}
          className="px-4 py-2.5 rounded-xl border border-white/10 text-sm text-gray-400 hover:text-white hover:border-white/25 hover:bg-white/5 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
        >
          Use Watchlist
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-col gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-xl border border-white/8 bg-white/3 p-4 animate-pulse">
              <div className="h-4 bg-white/10 rounded w-32 mb-3" />
              <div className="h-3 bg-white/5 rounded w-full mb-2" />
              <div className="h-3 bg-white/5 rounded w-3/4" />
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {data && !loading && (
        <div className="flex flex-col gap-4">
          {/* Summary bar + sort */}
          <div className="flex items-center justify-between flex-wrap gap-2">
            <p className="text-sm text-gray-500">
              <span className="font-mono text-gray-300">{data.total}</span> signals
              {data.tickers_scanned > 0 && (
                <> from <span className="font-mono text-gray-300">{data.tickers_scanned}</span> ticker{data.tickers_scanned !== 1 ? 's' : ''}</>
              )}
              {data.signals.length < data.total && (
                <> · showing top <span className="font-mono text-gray-300">{data.signals.length}</span></>
              )}
              {lastScan && (
                <> · <span className="text-gray-600">Last scanned: {new Date(lastScan).toLocaleString()}</span></>
              )}
            </p>
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-600 mr-1">Sort:</span>
              {(['conviction', 'edge_pct', 'iv_rank'] as const).map((key) => (
                <button
                  key={key}
                  onClick={() => setSortBy(key)}
                  className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                    sortBy === key
                      ? 'bg-white/10 text-white'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                  }`}
                >
                  {key === 'conviction' ? 'Conviction' : key === 'edge_pct' ? 'Edge %' : 'IV Rank'}
                </button>
              ))}
            </div>
          </div>

          {/* Signal cards */}
          {sorted.length === 0 ? (
            <p className="text-sm text-gray-500">No signals found.</p>
          ) : (
            sorted.map((s, i) => <SignalCard key={`${s.ticker}-${s.strike}-${s.expiry}-${i}`} signal={s} />)
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && !data && !error && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
          <div className="text-5xl opacity-30">{'\u26A1'}</div>
          <p className="text-gray-500 text-sm">Enter tickers or use your watchlist to scan for options signals</p>
        </div>
      )}
    </div>
  )
}
