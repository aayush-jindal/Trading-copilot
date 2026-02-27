import type { SwingSetup } from '../types'

interface Props {
  setup: SwingSetup
  supportStrength?: string
  resistanceStrength?: string
}

const STRENGTH_STYLES: Record<string, string> = {
  HIGH:   'bg-green-500/15 text-green-300 border-green-500/25',
  MEDIUM: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/25',
  LOW:    'bg-white/5 text-gray-400 border-white/10',
}

function StrengthBadge({ strength }: { strength: string }) {
  const cls = STRENGTH_STYLES[strength] ?? STRENGTH_STYLES.LOW
  return (
    <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${cls}`}>
      {strength}
    </span>
  )
}

const VERDICT_CONFIG = {
  ENTRY: {
    bg: 'bg-green-500/15',
    border: 'border-green-500/30',
    text: 'text-green-300',
    dot: 'bg-green-400',
    label: 'Entry Signal',
    pulse: true,
  },
  WATCH: {
    bg: 'bg-yellow-500/15',
    border: 'border-yellow-500/30',
    text: 'text-yellow-300',
    dot: 'bg-yellow-400',
    label: 'Watch Setup',
    pulse: false,
  },
  NO_TRADE: {
    bg: 'bg-white/5',
    border: 'border-white/10',
    text: 'text-gray-400',
    dot: 'bg-gray-500',
    label: 'No Trade',
    pulse: false,
  },
} satisfies Record<string, { bg: string; border: string; text: string; dot: string; label: string; pulse: boolean }>

function ConditionRow({
  label,
  pass,
  detail,
  badge,
}: {
  label: string
  pass: boolean
  detail?: string
  badge?: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-2 text-sm py-0.5">
      <span className={`mt-0.5 flex-shrink-0 font-bold ${pass ? 'text-green-400' : 'text-red-500/70'}`}>
        {pass ? '✓' : '✗'}
      </span>
      <span className={pass ? 'text-gray-200' : 'text-gray-500 line-through decoration-gray-600'}>
        {label}
      </span>
      {badge && <span className="mt-0.5">{badge}</span>}
      {detail && (
        <span className="ml-auto text-[11px] text-gray-500 font-mono flex-shrink-0 pl-2">
          {detail}
        </span>
      )}
    </div>
  )
}

function RiskRow({
  label,
  value,
  color = 'text-gray-200',
  badge,
}: {
  label: string
  value: string
  color?: string
  badge?: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[11px] text-gray-500">{label}</span>
      <div className="flex items-center gap-1.5">
        {badge}
        <span className={`text-sm font-mono font-semibold ${color}`}>{value}</span>
      </div>
    </div>
  )
}

function fmt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return '—'
  return `$${n.toFixed(2)}`
}

export default function SwingSetupPanel({ setup, supportStrength, resistanceStrength }: Props) {
  const { verdict, setup_score, conditions, risk, levels } = setup
  const cfg = VERDICT_CONFIG[verdict] ?? VERDICT_CONFIG.NO_TRADE

  const scoreColor =
    setup_score >= 70 ? 'bg-green-500' :
    setup_score >= 55 ? 'bg-yellow-500' :
    'bg-gray-600'

  const rrColor =
    (risk.rr_to_resistance ?? 0) >= 2 ? 'text-green-400' :
    (risk.rr_to_resistance ?? 0) >= 1 ? 'text-yellow-400' :
    'text-red-400'

  const srColor =
    levels.sr_alignment === 'aligned' ? 'text-green-400' :
    levels.sr_alignment === 'misaligned' ? 'text-red-400' :
    'text-gray-400'

  const TRIGGER_LABEL_MAP: Record<string, string> = {
    strong: 'strong',
    moderate: 'moderate',
    weak: 'weak',
    not_fired: 'not fired',
  }
  const triggerStrength = TRIGGER_LABEL_MAP[conditions.trigger_label] ?? 'weak'

  const bestPattern = conditions.reversal_candle.patterns[0]
  const patternLabel = bestPattern
    ? `${bestPattern.pattern.replace(/_/g, ' ')} · ${bestPattern.bars_ago === 0 ? 'today' : `${bestPattern.bars_ago}d ago`}`
    : 'Reversal candle'

  const triggerLabel = conditions.trigger_ok
    ? `Trigger fired · ${triggerStrength}`
    : (
      Number.isFinite(conditions.trigger_price)
        ? `Trigger — close above ${fmt(conditions.trigger_price)}`
        : 'Trigger — price breakout'
    )

  const triggerDetail = conditions.trigger_ok
    ? (() => {
        const parts: string[] = []
        if (conditions.trigger_volume_ok) {
          parts.push('vol ≥ 20d avg')
        } else {
          parts.push('vol < 20d avg')
        }
        if (conditions.trigger_bar_strength_ok) {
          parts.push('close in upper half')
        } else {
          parts.push('weak close location')
        }
        return parts.join(' · ')
      })()
    : 'waiting for breakout'

  return (
    <div className="glass-hover animate-fade-in [animation-delay:125ms] overflow-hidden">

      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-widest">
            Swing Setup
          </span>
          <span className="text-[10px] text-gray-700">· Pullback in Uptrend</span>
        </div>

        <div className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border ${cfg.bg} ${cfg.border}`}>
          <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${cfg.dot} ${cfg.pulse ? 'animate-pulse' : ''}`} />
          <span className={`text-[11px] font-semibold ${cfg.text}`}>{cfg.label}</span>
        </div>
      </div>

      {/* ── Score bar ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 pt-3 pb-2">
        <span className="text-[10px] text-gray-600 uppercase tracking-wider flex-shrink-0">Score</span>
        <div className="flex-1 h-1 rounded-full bg-white/5 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${scoreColor}`}
            style={{ width: `${setup_score}%` }}
          />
        </div>
        <span className={`text-xs font-mono font-bold tabular-nums ${cfg.text}`}>
          {setup_score}<span className="text-gray-600 font-normal">/100</span>
        </span>
      </div>

      {/* ── Body: two-column grid ──────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-0 divide-y md:divide-y-0 md:divide-x divide-white/5">

        {/* Conditions */}
        <div className="px-4 pt-3 pb-4 flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-2">
            Conditions
          </span>


          <ConditionRow
            label="Uptrend (price above SMA 50 & 200)"
            pass={conditions.uptrend_confirmed}
          />
          <ConditionRow
            label="Weekly trend aligned"
            pass={conditions.weekly_trend_aligned}
            detail={conditions.weekly_trend_aligned ? 'weekly bullish' : 'weekly not bullish'}
          />
          <ConditionRow
            label={`ADX ${conditions.adx.toFixed(1)}`}
            pass={conditions.adx_strong}
            detail={conditions.adx_strong ? '≥ 20 strong' : '< 20 weak'}
          />
          <ConditionRow
            label={`RSI cooled ${conditions.rsi_cooldown.toFixed(0)}pts from peak`}
            pass={conditions.pullback_rsi_ok}
            detail={conditions.rsi_pullback_label.replace(/_/g, ' ')}
          />
          <ConditionRow
            label={`Near support ${levels.nearest_support > 0 ? fmt(levels.nearest_support) : ''}`}
            pass={conditions.near_support}
            detail={conditions.near_support ? '≤ 0.75× ATR' : undefined}
            badge={supportStrength ? <StrengthBadge strength={supportStrength} /> : undefined}
          />
          <ConditionRow
            label={`Volume declining (${conditions.volume_ratio.toFixed(2)}× avg)`}
            pass={conditions.volume_declining}
            detail={`OBV ${conditions.obv_trend.toLowerCase()}`}
          />
          <ConditionRow
            label={patternLabel}
            pass={conditions.reversal_candle.found}
            detail={bestPattern ? bestPattern.strength : undefined}
          />
          <ConditionRow
            label={triggerLabel}
            pass={conditions.trigger_ok}
            detail={triggerDetail}
          />

          {setup.weekly_trend_warning && (
            <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-yellow-500/80 pt-1.5 border-t border-white/5">
              <span className="flex-shrink-0">⚠</span>
              <span>{setup.weekly_trend_warning}</span>
            </div>
          )}
        </div>

        {/* Risk levels */}
        <div className="px-4 pt-3 pb-4 flex flex-col gap-0.5">
          <span className="text-[10px] font-semibold text-gray-600 uppercase tracking-wider mb-2">
            Risk Levels
          </span>

          <RiskRow
            label="Entry zone"
            value={`${fmt(risk.entry_zone.low)} – ${fmt(risk.entry_zone.high)}`}
          />
          <RiskRow
            label="Stop loss"
            value={fmt(risk.stop_loss)}
            color="text-red-400"
          />
          <RiskRow
            label="Target"
            value={fmt(risk.target)}
            color="text-green-400"
          />
          {risk.rr_to_resistance != null && (
            <RiskRow
              label="R:R to resistance"
              value={`${risk.rr_to_resistance.toFixed(2)}×`}
              color={rrColor}
            />
          )}
          <RiskRow label="ATR 14" value={fmt(risk.atr14)} />

          <div className="mt-2 pt-2 border-t border-white/5">
            <RiskRow
              label="S/R alignment"
              value={levels.sr_alignment}
              color={srColor}
            />
            <RiskRow
              label="Nearest resistance"
              value={levels.nearest_resistance > 0 ? fmt(levels.nearest_resistance) : '—'}
              color="text-red-400/70"
              badge={resistanceStrength ? <StrengthBadge strength={resistanceStrength} /> : undefined}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
