interface NarrativePanelProps {
  narrative: string
  isStreaming: boolean
}

export default function NarrativePanel({ narrative, isStreaming }: NarrativePanelProps) {
  const hasContent = narrative.length > 0

  return (
    <div className="glass animate-fade-in border-l-4 border-l-blue-500 p-5">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-500/20 text-blue-400 text-xs">
          ✦
        </span>
        <h2 className="text-sm font-semibold text-blue-300 tracking-wide uppercase">
          AI Copilot
        </h2>
        {isStreaming && (
          <span className="flex gap-1 ml-1">
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:0ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:150ms]" />
            <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-bounce [animation-delay:300ms]" />
          </span>
        )}
      </div>

      {!hasContent && isStreaming && (
        <p className="text-gray-500 text-sm italic">Generating analysis…</p>
      )}

      {!hasContent && !isStreaming && (
        <p className="text-gray-600 text-sm italic">
          Search a ticker to generate a narrative.
        </p>
      )}

      {hasContent && (
        <p className={`text-gray-200 text-sm leading-7 whitespace-pre-wrap ${isStreaming ? 'blink-cursor' : ''}`}>
          {narrative}
        </p>
      )}
    </div>
  )
}
