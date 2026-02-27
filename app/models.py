from pydantic import BaseModel


class TickerInfo(BaseModel):
    symbol: str
    company_name: str | None = None
    sector: str | None = None
    market_cap: float | None = None


class PriceBar(BaseModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    adj_close: float | None = None
    volume: int | None = None


class PriceHistoryResponse(BaseModel):
    ticker: TickerInfo
    prices: list[PriceBar]
    count: int
    source: str  # "cache" or "fetched"


# ── TA Engine Response Models ──


class TrendSignals(BaseModel):
    sma_20: float | None = None
    sma_50: float | None = None
    sma_200: float | None = None
    ema_9: float | None = None
    ema_21: float | None = None
    price_vs_sma20: str
    price_vs_sma50: str
    price_vs_sma200: str
    distance_from_sma20_pct: float | None = None
    distance_from_sma50_pct: float | None = None
    distance_from_sma200_pct: float | None = None
    golden_cross: bool
    death_cross: bool
    signal: str


class MomentumSignals(BaseModel):
    rsi: float | None = None
    rsi_signal: str
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    macd_crossover: str
    stochastic_k: float | None = None
    stochastic_d: float | None = None
    stochastic_signal: str
    signal: str


class VolatilitySignals(BaseModel):
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    bb_width: float | None = None
    bb_position: float | None = None
    bb_squeeze: bool
    atr: float | None = None
    atr_vs_price_pct: float | None = None
    signal: str


class VolumeSignals(BaseModel):
    current_volume: int
    avg_volume_20d: int
    volume_ratio: float | None = None
    volume_signal: str
    obv: int | None = None
    obv_trend: str


class WeeklyTrend(BaseModel):
    weekly_trend: str                       # "BULLISH" | "BEARISH" | "NEUTRAL"
    weekly_sma10: float | None = None
    weekly_sma40: float | None = None
    price_vs_weekly_sma10: str
    price_vs_weekly_sma40: str
    weekly_sma10_vs_sma40: str
    weekly_trend_strength: str              # "STRONG" | "MODERATE" | "WEAK"


class SwingLevel(BaseModel):
    price: float
    strength: str  # "HIGH" | "MEDIUM" | "LOW"


class SupportResistance(BaseModel):
    high_52w: float
    low_52w: float
    distance_from_52w_high_pct: float
    distance_from_52w_low_pct: float
    swing_highs: list[SwingLevel]
    swing_lows: list[SwingLevel]
    nearest_resistance: float
    nearest_support: float
    distance_to_resistance_pct: float
    distance_to_support_pct: float
    support_strength: str       # "HIGH" | "MEDIUM" | "LOW"
    resistance_strength: str    # "HIGH" | "MEDIUM" | "LOW"


class CandlestickSignals(BaseModel):
    pattern: str
    pattern_type: str
    at_support: bool
    at_resistance: bool
    significance: str


class ReversalCandle(BaseModel):
    pattern: str
    bars_ago: int
    raw_value: int
    strength: str  # "normal" | "strong"


class ReversalCandleCondition(BaseModel):
    found: bool
    patterns: list[ReversalCandle]


class SwingConditions(BaseModel):
    uptrend_confirmed: bool
    weekly_trend_aligned: bool = False
    adx: float
    adx_strong: bool
    rsi: float
    rsi_cooldown: float = 0.0
    rsi_pullback_label: str = "no_pullback"
    pullback_rsi_ok: bool
    near_support: bool
    near_resistance: bool
    volume_ratio: float
    volume_declining: bool
    obv_trend: str
    reversal_candle: ReversalCandleCondition
    trigger_ok: bool


class SwingLevels(BaseModel):
    nearest_support: float
    nearest_resistance: float
    sr_alignment: str  # "aligned" | "misaligned" | "neutral"


class EntryZone(BaseModel):
    low: float
    high: float


class SwingRisk(BaseModel):
    atr14: float
    entry_zone: EntryZone
    stop_loss: float
    target: float
    rr_to_resistance: float | None = None


class SwingSetup(BaseModel):
    setup_type: str
    verdict: str  # "ENTRY" | "WATCH" | "NO_TRADE"
    setup_score: int
    weekly_trend_warning: str | None = None
    conditions: SwingConditions
    levels: SwingLevels
    risk: SwingRisk
    reasons: list[str]


class AnalysisResponse(BaseModel):
    ticker: str
    price: float
    trend: TrendSignals
    momentum: MomentumSignals
    volatility: VolatilitySignals
    volume: VolumeSignals
    support_resistance: SupportResistance
    candlestick: list[CandlestickSignals]
    swing_setup: SwingSetup | None = None
    weekly_trend: WeeklyTrend | None = None
