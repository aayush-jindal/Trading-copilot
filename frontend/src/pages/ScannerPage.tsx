import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { scanWatchlist, unifiedScan } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'
import LoadingSkeleton from '../components/LoadingSkeleton'
import type { StrategyResult, StrategyType, Verdict, UnifiedSignal, UnifiedScanResponse } from '../types'

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

const SOURCE_CHIP = {
  equity:  { bg: 'bg-teal-500/15',   border: 'border-teal-500/30',   text: 'text-teal-300',   label: 'Equity' },
  options: { bg: 'bg-indigo-500/15',  border: 'border-indigo-500/30', text: 'text-indigo-300', label: 'Options' },
}

const IV_REGIME_STYLE: Record<string, string> = {
  LOW: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
  NORMAL: 'bg-white/5 text-gray-400 border-white/10',
  ELEVATED: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
  HIGH: 'bg-red-500/15 text-red-300 border-red-500/30',
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '\u2014'
  return `$${n.toFixed(2)}`
}

function convictionColor(c: number): string {
  if (c >= 80) return 'text-green-300'
  if (c >= 60) return 'text-green-400'
  if (c >= 30) return 'text-yellow-400'
  return 'text-gray-500'
}

// ── ScanRow — equity-only row (original) ────────────────────────────────────

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
          {result.ticker ?? '\u2014'}
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
            {' \u00B7 '}SL {fmt(result.risk.stop_loss)}
            {' \u00B7 '}T {fmt(result.risk.target)}
            {' \u00B7 '}R:R {result.risk.risk_reward.toFixed(2)}\u00D7
            {result.risk.position_size != null && ` \u00B7 ${result.risk.position_size}sh`}
          </span>
        )}
      </div>
    </div>
  )
}

// ── UnifiedRow — renders both equity and options signals ─────────────────────

function UnifiedRow({
  signal,
  onClick,
}: {
  signal: UnifiedSignal
  onClick: () => void
}) {
  const sourceCfg = SOURCE_CHIP[signal.signal_source]
  const isCorrelated = signal.signal_source === 'options'
    ? !!signal.correlated_equity_signal
    : !!signal.correlated_option_signal

  if (signal.signal_source === 'equity') {
    const typeCfg    = TYPE_CHIP[(signal.type as StrategyType) ?? 'trend'] ?? TYPE_CHIP.trend
    const verdictCfg = VERDICT_CHIP[(signal.verdict as Verdict) ?? 'NO_TRADE'] ?? VERDICT_CHIP.NO_TRADE

    return (
      <div
        onClick={onClick}
        className={`glass rounded-xl px-4 py-3 border cursor-pointer hover:border-blue-500/40 hover:bg-white/[0.04] transition-all ${isCorrelated ? 'border-green-500/25 bg-green-500/[0.02]' : 'border-white/10'}`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-base font-bold text-white w-16 flex-shrink-0">
            {signal.ticker ?? '\u2014'}
          </span>
          <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${sourceCfg.bg} ${sourceCfg.border} ${sourceCfg.text}`}>
            {sourceCfg.label}
          </span>
          <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${typeCfg.bg} ${typeCfg.border} ${typeCfg.text}`}>
            {typeCfg.label}
          </span>
          <span className="text-sm text-gray-400 font-mono flex-1 min-w-[100px]">
            {signal.name}
          </span>
          <span className="text-xs text-gray-500 flex-shrink-0 tabular-nums">
            {signal.score}<span className="text-gray-700">/100</span>
          </span>
          <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${verdictCfg.bg} ${verdictCfg.border} ${verdictCfg.text}`}>
            {signal.verdict}
          </span>
          {isCorrelated && (
            <span className="inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium bg-green-500/15 border-green-500/30 text-green-300">
              + Options
            </span>
          )}
          {signal.risk && (
            <span className="text-[11px] text-gray-500 font-mono flex-shrink-0 ml-auto">
              E {fmt(signal.risk.entry_price)}
              {' \u00B7 '}SL {fmt(signal.risk.stop_loss)}
              {' \u00B7 '}T {fmt(signal.risk.target)}
              {' \u00B7 '}R:R {signal.risk.risk_reward.toFixed(2)}\u00D7
            </span>
          )}
        </div>
      </div>
    )
  }

  // Options signal
  const ivStyle = IV_REGIME_STYLE[signal.iv_regime ?? 'NORMAL'] ?? IV_REGIME_STYLE.NORMAL

  return (
    <div
      onClick={onClick}
      className={`glass rounded-xl px-4 py-3 border cursor-pointer hover:border-blue-500/40 hover:bg-white/[0.04] transition-all ${isCorrelated ? 'border-green-500/25 bg-green-500/[0.02]' : 'border-white/10'}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-base font-bold text-white w-16 flex-shrink-0">
          {signal.ticker ?? '\u2014'}
        </span>
        <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${sourceCfg.bg} ${sourceCfg.border} ${sourceCfg.text}`}>
          {sourceCfg.label}
        </span>
        <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${signal.option_type === 'call' ? 'bg-green-500/10 text-green-400 border-green-500/20' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
          {signal.option_type?.toUpperCase()}
        </span>
        <span className={`px-1.5 py-0.5 rounded-md border text-[10px] font-medium ${ivStyle}`}>
          {signal.iv_regime}
        </span>
        <span className="text-sm text-gray-400 font-mono flex-1 min-w-[100px]">
          {signal.recommended_strategy?.label ?? `$${signal.strike?.toFixed(0)} ${signal.expiry}`}
        </span>
        <span className={`text-xs font-mono ${(signal.edge_pct ?? 0) > 0 ? 'text-green-400' : (signal.edge_pct ?? 0) < 0 ? 'text-red-400' : 'text-gray-400'}`}>
          edge {(signal.edge_pct ?? 0) > 0 ? '+' : ''}{signal.edge_pct?.toFixed(1)}%
        </span>
        <span className={`text-sm font-mono font-semibold ${convictionColor(signal.conviction ?? 0)}`}>
          {signal.conviction?.toFixed(0)}
        </span>
        {isCorrelated && (
          <span className="inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium bg-green-500/15 border-green-500/30 text-green-300">
            + {signal.correlated_equity_signal}
          </span>
        )}
        <span className="text-[11px] text-gray-500 font-mono flex-shrink-0">
          {signal.dte}d \u00B7 ${signal.spot?.toFixed(2)}
        </span>
      </div>

      {/* Hedge suggestion */}
      {signal.hedge_suggestion && (
        <div className="mt-2 px-3 py-2 rounded-lg border border-yellow-500/20 bg-yellow-500/5 text-xs text-yellow-300">
          {signal.hedge_suggestion}
        </div>
      )}
    </div>
  )
}

// ── ScannerPage ───────────────────────────────────────────────────────────────

type ScanMode = 'equity' | 'unified'

export default function ScannerPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()

  const [mode, setMode] = useState<ScanMode>('unified')
  const [results, setResults]       = useState<StrategyResult[]>([])
  const [unifiedData, setUnifiedData] = useState<UnifiedScanResponse | null>(null)
  const [isLoading, setIsLoading]   = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [lastRun, setLastRun]       = useState<Date | null>(null)

  async function runScan() {
    setIsLoading(true)
    setError(null)
    try {
      if (mode === 'unified') {
        const data = await unifiedScan(40)
        setUnifiedData(data)
        setResults([])
      } else {
        const data = await scanWatchlist()
        setResults(data)
        setUnifiedData(null)
      }
      setLastRun(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Scan failed')
    } finally {
      setIsLoading(false)
    }
  }

  // Run scan on mount and when mode changes
  useEffect(() => {
    runScan()
  }, [mode])

  // Sort equity results: ENTRY first, then by score descending
  const sortedEquity = [...results].sort((a, b) => {
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
            <div className="flex items-center gap-3 mt-1">
              {lastRun && (
                <p className="text-xs text-gray-500">
                  Last run: {lastRun.toLocaleTimeString()}
                </p>
              )}
              {mode === 'unified' && unifiedData && (
                <p className="text-xs text-gray-600">
                  {unifiedData.equity_count} equity + {unifiedData.options_count} options from {unifiedData.tickers_scanned} tickers
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Mode toggle */}
            <div className="flex rounded-lg border border-white/10 overflow-hidden">
              {(['equity', 'unified'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  disabled={isLoading}
                  className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                    mode === m
                      ? 'bg-white/10 text-white'
                      : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
                  }`}
                >
                  {m === 'equity' ? 'Equity' : 'Unified'}
                </button>
              ))}
            </div>

            <button
              onClick={runScan}
              disabled={isLoading}
              className="px-4 py-2 text-sm font-medium rounded-lg border border-blue-500/40 text-blue-300 bg-blue-500/10 hover:bg-blue-500/15 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              {isLoading ? 'Scanning\u2026' : 'Refresh'}
            </button>
          </div>
        </div>

        {/* Error banner */}
        {error && (
          <div className="animate-fade-in border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {/* Loading */}
        {isLoading && <LoadingSkeleton />}

        {/* Unified results */}
        {!isLoading && mode === 'unified' && unifiedData && unifiedData.signals.length > 0 && (
          <div className="flex flex-col gap-2 animate-fade-in">
            {unifiedData.signals.map((signal, i) => (
              <UnifiedRow
                key={`${signal.ticker}-${signal.signal_source}-${signal.name ?? signal.strike}-${i}`}
                signal={signal}
                onClick={() => handleRowClick(signal.ticker)}
              />
            ))}
          </div>
        )}

        {/* Equity-only results */}
        {!isLoading && mode === 'equity' && sortedEquity.length > 0 && (
          <div className="flex flex-col gap-2 animate-fade-in">
            {sortedEquity.map((result, i) => (
              <ScanRow
                key={`${result.ticker}-${result.name}-${i}`}
                result={result}
                onClick={() => handleRowClick(result.ticker)}
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && !error && (
          (mode === 'equity' && sortedEquity.length === 0) ||
          (mode === 'unified' && (!unifiedData || unifiedData.signals.length === 0))
        ) && (
          <div className="flex flex-col items-center justify-center flex-1 py-32 gap-4 animate-fade-in">
            <div className="text-5xl opacity-30">{'\uD83D\uDD0D'}</div>
            <p className="text-gray-500 text-sm">No strategy setups firing on your watchlist right now.</p>
            <p className="text-gray-600 text-xs">Add tickers to your watchlist or check back later.</p>
          </div>
        )}

      </main>
    </div>
  )
}
