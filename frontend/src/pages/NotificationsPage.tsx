import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { NOTIFICATIONS_CHANGED } from '../components/NotificationBell'
import {
  getNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from '../services/roadmapApi'

// Ті самі картки й кнопки, що й у кабінеті служби
import './ServiceDashboardPage.css'

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

// Повідомляємо дзвіночок угорі, що кількість непрочитаних змінилась
function notifyBell() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED))
}

// Стрічка сповіщень (KAN-61): зміни статусів власних заявок
// (GET /notifications, POST /notifications/{id}/read, POST /notifications/read-all)
function NotificationsPage() {
  const navigate = useNavigate()

  const [items, setItems] = useState<NotificationItem[]>([])
  const [total, setTotal] = useState(0)
  const [unread, setUnread] = useState(0)
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    getNotifications(unreadOnly, 100)
      .then((page) => {
        if (!cancelled) {
          setItems(page.items)
          setTotal(page.total)
          setUnread(page.unread)
          setError('')
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [unreadOnly, reloadKey])

  async function markRead(item: NotificationItem) {
    if (item.is_read) return
    try {
      await markNotificationRead(item.id)
      setItems((previous) =>
        unreadOnly
          ? previous.filter((other) => other.id !== item.id)
          : previous.map((other) =>
              other.id === item.id ? { ...other, is_read: true } : other
            )
      )
      setUnread((count) => Math.max(0, count - 1))
      if (unreadOnly) setTotal((count) => Math.max(0, count - 1))
      notifyBell()
    } catch (reason) {
      setError((reason as Error).message)
    }
  }

  async function openReport(item: NotificationItem) {
    await markRead(item)
    if (item.request_id) navigate(`/reports/${item.request_id}`)
  }

  async function markAll() {
    try {
      await markAllNotificationsRead()
      notifyBell()
      setReloadKey((key) => key + 1)
    } catch (reason) {
      setError((reason as Error).message)
    }
  }

  return (
    <div className="rm-service-page">
      <div className="rm-service-stats">
        <div className="rm-service-stat">
          <span>Непрочитані</span>
          <strong>{unread}</strong>
          <small>Нові зміни у ваших заявках</small>
        </div>

        <div className="rm-service-stat">
          <span>{unreadOnly ? 'Показано' : 'Усього сповіщень'}</span>
          <strong>{total}</strong>
          <small>Зміни статусів заявок</small>
        </div>
      </div>

      <section className="rm-service-card">
        <div className="rm-service-section-heading">
          <div>
            <h2>Сповіщення</h2>
            <p>
              Коли служба змінює статус вашої заявки, тут з'являється
              повідомлення з коментарем і строком.
            </p>
          </div>

          <button
            type="button"
            className="rm-service-primary"
            onClick={markAll}
            disabled={unread === 0}
          >
            Позначити всі прочитаними
          </button>
        </div>

        <div className="rm-service-filters">
          <label>
            Показати
            <select
              value={unreadOnly ? 'unread' : 'all'}
              onChange={(event) =>
                setUnreadOnly(event.target.value === 'unread')
              }
            >
              <option value="all">Усі сповіщення</option>
              <option value="unread">Лише непрочитані</option>
            </select>
          </label>
        </div>

        {loading && <p className="rm-service-empty">Завантаження сповіщень…</p>}

        {error && (
          <p className="rm-service-error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && items.length === 0 && (
          <p className="rm-service-empty">
            {unreadOnly
              ? 'Непрочитаних сповіщень немає.'
              : 'Сповіщень ще немає. Вони з’являться, коли служба змінить статус вашої заявки.'}
          </p>
        )}

        {items.length > 0 && (
          <ul
            style={{
              listStyle: 'none',
              margin: 0,
              padding: 0,
              display: 'grid',
              gap: 10,
            }}
          >
            {items.map((item) => (
              <li
                key={item.id}
                style={{
                  display: 'flex',
                  gap: 14,
                  alignItems: 'flex-start',
                  padding: '14px 16px',
                  border: '1px solid #d9ecf9',
                  borderLeft: item.is_read
                    ? '1px solid #d9ecf9'
                    : '4px solid #2d8bc8',
                  borderRadius: 12,
                  background: item.is_read ? '#fff' : '#f3faff',
                }}
              >
                <div style={{ flex: 1 }}>
                  <p
                    style={{
                      margin: 0,
                      fontWeight: item.is_read ? 400 : 600,
                      color: '#1d3557',
                    }}
                  >
                    {item.message}
                  </p>
                  <small style={{ color: '#7a95ab' }}>
                    {formatDateTime(item.created_at)}
                    {!item.is_read && ' · нове'}
                  </small>
                </div>

                <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
                  {item.request_id && (
                    <button
                      type="button"
                      className="rm-service-row-link"
                      onClick={() => openReport(item)}
                    >
                      Відкрити заявку →
                    </button>
                  )}

                  {!item.is_read && (
                    <button
                      type="button"
                      className="rm-service-reset"
                      onClick={() => markRead(item)}
                    >
                      Прочитано
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {!unreadOnly && total > items.length && (
          <p className="rm-service-empty">
            Показано останні {items.length} із {total}.
          </p>
        )}
      </section>
    </div>
  )
}

export default NotificationsPage