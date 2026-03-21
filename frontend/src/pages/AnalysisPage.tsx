import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  addToWatchlist,
  fetchAnalysis,
  fetchKnowledgeStrategies,
  fetchPrices,
  fetchStrategies,
  getNotifications,
  getWatchlist,
  removeFromWatchlist,
  streamNarrative,
} from '../api/client'
import Logo from '../components/Logo'
import NotificationsPanel from '../components/NotificationsPanel'
import SearchBar from '../components/SearchBar'
import PriceChart from '../components/PriceChart'
import SignalPanel from '../components/SignalPanel'
import SwingSetupPanel from '../components/SwingSetupPanel'
import StrategyPanel from '../components/StrategyPanel'
import NarrativePanel from '../components/NarrativePanel'
import BookStrategiesPanel, { type BookStrategiesData } from '../components/BookStrategiesPanel'
import TickerCard from '../components/TickerCard'
import LoadingSkeleton from '../components/LoadingSkeleton'
import { useAuth } from '../context/AuthContext'
import { OptionsContent } from './OptionsPage'
import type { AnalysisResponse, PriceBar, StrategyResult, TickerInfo } from '../types'

const DEFAULT_DAYS = 365

const HISTORY_KEY = 'tc_history'
const MAX_HISTORY = 5

function loadHistory(): string[] {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? '[]')
  } catch {
    return []
  }
}

function saveHistory(ticker: string, prev: string[]): string[] {
  const updated = [ticker, ...prev.filter((t) => t !== ticker)].slice(0, MAX_HISTORY)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(updated))
  return updated
}

export default function AnalysisPage() {
  const { logout, user } = useAuth()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const [currentTicker, setCurrentTicker] = useState<string | null>(null)
  const [tickerInfo, setTickerInfo]       = useState<TickerInfo | null>(null)
  const [prices, setPrices]               = useState<PriceBar[]>([])
  const [analysis, setAnalysis]           = useState<AnalysisResponse | null>(null)
  const [narrative, setNarrative]         = useState('')
  const [isLoading, setIsLoading]               = useState(false)
  const [isStreaming, setIsStreaming]            = useState(false)
  const [error, setError]                       = useState<string | null>(null)
  const [strategies, setStrategies]             = useState<StrategyResult[]>([])
  const [activeStrategyIdx, setActiveStrategyIdx] = useState(0)
  const [bookStrategies, setBookStrategies]     = useState<BookStrategiesData | null>(null)
  const [isLoadingBook, setIsLoadingBook]       = useState(false)
  const [bookError, setBookError]               = useState<string | null>(null)
  const [history, setHistory]             = useState<string[]>(loadHistory)
  const [days, setDays]                   = useState(DEFAULT_DAYS)

  // Watchlist state
  const [watchlistSet, setWatchlistSet]   = useState<Set<string>>(new Set())
  const [watchlistLoading, setWatchlistLoading] = useState(false)

  // Notifications state
  const [showNotifications, setShowNotifications] = useState(false)
  const [unreadCount, setUnreadCount]     = useState(0)

  // Tab state
  const [activeTab, setActiveTab] = useState<'analysis' | 'options'>('analysis')

  const closeStreamRef = useRef<(() => void) | null>(null)

  // Load watchlist + unread count on mount
  useEffect(() => {
    getWatchlist()
      .then((items) => setWatchlistSet(new Set(items.map((i) => i.ticker_symbol))))
      .catch(() => {})

    getNotifications()
      .then((items) => setUnreadCount(items.filter((n) => !n.is_read).length))
      .catch(() => {})
  }, [])

  // Handle ?ticker= deep-link from watchlist page
  useEffect(() => {
    const ticker = searchParams.get('ticker')
    if (ticker) {
      handleSearch(ticker.toUpperCase())
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // only on mount

  async function handleDaysChange(newDays: number) {
    if (!currentTicker || newDays === days) return
    setDays(newDays)
    setPrices([])
    try {
      const priceRes = await fetchPrices(currentTicker, newDays + 200)
      setTickerInfo(priceRes.ticker)
      setPrices(priceRes.prices)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
    }
  }

  async function handleSearch(ticker: string) {
    closeStreamRef.current?.()
    closeStreamRef.current = null

    setCurrentTicker(ticker)
    setTickerInfo(null)
    setPrices([])
    setAnalysis(null)
    setStrategies([])
    setActiveStrategyIdx(0)
    setNarrative('')
    setError(null)
    setIsLoading(true)
    setIsStreaming(false)
    setBookStrategies(null)
    setBookError(null)
    setIsLoadingBook(false)

    try {
      const [priceRes, analysisRes, strategiesData] = await Promise.all([
        fetchPrices(ticker, days + 200),
        fetchAnalysis(ticker),
        // fetchStrategies is in the same Promise.all so it fires with the same
        // ticker context — prevents stale strategies from a previous search showing
        // alongside analysis from a new one. Failures silently return [].
        fetchStrategies(ticker).catch(() => [] as StrategyResult[]),
      ])
      setTickerInfo(priceRes.ticker)
      setPrices(priceRes.prices)
      setAnalysis(analysisRes)
      setStrategies(strategiesData)
      setHistory((prev) => saveHistory(ticker, prev))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data')
      setIsLoading(false)
      return
    }

    setIsLoading(false)
    setIsStreaming(true)

    closeStreamRef.current = streamNarrative(
      ticker,
      (chunk) => setNarrative((n) => n + chunk),
      () => {
        setIsStreaming(false)
        closeStreamRef.current = null
      },
      (err) => {
        setError(err)
        setIsStreaming(false)
        closeStreamRef.current = null
      }
    )
  }

  async function handleWatchlistToggle() {
    if (!currentTicker) return
    setWatchlistLoading(true)
    try {
      if (watchlistSet.has(currentTicker)) {
        await removeFromWatchlist(currentTicker)
        setWatchlistSet((prev) => {
          const next = new Set(prev)
          next.delete(currentTicker)
          return next
        })
      } else {
        await addToWatchlist(currentTicker)
        setWatchlistSet((prev) => new Set(prev).add(currentTicker))
      }
    } catch {
      // Silently ignore — watchlist state remains unchanged
    } finally {
      setWatchlistLoading(false)
    }
  }

  async function handleGenerateBook() {
    if (!currentTicker) return
    setIsLoadingBook(true)
    setBookError(null)
    fetchKnowledgeStrategies(currentTicker)
      .then((res) => setBookStrategies(res.strategies))
      .catch((err) => setBookError(err instanceof Error ? err.message : 'Failed to load book strategies'))
      .finally(() => setIsLoadingBook(false))
  }

  const isWatched = currentTicker ? watchlistSet.has(currentTicker) : false

  // Compute day change from last 2 price bars
  const dayChange    = prices.length >= 2 ? prices[prices.length - 1].close - prices[prices.length - 2].close : 0
  const dayChangePct = prices.length >= 2 ? (dayChange / prices[prices.length - 2].close) * 100 : 0

  const showContent = !isLoading && prices.length > 0

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-white/10 backdrop-blur-sm bg-black/30 px-5 sm:px-8 py-0 h-16 flex items-center justify-between sticky top-0 z-10">
        <Logo size="nav" />

        <div className="flex items-center gap-1 sm:gap-2">
          <SearchBar
            onSearch={handleSearch}
            disabled={isLoading}
            history={history}
          />

          {/* Watchlist toggle button — only when a ticker is loaded */}
          {currentTicker && (
            <button
              onClick={handleWatchlistToggle}
              disabled={watchlistLoading}
              className={`
                hidden sm:flex items-center gap-1.5 px-3.5 py-2 rounded-lg border text-sm font-medium transition-all
                ${isWatched
                  ? 'border-green-500/40 text-green-400 bg-green-500/10 hover:bg-red-500/10 hover:text-red-400 hover:border-red-500/40'
                  : 'border-white/15 text-gray-400 hover:text-white hover:border-blue-500/40 hover:bg-blue-500/10'
                }
                disabled:opacity-40 disabled:cursor-not-allowed
              `}
            >
              {isWatched ? (
                <><span className="text-xs">✓</span> Watching</>
              ) : (
                <><span className="text-base leading-none">+</span> Watchlist</>
              )}
            </button>
          )}

          {/* Watchlist page nav */}
          <button
            onClick={() => navigate('/watchlist')}
            className="hidden sm:block px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Watchlist
          </button>
          <button
            onClick={() => navigate('/player')}
            className="hidden sm:block px-3.5 py-2 text-sm text-gray-400 hover:text-white font-medium rounded-lg hover:bg-white/5 transition-all"
          >
            Backtester
          </button>
          {/* Divider */}
          <div className="hidden sm:block w-px h-5 bg-white/10 mx-1" />

          {/* Notifications bell */}
          <button
            onClick={() => setShowNotifications(true)}
            className="relative p-2 text-gray-400 hover:text-white rounded-lg hover:bg-white/5 transition-all"
            aria-label="Notifications"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7}
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 min-w-[16px] h-4 px-1 rounded-full bg-blue-500 text-white text-[10px] font-bold flex items-center justify-center leading-none">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {/* User chip + sign-out */}
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

        {/* Tab bar */}
        <div className="flex gap-1 border-b border-white/8 pb-0">
          {(['analysis', 'options'] as const).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all capitalize -mb-px border-b-2 ${
                activeTab === tab
                  ? 'text-white border-blue-500'
                  : 'text-gray-500 border-transparent hover:text-gray-300 hover:border-white/20'
              }`}
            >
              {tab === 'analysis' ? 'Analysis' : 'Options Scanner'}
            </button>
          ))}
        </div>

        {/* Options tab */}
        {activeTab === 'options' && <OptionsContent />}

        {/* Analysis tab */}
        {activeTab === 'analysis' && <>

        {/* Error banner */}
        {error && (
          <div className="animate-fade-in border border-red-500/30 bg-red-500/10 text-red-300 rounded-xl px-4 py-3 text-sm">
            ⚠ {error}
          </div>
        )}

        {/* Loading skeleton */}
        {isLoading && <LoadingSkeleton />}

        {/* Content panels — all fade in together */}
        {showContent && (
          <>
            {/* Ticker identity card */}
            {tickerInfo && (
              <TickerCard
                info={tickerInfo}
                price={analysis?.price ?? prices[prices.length - 1].close}
                dayChange={dayChange}
                dayChangePct={dayChangePct}
              />
            )}

            {/* Chart */}
            <div className="animate-fade-in [animation-delay:50ms]">
              <PriceChart prices={prices} days={days} onDaysChange={handleDaysChange} ticker={currentTicker ?? undefined} />
            </div>

            {/* Signal grid */}
            <div className="[animation-delay:100ms]">
              {analysis && <SignalPanel analysis={analysis} />}
            </div>

            {/* Swing setup */}
            {analysis?.swing_setup && (
              <div className="[animation-delay:125ms]">
                <SwingSetupPanel
                  setup={analysis.swing_setup}
                  supportStrength={analysis.support_resistance.support_strength}
                  resistanceStrength={analysis.support_resistance.resistance_strength}
                />
              </div>
            )}

            {/* Strategy tabs — sorted ENTRY first, then by score descending */}
            {strategies.length > 0 && (() => {
              const sorted = [...strategies].sort((a, b) => {
                if (a.verdict === 'ENTRY' && b.verdict !== 'ENTRY') return -1
                if (b.verdict === 'ENTRY' && a.verdict !== 'ENTRY') return 1
                return b.score - a.score
              })
              const safeIdx = Math.min(activeStrategyIdx, sorted.length - 1)
              const active  = sorted[safeIdx]

              return (
                <div className="flex flex-col gap-0 [animation-delay:140ms]">
                  {/* Tab row */}
                  <div className="flex gap-1 overflow-x-auto pb-0 scrollbar-none border-b border-white/8">
                    {sorted.map((s, i) => {
                      const isActive = i === safeIdx
                      const tabColor =
                        s.verdict === 'ENTRY'
                          ? isActive
                            ? 'border-green-400 text-green-300 bg-green-500/10'
                            : 'border-transparent text-green-500/60 hover:text-green-300 hover:border-green-500/40'
                          : s.verdict === 'WATCH'
                          ? isActive
                            ? 'border-yellow-400 text-yellow-300 bg-yellow-500/10'
                            : 'border-transparent text-yellow-500/50 hover:text-yellow-300 hover:border-yellow-500/40'
                          : isActive
                          ? 'border-white/30 text-gray-300 bg-white/5'
                          : 'border-transparent text-gray-600 hover:text-gray-400 hover:border-white/20'

                      return (
                        <button
                          key={s.name}
                          onClick={() => setActiveStrategyIdx(i)}
                          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-all whitespace-nowrap flex-shrink-0 rounded-t-md ${tabColor}`}
                        >
                          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                            s.verdict === 'ENTRY' ? 'bg-green-400' :
                            s.verdict === 'WATCH' ? 'bg-yellow-400' : 'bg-gray-500'
                          }`} />
                          {s.name.replace(/^S\d+_/, '')}
                          <span className="text-[10px] opacity-50 tabular-nums">{s.score}</span>
                        </button>
                      )
                    })}
                  </div>

                  {/* Active panel */}
                  <StrategyPanel result={active} />
                </div>
              )
            })()}

            {/* Narrative */}
            <div className="[animation-delay:150ms]">
              {(analysis || isStreaming || narrative) && (
                <NarrativePanel narrative={narrative} isStreaming={isStreaming} />
              )}
            </div>

            {/* Book Strategies */}
            <div className="[animation-delay:175ms]">
              {!bookStrategies && !isLoadingBook && !bookError && (
                <button
                  onClick={handleGenerateBook}
                  className="w-full py-3 rounded-xl border border-amber-500/20 bg-amber-500/5 text-amber-400/80 text-sm font-medium hover:bg-amber-500/10 hover:text-amber-300 hover:border-amber-500/40 transition-all"
                >
                  📚 Generate book analysis
                </button>
              )}
              {(isLoadingBook || bookStrategies || bookError) && (
                <BookStrategiesPanel
                  strategies={bookStrategies}
                  isLoading={isLoadingBook}
                  error={bookError}
                />
              )}
            </div>
          </>
        )}

        {/* Empty state */}
        {!isLoading && !showContent && !error && (
          <div className="flex flex-col items-center justify-center flex-1 py-32 gap-4 animate-fade-in">
            <div className="text-6xl opacity-30">📈</div>
            <p className="text-gray-500 text-sm">Enter a ticker symbol above to get started</p>
            {history.length > 0 && (
              <div className="flex items-center gap-2 flex-wrap justify-center mt-2">
                <span className="text-xs text-gray-600">Recent:</span>
                {history.map((t) => (
                  <button
                    key={t}
                    onClick={() => handleSearch(t)}
                    className="px-3 py-1 text-sm rounded-lg glass-hover text-gray-400 hover:text-white font-mono transition-all"
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        </>}
      </main>

      {/* Notifications slide-out panel */}
      {showNotifications && (
        <NotificationsPanel
          onClose={() => setShowNotifications(false)}
          onUnreadChange={setUnreadCount}
        />
      )}
    </div>
  )
}
