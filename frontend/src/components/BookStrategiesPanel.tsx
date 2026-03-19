// Shapes returned by tools/knowledge_base/strategy_gen.py → /analyze/{ticker}/knowledge-strategies

interface StrategySource {
  book: string
  page: number
  rule: string
}

interface BookStrategy {
  name: string
  conditions_status: 'MET' | 'PARTIAL' | 'NOT MET'
  conditions_detail: string
  conviction: 'HIGH' | 'MEDIUM' | 'LOW'
  sources: StrategySource[]
  confirmation_signals: string[]
  invalidation_signals: string[]
}

interface BestOpportunity {
  strategy_name: string
  rationale: string
  conviction: 'HIGH' | 'MEDIUM' | 'LOW'
}

export interface BookStrategiesData {
  strategies: BookStrategy[]
  best_opportunity: BestOpportunity | null
  signals_to_watch: string[]
}

interface BookStrategiesPanelProps {
  strategies: BookStrategiesData | null
  isLoading: boolean
  error: string | null
}

const STATUS_STYLE: Record<string, string> = {
  'MET':     'bg-green-500/15 border-green-500/30 text-green-300',
  'PARTIAL': 'bg-amber-500/15 border-amber-500/30 text-amber-300',
  'NOT MET': 'bg-white/5 border-white/10 text-gray-500',
}

const CONVICTION_STYLE: Record<string, string> = {
  HIGH:   'text-green-400',
  MEDIUM: 'text-amber-400',
  LOW:    'text-gray-500',
}

export default function BookStrategiesPanel({ strategies, isLoading, error }: BookStrategiesPanelProps) {
  return (
    <div className="glass animate-fade-in border-l-4 border-l-amber-500 p-5">
      {/* Header — unchanged */}
      <div className="flex items-center gap-2 mb-4">
        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-amber-500/20 text-amber-400 text-xs">
          📚
        </span>
        <h2 className="text-sm font-semibold text-amber-300 tracking-wide uppercase">
          Book Strategies
        </h2>
        {isLoading && (
          <span className="flex gap-1 ml-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce [animation-delay:300ms]" />
          </span>
        )}
      </div>

      {/* Loading state — unchanged */}
      {isLoading && !strategies && (
        <p className="text-gray-500 text-sm italic">
          Retrieving relevant book passages and generating strategies…
        </p>
      )}

      {/* Error state — unchanged */}
      {error && !strategies && (
        <p className="text-amber-600/80 text-sm italic">
          {error.includes('empty') || error.includes('ingest')
            ? 'Knowledge base is empty — run ingest first to index your trading books.'
            : error}
        </p>
      )}

      {/* Structured content */}
      {strategies && (
        <div className="flex flex-col gap-5">

          {/* Strategy cards */}
          {strategies.strategies.map((s, i) => (
            <div key={i} className="flex flex-col gap-2 border-t border-white/5 pt-4 first:border-0 first:pt-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-semibold text-amber-200">{s.name}</span>
                <span className={`inline-flex text-[10px] px-1.5 py-0.5 rounded-full border font-medium ${STATUS_STYLE[s.conditions_status] ?? STATUS_STYLE['NOT MET']}`}>
                  {s.conditions_status}
                </span>
                <span className={`text-[11px] font-semibold ml-auto ${CONVICTION_STYLE[s.conviction] ?? 'text-gray-500'}`}>
                  {s.conviction} conviction
                </span>
              </div>

              <p className="text-sm text-gray-300 leading-relaxed">{s.conditions_detail}</p>

              {s.sources.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {s.sources.map((src, j) => (
                    <span key={j} className="text-[10px] px-1.5 py-0.5 rounded border border-amber-500/20 bg-amber-500/5 text-amber-400/70 font-mono">
                      {src.book} p.{src.page}
                    </span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-1">
                {s.confirmation_signals.length > 0 && (
                  <div>
                    <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Confirm before entry</p>
                    <ul className="flex flex-col gap-0.5">
                      {s.confirmation_signals.map((sig, j) => (
                        <li key={j} className="text-xs text-gray-400 flex gap-1.5">
                          <span className="text-green-600 flex-shrink-0">+</span>{sig}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {s.invalidation_signals.length > 0 && (
                  <div>
                    <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1">Invalidation</p>
                    <ul className="flex flex-col gap-0.5">
                      {s.invalidation_signals.map((sig, j) => (
                        <li key={j} className="text-xs text-gray-400 flex gap-1.5">
                          <span className="text-red-600 flex-shrink-0">✗</span>{sig}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Best opportunity */}
          {strategies.best_opportunity && (
            <div className="border-t border-amber-500/20 pt-4 flex flex-col gap-1">
              <p className="text-[10px] text-amber-500/70 uppercase tracking-wider font-semibold">Best Opportunity</p>
              <p className="text-sm font-semibold text-amber-200">{strategies.best_opportunity.strategy_name}</p>
              <p className="text-sm text-gray-300 leading-relaxed">{strategies.best_opportunity.rationale}</p>
              <p className={`text-[11px] font-semibold ${CONVICTION_STYLE[strategies.best_opportunity.conviction] ?? 'text-gray-500'}`}>
                {strategies.best_opportunity.conviction} conviction
              </p>
            </div>
          )}

          {/* Signals to watch */}
          {strategies.signals_to_watch.length > 0 && (
            <div className="border-t border-white/5 pt-4">
              <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-2">Signals to Watch</p>
              <ul className="flex flex-col gap-0.5">
                {strategies.signals_to_watch.map((sig, i) => (
                  <li key={i} className="text-xs text-gray-400 flex gap-1.5">
                    <span className="text-amber-600 flex-shrink-0">·</span>{sig}
                  </li>
                ))}
              </ul>
            </div>
          )}

        </div>
      )}
    </div>
  )
}
