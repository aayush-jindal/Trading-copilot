import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { scanOptions } from '../api/client'
import Logo from '../components/Logo'
import { useAuth } from '../context/AuthContext'
import type { OptionsOpportunity, OptionsTickerResult, OptionsScanResponse } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

const OUTLOOK_LABEL: Record<string, string> = {
  short: 'SHORT · 7–21d',
  medium: 'MED · 30–60d',
  long: 'LONG · 61–120d',
}

const STRATEGY_LABEL: Record<string, string> = {
  long_call: 'Long Call',
  long_put: 'Long Put',
  bull_call_spread: 'Bull Call Spread',
  bear_put_spread: 'Bear Put Spread',
  iron_condor: 'Iron Condor',
  short_strangle: 'Short Strangle',
  long_straddle: 'Long Straddle',
  long_strangle: 'Long Strangle',
}

function BiasChip({ bias }: { bias: string }) {
  const map: Record<string, string> = {
    bullish: 'bg-green-500/15 text-green-400 border-green-500/30',
    bearish: 'bg-red-500/15 text-red-400 border-red-500/30',
    neutral_high_iv: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
    neutral_low_iv: 'bg-blue-500/15 text-blue-400 border-blue-500/30',
  }
  const labels: Record<string, string> = {
    bullish: 'Bullish',
    bearish: 'Bearish',
    neutral_high_iv: 'Neutral · High IV',
    neutral_low_iv: 'Neutral · Low IV',
  }
  return (
    <span className={`px-2 py-0.5 rounded-md border text-xs font-medium ${map[bias] ?? 'bg-white/10 text-gray-400 border-white/10'}`}>
      {labels[bias] ?? bias}
    </span>
  )
}

function OutlookChip({ outlook }: { outlook: string }) {
  const map: Record<string, string> = {
    short: 'bg-purple-500/15 text-purple-300 border-purple-500/30',
    medium: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
    long: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30',
  }
  return (
    <span className={`px-2 py-0.5 rounded-md border text-xs font-mono ${map[outlook] ?? 'bg-white/10 text-gray-400 border-white/10'}`}>
      {OUTLOOK_LABEL[outlook] ?? outlook.toUpperCase()}
    </span>
  )
}

function fmt(n: number | null | undefined, prefix = '$') {
  if (n == null) return '—'
  return `${prefix}${n.toFixed(2)}`
}

// ── Opportunity card ──────────────────────────────────────────────────────────

function OpportunityCard({ opp }: { opp: OptionsOpportunity }) {
  const [showLegs, setShowLegs] = useState(false)

  return (
    <div className="rounded-xl border border-white/8 bg-white/3 p-4 flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap">
        <OutlookChip outlook={opp.outlook} />
        <span className="text-sm font-medium text-white">
          {STRATEGY_LABEL[opp.strategy] ?? opp.strategy}
        </span>
        <BiasChip bias={opp.bias} />
        <span className="ml-auto text-xs text-gray-500 font-mono">{opp.expiry} · {opp.dte}d</span>
      </div>

      {/* Trade levels */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-sm">
        <div>
          <p className="text-xs text-gray-500 mb-0.5">{opp.is_credit ? 'Credit recv.' : 'Debit paid'}</p>
          <p className="font-mono text-white">{fmt(opp.entry)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">{opp.is_credit ? 'Take-profit' : 'Target exit'}</p>
          <p className="font-mono text-green-400">{fmt(opp.exit_target)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Option stop</p>
          <p className="font-mono text-red-400">{fmt(opp.option_stop)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Underlying stop</p>
          <p className="font-mono text-red-400">{fmt(opp.underlying_stop)}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Max profit</p>
          <p className="font-mono text-green-300">{opp.max_profit != null ? fmt(opp.max_profit) : 'Unlimited'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Max loss</p>
          <p className="font-mono text-red-300">{opp.max_loss != null ? fmt(opp.max_loss) : 'Unlimited'}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">P(profit)</p>
          <p className="font-mono text-white">{opp.prob_profit.toFixed(1)}%</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">IV vs HV</p>
          <p className={`font-mono ${opp.iv_vs_hv > 10 ? 'text-yellow-400' : opp.iv_vs_hv < -10 ? 'text-blue-400' : 'text-gray-400'}`}>
            {opp.iv_vs_hv > 0 ? '+' : ''}{opp.iv_vs_hv.toFixed(1)}%
          </p>
        </div>
      </div>

      {/* Greeks row */}
      <div className="flex gap-4 text-xs font-mono text-gray-500 border-t border-white/6 pt-2">
        <span>Δ {opp.delta > 0 ? '+' : ''}{opp.delta.toFixed(3)}</span>
        <span>Θ ${opp.theta.toFixed(3)}/d</span>
        <span>ν {opp.vega.toFixed(3)}</span>
        <span>Γ {opp.gamma.toFixed(4)}</span>
      </div>

      {/* Legs toggle */}
      {opp.legs.length > 0 && (
        <div>
          <button
            onClick={() => setShowLegs((s) => !s)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            {showLegs ? '▲ Hide legs' : `▼ Show ${opp.legs.length} leg${opp.legs.length > 1 ? 's' : ''}`}
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
                    <th className="text-right px-3 py-1.5">Δ</th>
                  </tr>
                </thead>
                <tbody>
                  {opp.legs.map((leg, i) => (
                    <tr key={i} className="border-b border-white/5 last:border-0">
                      <td className={`px-3 py-1.5 font-semibold ${leg.action === 'buy' ? 'text-green-400' : 'text-red-400'}`}>
                        {leg.action.toUpperCase()}
                      </td>
                      <td className="px-3 py-1.5 text-gray-300">{leg.option_type.toUpperCase()}</td>
                      <td className="px-3 py-1.5 text-right text-gray-200">${leg.strike.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-gray-200">${leg.price.toFixed(2)}</td>
                      <td className="px-3 py-1.5 text-right text-gray-400">{leg.iv.toFixed(1)}%</td>
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

// ── Ticker result block ───────────────────────────────────────────────────────

function TickerBlock({ result }: { result: OptionsTickerResult }) {
  return (
    <div className="flex flex-col gap-3 animate-fade-in">
      {/* Ticker header */}
      <div className="flex items-baseline gap-3 border-b border-white/8 pb-3">
        <span className="text-lg font-bold text-white font-mono">{result.ticker}</span>
        {result.name && <span className="text-sm text-gray-400">{result.name}</span>}
        {result.sector && <span className="text-xs text-gray-600">{result.sector}</span>}
        {result.current_price != null && (
          <span className="ml-auto text-sm font-mono text-gray-300">${result.current_price.toFixed(2)}</span>
        )}
      </div>

      {result.error ? (
        <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {result.error}
        </p>
      ) : result.opportunities.length === 0 ? (
        <p className="text-sm text-gray-500">No opportunities found.</p>
      ) : (
        result.opportunities.map((opp, i) => <OpportunityCard key={i} opp={opp} />)
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

// ── Standalone content (embeddable as a tab) ─────────────────────────────────

export function OptionsContent() {
  const [input, setInput]         = useState('')
  const [includeAi, setIncludeAi] = useState(false)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [data, setData]           = useState<OptionsScanResponse | null>(null)

  async function handleScan() {
    const tickers = input
      .toUpperCase()
      .split(/[\s,]+/)
      .map((t) => t.trim())
      .filter(Boolean)

    if (tickers.length === 0) return

    setLoading(true)
    setError(null)
    setData(null)
    try {
      const result = await scanOptions(tickers, includeAi)
      setData(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed')
    } finally {
      setLoading(false)
    }
  }

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
            checked={includeAi}
            onChange={(e) => setIncludeAi(e.target.checked)}
            className="accent-blue-500"
          />
          AI narrative
        </label>
        <button
          onClick={handleScan}
          disabled={loading || !input.trim()}
          className="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium text-white transition-colors"
        >
          {loading ? 'Scanning…' : 'Scan'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm">
          ⚠ {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex flex-col gap-4">
          {[1, 2].map((i) => (
            <div key={i} className="rounded-xl border border-white/8 bg-white/3 p-4 animate-pulse">
              <div className="h-4 bg-white/10 rounded w-24 mb-3" />
              <div className="h-3 bg-white/5 rounded w-full mb-2" />
              <div className="h-3 bg-white/5 rounded w-3/4" />
            </div>
          ))}
        </div>
      )}

      {/* Results */}
      {data && !loading && (
        <div className="flex flex-col gap-8">
          {data.results.map((r) => (
            <TickerBlock key={r.ticker} result={r} />
          ))}
          {data.ai_narrative && (
            <div className="rounded-xl border border-white/8 bg-white/3 p-5 flex flex-col gap-3 animate-fade-in">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">AI Synthesis</p>
              <p className="text-sm text-gray-300 whitespace-pre-wrap leading-relaxed">{data.ai_narrative}</p>
            </div>
          )}
        </div>
      )}

      {/* Empty state */}
      {!loading && !data && !error && (
        <div className="flex flex-col items-center justify-center py-24 gap-3 text-center">
          <div className="text-5xl opacity-30">⚡</div>
          <p className="text-gray-500 text-sm">Enter one or more tickers to scan for options opportunities</p>
        </div>
      )}
    </div>
  )
}

// ── Standalone page (kept for direct /options route) ─────────────────────────

export default function OptionsPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-white/10 backdrop-blur-sm bg-black/30 px-5 sm:px-8 py-0 h-16 flex items-center justify-between sticky top-0 z-10">
        <Logo size="nav" />
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/')}
            className="hidden sm:block px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Analysis
          </button>
          <button
            onClick={() => navigate('/watchlist')}
            className="hidden sm:block px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Watchlist
          </button>
          <div className="hidden sm:block w-px h-5 bg-white/10 mx-1" />
          <span className="hidden sm:block text-sm text-gray-500 font-medium">{user?.username}</span>
          <button
            onClick={logout}
            className="px-3 py-1.5 text-xs font-medium rounded-lg border border-white/10 text-gray-400 hover:text-white hover:border-white/25 hover:bg-white/5 transition-all"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="flex-1 px-4 sm:px-6 py-6 flex flex-col gap-6 max-w-5xl w-full mx-auto">
        <div>
          <h1 className="text-xl font-semibold text-white mb-1">Options Scanner</h1>
          <p className="text-sm text-gray-500">Scan tickers for multi-leg options opportunities across short, medium, and long outlooks.</p>
        </div>
        <OptionsContent />
      </main>
    </div>
  )
}
