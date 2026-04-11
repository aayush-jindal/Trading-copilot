import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getNotifications, markAllNotificationsRead } from '../api/client'
import type { Notification, NotificationType } from '../types'

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

const NOTIFICATION_STYLE: Record<NotificationType, { icon: string; label: string; color: string }> = {
  digest: { icon: '📊', label: 'Daily Digest', color: 'text-blue-400' },
  option_exit: { icon: '🚨', label: 'Trade Alert', color: 'text-red-400' },
  option_signal: { icon: '📈', label: 'Options Signal', color: 'text-green-400' },
  iv_alert: { icon: '⚡', label: 'IV Alert', color: 'text-yellow-400' },
}

interface Props {
  onClose: () => void
  onUnreadChange: (count: number) => void
}

export default function NotificationsPanel({ onClose, onUnreadChange }: Props) {
  const navigate = useNavigate()
  const panelRef = useRef<HTMLDivElement>(null)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    getNotifications()
      .then((data) => {
        setNotifications(data)
        onUnreadChange(0)
        // Mark all as read silently
        if (data.some((n) => !n.is_read)) {
          markAllNotificationsRead().catch(() => {})
        }
      })
      .catch(() => {})
      .finally(() => setIsLoading(false))
  }, [onUnreadChange])

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  function handleTickerClick(ticker: string) {
    onClose()
    navigate(`/?ticker=${ticker}`)
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-[2px]"
        onClick={onClose}
      />

      {/* Slide-out panel */}
      <div
        ref={panelRef}
        className="fixed right-0 top-0 bottom-0 z-50 w-full max-w-sm bg-[#0a0f1a] border-l border-white/10 flex flex-col shadow-2xl animate-slide-in-right"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-white/10">
          <h2 className="text-sm font-semibold text-white">Notifications</h2>
          <button
            onClick={onClose}
            className="text-gray-500 hover:text-white transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto py-2">
          {isLoading && (
            <div className="flex flex-col gap-3 p-4">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-24 rounded-xl bg-white/5 animate-pulse" />
              ))}
            </div>
          )}

          {!isLoading && notifications.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full py-16 gap-3">
              <div className="text-4xl opacity-20">🔔</div>
              <p className="text-gray-500 text-sm text-center px-6">
                No digests yet. Digests are generated after market close on weekdays.
              </p>
            </div>
          )}

          {!isLoading && notifications.map((notification) => {
            const style = NOTIFICATION_STYLE[notification.type] || NOTIFICATION_STYLE.digest
            return (
            <div
              key={notification.id}
              className="mx-3 my-2 rounded-xl border border-white/8 bg-white/[0.03] p-4"
            >
              {/* Notification header */}
              <div className="flex items-center justify-between mb-3">
                <span className={`text-xs font-semibold ${style.color} uppercase tracking-wide flex items-center gap-1.5`}>
                  <span>{style.icon}</span>
                  <span>{notification.type !== 'digest' ? style.label + ' — ' : ''}{notification.content.date}</span>
                </span>
                <span className="text-xs text-gray-600">
                  {formatDate(notification.created_at)}
                </span>
              </div>

              {/* Digest entries */}
              <div className="flex flex-col gap-2">
                {notification.content.entries.map((entry) => (
                  <div key={entry.ticker} className="flex gap-2 text-sm">
                    <button
                      onClick={() => handleTickerClick(entry.ticker)}
                      className="font-mono text-blue-400 hover:text-blue-300 font-medium shrink-0 transition-colors"
                    >
                      {entry.ticker}
                    </button>
                    <span className="text-gray-400 leading-relaxed">{entry.summary.replace(/^[A-Z]+ → /, '')}</span>
                  </div>
                ))}
              </div>
            </div>
          )})}
        </div>
      </div>
    </>
  )
}
