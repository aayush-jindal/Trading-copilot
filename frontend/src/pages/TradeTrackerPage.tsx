import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { closeTrade, fetchOpenTrades, logTrade } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'
import type { OpenTrade } from '../types'

// ── Strategy dropdown data ────────────────────────────────────────────────────

// The six validated strategy names are known at build time; auto-populate type.
const STRATEGIES: { name: string; type: string }[] = [
  { name: 'S1_TrendPullback',      type: 'trend' },
  { name: 'S2_RSIMeanReversion',   type: 'reversion' },
  { name: 'S3_BBSqueeze',          type: 'breakout' },
  { name: 'S7_MACDCross',          type: 'trend' },
  { name: 'S8_StochasticCross',    type: 'reversion' },
  { name: 'S9_EMACross',           type: 'trend' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function rColor(r: number | null | undefined): string {
  if (r == null) return 'text-gray-400'
  return r >= 0 ? 'text-green-400' : 'text-red-400'
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return `$${n.toFixed(2)}`
}

// ── AlertBadge ────────────────────────────────────────────────────────────────

function AlertBadge({ alert }: { alert: string | null | undefined }) {
  if (!alert) return <span className="text-gray-700">—</span>
  if (alert === 'APPROACHING_STOP') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full border bg-amber-500/15 border-amber-500/30 text-amber-300 font-medium">
        ⚠ Stop
      </span>
    )
  }
  if (alert === 'AT_TARGET') {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full border bg-green-500/15 border-green-500/30 text-green-300 font-medium">
        ✓ Target
      </span>
    )
  }
  return <span className="text-[11px] text-gray-500">{alert}</span>
}

// ── TradeTable ────────────────────────────────────────────────────────────────

function TradeTable({
  trades,
  onClose,
}: {
  trades: OpenTrade[]
  onClose: (id: number) => void
}) {
  if (trades.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 gap-3 animate-fade-in">
        <div className="text-5xl opacity-30">📋</div>
        <p className="text-gray-500 text-sm">No open trades. Log one below.</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto animate-fade-in">
      <table className="w-full text-sm border-separate border-spacing-y-1">
        <thead>
          <tr className="text-[10px] text-gray-600 uppercase tracking-wider">
            <th className="text-left px-3 py-1">Ticker</th>
            <th className="text-left px-3 py-1">Strategy</th>
            <th className="text-right px-3 py-1">Entry</th>
            <th className="text-right px-3 py-1">Stop</th>
            <th className="text-right px-3 py-1">Target</th>
            <th className="text-right px-3 py-1">Shares</th>
            <th className="text-right px-3 py-1">R:R</th>
            <th className="text-right px-3 py-1">Current R</th>
            <th className="text-center px-3 py-1">Alert</th>
            <th className="text-center px-3 py-1">Action</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((trade) => (
            <tr
              key={trade.id}
              className="glass rounded-xl border border-white/10 hover:border-white/20 transition-all"
            >
              <td className="px-3 py-2.5 font-mono font-bold text-white rounded-l-xl">{trade.ticker}</td>
              <td className="px-3 py-2.5 text-gray-400 font-mono text-xs">{trade.strategy_name}</td>
              <td className="px-3 py-2.5 text-right font-mono text-gray-200">{fmt(trade.entry_price)}</td>
              <td className="px-3 py-2.5 text-right font-mono text-red-400">{fmt(trade.stop_loss)}</td>
              <td className="px-3 py-2.5 text-right font-mono text-green-400">{fmt(trade.target)}</td>
              <td className="px-3 py-2.5 text-right font-mono text-gray-400">{trade.shares}</td>
              <td className="px-3 py-2.5 text-right font-mono text-gray-400">
                {trade.risk_reward != null ? `${trade.risk_reward.toFixed(2)}×` : '—'}
              </td>
              <td className={`px-3 py-2.5 text-right font-mono font-semibold tabular-nums ${rColor(trade.current_r)}`}>
                {trade.current_r != null ? `${trade.current_r.toFixed(2)}R` : '—'}
              </td>
              <td className="px-3 py-2.5 text-center">
                <AlertBadge alert={trade.exit_alert} />
              </td>
              <td className="px-3 py-2.5 text-center rounded-r-xl">
                <button
                  onClick={() => onClose(trade.id)}
                  className="px-2.5 py-1 text-xs rounded-lg border border-white/10 text-gray-500 hover:text-red-400 hover:border-red-500/30 transition-all"
                >
                  Close
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── LogTradeForm ──────────────────────────────────────────────────────────────

interface FormState {
  ticker: string
  strategy_name: string
  strategy_type: string
  entry_price: string
  stop_loss: string
  target: string
  shares: string
}

const EMPTY_FORM: FormState = {
  ticker: '',
  strategy_name: '',
  strategy_type: '',
  entry_price: '',
  stop_loss: '',
  target: '',
  shares: '',
}

function LogTradeForm({ onLogged }: { onLogged: () => void }) {
  const [form, setForm]       = useState<FormState>(EMPTY_FORM)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  function handleStrategyChange(name: string) {
    const found = STRATEGIES.find((s) => s.name === name)
    setForm((f) => ({ ...f, strategy_name: name, strategy_type: found?.type ?? '' }))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const payload = {
      ticker: form.ticker.trim().toUpperCase(),
      strategy_name: form.strategy_name,
      strategy_type: form.strategy_type,
      entry_price: parseFloat(form.entry_price),
      stop_loss:   parseFloat(form.stop_loss),
      target:      parseFloat(form.target),
      shares:      parseInt(form.shares, 10),
    }
    if (!payload.ticker || !payload.strategy_name) {
      setError('Ticker and strategy are required.')
      return
    }
    if ([payload.entry_price, payload.stop_loss, payload.target, payload.shares].some(isNaN)) {
      setError('Entry, stop, target, and shares must be valid numbers.')
      return
    }
    setIsLoading(true)
    try {
      await logTrade(payload)
      setForm(EMPTY_FORM)
      onLogged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to log trade')
    } finally {
      setIsLoading(false)
    }
  }

  const inputCls = 'w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500/50 transition-colors'
  const labelCls = 'block text-[11px] text-gray-500 uppercase tracking-wide mb-1'

  return (
    <div className="glass rounded-2xl p-5 border border-white/10">
      <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">Log Trade</h2>

      {error && (
        <div className="mb-3 border border-red-500/30 bg-red-500/10 text-red-300 rounded-lg px-3 py-2 text-xs">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Ticker */}
          <div>
            <label className={labelCls}>Ticker</label>
            <input
              className={inputCls}
              placeholder="SPY"
              value={form.ticker}
              onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value }))}
            />
          </div>

          {/* Strategy dropdown — auto-populates strategy_type */}
          <div className="col-span-2 sm:col-span-1 lg:col-span-2">
            <label className={labelCls}>Strategy</label>
            <select
              className={`${inputCls} cursor-pointer`}
              value={form.strategy_name}
              onChange={(e) => handleStrategyChange(e.target.value)}
            >
              <option value="">Select…</option>
              {STRATEGIES.map((s) => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Entry */}
          <div>
            <label className={labelCls}>Entry</label>
            <input
              className={inputCls}
              type="number"
              step="0.01"
              placeholder="0.00"
              value={form.entry_price}
              onChange={(e) => setForm((f) => ({ ...f, entry_price: e.target.value }))}
            />
          </div>

          {/* Stop */}
          <div>
            <label className={labelCls}>Stop</label>
            <input
              className={inputCls}
              type="number"
              step="0.01"
              placeholder="0.00"
              value={form.stop_loss}
              onChange={(e) => setForm((f) => ({ ...f, stop_loss: e.target.value }))}
            />
          </div>

          {/* Target */}
          <div>
            <label className={labelCls}>Target</label>
            <input
              className={inputCls}
              type="number"
              step="0.01"
              placeholder="0.00"
              value={form.target}
              onChange={(e) => setForm((f) => ({ ...f, target: e.target.value }))}
            />
          </div>

          {/* Shares */}
          <div>
            <label className={labelCls}>Shares</label>
            <input
              className={inputCls}
              type="number"
              min="1"
              placeholder="10"
              value={form.shares}
              onChange={(e) => setForm((f) => ({ ...f, shares: e.target.value }))}
            />
          </div>
        </div>

        <div className="mt-4 flex justify-end">
          <button
            type="submit"
            disabled={isLoading}
            className="px-5 py-2 text-sm font-semibold rounded-lg border border-blue-500/40 text-blue-300 bg-blue-500/10 hover:bg-blue-500/15 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {isLoading ? 'Logging…' : 'Log Trade'}
          </button>
        </div>
      </form>
    </div>
  )
}

// ── TradeTrackerPage ──────────────────────────────────────────────────────────

export default function TradeTrackerPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()

  const [trades, setTrades]       = useState<OpenTrade[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError]         = useState<string | null>(null)
  const [closing, setClosing]     = useState<number | null>(null)

  async function loadTrades() {
    setIsLoading(true)
    setError(null)
    try {
      setTrades(await fetchOpenTrades())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trades')
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    loadTrades()
  }, [])

  async function handleClose(id: number) {
    setClosing(id)
    try {
      await closeTrade(id)
      // Re-fetch from server — source of truth, no optimistic filtering
      await loadTrades()
    } catch {
      // silently ignore close errors
    } finally {
      setClosing(null)
    }
  }

  const tradesForTable = closing != null
    ? trades.filter((t) => t.id !== closing)
    : trades

  return (
    <div className="min-h-screen flex flex-col">

      {/* Header */}
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
          <button
            onClick={() => navigate('/scanner')}
            className="hidden sm:block px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Scanner
          </button>

          <div className="hidden sm:block w-px h-5 bg-white/10 mx-1" />

          <div className="flex items-center gap-2 pl-2 ml-1 border-l border-white/10">
            <span className="hidden sm:block text-sm text-gray-500 font-medium">{user?.username}</span>
            <button
              onClick={logout}
              className="px-3 py-1.5 text-xs font-medium rounded-lg border border-white/10 text-gray-400 hover:text-white hover:border-white/25 hover:bg-white/5 transition-all"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 px-4 sm:px-6 py-5 flex flex-col gap-4 max-w-7xl w-full mx-auto">

        <h1 className="text-xl font-bold text-white">Trade Tracker</h1>

        {/* Error banner */}
        {error && (
          <div className="animate-fade-in border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm">
            ⚠ {error}
          </div>
        )}

        {/* Open trades table */}
        <div className="glass rounded-2xl p-5 border border-white/10">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Open Trades
            {trades.length > 0 && (
              <span className="ml-2 text-gray-600 font-normal normal-case">({trades.length})</span>
            )}
          </h2>
          {isLoading ? (
            <div className="py-8 text-center text-sm text-gray-600">Loading trades…</div>
          ) : (
            <TradeTable trades={tradesForTable} onClose={handleClose} />
          )}
        </div>

        {/* Log trade form */}
        <LogTradeForm onLogged={loadTrades} />

      </main>
    </div>
  )
}
