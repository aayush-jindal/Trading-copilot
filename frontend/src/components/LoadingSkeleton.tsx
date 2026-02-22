function Block({ className }: { className: string }) {
  return (
    <div className={`shimmer-bg animate-shimmer rounded-lg ${className}`} />
  )
}

export default function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-4 animate-fade-in">
      {/* Ticker card skeleton */}
      <div className="glass px-5 py-4 flex justify-between items-center">
        <div className="flex flex-col gap-2">
          <Block className="h-6 w-24" />
          <Block className="h-4 w-40" />
        </div>
        <div className="flex flex-col items-end gap-2">
          <Block className="h-8 w-28" />
          <Block className="h-4 w-20" />
        </div>
      </div>

      {/* Chart skeleton */}
      <div className="glass overflow-hidden">
        <div className="flex items-center gap-5 px-5 py-3 border-b border-white/10">
          {[64, 56, 72, 64].map((w, i) => (
            <Block key={i} className={`h-3 w-${w === 64 ? '16' : w === 56 ? '14' : w === 72 ? '18' : '16'}`} />
          ))}
        </div>
        <Block className="w-full h-[560px] rounded-none" />
      </div>

      {/* Signal grid skeleton */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Block key={i} className="h-20" />
        ))}
      </div>

      {/* Narrative skeleton */}
      <div className="glass p-5 flex flex-col gap-3">
        <Block className="h-4 w-32" />
        <Block className="h-4 w-full" />
        <Block className="h-4 w-5/6" />
        <Block className="h-4 w-4/6" />
        <Block className="h-4 w-3/6" />
      </div>
    </div>
  )
}
