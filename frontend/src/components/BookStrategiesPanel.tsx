interface BookStrategiesPanelProps {
  strategies: string | null
  isLoading: boolean
  error: string | null
}

export default function BookStrategiesPanel({ strategies, isLoading, error }: BookStrategiesPanelProps) {
  return (
    <div className="glass animate-fade-in border-l-4 border-l-amber-500 p-5">
      {/* Header */}
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

      {isLoading && !strategies && (
        <p className="text-gray-500 text-sm italic">
          Retrieving relevant book passages and generating strategies…
        </p>
      )}

      {error && !strategies && (
        <p className="text-amber-600/80 text-sm italic">
          {error.includes('empty') || error.includes('ingest')
            ? 'Knowledge base is empty — run ingest first to index your trading books.'
            : error}
        </p>
      )}

      {strategies && (
        <div className="text-gray-200 text-sm leading-7 whitespace-pre-wrap font-mono">
          {strategies}
        </div>
      )}
    </div>
  )
}
