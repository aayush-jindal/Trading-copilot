import type { Condition, RiskLevels, StrategyResult, StrategyType, Verdict } from '../types'

interface Props {
  result: StrategyResult
  onLogTrade?: () => void
}

// Color scheme per strategy type — dark theme matching SwingSetupPanel
const TYPE_CONFIG: Record<StrategyType, { label: string; bg: string; border: string; text: string }> = {
  trend:     { label: 'Trend',     bg: 'bg-teal-500/15',   border: 'border-teal-500/30',   text: 'text-teal-300' },
  reversion: { label: 'Reversion', bg: 'bg-purple-500/15', border: 'border-purple-500/30', text: 'text-purple-300' },
  breakout:  { label: 'Breakout',  bg: 'bg-amber-500/15',  border: 'border-amber-500/30',  text: 'text-amber-300' },
  rotation:  { label: 'Rotation',  bg: 'bg-blue-500/15',   border: 'border-blue-500/30',   text: 'text-blue-300' },
}

const VERDICT_CONFIG: Record<
  Verdict,
  { bg: string; border: string; text: string; dot: string; label: string; pulse: boolean }
> = {
  ENTRY:    { bg: 'bg-green-500/15',  border: 'border-green-500/30',  text: 'text-green-300',  dot: 'bg-green-400',  label: 'Entry Signal', pulse: true },
  WATCH:    { bg: 'bg-yellow-500/15', border: 'border-yellow-500/30', text: 'text-yellow-300', dot: 'bg-yellow-400', label: 'Watch Setup',  pulse: false },
  NO_TRADE: { bg: 'bg-white/5',       border: 'border-white/10',       text: 'text-gray-400',   dot: 'bg-gray-500',   label: 'No Trade',    pulse: false },
}

function fmt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return `$${n.toFixed(2)}`
}

function ConditionRow({ cond }: { cond: Condition }) {
  return (
    <div className="flex items-start gap-2 text-sm py-0.5">
      <span className={`mt-0.5 flex-shrink-0 font-bold ${cond.passed ? 'text-green-400' : 'text-red-500/70'}`}>
        {cond.passed ? '✓' : '✗'}
      </span>
      <span className={cond.passed ? 'text-gray-200' : 'text-gray-500 line-through decoration-gray-600'}>
        {cond.label}
      </span>
      <span className="ml-auto text-[11px] text-gray-500 font-mono flex-shrink-0 pl-2">
        {cond.value}
      </span>
    </div>
  )
}

function RiskPanel({ risk, rrColor }: { risk: RiskLevels; rrColor: string }) {
  return (
    <>
      {/* Entry zone — only when both bounds are present */}
      {risk.entry_zone_low != null && risk.entry_zone_high != null && (
        <div className="flex items-center justify-between gap-2 py-0.5">
          <span className="text-[11px] text-gray-500">Entry zone</span>
          <span className="text-sm font-mono font-semibold text-gray-200">
            {fmt(risk.entry_zone_low)} – {fmt(risk.entry_zone_high)}
          </span>
        </div>
      )}
      <div className="flex items-center justify-between gap-2 py-0.5">
        <span className="text-[11px] text-gray-500">Stop loss</span>
        <span className="text-sm font-mono font-semibold text-red-400">{fmt(risk.stop_loss)}</span>
      </div>
      <div className="flex items-center justify-between gap-2 py-0.5">
        <span className="text-[11px] text-gray-500">Target</span>
        <span className="text-sm font-mono font-semibold text-green-400">{fmt(risk.target)}</span>
      </div>
      <div className="flex items-center justify-between gap-2 py-0.5">
        <span className="text-[11px] text-gray-500">R:R</span>
        <span className={`text-sm font-mono font-semibold ${rrColor}`}>
          {risk.risk_reward.toFixed(2)}×
        </span>
      </div>
      {/* ATR — only when present */}
      {risk.atr != null && (
        <div className="flex items-center justify-between gap-2 py-0.5">
          <span className="text-[11px] text-gray-500">ATR</span>
          <span className="text-sm font-mono font-semibold text-gray-200">{fmt(risk.atr)}</span>
        </div>
      )}
      {/* Position size — only when present */}
      {risk.position_size != null && (
        <div className="flex items-center justify-between gap-2 py-0.5">
          <span className="text-[11px] text-gray-500">Position size</span>
          <span className="text-sm font-mono font-semibold text-gray-200">{risk.position_size} shares</span>
        </div>
      )}
    </>
  )
}

export default function StrategyPanel({ result, onLogTrade }: Props) {
  const { name, type, verdict, score, conditions, risk } = result

  const typeCfg    = TYPE_CONFIG[type as StrategyType]    ?? TYPE_CONFIG.trend
  const verdictCfg = VERDICT_CONFIG[verdict as Verdict] ?? VERDICT_CONFIG.NO_TRADE

  const scoreColor =
    score >= 70 ? 'bg-green-500' :
    score >= 50 ? 'bg-yellow-500' :
    'bg-gray-600'

  const rrColor =
    (risk?.risk_reward ?? 0) >= 2 ? 'text-green-400' :
    (risk?.risk_reward ?? 0) >= 1 ? 'text-yellow-400' :
    'text-red-400'

  return (
    <div className="glass-hover animate-fade-in overflow-hidden">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">
            {name}
          </span>
          <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${typeCfg.bg} ${typeCfg.border} ${typeCfg.text}`}>
            {typeCfg.label}
          </span>
        </div>

        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border ${verdictCfg.bg} ${verdictCfg.border}`}>
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${verdictCfg.dot} ${verdictCfg.pulse ? 'animate-pulse' : ''}`} />
          <span className={`text-[11px] font-semibold ${verdictCfg.text}`}>{verdictCfg.label}</span>
        </div>
      </div>

      {/* ── Score bar ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <span className="text-[10px] text-gray-600 uppercase tracking-wider flex-shrink-0">Score</span>
        <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${scoreColor}`}
            style={{ width: `${score}%` }}
          />
        </div>
        <span className={`text-xs font-mono font-bold tabular-nums ${verdictCfg.text}`}>
          {score}<span className="text-gray-600 font-normal">/100</span>
        </span>
      </div>

      {/* ── Body: two-column grid ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-white/5">

        {/* Left: conditions list */}
        <div className="px-4 pt-3 pb-4 flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-2">
            Conditions
          </span>
          {conditions.map((cond, i) => (
            <ConditionRow key={i} cond={cond} />
          ))}
        </div>

        {/* Right: risk levels */}
        <div className="px-4 pt-3 pb-4 flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-2">
            Risk Levels
          </span>

          {risk ? (
            <RiskPanel risk={risk} rrColor={rrColor} />
          ) : (
            <span className="text-[11px] text-gray-600 italic">No risk data available</span>
          )}

          {/* Log Trade button — only for ENTRY verdict when callback is provided */}
          {verdict === 'ENTRY' && onLogTrade != null && (
            <button
              onClick={onLogTrade}
              className={`mt-3 w-full py-1.5 rounded text-[12px] font-semibold border ${typeCfg.bg} ${typeCfg.border} ${typeCfg.text} hover:brightness-110 transition-all`}
            >
              Log Trade
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
