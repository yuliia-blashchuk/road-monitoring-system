
import { useMemo, useState } from 'react'
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
} from 'react-leaflet'

import {
  mapEvents,
  type RoadEvent,
  type RoadEventStatus,
  type RoadEventType,
} from '../data/mapEvents'

import 'leaflet/dist/leaflet.css'
import './ServiceDashboardPage.css'

type ServiceStatus = RoadEventStatus | 'rejected'
type Priority = 'high' | 'medium' | 'low'

type ReportUpdate = {
  status: ServiceStatus
  reason?: string
}

const typeLabels: Record<RoadEventType, string> = {
  pothole: 'Пошкодження дороги',
  accident: 'Аварія',
  obstacle: 'Перешкода',
  roadworks: 'Ремонтні роботи',
  traffic_light: 'Світлофор',
    damaged_surface: 'Пошкоджене покриття',
  other: 'Інше',
}

const statusLabels: Record<ServiceStatus, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'В роботі',
  resolved: 'Усунена',
  rejected: 'Відхилена',
    done: 'Виконана',
}

const priorityLabels: Record<Priority, string> = {
  high: 'Високий',
  medium: 'Середній',
  low: 'Низький',
}

const priorityOrder: Record<Priority, number> = {
  high: 0,
  medium: 1,
  low: 2,
}

// Демонстраційне визначення пріоритету.
function getPriority(report: RoadEvent): Priority {
  if (
    report.type === 'accident' ||
    report.type === 'traffic_light'
  ) {
    return 'high'
  }

  if (
    report.type === 'pothole' ||
    report.type === 'obstacle'
  ) {
    return 'medium'
  }

  return 'low'
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

function ServiceDashboardPage() {
  const [updates, setUpdates] = useState<
    Record<number, ReportUpdate>
  >({})

  const [selectedId, setSelectedId] = useState<number>(
    mapEvents[0]?.id ?? 0
  )

  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [priorityFilter, setPriorityFilter] = useState('all')
  const [sortBy, setSortBy] = useState('priority')

  const [rejectReason, setRejectReason] = useState('')
  const [showRejectForm, setShowRejectForm] =
    useState(false)
  const [error, setError] = useState('')

  function getStatus(report: RoadEvent): ServiceStatus {
    return updates[report.id]?.status ?? report.status
  }

  const filteredReports = useMemo(() => {
    const result = mapEvents.filter((report) => {
      const status = getStatus(report)
      const priority = getPriority(report)

      return (
        (typeFilter === 'all' ||
          report.type === typeFilter) &&
        (statusFilter === 'all' ||
          status === statusFilter) &&
        (priorityFilter === 'all' ||
          priority === priorityFilter)
      )
    })

    result.sort((a, b) => {
      if (sortBy === 'priority') {
        const difference =
          priorityOrder[getPriority(a)] -
          priorityOrder[getPriority(b)]

        if (difference !== 0) return difference
      }

      if (sortBy === 'oldest') {
        return (
          new Date(a.createdAt).getTime() -
          new Date(b.createdAt).getTime()
        )
      }

      return (
        new Date(b.createdAt).getTime() -
        new Date(a.createdAt).getTime()
      )
    })

    return result
  }, [
    updates,
    typeFilter,
    statusFilter,
    priorityFilter,
    sortBy,
  ])

  const selectedReport =
  filteredReports.find((report) => report.id === selectedId) ??
  filteredReports[0]

  function selectReport(id: number) {
    setSelectedId(id)
    setShowRejectForm(false)
    setRejectReason('')
    setError('')
  }

  function changeStatus(status: ServiceStatus) {
    if (!selectedReport) return

    const currentStatus = getStatus(selectedReport)

    const allowedTransitions: Record<
      ServiceStatus,
      ServiceStatus[]
    > = {
      new: ['accepted', 'rejected'],
      accepted: ['in_progress', 'rejected'],
      in_progress: ['resolved'],
            done: ['resolved'],
      resolved: [],
      rejected: [],
    }

    if (!allowedTransitions[currentStatus].includes(status)) {
      setError('Такий перехід статусу недоступний.')
      return
    }

    if (status === 'rejected' && !rejectReason.trim()) {
      setError('Вкажіть причину відхилення заявки.')
      return
    }

    setUpdates((previous) => ({
      ...previous,
      [selectedReport.id]: {
        status,
        reason:
          status === 'rejected'
            ? rejectReason.trim()
            : undefined,
      },
    }))

    setError('')
    setShowRejectForm(false)
    setRejectReason('')
  }

  const total = mapEvents.length

  const newCount = mapEvents.filter(
    (report) => getStatus(report) === 'new'
  ).length

  const activeCount = mapEvents.filter((report) =>
    ['accepted', 'in_progress'].includes(getStatus(report))
  ).length

  const highCount = mapEvents.filter(
    (report) =>
      getPriority(report) === 'high' &&
      getStatus(report) !== 'resolved' &&
      getStatus(report) !== 'rejected'
  ).length

  const currentStatus = selectedReport
    ? getStatus(selectedReport)
    : 'new'

  return (
    <div className="rm-service-page">
      <div className="rm-service-heading">
        <div>
          <p className="rm-service-eyebrow">
            RoadMap / Робочий простір
          </p>

          <h1>Кабінет дорожньої служби</h1>
          <p>
            Перегляд і опрацювання дорожніх заявок.
          </p>
        </div>

        <span className="rm-service-demo">
          Демонстраційний режим
        </span>
      </div>

      <div className="rm-service-notice">
        Тут використовуються демонстраційні дані RoadMap.
        Зміни статусів не надсилаються на сервер і
        скидаються після оновлення сторінки.
      </div>

      <div className="rm-service-stats">
        <div className="rm-service-stat">
          <span>Усього заявок</span>
          <strong>{total}</strong>
          <small>У демонстраційній черзі</small>
        </div>

        <div className="rm-service-stat">
          <span>Нові заявки</span>
          <strong>{newCount}</strong>
          <small>Очікують розгляду</small>
        </div>

        <div className="rm-service-stat">
          <span>В опрацюванні</span>
          <strong>{activeCount}</strong>
          <small>Прийняті та в роботі</small>
        </div>

        <div className="rm-service-stat">
          <span>Високий пріоритет</span>
          <strong>{highCount}</strong>
          <small>Активні заявки</small>
        </div>
      </div>

      <section className="rm-service-card">
        <div className="rm-service-section-heading">
          <div>
            <h2>Вхідні заявки</h2>
            <p>Фільтруйте та сортуйте звернення.</p>
          </div>

          <span className="rm-service-count">
            {filteredReports.length} із {total}
          </span>
        </div>

        <div className="rm-service-filters">
          <label>
            Тип проблеми
            <select
              value={typeFilter}
              onChange={(event) =>
                setTypeFilter(event.target.value)
              }
            >
              <option value="all">Усі категорії</option>
              {Object.entries(typeLabels).map(
                ([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                )
              )}
            </select>
          </label>

          <label>
            Статус
            <select
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value)
              }
            >
              <option value="all">Усі статуси</option>
              {Object.entries(statusLabels).map(
                ([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                )
              )}
            </select>
          </label>

          <label>
            Пріоритет
            <select
              value={priorityFilter}
              onChange={(event) =>
                setPriorityFilter(event.target.value)
              }
            >
              <option value="all">Усі пріоритети</option>
              {Object.entries(priorityLabels).map(
                ([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                )
              )}
            </select>
          </label>

          <label>
            Сортування
            <select
              value={sortBy}
              onChange={(event) =>
                setSortBy(event.target.value)
              }
            >
              <option value="priority">
                За пріоритетом
              </option>
              <option value="newest">
                Спочатку новіші
              </option>
              <option value="oldest">
                Спочатку старіші
              </option>
            </select>
          </label>

          <button
            type="button"
            className="rm-service-reset"
            onClick={() => {
              setTypeFilter('all')
              setStatusFilter('all')
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
              {filteredReports.map((report) => {
                const status = getStatus(report)
                const priority = getPriority(report)

                return (
                  <tr
                    key={report.id}
                    className={
                    selectedReport?.id === report.id
                         ? 'selected'
                         : ''
                    }
                    onClick={() => selectReport(report.id)}
                  >
                    <td>#{report.id}</td>
                    <td>
                      <button
                        type="button"
                        className="rm-service-row-link"
                        onClick={() =>
                          selectReport(report.id)
                        }
                      >
                        {report.title}
                      </button>
                    </td>
                    <td>{report.address}</td>
                    <td>
                      <span
                        className={
                          `rm-service-priority ` +
                          `rm-service-priority--${priority}`
                        }
                      >
                        {priorityLabels[priority]}
                      </span>
                    </td>
                    <td>
                      <span
                        className={
                          `rm-service-status ` +
                          `rm-service-status--${status}`
                        }
                      >
                        {statusLabels[status]}
                      </span>
                    </td>
                    <td>{formatDate(report.createdAt)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {filteredReports.length === 0 && (
            <p className="rm-service-empty">
              За вибраними фільтрами заявок немає.
            </p>
          )}
        </div>
      </section>

      {selectedReport && (
        <div className="rm-service-details-grid">
          <section className="rm-service-card">
            <div className="rm-service-section-heading">
              <div>
                <h2>Заявка №{selectedReport.id}</h2>
                <p>{selectedReport.title}</p>
              </div>

              <span
                className={
                  `rm-service-status ` +
                  `rm-service-status--${currentStatus}`
                }
              >
                {statusLabels[currentStatus]}
              </span>
            </div>

            <div className="rm-service-detail-list">
              <div>
                <span>Тип проблеми</span>
                <strong>
                  {typeLabels[selectedReport.type]}
                </strong>
              </div>

              <div>
                <span>Адреса</span>
                <strong>{selectedReport.address}</strong>
              </div>

              <div>
                <span>Пріоритет</span>
                <strong>
                  {priorityLabels[getPriority(selectedReport)]}
                </strong>
              </div>

              <div>
                <span>Дата створення</span>
                <strong>
                  {formatDate(selectedReport.createdAt)}
                </strong>
              </div>
            </div>

            <h3>Опрацювання заявки</h3>

            <div className="rm-service-actions">
              {currentStatus === 'new' && (
                <button
                  type="button"
                  onClick={() => changeStatus('accepted')}
                  className="rm-service-primary"
                >
                  Прийняти заявку
                </button>
              )}

              {currentStatus === 'accepted' && (
                <button
                  type="button"
                  onClick={() => changeStatus('in_progress')}
                  className="rm-service-primary"
                >
                  Почати роботи
                </button>
              )}

              {currentStatus === 'in_progress' && (
                <button
                  type="button"
                  onClick={() => changeStatus('resolved')}
                  className="rm-service-primary"
                >
                  Позначити як усунену
                </button>
              )}

              {['new', 'accepted'].includes(currentStatus) && (
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
                  value={rejectReason}
                  onChange={(event) =>
                    setRejectReason(event.target.value)
                  }
                  placeholder="Поясніть, чому заявка відхиляється..."
                />

                <div className="rm-service-actions">
                  <button
                    type="button"
                    className="rm-service-danger"
                    onClick={() => changeStatus('rejected')}
                  >
                    Підтвердити відхилення
                  </button>

                  <button
                    type="button"
                    className="rm-service-reset"
                    onClick={() => {
                      setShowRejectForm(false)
                      setRejectReason('')
                      setError('')
                    }}
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

            {updates[selectedReport.id]?.reason && (
              <div className="rm-service-rejection-note">
                <strong>Причина відхилення:</strong>
                <p>{updates[selectedReport.id].reason}</p>
              </div>
            )}

            {['resolved', 'rejected'].includes(currentStatus) && (
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
                center={[
                  selectedReport.lat,
                  selectedReport.lng,
                ]}
                zoom={16}
                scrollWheelZoom
                style={{ height: '340px', width: '100%' }}
              >
                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                <CircleMarker
                  center={[
                    selectedReport.lat,
                    selectedReport.lng,
                  ]}
                  radius={11}
                  pathOptions={{
                    color: '#ffffff',
                    weight: 3,
                    fillColor: '#2e96d1',
                    fillOpacity: 1,
                  }}
                >
                  <Popup>
                    <strong>{selectedReport.title}</strong>
                    <p>{selectedReport.address}</p>
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
