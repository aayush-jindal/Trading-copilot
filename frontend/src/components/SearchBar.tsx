import { useState } from 'react'

interface SearchBarProps {
  onSearch: (ticker: string) => void
  disabled?: boolean
  history?: string[]
}

export default function SearchBar({ onSearch, disabled, history = [] }: SearchBarProps) {
  const [value, setValue] = useState('')

  function handleSubmit() {
    const trimmed = value.trim().toUpperCase()
    if (trimmed) {
      onSearch(trimmed)
      setValue('')
    }
  }

  return (
    <div className="flex flex-col items-end gap-2">
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder="AAPL"
          disabled={disabled}
          className="
            w-28 px-3 py-1.5 rounded-lg bg-white/5 border border-white/15
            text-gray-100 placeholder-gray-500 text-sm font-mono uppercase
            focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50
            disabled:opacity-50 transition-colors
          "
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="
            px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium
            disabled:opacity-40 disabled:cursor-not-allowed transition-colors
          "
        >
          Search
        </button>
      </div>

      {history.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap justify-end">
          {history.map((t) => (
            <button
              key={t}
              onClick={() => onSearch(t)}
              disabled={disabled}
              className="
                px-2 py-0.5 text-xs rounded-full border border-white/10 bg-white/5
                text-gray-400 hover:text-gray-100 hover:border-blue-500/50 hover:bg-blue-500/10
                disabled:opacity-40 transition-all font-mono
              "
            >
              {t}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
