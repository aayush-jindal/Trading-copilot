import type {
  AnalysisResponse,
  Notification,
  OptionsScanResponse,
  PriceHistoryResponse,
  WatchlistDashboardItem,
  WatchlistItem,
} from '../types'

const TOKEN_KEY = 'tc_token'

function authHeader(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(url, {
    ...init,
    headers: { ...authHeader(), ...(init.headers as Record<string, string> | undefined) },
  })
  if (res.status === 401) {
    localStorage.removeItem(TOKEN_KEY)
    window.location.href = '/login'
    // Return a never-resolving promise so callers don't continue processing
    return new Promise(() => {})
  }
  return res
}

// ── Price + Analysis ──────────────────────────────────────────────────────────

export async function fetchPrices(
  ticker: string,
  days = 365
): Promise<PriceHistoryResponse> {
  const res = await apiFetch(`/api/data/${encodeURIComponent(ticker)}/latest?days=${days}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error((detail as { detail?: string })?.detail ?? `Failed to fetch prices (${res.status})`)
  }
  return res.json()
}

export async function fetchAnalysis(ticker: string): Promise<AnalysisResponse> {
  const res = await apiFetch(`/api/analyze/${encodeURIComponent(ticker)}`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error((detail as { detail?: string })?.detail ?? `Failed to fetch analysis (${res.status})`)
  }
  return res.json()
}

// SSE via fetch so we can send Authorization header (EventSource doesn't support headers)
export function streamNarrative(
  ticker: string,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void
): () => void {
  const controller = new AbortController()
  const token = localStorage.getItem(TOKEN_KEY)

  // Safety net: if the server opens the connection but sends no data within 20s,
  // abort so the UI doesn't freeze indefinitely (e.g. mid-stream backend crash).
  let firstDataReceived = false
  const connectionTimeout = setTimeout(() => {
    if (!firstDataReceived) {
      controller.abort()
      onError('AI synthesis timed out — check that your API key is configured.')
    }
  }, 20_000)

  fetch(`/api/synthesize/${encodeURIComponent(ticker)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal: controller.signal,
  })
    .then(async (res) => {
      if (!res.ok || !res.body) {
        clearTimeout(connectionTimeout)
        // Parse the error detail from the JSON body (e.g. 503 "API key not set")
        const detail = await res.json().catch(() => ({}))
        const msg = (detail as { detail?: string })?.detail ?? `AI synthesis unavailable (${res.status})`
        onError(msg)
        return
      }
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        // Clear the connection timeout on first byte received
        if (!firstDataReceived) {
          firstDataReceived = true
          clearTimeout(connectionTimeout)
        }

        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE event blocks (separated by \n\n)
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          for (const line of block.split('\n')) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6)
              if (data === '[DONE]') {
                onDone()
                return
              }
              // [ERROR] prefix: backend caught an exception and sent it as an SSE event
              if (data.startsWith('[ERROR]')) {
                onError(data.slice(7).trim() || 'AI synthesis failed')
                return
              }
              onChunk(data)
            }
          }
        }
      }
      clearTimeout(connectionTimeout)
      onDone()
    })
    .catch((err: unknown) => {
      clearTimeout(connectionTimeout)
      if (err instanceof Error && err.name !== 'AbortError') {
        onError('Narrative stream disconnected')
      }
    })

  return () => {
    clearTimeout(connectionTimeout)
    controller.abort()
  }
}

export async function fetchKnowledgeStrategies(
  ticker: string
): Promise<{ ticker: string; strategies: string }> {
  const res = await apiFetch(`/api/analyze/${encodeURIComponent(ticker)}/knowledge-strategies`)
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(
      (detail as { detail?: string })?.detail ?? `Knowledge strategies unavailable (${res.status})`
    )
  }
  return res.json()
}

// ── Options scanner ───────────────────────────────────────────────────────────

export async function scanOptions(
  tickers: string[],
  includeAi = false
): Promise<OptionsScanResponse> {
  const res = await apiFetch('/api/options/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tickers, include_ai: includeAi }),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error((detail as { detail?: string })?.detail ?? `Options scan failed (${res.status})`)
  }
  return res.json()
}

// ── Watchlist ─────────────────────────────────────────────────────────────────

export async function getWatchlist(): Promise<WatchlistItem[]> {
  const res = await apiFetch('/api/watchlist')
  if (!res.ok) throw new Error('Failed to fetch watchlist')
  return res.json()
}

export async function addToWatchlist(ticker: string): Promise<void> {
  const res = await apiFetch(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: 'POST' })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error((detail as { detail?: string })?.detail ?? 'Failed to add to watchlist')
  }
}

export async function removeFromWatchlist(ticker: string): Promise<void> {
  const res = await apiFetch(`/api/watchlist/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to remove from watchlist')
}

export async function getWatchlistDashboard(): Promise<WatchlistDashboardItem[]> {
  const res = await apiFetch('/api/watchlist/dashboard')
  if (!res.ok) throw new Error('Failed to fetch watchlist dashboard')
  return res.json()
}

// ── Notifications ─────────────────────────────────────────────────────────────

export async function getNotifications(): Promise<Notification[]> {
  const res = await apiFetch('/api/notifications')
  if (!res.ok) throw new Error('Failed to fetch notifications')
  return res.json()
}

export async function markAllNotificationsRead(): Promise<void> {
  await apiFetch('/api/notifications/read-all', { method: 'PATCH' })
}
