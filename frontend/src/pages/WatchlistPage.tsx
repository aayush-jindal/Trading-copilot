import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { addToWatchlist, getWatchlistDashboard, removeFromWatchlist } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Logo from '../components/Logo'
import type { WatchlistDashboardItem } from '../types'

// ── Helpers ───────────────────────────────────────────────────────────────────

function trendColor(signal: string) {
  const s = signal.toLowerCase()
  if (s.includes('bull') || s === 'strong_uptrend' || s === 'uptrend')
    return 'text-green-400 bg-green-500/10 border-green-500/20'
  if (s.includes('bear') || s === 'strong_downtrend' || s === 'downtrend')
    return 'text-red-400 bg-red-500/10 border-red-500/20'
  return 'text-gray-400 bg-white/5 border-white/10'
}

function trendLabel(signal: string) {
  return signal.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

// ── WatchlistCard ─────────────────────────────────────────────────────────────

interface WatchlistCardProps {
  item: WatchlistDashboardItem
  onRemove: (ticker: string) => void
  onNavigate: (ticker: string) => void
}

function WatchlistCard({ item, onRemove, onNavigate }: WatchlistCardProps) {
  const [removing, setRemoving] = useState(false)
  const isPositive = item.day_change >= 0

  async function handleRemove(e: React.MouseEvent) {
    e.stopPropagation()
    setRemoving(true)
    try {
      await removeFromWatchlist(item.ticker_symbol)
      onRemove(item.ticker_symbol)
    } catch {
      setRemoving(false)
    }
  }

  return (
    <div
      onClick={() => onNavigate(item.ticker_symbol)}
      className="glass rounded-2xl p-5 border border-white/10 cursor-pointer hover:border-blue-500/40 hover:bg-white/[0.04] transition-all group"
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="font-mono text-lg font-bold text-white">{item.ticker_symbol}</div>
          {item.company_name && (
            <div className="text-xs text-gray-500 mt-0.5 truncate max-w-[160px]">{item.company_name}</div>
          )}
        </div>
        <button
          onClick={handleRemove}
          disabled={removing}
          className="opacity-0 group-hover:opacity-100 px-2 py-1 text-xs rounded-lg border border-white/10 text-gray-500 hover:text-red-400 hover:border-red-500/30 disabled:opacity-30 transition-all"
        >
          Remove
        </button>
      </div>

      <div className="flex items-end justify-between">
        <div>
          <div className="text-2xl font-semibold text-white tabular-nums">
            ${item.price.toFixed(2)}
          </div>
          <div className={`text-sm tabular-nums mt-0.5 ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '▲' : '▼'}{' '}
            {Math.abs(item.day_change).toFixed(2)} ({Math.abs(item.day_change_pct).toFixed(2)}%)
          </div>
        </div>
        <span className={`text-xs px-2 py-1 rounded-full border font-medium ${trendColor(item.trend_signal)}`}>
          {trendLabel(item.trend_signal)}
        </span>
      </div>
    </div>
  )
}

// ── AddTickerModal ────────────────────────────────────────────────────────────

interface AddTickerModalProps {
  onClose: () => void
  onAdded: (items: WatchlistDashboardItem[]) => void
}

function AddTickerModal({ onClose, onAdded }: AddTickerModalProps) {
  const [ticker, setTicker] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // Focus input and close on Escape
  useEffect(() => {
    inputRef.current?.focus()
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  async function handleAdd() {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return
    setError(null)
    setIsLoading(true)
    try {
      await addToWatchlist(symbol)
      // Refresh full dashboard so new item has price + signals
      const updated = await getWatchlistDashboard()
      onAdded(updated)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add ticker')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
        <div className="pointer-events-auto w-full max-w-sm glass rounded-2xl p-7 border border-white/15 shadow-2xl animate-fade-in">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-base font-semibold text-white">Add to Watchlist</h3>
              <p className="text-xs text-gray-500 mt-0.5">Enter a ticker symbol</p>
            </div>
            <button
              onClick={onClose}
              className="text-gray-500 hover:text-white transition-colors text-lg leading-none p-1"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          <div className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
              placeholder="AAPL"
              maxLength={10}
              className="
                flex-1 px-4 py-3 rounded-xl bg-white/5 border border-white/15
                text-gray-100 placeholder-gray-600 text-sm font-mono uppercase
                focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/20
                hover:border-white/25 transition-all
              "
            />
            <button
              onClick={handleAdd}
              disabled={isLoading || !ticker.trim()}
              className="px-5 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-500/20"
            >
              {isLoading ? '…' : 'Add'}
            </button>
          </div>

          {error && (
            <p className="mt-3 text-sm text-red-400 flex items-center gap-2">
              <span>⚠</span> {error}
            </p>
          )}
        </div>
      </div>
    </>
  )
}

// ── WatchlistPage ─────────────────────────────────────────────────────────────

export default function WatchlistPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()
  const [items, setItems] = useState<WatchlistDashboardItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Add ticker modal state — no navigation needed
  const [showAddModal, setShowAddModal] = useState(false)

  useEffect(() => {
    getWatchlistDashboard()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load watchlist'))
      .finally(() => setIsLoading(false))
  }, [])

  function handleRemove(ticker: string) {
    setItems((prev) => prev.filter((i) => i.ticker_symbol !== ticker))
  }

  function handleNavigate(ticker: string) {
    navigate(`/?ticker=${ticker}`)
  }

  return (
    <div className="min-h-screen flex flex-col">

      {/* Header — matches AnalysisPage height/padding */}
      <header className="border-b border-white/10 backdrop-blur-sm bg-black/30 px-5 sm:px-8 py-0 h-16 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="hover:opacity-80 transition-opacity" aria-label="Home">
            <Logo size="nav" />
          </button>
          <div className="hidden sm:flex items-center gap-2 text-gray-600">
            <span>/</span>
            <span className="text-sm text-gray-400 font-medium">Watchlist</span>
          </div>
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          <button
            onClick={() => navigate('/')}
            className="px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Analysis
          </button>
          <div className="hidden sm:block w-px h-5 bg-white/10 mx-1" />
          <div className="flex items-center gap-2 pl-1">
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

      {/* Main */}
      <main className="flex-1 px-4 sm:px-8 py-7 max-w-7xl w-full mx-auto">

        {/* Page title row */}
        <div className="flex items-center justify-between mb-7">
          <div>
            <h1 className="text-xl font-bold text-white">Your Watchlist</h1>
            {!isLoading && items.length > 0 && (
              <p className="text-xs text-gray-500 mt-0.5">{items.length} ticker{items.length !== 1 ? 's' : ''}</p>
            )}
          </div>
          {/* FIX: opens modal instead of navigating away */}
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-xl bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white transition-all shadow-lg shadow-blue-500/20"
          >
            <span className="text-base leading-none">+</span>
            Add ticker
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm mb-6">
            ⚠ {error}
          </div>
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="glass rounded-2xl h-36 animate-pulse opacity-40" />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && items.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-32 gap-5">
            <div className="text-5xl opacity-20">👁</div>
            <div className="text-center">
              <p className="text-gray-400 font-medium">Your watchlist is empty</p>
              <p className="text-gray-600 text-sm mt-1">Add tickers to track them here</p>
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="mt-1 px-5 py-2.5 text-sm font-semibold rounded-xl bg-blue-600 hover:bg-blue-500 text-white transition-all shadow-lg shadow-blue-500/20"
            >
              + Add your first ticker
            </button>
          </div>
        )}

        {/* Grid */}
        {!isLoading && items.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {items.map((item) => (
              <WatchlistCard
                key={item.ticker_symbol}
                item={item}
                onRemove={handleRemove}
                onNavigate={handleNavigate}
              />
            ))}
          </div>
        )}
      </main>

      {/* Add ticker modal — inline, no navigation */}
      {showAddModal && (
        <AddTickerModal
          onClose={() => setShowAddModal(false)}
          onAdded={setItems}
        />
      )}
    </div>
  )
}
