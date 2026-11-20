
import { Link, useParams } from 'react-router'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import L from 'leaflet'

import {
  mapEvents,
  type RoadEventStatus,
  type RoadEventType,
} from '../data/mapEvents'

import './ReportDetailsPage.css'

const typeLabels: Record<RoadEventType, string> = {
  pothole: 'Пошкодження дороги',
  accident: 'Дорожня аварія',
  obstacle: 'Перешкода на дорозі',
  roadworks: 'Ремонтні роботи',
  traffic_light: 'Несправний світлофор',
}

const statusLabels: Record<RoadEventStatus, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'В роботі',
  resolved: 'Усунена',
}

const statusOrder: RoadEventStatus[] = [
  'new',
  'accepted',
  'in_progress',
  'resolved',
]

const markerIcon = L.divIcon({
  className: 'rm-details-marker',
  html: '<div class="rm-details-map-pin">●</div>',
  iconSize: [38, 38],
  iconAnchor: [19, 19],
})

function formatDate(date: string): string {
  return new Date(date).toLocaleString('uk-UA', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ReportDetailsPage() {
  const { id } = useParams()

  const report = mapEvents.find(
    (event) => String(event.id) === id
  )

  if (!report) {
    return (
      <div className="rm-details-page">
        <Link to="/" className="rm-details-back">
          ← Повернутися до карти
        </Link>

        <section className="rm-details-card">
          <h1>Заявку не знайдено</h1>
          <p>
            Можливо, вона відсутня серед демонстраційних подій.
          </p>
        </section>
      </div>
    )
  }

  const currentStatusIndex = statusOrder.indexOf(report.status)

  // Демонстраційна історія: реальні зміни статусів
  // будуть завантажуватися через API.
  const history = statusOrder
    .slice(0, currentStatusIndex + 1)
    .map((status, index) => {
      const created = new Date(report.createdAt).getTime()
      const now = Date.now()
      const duration = Math.max(0, now - created)

      const time =
        created +
        (index / Math.max(currentStatusIndex, 1)) * duration

      return {
        status,
        date: new Date(time).toISOString(),
      }
    })

  return (
    <div className="rm-details-page">
      <Link to="/" className="rm-details-back">
        ← Повернутися до карти доріг
      </Link>

      <div className="rm-details-heading">
        <div>
          <p className="rm-details-eyebrow">
            RoadMap / Дорожні події
          </p>

          <h1>Картка заявки №{report.id}</h1>

          <p>
            Інформація про дорожню проблему та її опрацювання.
          </p>
        </div>

        <span
          className={`rm-details-status rm-details-status--${report.status}`}
        >
          {statusLabels[report.status]}
        </span>
      </div>

      <div className="rm-details-notice">
        Демонстраційна заявка. Дані не відображають
        реальний стан доріг.
      </div>

      <div className="rm-details-grid">
        <div className="rm-details-main">
          <section className="rm-details-card">
            <h2>Інформація про заявку</h2>

            <div className="rm-details-info-grid">
              <div>
                <span className="rm-details-label">
                  Тип проблеми
                </span>
                <strong>{typeLabels[report.type]}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Номер заявки
                </span>
                <strong>№{report.id}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Поточний статус
                </span>
                <strong>{statusLabels[report.status]}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Дата створення
                </span>
                <strong>{formatDate(report.createdAt)}</strong>
              </div>
            </div>

            <div className="rm-details-description">
              <span className="rm-details-label">
                Назва проблеми
              </span>
              <p>{report.title}</p>
            </div>

            <div className="rm-details-description">
              <span className="rm-details-label">
                Адреса
              </span>
              <p>{report.address}</p>
            </div>
          </section>

          <section className="rm-details-card">
            <h2>Місце проблеми на карті</h2>

            <div className="rm-details-map">
              <MapContainer
                center={[report.lat, report.lng]}
                zoom={16}
                scrollWheelZoom
                style={{ width: '100%', height: '320px' }}
              >
                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                <Marker
                  position={[report.lat, report.lng]}
                  icon={markerIcon}
                >
                  <Popup>
                    <strong>{report.title}</strong>
                    <p>{report.address}</p>
                  </Popup>
                </Marker>
              </MapContainer>
            </div>

            <p className="rm-details-coordinates">
              Координати: {report.lat.toFixed(5)},{' '}
              {report.lng.toFixed(5)}
            </p>
          </section>

          <section className="rm-details-card">
            <h2>Фотографії проблеми</h2>

            <div className="rm-details-photo-empty">
              <span aria-hidden="true">▧</span>
              <p>Для цієї демонстраційної події фото не додано.</p>
              <small>
                Фотографії з'являться після підключення
                заявок до серверного API.
              </small>
            </div>
          </section>
        </div>

        <aside className="rm-details-side">
          <section className="rm-details-card">
            <h2>Історія змін статусу</h2>

            <p className="rm-details-history-note">
              Приклад історії для демонстрації інтерфейсу.
            </p>

            <div className="rm-details-timeline">
              {history.map((item, index) => (
                <div
                  className="rm-details-timeline-item"
                  key={item.status}
                >
                  <span
                    className={`rm-details-timeline-dot${
                      index === history.length - 1
                        ? ' current'
                        : ''
                    }`}
                  />

                  <div>
                    <strong>
                      {statusLabels[item.status]}
                    </strong>

                    <p>{formatDate(item.date)}</p>

                    {index === 0 && (
                      <small>Заявку створено</small>
                    )}

                    {index === history.length - 1 && (
                      <small>Поточний статус</small>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="rm-details-card">
            <h2>Про заявку</h2>

            <p className="rm-details-side-text">
              Тут можна переглянути поточний стан дорожньої
              проблеми та послідовність її опрацювання.
            </p>

            <p className="rm-details-side-text">
              Після інтеграції з API історія відображатиме
              фактичні зміни статусів із сервера.
            </p>
          </section>

          <Link
            to="/"
            className="rm-details-primary-button"
          >
            Повернутися до карти
          </Link>
        </aside>
      </div>
    </div>
  )
}

export default ReportDetailsPage
