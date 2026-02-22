export interface PriceBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  adj_close: number
  volume: number
}

export interface TickerInfo {
  symbol: string
  company_name: string | null
  sector: string | null
  market_cap: number | null
}

export interface PriceHistoryResponse {
  ticker: TickerInfo
  prices: PriceBar[]
  count: number
  source: string
}

export interface TrendSignals {
  sma_20: number | null
  sma_50: number | null
  sma_200: number | null
  ema_9: number | null
  ema_21: number | null
  price_vs_sma20: string
  price_vs_sma50: string
  price_vs_sma200: string
  distance_from_sma20_pct: number | null
  distance_from_sma50_pct: number | null
  distance_from_sma200_pct: number | null
  golden_cross: boolean
  death_cross: boolean
  signal: string
}

export interface MomentumSignals {
  rsi: number | null
  rsi_signal: string
  macd: number | null
  macd_signal: number | null      // MACD signal line (numeric)
  macd_histogram: number | null
  macd_crossover: string          // "none" | "bullish" | "bearish"
  stochastic_k: number | null
  stochastic_d: number | null
  stochastic_signal: string
  signal: string
}

export interface VolatilitySignals {
  bb_upper: number | null
  bb_middle: number | null
  bb_lower: number | null
  bb_width: number | null
  bb_position: number | null      // 0–100 scale
  bb_squeeze: boolean
  atr: number | null
  atr_vs_price_pct: number | null
  signal: string
}

export interface VolumeSignals {
  current_volume: number
  avg_volume_20d: number
  volume_ratio: number | null
  volume_signal: string
  obv: number | null
  obv_trend: string
}

export interface SupportResistance {
  high_52w: number
  low_52w: number
  distance_from_52w_high_pct: number
  distance_from_52w_low_pct: number
  swing_highs: number[]
  swing_lows: number[]
  nearest_resistance: number
  nearest_support: number
  distance_to_resistance_pct: number
  distance_to_support_pct: number
}

export interface CandlestickSignal {
  pattern: string
  pattern_type: string
  at_support: boolean
  at_resistance: boolean
  significance: string
}

export interface AnalysisResponse {
  ticker: string
  price: number
  trend: TrendSignals
  momentum: MomentumSignals
  volatility: VolatilitySignals
  volume: VolumeSignals
  support_resistance: SupportResistance
  candlestick: CandlestickSignal[]
}

export interface AuthResponse {
  access_token: string
  token_type: string
}

export interface WatchlistItem {
  ticker_symbol: string
  date_added: string
}

export interface WatchlistDashboardItem {
  ticker_symbol: string
  company_name: string | null
  price: number
  day_change: number
  day_change_pct: number
  trend_signal: string
}

export interface DigestEntry {
  ticker: string
  summary: string
}

export interface DigestContent {
  date: string
  entries: DigestEntry[]
}

export interface Notification {
  id: number
  content: DigestContent
  created_at: string
  is_read: boolean
}
