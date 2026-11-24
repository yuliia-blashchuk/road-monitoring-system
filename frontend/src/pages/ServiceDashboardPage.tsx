import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
} from 'react-leaflet'

import type { RoadEventStatus } from '../data/mapEvents'
import {
  changeStatus,
  getQueue,
  type Priority,
  type QueueItem,
} from '../services/roadmapApi'

import 'leaflet/dist/leaflet.css'
import './ServiceDashboardPage.css'

const ALL_STATUSES: RoadEventStatus[] = [
  'new',
  'accepted',
  'in_progress',
  'done',
  'resolved',
  'rejected',
]

const statusLabels: Record<RoadEventStatus, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'В роботі',
  done: 'Виконана',
  resolved: 'Усунена',
  rejected: 'Відхилена',
}

const priorityLabels: Record<Priority, string> = {
  critical: 'Критичний',
  high: 'Високий',
  medium: 'Середній',
  low: 'Низький',
}

const priorityOrder: Record<Priority, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
}

// Текст кнопки для кожного переходу (крім відхилення - для нього окрема форма)
const actionLabels: Partial<Record<RoadEventStatus, string>> = {
  accepted: 'Прийняти заявку',
  in_progress: 'Почати роботи',
  resolved: 'Позначити як усунену',
}

// Для critical окремого стилю немає - показуємо як high
function priorityClass(priority: Priority): string {
  return priority === 'critical' ? 'high' : priority
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function ServiceDashboardPage() {
  // Черга служби з бекенду (GET /queue): лише заявки своєї служби й копії
  const [reports, setReports] = useState<QueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')

  const [selectedId, setSelectedId] = useState<number | null>(null)

  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('open')
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [sortBy, setSortBy] = useState('priority')

  const [comment, setComment] = useState('')
  const [deadline, setDeadline] = useState('')
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // Лічильник оновлень: після зміни статусу збільшуємо його, і черга завантажується знову
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    getQueue(ALL_STATUSES, 100)
      .then((page) => {
        if (!cancelled) {
          setReports(page.items)
          setLoadError('')
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setLoadError(reason.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  // Типи проблем, які є в черзі служби
  const typeOptions = useMemo(() => {
    const options = new Map<string, string>()
    reports.forEach((report) =>
      options.set(report.problem_type, report.problem_label)
    )
    return [...options.entries()]
  }, [reports])

  const filteredReports = useMemo(() => {
    const result = reports.filter((report) => {
      const isOpen = !['resolved', 'rejected'].includes(report.status)
      return (
        (typeFilter === 'all' || report.problem_type === typeFilter) &&
        (statusFilter === 'all' ||
          (statusFilter === 'open' && isOpen) ||
          report.status === statusFilter) &&
        (priorityFilter === 'all' || report.priority === priorityFilter)
      )
    })

    result.sort((a, b) => {
      if (sortBy === 'priority') {
        const difference =
          priorityOrder[a.priority] - priorityOrder[b.priority]
        if (difference !== 0) return difference
        return (
          new Date(a.created_at).getTime() -
          new Date(b.created_at).getTime()
        )
      }

      if (sortBy === 'oldest') {
        return (
          new Date(a.created_at).getTime() -
          new Date(b.created_at).getTime()
        )
      }

      return (
        new Date(b.created_at).getTime() -
        new Date(a.created_at).getTime()
      )
    })

    return result
  }, [reports, typeFilter, statusFilter, priorityFilter, sortBy])

  const selectedReport =
    filteredReports.find((report) => report.id === selectedId) ??
    filteredReports[0]

  function clearForm() {
    setShowRejectForm(false)
    setRejectReason('')
    setComment('')
    setDeadline('')
    setError('')
  }

  function selectReport(id: number) {
    setSelectedId(id)
    setMessage('')
    clearForm()
  }

  // Зміна статусу через бекенд (PATCH /reports/{id}/status): правила переходів
  // перевіряє сервер, а водій отримує сповіщення
  async function submitStatus(status: RoadEventStatus) {
    if (!selectedReport) return

    if (status === 'rejected' && !rejectReason.trim()) {
      setError('Вкажіть причину відхилення заявки.')
      return
    }

    setSaving(true)
    setError('')
    setMessage('')
    try {
      await changeStatus(selectedReport.id, {
        status,
        comment: comment.trim() || undefined,
        reject_reason: status === 'rejected' ? rejectReason.trim() : undefined,
        // Поле дати дає рядок YYYY-MM-DD; строк має сенс лише при прийнятті чи початку робіт
        deadline:
          /^\d{4}-\d{2}-\d{2}$/.test(deadline) &&
          (status === 'accepted' || status === 'in_progress')
            ? deadline
            : undefined,
      })
      setSelectedId(selectedReport.id)
      clearForm()
      setMessage(
        `Статус заявки №${selectedReport.number} змінено на «${statusLabels[status]}». ` +
          'Водій отримав сповіщення.'
      )
      setReloadKey((key) => key + 1)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const openReports = reports.filter(
    (report) => !['resolved', 'rejected'].includes(report.status)
  )
  const total = openReports.length
  const newCount = openReports.filter((report) => report.status === 'new').length
  const activeCount = openReports.filter((report) =>
    ['accepted', 'in_progress', 'done'].includes(report.status)
  ).length
  const highCount = openReports.filter((report) =>
    ['critical', 'high'].includes(report.priority)
  ).length

  const nextStatuses = selectedReport?.next_statuses ?? []
  const canSetDeadline =
    nextStatuses.includes('accepted') || nextStatuses.includes('in_progress')

  return (
    <div className="rm-service-page">
      <div className="rm-service-heading">
        <div>
          <p className="rm-service-eyebrow">
            RoadMap / Робочий простір
          </p>

          <h1>Кабінет дорожньої служби</h1>
          <p>
            Перегляд і опрацювання дорожніх заявок вашої служби.
          </p>
        </div>

        <span className="rm-service-demo">
          Дані з бази RoadMap
        </span>
      </div>

      {loading && (
        <div className="rm-service-notice">Завантаження черги заявок…</div>
      )}

      {loadError && (
        <div className="rm-service-notice" role="alert">
          {loadError}
        </div>
      )}

      <div className="rm-service-stats">
        <div className="rm-service-stat">
          <span>Відкриті заявки</span>
          <strong>{total}</strong>
          <small>У черзі вашої служби</small>
        </div>

        <div className="rm-service-stat">
          <span>Нові заявки</span>
          <strong>{newCount}</strong>
          <small>Очікують розгляду</small>
        </div>

        <div className="rm-service-stat">
          <span>В опрацюванні</span>
          <strong>{activeCount}</strong>
          <small>Прийняті, в роботі, виконані</small>
        </div>

        <div className="rm-service-stat">
          <span>Високий пріоритет</span>
          <strong>{highCount}</strong>
          <small>Критичні та високі</small>
        </div>
      </div>

      <section className="rm-service-card">
        <div className="rm-service-section-heading">
          <div>
            <h2>Вхідні заявки</h2>
            <p>Фільтруйте та сортуйте звернення.</p>
          </div>

          <span className="rm-service-count">
            {filteredReports.length} із {reports.length}
          </span>
        </div>

        <div className="rm-service-filters">
          <label>
            Тип проблеми
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value)}
            >
              <option value="all">Усі категорії</option>
              {typeOptions.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Статус
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="open">Відкриті</option>
              <option value="all">Усі статуси</option>
              {ALL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </select>
          </label>

          <label>
            Пріоритет
            <select
              value={priorityFilter}
              onChange={(event) => setPriorityFilter(event.target.value)}
            >
              <option value="all">Усі пріоритети</option>
              {Object.entries(priorityLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Сортування
            <select
              value={sortBy}
              onChange={(event) => setSortBy(event.target.value)}
            >
              <option value="priority">За пріоритетом</option>
              <option value="newest">Спочатку новіші</option>
              <option value="oldest">Спочатку старіші</option>
            </select>
          </label>

          <button
            type="button"
            className="rm-service-reset"
            onClick={() => {
              setTypeFilter('all')
              setStatusFilter('open')
              setPriorityFilter('all')
              setSortBy('priority')
            }}
          >
            Скинути
          </button>
        </div>

        <div className="rm-service-table-wrap">
          <table className="rm-service-table">
            <thead>
              <tr>
                <th>№</th>
                <th>Проблема</th>
                <th>Адреса</th>
                <th>Пріоритет</th>
                <th>Статус</th>
                <th>Створено</th>
              </tr>
            </thead>

            <tbody>
              {filteredReports.map((report) => (
                <tr
                  key={report.id}
                  className={selectedReport?.id === report.id ? 'selected' : ''}
                  onClick={() => selectReport(report.id)}
                >
                  <td>№{report.number}</td>
                  <td>
                    <button
                      type="button"
                      className="rm-service-row-link"
                      onClick={() => selectReport(report.id)}
                    >
                      {report.problem_label}
                      {report.is_copy ? ' (копія)' : ''}
                    </button>
                  </td>
                  <td>{report.address ?? 'Адресу не вказано'}</td>
                  <td>
                    <span
                      className={
                        `rm-service-priority ` +
                        `rm-service-priority--${priorityClass(report.priority)}`
                      }
                    >
                      {priorityLabels[report.priority]}
                    </span>
                  </td>
                  <td>
                    <span
                      className={
                        `rm-service-status ` +
                        `rm-service-status--${report.status}`
                      }
                    >
                      {statusLabels[report.status]}
                    </span>
                  </td>
                  <td>{formatDate(report.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {!loading && filteredReports.length === 0 && (
            <p className="rm-service-empty">
              За вибраними фільтрами заявок немає.
            </p>
          )}
        </div>
      </section>

      {message && (
        <p className="rm-service-complete" role="status">
          {message}
        </p>
      )}

      {selectedReport && (
        <div className="rm-service-details-grid">
          <section className="rm-service-card">
            <div className="rm-service-section-heading">
              <div>
                <h2>Заявка №{selectedReport.number}</h2>
                <p>
                  {selectedReport.problem_label}
                  {selectedReport.is_copy
                    ? ' · ваша служба отримала копію'
                    : ''}
                </p>
              </div>

              <span
                className={
                  `rm-service-status ` +
                  `rm-service-status--${selectedReport.status}`
                }
              >
                {statusLabels[selectedReport.status]}
              </span>
            </div>

            <div className="rm-service-detail-list">
              <div>
                <span>Адреса</span>
                <strong>{selectedReport.address ?? 'Адресу не вказано'}</strong>
              </div>

              <div>
                <span>Пріоритет</span>
                <strong>{priorityLabels[selectedReport.priority]}</strong>
              </div>

              <div>
                <span>Автор</span>
                <strong>{selectedReport.author ?? '—'}</strong>
              </div>

              <div>
                <span>Підтверджень «Теж бачу»</span>
                <strong>{selectedReport.confirmations_count}</strong>
              </div>

              <div>
                <span>Дата створення</span>
                <strong>{formatDate(selectedReport.created_at)}</strong>
              </div>

              {selectedReport.deadline && (
                <div>
                  <span>Орієнтовний строк</span>
                  <strong>{formatDate(selectedReport.deadline)}</strong>
                </div>
              )}

              {selectedReport.progress_percent != null && (
                <div>
                  <span>Прогрес підрядника</span>
                  <strong>{selectedReport.progress_percent} %</strong>
                </div>
              )}

              {selectedReport.comment && (
                <div>
                  <span>Коментар водія</span>
                  <strong>{selectedReport.comment}</strong>
                </div>
              )}
            </div>

            <p>
              <Link to={`/reports/${selectedReport.id}`}>
                Відкрити повну картку з фото та історією →
              </Link>
            </p>

            <h3>Опрацювання заявки</h3>

            {nextStatuses.length > 0 && !showRejectForm && (
              <div className="rm-service-reject-form">
                <label htmlFor="service-comment">
                  Коментар для водія (необов'язково)
                </label>
                <textarea
                  id="service-comment"
                  rows={2}
                  maxLength={300}
                  value={comment}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="Наприклад: бригада виїде протягом 3 днів"
                />

                {canSetDeadline && (
                  <>
                    <label htmlFor="service-deadline">
                      Орієнтовний строк (необов'язково)
                    </label>
                    <input
                      id="service-deadline"
                      type="date"
                      value={deadline}
                      onChange={(event) => setDeadline(event.target.value)}
                    />
                  </>
                )}
              </div>
            )}

            <div className="rm-service-actions">
              {nextStatuses
                .filter((status) => status !== 'rejected' && actionLabels[status])
                .map((status) => (
                  <button
                    key={status}
                    type="button"
                    onClick={() => submitStatus(status)}
                    className="rm-service-primary"
                    disabled={saving}
                  >
                    {actionLabels[status]}
                  </button>
                ))}

              {nextStatuses.includes('rejected') && !showRejectForm && (
                <button
                  type="button"
                  className="rm-service-danger"
                  onClick={() => {
                    setShowRejectForm(true)
                    setError('')
                  }}
                >
                  Відхилити заявку
                </button>
              )}
            </div>

            {showRejectForm && (
              <div className="rm-service-reject-form">
                <label htmlFor="service-reject-reason">
                  Причина відхилення *
                </label>

                <textarea
                  id="service-reject-reason"
                  rows={3}
                  maxLength={300}
                  value={rejectReason}
                  onChange={(event) => setRejectReason(event.target.value)}
                  placeholder="Наприклад: не підтверджено на місці"
                />

                <div className="rm-service-actions">
                  <button
                    type="button"
                    className="rm-service-danger"
                    onClick={() => submitStatus('rejected')}
                    disabled={saving}
                  >
                    Підтвердити відхилення
                  </button>

                  <button
                    type="button"
                    className="rm-service-reset"
                    onClick={clearForm}
                  >
                    Скасувати
                  </button>
                </div>
              </div>
            )}

            {error && (
              <p role="alert" className="rm-service-error">
                {error}
              </p>
            )}

            {selectedReport.status === 'done' && (
              <p className="rm-service-complete">
                Підрядник здав роботи. Перевірте фото «після» в повній картці
                й позначте заявку як усунену.
              </p>
            )}

            {['resolved', 'rejected'].includes(selectedReport.status) && (
              <p className="rm-service-complete">
                Опрацювання заявки завершено.
              </p>
            )}
          </section>

          <section className="rm-service-card">
            <h2>Місце проблеми на карті</h2>

            <div className="rm-service-map">
              <MapContainer
                key={selectedReport.id}
                center={[selectedReport.lat, selectedReport.lng]}
                zoom={16}
                scrollWheelZoom
                style={{ height: '340px', width: '100%' }}
              >
                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                <CircleMarker
                  center={[selectedReport.lat, selectedReport.lng]}
                  radius={11}
                  pathOptions={{
                    color: '#ffffff',
                    weight: 3,
                    fillColor: '#2e96d1',
                    fillOpacity: 1,
                  }}
                >
                  <Popup>
                    <strong>
                      {selectedReport.problem_label} №{selectedReport.number}
                    </strong>
                    <p>{selectedReport.address ?? 'Адресу не вказано'}</p>
                  </Popup>
                </CircleMarker>
              </MapContainer>
            </div>

            <p className="rm-service-map-caption">
              Оберіть заявку в таблиці, щоб переглянути
              її місце розташування.
            </p>
          </section>
        </div>
      )}
    </div>
  )
}

export default ServiceDashboardPage