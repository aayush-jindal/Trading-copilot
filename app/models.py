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


class SupportResistance(BaseModel):
    high_52w: float
    low_52w: float
    distance_from_52w_high_pct: float
    distance_from_52w_low_pct: float
    swing_highs: list[float]
    swing_lows: list[float]
    nearest_resistance: float
    nearest_support: float
    distance_to_resistance_pct: float
    distance_to_support_pct: float


class CandlestickSignals(BaseModel):
    pattern: str
    pattern_type: str
    at_support: bool
    at_resistance: bool
    significance: str


class AnalysisResponse(BaseModel):
    ticker: str
    price: float
    trend: TrendSignals
    momentum: MomentumSignals
    volatility: VolatilitySignals
    volume: VolumeSignals
    support_resistance: SupportResistance
    candlestick: list[CandlestickSignals]
