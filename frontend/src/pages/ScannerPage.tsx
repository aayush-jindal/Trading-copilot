import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { scanWatchlist } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'
import LoadingSkeleton from '../components/LoadingSkeleton'
import type { StrategyResult, StrategyType, Verdict } from '../types'

// ── Color helpers ──────────────────────────────────────────────────────────────

const TYPE_CHIP: Record<StrategyType, { bg: string; border: string; text: string; label: string }> = {
  trend:     { bg: 'bg-teal-500/15',   border: 'border-teal-500/30',   text: 'text-teal-300',   label: 'Trend' },
  reversion: { bg: 'bg-purple-500/15', border: 'border-purple-500/30', text: 'text-purple-300', label: 'Reversion' },
  breakout:  { bg: 'bg-amber-500/15',  border: 'border-amber-500/30',  text: 'text-amber-300',  label: 'Breakout' },
  rotation:  { bg: 'bg-blue-500/15',   border: 'border-blue-500/30',   text: 'text-blue-300',   label: 'Rotation' },
}

const VERDICT_CHIP: Record<Verdict, { bg: string; border: string; text: string }> = {
  ENTRY:    { bg: 'bg-green-500/15',  border: 'border-green-500/30',  text: 'text-green-300' },
  WATCH:    { bg: 'bg-yellow-500/15', border: 'border-yellow-500/30', text: 'text-yellow-300' },
  NO_TRADE: { bg: 'bg-white/5',       border: 'border-white/10',       text: 'text-gray-400' },
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '—'
  return `$${n.toFixed(2)}`
}

// ── ScanRow — compact single-line result ─────────────────────────────────────

function ScanRow({
  result,
  onClick,
}: {
  result: StrategyResult
  onClick: () => void
}) {
  const typeCfg    = TYPE_CHIP[result.type as StrategyType]    ?? TYPE_CHIP.trend
  const verdictCfg = VERDICT_CHIP[result.verdict as Verdict] ?? VERDICT_CHIP.NO_TRADE

  return (
    <div
      onClick={onClick}
      className="glass rounded-xl px-4 py-3 border border-white/10 cursor-pointer hover:border-blue-500/40 hover:bg-white/[0.04] transition-all"
    >
      <div className="flex flex-wrap items-center gap-2">

        {/* Ticker */}
        <span className="font-mono text-base font-bold text-white w-16 flex-shrink-0">
          {result.ticker ?? '—'}
        </span>

        {/* Strategy type chip */}
        <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${typeCfg.bg} ${typeCfg.border} ${typeCfg.text}`}>
          {typeCfg.label}
        </span>

        {/* Strategy name */}
        <span className="text-sm text-gray-400 font-mono flex-1 min-w-[120px]">
          {result.name}
        </span>

        {/* Score */}
        <span className="text-xs text-gray-500 flex-shrink-0 tabular-nums">
          {result.score}<span className="text-gray-700">/100</span>
        </span>

        {/* Verdict badge */}
        <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${verdictCfg.bg} ${verdictCfg.border} ${verdictCfg.text}`}>
          {result.verdict}
        </span>

        {/* Risk levels — shown only when risk is present */}
        {result.risk && (
          <span className="text-[11px] text-gray-500 font-mono flex-shrink-0 ml-auto">
            E {fmt(result.risk.entry_price)}
            {' · '}SL {fmt(result.risk.stop_loss)}
            {' · '}T {fmt(result.risk.target)}
            {' · '}R:R {result.risk.risk_reward.toFixed(2)}×
            {result.risk.position_size != null && ` · ${result.risk.position_size}sh`}
          </span>
        )}
      </div>
    </div>
  )
}

// ── ScannerPage ───────────────────────────────────────────────────────────────

export default function ScannerPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()

  const [results, setResults]       = useState<StrategyResult[]>([])
  const [isLoading, setIsLoading]   = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [lastRun, setLastRun]       = useState<Date | null>(null)

  async function runScan() {
    setIsLoading(true)
    setError(null)
    try {
      const data = await scanWatchlist()
      setResults(data)
      setLastRun(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed')
    } finally {
      setIsLoading(false)
    }
  }

  // Run scan on mount
  useEffect(() => {
    runScan()
  }, [])

  // Sort: ENTRY first, then by score descending
  const sorted = [...results].sort((a, b) => {
    if (a.verdict === 'ENTRY' && b.verdict !== 'ENTRY') return -1
    if (b.verdict === 'ENTRY' && a.verdict !== 'ENTRY') return 1
    return b.score - a.score
  })

  function handleRowClick(ticker: string | null | undefined) {
    if (!ticker) return
    navigate(`/?ticker=${encodeURIComponent(ticker)}`)
  }

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
            onClick={() => navigate('/trades')}
            className="hidden sm:block px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Trades
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

        {/* Page header */}
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-bold text-white">Morning Scan</h1>
            {lastRun && (
              <p className="text-xs text-gray-500 mt-0.5">
                Last run: {lastRun.toLocaleTimeString()}
              </p>
            )}
          </div>
          <button
            onClick={runScan}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium rounded-lg border border-blue-500/40 text-blue-300 bg-blue-500/10 hover:bg-blue-500/15 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {isLoading ? 'Scanning…' : 'Refresh'}
          </button>
        </div>

        {/* Error banner */}
        {error && (
          <div className="animate-fade-in border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm">
            ⚠ {error}
          </div>
        )}

        {/* Loading — /scan/watchlist can take 5–10s; skeleton keeps UI responsive */}
        {isLoading && <LoadingSkeleton />}

        {/* Results list */}
        {!isLoading && sorted.length > 0 && (
          <div className="flex flex-col gap-2 animate-fade-in">
            {sorted.map((result, i) => (
              <ScanRow
                key={`${result.ticker}-${result.name}-${i}`}
                result={result}
                onClick={() => handleRowClick(result.ticker)}
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && sorted.length === 0 && (
          <div className="flex flex-col items-center justify-center flex-1 py-32 gap-4 animate-fade-in">
            <div className="text-5xl opacity-30">🔍</div>
            <p className="text-gray-500 text-sm">No strategy setups firing on your watchlist right now.</p>
            <p className="text-gray-600 text-xs">Add tickers to your watchlist or check back later.</p>
          </div>
        )}

      </main>
    </div>
  )
}
