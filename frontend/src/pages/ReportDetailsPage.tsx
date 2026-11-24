import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import L from 'leaflet'

import type { RoadEventStatus } from '../data/mapEvents'
import {
  ApiError,
  getMapReports,
  getPhotoUrl,
  getReport,
  getReportHistory,
  getToken,
  type HistoryItem,
  type MapReport,
  type PhotoInfo,
  type Priority,
  type ReportCard,
} from '../services/roadmapApi'

import './ReportDetailsPage.css'

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

const photoKindLabels: Record<PhotoInfo['kind'], string> = {
  before: 'Фото від водія',
  after: 'Фото після робіт',
  act: 'Акт виконаних робіт',
}

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

// Картка з бекенду: повна (GET /reports/{id}) або публічна з карти для гостя
type LoadedReport =
  | { kind: 'full'; card: ReportCard; history: HistoryItem[] }
  | { kind: 'public'; card: MapReport }

type LoadedPhoto = PhotoInfo & { src: string }

function ReportDetailsPage() {
  const { id } = useParams()
  const reportId = Number(id)

  const [report, setReport] = useState<LoadedReport | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [photos, setPhotos] = useState<LoadedPhoto[]>([])

  useEffect(() => {
    let cancelled = false

    async function load() {
      // Гість або чужа заявка: показуємо публічні дані з карти (без автора, фото й історії)
      async function loadPublic(message: string) {
        const reports = await getMapReports({ limit: 1000 })
        const found = reports.find((item) => item.id === reportId)
        if (cancelled) return
        if (found) setReport({ kind: 'public', card: found })
        else setError(message)
      }

      try {
        if (!getToken()) {
          await loadPublic('Заявку не знайдено або вона вже закрита.')
          return
        }
        const [card, history] = await Promise.all([
          getReport(reportId),
          getReportHistory(reportId),
        ])
        if (!cancelled) setReport({ kind: 'full', card, history: history.items })
      } catch (reason) {
        if (cancelled) return
        if (reason instanceof ApiError && (reason.status === 401 || reason.status === 403)) {
          await loadPublic('Ця заявка вам недоступна.')
        } else {
          setError((reason as Error).message)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [reportId])

  // Фото захищені токеном: завантажуємо їх окремо й показуємо через тимчасові адреси
  useEffect(() => {
    if (report?.kind !== 'full' || report.card.photos.length === 0) return

    let cancelled = false
    const created: string[] = []

    Promise.all(
      report.card.photos.map(async (photo) => {
        const src = await getPhotoUrl(photo)
        created.push(src)
        return { ...photo, src }
      })
    )
      .then((items) => {
        if (!cancelled) setPhotos(items)
      })
      .catch(() => {
        if (!cancelled) setPhotos([])
      })

    return () => {
      cancelled = true
      created.forEach((src) => URL.revokeObjectURL(src))
    }
  }, [report])

  if (loading) {
    return (
      <div className="rm-details-page">
        <section className="rm-details-card">
          <p>Завантаження заявки…</p>
        </section>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="rm-details-page">
        <Link to="/" className="rm-details-back">
          ← Повернутися до карти
        </Link>

        <section className="rm-details-card">
          <h1>Заявку не знайдено</h1>
          <p>{error || 'Заявку не знайдено.'}</p>
        </section>
      </div>
    )
  }

  const card = report.card
  const full = report.kind === 'full' ? report.card : null
  const history = report.kind === 'full' ? report.history : []

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

          <h1>Картка заявки №{card.number}</h1>

          <p>
            Інформація про дорожню проблему та її опрацювання.
          </p>
        </div>

        <span
          className={`rm-details-status rm-details-status--${card.status}`}
        >
          {statusLabels[card.status]}
        </span>
      </div>

      {report.kind === 'public' && (
        <div className="rm-details-notice">
          Показано публічні дані заявки. Фото, коментар та історію
          змін бачать автор заявки й служба після{' '}
          <Link to="/login">входу в систему</Link>.
        </div>
      )}

      {full?.reject_reason && (
        <div className="rm-details-notice">
          Причина відхилення: {full.reject_reason}
        </div>
      )}

      <div className="rm-details-grid">
        <div className="rm-details-main">
          <section className="rm-details-card">
            <h2>Інформація про заявку</h2>

            <div className="rm-details-info-grid">
              <div>
                <span className="rm-details-label">
                  Тип проблеми
                </span>
                <strong>{card.problem_label}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Номер заявки
                </span>
                <strong>№{card.number}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Поточний статус
                </span>
                <strong>{statusLabels[card.status]}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Дата створення
                </span>
                <strong>{formatDate(card.created_at)}</strong>
              </div>

              <div>
                <span className="rm-details-label">
                  Підтвердили «Теж бачу»
                </span>
                <strong>{card.confirmations_count}</strong>
              </div>

              {full && (
                <div>
                  <span className="rm-details-label">
                    Служба
                  </span>
                  <strong>{full.service ?? 'Не визначено'}</strong>
                </div>
              )}

              {full?.copy_service && (
                <div>
                  <span className="rm-details-label">
                    Копія службі
                  </span>
                  <strong>{full.copy_service}</strong>
                </div>
              )}

              {full?.priority && (
                <div>
                  <span className="rm-details-label">
                    Пріоритет
                  </span>
                  <strong>{priorityLabels[full.priority]}</strong>
                </div>
              )}

              {full?.deadline && (
                <div>
                  <span className="rm-details-label">
                    Орієнтовний строк
                  </span>
                  <strong>
                    {new Date(full.deadline).toLocaleDateString('uk-UA')}
                  </strong>
                </div>
              )}

              {full?.progress_percent != null && (
                <div>
                  <span className="rm-details-label">
                    Виконано робіт
                  </span>
                  <strong>{full.progress_percent} %</strong>
                </div>
              )}

              {full?.author && (
                <div>
                  <span className="rm-details-label">
                    Автор
                  </span>
                  <strong>{full.author}</strong>
                </div>
              )}
            </div>

            <div className="rm-details-description">
              <span className="rm-details-label">
                Адреса
              </span>
              <p>{card.address ?? 'Адресу не вказано'}</p>
            </div>

            {full?.comment && (
              <div className="rm-details-description">
                <span className="rm-details-label">
                  Коментар водія
                </span>
                <p>{full.comment}</p>
              </div>
            )}
          </section>

          <section className="rm-details-card">
            <h2>Місце проблеми на карті</h2>

            <div className="rm-details-map">
              <MapContainer
                center={[card.lat, card.lng]}
                zoom={16}
                scrollWheelZoom
                style={{ width: '100%', height: '320px' }}
              >
                <TileLayer
                  attribution="&copy; OpenStreetMap contributors"
                  url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                />

                <Marker
                  position={[card.lat, card.lng]}
                  icon={markerIcon}
                >
                  <Popup>
                    <strong>
                      {card.problem_label} №{card.number}
                    </strong>
                    <p>{card.address ?? 'Адресу не вказано'}</p>
                  </Popup>
                </Marker>
              </MapContainer>
            </div>

            <p className="rm-details-coordinates">
              Координати: {card.lat.toFixed(5)},{' '}
              {card.lng.toFixed(5)}
            </p>
          </section>

          <section className="rm-details-card">
            <h2>Фотографії</h2>

            {photos.length === 0 ? (
              <div className="rm-details-photo-empty">
                <span aria-hidden="true">▧</span>
                <p>
                  {report.kind === 'public'
                    ? 'Фото бачать лише автор заявки та служба.'
                    : full && full.photos.length > 0
                      ? 'Завантаження фото…'
                      : 'До цієї заявки фото не додано.'}
                </p>
              </div>
            ) : (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
                  gap: '12px',
                }}
              >
                {photos.map((photo) => (
                  <figure key={photo.id} style={{ margin: 0 }}>
                    {photo.mime_type === 'application/pdf' ? (
                      <a href={photo.src} target="_blank" rel="noreferrer">
                        📄 Відкрити акт (PDF)
                      </a>
                    ) : (
                      <a href={photo.src} target="_blank" rel="noreferrer">
                        <img
                          src={photo.src}
                          alt={photoKindLabels[photo.kind]}
                          style={{
                            width: '100%',
                            height: '140px',
                            objectFit: 'cover',
                            borderRadius: '10px',
                          }}
                        />
                      </a>
                    )}
                    <figcaption className="rm-details-label">
                      {photoKindLabels[photo.kind]}
                    </figcaption>
                  </figure>
                ))}
              </div>
            )}
          </section>
        </div>

        <aside className="rm-details-side">
          <section className="rm-details-card">
            <h2>Історія змін статусу</h2>

            {history.length === 0 ? (
              <p className="rm-details-history-note">
                {report.kind === 'public'
                  ? 'Історію змін бачать автор заявки та служба.'
                  : 'Історія порожня.'}
              </p>
            ) : (
              <div className="rm-details-timeline">
                {history.map((item, index) => (
                  <div
                    className="rm-details-timeline-item"
                    key={`${item.to_status}-${item.changed_at}`}
                  >
                    <span
                      className={`rm-details-timeline-dot${
                        index === history.length - 1
                          ? ' current'
                          : ''
                      }`}
                    />

                    <div>
                      <strong>{item.to_label}</strong>

                      <p>{formatDate(item.changed_at)}</p>

                      {item.comment && <p>{item.comment}</p>}

                      {index === 0 && <small>Заявку створено</small>}

                      {index === history.length - 1 && index > 0 && (
                        <small>Поточний статус</small>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rm-details-card">
            <h2>Про заявку</h2>

            <p className="rm-details-side-text">
              Дані завантажено з бази RoadMap. Кожна зміна статусу
              записується в історію, а автор отримує сповіщення.
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