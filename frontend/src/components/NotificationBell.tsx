import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { getNotifications, TOKEN_KEY } from '../services/roadmapApi'

// Подія, яку надсилає сторінка сповіщень після «Прочитано»,
// щоб дзвіночок одразу оновив лічильник.
export const NOTIFICATIONS_CHANGED = 'roadmap:notifications-changed'

const REFRESH_MS = 20_000

// Дзвіночок у верхньому рядку з кількістю непрочитаних сповіщень.
// Оновлюється кожні 20 секунд, після повернення на вкладку
// і після дій на сторінці сповіщень.
function NotificationBell({ children }: { children: ReactNode }) {
  const [unread, setUnread] = useState(0)

  useEffect(() => {
    let cancelled = false

    function refresh() {
      if (!sessionStorage.getItem(TOKEN_KEY)) {
        setUnread(0)
        return
      }
      getNotifications(true, 1)
        .then((page) => {
          if (!cancelled) setUnread(page.unread)
        })
        .catch(() => {
          if (!cancelled) setUnread(0)
        })
    }

    const first = window.setTimeout(refresh, 0)
    const timer = window.setInterval(refresh, REFRESH_MS)
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh)
    window.addEventListener('focus', refresh)

    return () => {
      cancelled = true
      window.clearTimeout(first)
      window.clearInterval(timer)
      window.removeEventListener(NOTIFICATIONS_CHANGED, refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [])

  const label =
    unread > 0 ? `Сповіщення: ${unread} непрочитаних` : 'Сповіщення'

  return (
    <Link
      to="/notifications"
      className="rm-top-icon"
      title={label}
      aria-label={label}
    >
      {children}

      {unread > 0 && (
        <span
          className="rm-notification-dot"
          style={{
            right: -4,
            top: -4,
            width: 'auto',
            minWidth: 18,
            height: 18,
            padding: '0 5px',
            borderRadius: 9,
            color: '#fff',
            fontSize: 11,
            fontWeight: 700,
            lineHeight: '18px',
            textAlign: 'center',
          }}
        >
          {unread > 99 ? '99+' : unread}
        </span>
      )}
    </Link>
  )
}

export default NotificationBell