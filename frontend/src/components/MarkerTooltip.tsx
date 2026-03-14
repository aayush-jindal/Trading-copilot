import type { MarkerTooltipData } from '../types'

interface Props {
  data: MarkerTooltipData | null
  point: { x: number; y: number } | null
  chartRect: DOMRect | null
}

const TOOLTIP_W = 220
const TOOLTIP_H = 160

export default function MarkerTooltip({ data, point, chartRect }: Props) {
  if (!data || !point || !chartRect) return null

  const { marker, runLabel, runColour } = data
  const isEntry = marker.type === 'entry'

  // Position: above cursor; flip below if too close to top; nudge horizontally
  let left = point.x - TOOLTIP_W / 2
  let top = point.y - TOOLTIP_H - 14

  if (top < chartRect.top + 8) {
    top = point.y + 20
  }
  if (left < chartRect.left + 4) {
    left = chartRect.left + 4
  }
  if (left + TOOLTIP_W > chartRect.right - 4) {
    left = chartRect.right - TOOLTIP_W - 4
  }

  return (
    <div
      style={{
        position: 'fixed',
        left,
        top,
        width: TOOLTIP_W,
        background: '#1F2937',
        border: `1px solid ${runColour}`,
        borderRadius: 8,
        padding: '10px 12px',
        fontSize: 12,
        color: '#E5E7EB',
        zIndex: 1000,
        pointerEvents: 'none',
        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ fontWeight: 700, color: isEntry ? runColour : '#9CA3AF' }}>
          {isEntry ? '▲ ENTRY' : '● EXIT'}
        </span>
        <span style={{ color: '#6B7280' }}>{marker.time}</span>
      </div>

      {/* Entry fields */}
      {isEntry && (() => {
        const m = marker as import('../types').ChartMarkerEntry
        return (
          <>
            <Row
              label="Verdict"
              value={m.verdict}
              colour={m.verdict === 'ENTRY' ? '#34D399' : '#60A5FA'}
            />
            <Row label="Score" value={m.score} />
            {m.rr_ratio != null && (
              <Row label="R:R" value={`${Number(m.rr_ratio).toFixed(2)}×`} />
            )}
          </>
        )
      })()}

      {/* Exit fields */}
      {!isEntry && (() => {
        const m = marker as import('../types').ChartMarkerExit
        const retPct = Number(m.return_pct)
        return (
          <>
            <Row
              label="Outcome"
              value={m.outcome}
              colour={
                m.outcome === 'WIN'
                  ? '#34D399'
                  : m.outcome === 'LOSS'
                  ? '#F87171'
                  : '#6B7280'
              }
            />
            <Row
              label="Return"
              value={`${retPct >= 0 ? '+' : ''}${retPct.toFixed(2)}%`}
              colour={retPct >= 0 ? '#34D399' : '#F87171'}
            />
            {m.days_to_outcome != null && (
              <Row label="Days" value={m.days_to_outcome} />
            )}
          </>
        )
      })()}

      {/* Run label footer */}
      <div
        style={{
          marginTop: 6,
          borderTop: '1px solid #374151',
          paddingTop: 4,
          color: '#6B7280',
          fontSize: 11,
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}
      >
        {runLabel}
      </div>
    </div>
  )
}

function Row({
  label,
  value,
  colour,
}: {
  label: string
  value: string | number
  colour?: string
}) {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: 2,
      }}
    >
      <span style={{ color: '#9CA3AF' }}>{label}</span>
      <span style={{ fontWeight: 600, color: colour ?? '#E5E7EB' }}>{value}</span>
    </div>
  )
}
