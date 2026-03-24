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

export interface WeeklyTrend {
  weekly_trend: string                // "BULLISH" | "BEARISH" | "NEUTRAL"
  weekly_sma10: number | null
  weekly_sma40: number | null
  price_vs_weekly_sma10: string
  price_vs_weekly_sma40: string
  weekly_sma10_vs_sma40: string
  weekly_trend_strength: string       // "STRONG" | "MODERATE" | "WEAK"
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

export interface SwingLevel {
  price: number
  strength: string  // "HIGH" | "MEDIUM" | "LOW"
}

export interface SupportResistance {
  high_52w: number
  low_52w: number
  distance_from_52w_high_pct: number
  distance_from_52w_low_pct: number
  swing_highs: SwingLevel[]
  swing_lows: SwingLevel[]
  nearest_resistance: number
  nearest_support: number
  distance_to_resistance_pct: number
  distance_to_support_pct: number
  support_strength: string    // "HIGH" | "MEDIUM" | "LOW"
  resistance_strength: string // "HIGH" | "MEDIUM" | "LOW"
  support_is_provisional: boolean
  resistance_is_provisional: boolean
  provisional_support: number | null
  provisional_resistance: number | null
}

export interface CandlestickSignal {
  pattern: string
  pattern_type: string
  at_support: boolean
  at_resistance: boolean
  significance: string
}

export interface ReversalCandle {
  pattern: string
  bars_ago: number
  raw_value: number
  strength: 'normal' | 'strong'
}

export interface ReversalCandleCondition {
  found: boolean
  patterns: ReversalCandle[]
}

export interface SwingConditions {
  uptrend_confirmed: boolean
  weekly_trend_aligned: boolean
  adx: number
  adx_strong: boolean
  rsi: number
  rsi_cooldown: number
  rsi_pullback_label: string
  pullback_rsi_ok: boolean
  near_support: boolean
  near_resistance: boolean
  volume_ratio: number
  volume_declining: boolean
  obv_trend: string
  reversal_candle: ReversalCandleCondition
  trigger_ok: boolean
  trigger_price: number
  trigger_volume_ok: boolean
  trigger_bar_strength_ok: boolean
  trigger_points: number
  trigger_label: 'strong' | 'moderate' | 'weak' | 'not_fired'
  rr_ratio: number | null
  rr_label: 'good' | 'marginal' | 'poor' | 'bad' | 'unavailable'
  rr_gate_pass: boolean
  rr_warning: string | null
}

export interface SwingLevels {
  nearest_support: number
  nearest_resistance: number
  sr_alignment: string
  support_is_provisional: boolean
  resistance_is_provisional: boolean
}

export interface EntryZone {
  low: number
  high: number
}

export interface SwingRisk {
  atr14: number
  entry_zone: EntryZone
  stop_loss: number
  target: number
  rr_ratio: number | null
  rr_to_resistance: number | null
}

export interface SwingSetup {
  setup_type: string
  verdict: 'ENTRY' | 'WATCH' | 'NO_TRADE'
  setup_score: number
  weekly_trend_warning: string | null
  conditions: SwingConditions
  levels: SwingLevels
  risk: SwingRisk
  reasons: string[]
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
  swing_setup: SwingSetup | null
  weekly_trend: WeeklyTrend | null
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

// Player / Backtester types
export interface ChartCandle {
  time: string
  open: number
  high: number
  low: number
  close: number
}

export interface ChartMarkerEntry {
  type: 'entry'
  time: string
  verdict: 'ENTRY' | 'WATCH' | 'NO_TRADE'
  score: number
  price?: number | null
  rr_ratio?: number | null
}

export interface ChartMarkerExit {
  type: 'exit'
  time: string
  outcome: 'WIN' | 'LOSS' | 'EXPIRED'
  price?: number | null
  return_pct: number
  days_to_outcome?: number | null
}

export type ChartMarker = ChartMarkerEntry | ChartMarkerExit

export interface MarkerTooltipData {
  marker: ChartMarker
  runId: string
  runLabel: string
  runColour: string
}

export interface PnLPoint {
  time: string
  value: number
}

export interface BacktestRun {
  run_id: string
  ticker: string
  run_label: string
  total_signals: number
  entry_signal_count: number
  win_rate_entry: number
  win_rate_watch: number
  expected_value: number
  avg_mae: number
  avg_mfe: number
  avg_days_to_outcome: number
  fixed_pnl: number
  compound_pnl: number
  compound_final_pot: number
}

export interface BacktestSignal {
  run_id: string
  signal_date: string
  verdict: 'ENTRY' | 'WATCH' | 'NO_TRADE'
  setup_score: number
  rr_ratio: number | null
  support_strength: string | null
  outcome: 'WIN' | 'LOSS' | 'EXPIRED'
  outcome_date: string | null
  return_pct: number | null
  mae: number | null
  mfe: number | null
  days_to_outcome: number | null
  uptrend_confirmed: boolean
  weekly_trend_aligned: boolean
  near_support: boolean
  reversal_found: boolean
  trigger_ok: boolean
  four_h_confirmed: boolean
  entry_price: number | null
  stop_loss: number | null
  target: number | null
  exit_price: number | null
  trade_pnl_fixed?: number
  running_pnl_fixed?: number
  trade_pnl_compound?: number
  running_pnl_compound?: number
  running_pot?: number
}

export interface RunMarkersResponse {
  run_id: string
  markers: ChartMarker[]
  pnl_series?: PnLPoint[]
  pnl_series_fixed?: PnLPoint[]
  pnl_series_compound?: PnLPoint[]
  final_pnl?: number
  total_trades?: number
}
