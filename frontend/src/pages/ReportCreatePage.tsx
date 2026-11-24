import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router'
import { MapContainer, Marker, Popup, TileLayer, useMapEvents } from 'react-leaflet'
import L from 'leaflet'

import type { RoadEventStatus } from '../data/mapEvents'
import {
  confirmReport,
  createReport,
  getNearbyReports,
  getProblemTypes,
  getToken,
  type NearbyReport,
  type ProblemType,
  type ReportCreated,
} from '../services/roadmapApi'
import './ReportCreatePage.css'

type Point = {
  lat: number
  lng: number
}

const LVIV_CENTER: [number, number] = [49.8397, 24.0297]

const MAX_PHOTOS = 3
const MAX_PHOTO_SIZE = 5 * 1024 * 1024
const COMMENT_MAX = 300

const statusLabels: Record<RoadEventStatus, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'У роботі',
  done: 'Виконана',
  resolved: 'Усунена',
  rejected: 'Відхилена',
}

const selectedIcon = L.divIcon({
  className: 'rm-report-map-marker',
  html: '<div class="rm-report-pin">📍</div>',
  iconSize: [40, 44],
  iconAnchor: [20, 40],
})

function LocationPicker({
  point,
  onSelect,
}: {
  point: Point | null
  onSelect: (point: Point) => void
}) {
  const map = useMapEvents({
    click(event) {
      onSelect({
        lat: event.latlng.lat,
        lng: event.latlng.lng,
      })
    },
  })

  useEffect(() => {
    if (point) {
      map.flyTo(
        [point.lat, point.lng],
        Math.max(map.getZoom(), 15),
        { duration: 0.5 }
      )
    }
  }, [map, point])

  if (!point) return null

  return (
    <Marker
      position={[point.lat, point.lng]}
      icon={selectedIcon}
    >
      <Popup>Місце вашої дорожньої проблеми</Popup>
    </Marker>
  )
}

function ReportCreatePage() {
  // Заявку може надіслати лише водій, який увійшов (табл. 14: report.create)
  const isLoggedIn = Boolean(getToken())

  const [problemTypes, setProblemTypes] = useState<ProblemType[]>([])
  const [point, setPoint] = useState<Point | null>(null)
  const [problemType, setProblemType] = useState('')
  const [address, setAddress] = useState('')
  const [comment, setComment] = useState('')
  const [photos, setPhotos] = useState<File[]>([])
  const [agreeData, setAgreeData] = useState(false)

  const [locationMessage, setLocationMessage] = useState('')
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [created, setCreated] = useState<ReportCreated | null>(null)

  // Схожі заявки поруч (GET /reports/nearby) і «Теж бачу»
  const [nearby, setNearby] = useState<NearbyReport[]>([])
  const [nearbyError, setNearbyError] = useState('')
  const [confirmMessage, setConfirmMessage] = useState('')

  // Типи проблем - з довідника бекенду (GET /problem-types)
  useEffect(() => {
    getProblemTypes()
      .then(setProblemTypes)
      .catch((reason: Error) => setError(reason.message))
  }, [])

  const selectedType = problemTypes.find((type) => type.code === problemType)

  // Пошук дублікатів, щойно вибрано і місце, і тип проблеми
  useEffect(() => {
    if (!isLoggedIn || !point || !selectedType) return

    let cancelled = false
    getNearbyReports(point.lat, point.lng, selectedType.id)
      .then((items) => {
        if (!cancelled) {
          setNearby(items)
          setNearbyError('')
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) {
          setNearby([])
          setNearbyError(reason.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [isLoggedIn, point, selectedType])

  const previews = useMemo(
    () =>
      photos.map((file) => ({
        file,
        url: URL.createObjectURL(file),
      })),
    [photos]
  )

  useEffect(() => {
    return () => {
      previews.forEach((item) => URL.revokeObjectURL(item.url))
    }
  }, [previews])

  // Згода потрібна лише тоді, коли водій передає фото або коментар (п. 3.5)
  const needsConsent = photos.length > 0 || comment.trim().length > 0

  function selectPoint(next: Point) {
    setPoint(next)
    setConfirmMessage('')
  }

  function detectLocation() {
    setLocationMessage('')

    if (!navigator.geolocation) {
      setLocationMessage(
        'Ваш браузер не підтримує геолокацію. Виберіть точку на карті.'
      )
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        selectPoint({
          lat: position.coords.latitude,
          lng: position.coords.longitude,
        })

        setLocationMessage('Місце визначено. За потреби перемістіть точку на карті.')
      },
      () => {
        setLocationMessage(
          'Не вдалося отримати геолокацію. Дозвольте доступ або виберіть місце вручну.'
        )
      },
      {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 60000,
      }
    )
  }

  function handlePhotos(event: ChangeEvent<HTMLInputElement>) {
    const newFiles = Array.from(event.target.files ?? [])
    setError('')

    if (photos.length + newFiles.length > MAX_PHOTOS) {
      setError('Можна додати не більше 3 фотографій.')
      event.target.value = ''
      return
    }

    for (const file of newFiles) {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
        setError('Дозволені формати фотографій: JPG, PNG та WebP.')
        event.target.value = ''
        return
      }

      if (file.size > MAX_PHOTO_SIZE) {
        setError('Розмір кожного фото не повинен перевищувати 5 МБ.')
        event.target.value = ''
        return
      }
    }

    setPhotos((previous) => [...previous, ...newFiles])
    event.target.value = ''
  }

  function removePhoto(index: number) {
    setPhotos((previous) =>
      previous.filter((_, itemIndex) => itemIndex !== index)
    )
  }

  // «Теж бачу»: підтвердити наявну заявку замість створення дубліката
  async function handleConfirm(item: NearbyReport) {
    setConfirmMessage('')
    setNearbyError('')
    try {
      const result = await confirmReport(item.id)
      setConfirmMessage(
        `Дякуємо! Ви підтвердили заявку №${item.number}. ` +
          `Підтверджень: ${result.confirmations_count}.`
      )
      setNearby((previous) =>
        previous.map((report) =>
          report.id === item.id
            ? { ...report, confirmations_count: result.confirmations_count }
            : report
        )
      )
    } catch (reason) {
      setNearbyError((reason as Error).message)
    }
  }

  function resetForm() {
    setPoint(null)
    setProblemType('')
    setAddress('')
    setComment('')
    setPhotos([])
    setAgreeData(false)
    setNearby([])
    setConfirmMessage('')
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    setError('')
    setCreated(null)

    if (!isLoggedIn) {
      setError('Щоб надіслати заявку, увійдіть як водій.')
      return
    }

    if (!point) {
      setError('Позначте місце проблеми на карті.')
      return
    }

    if (!problemType) {
      setError('Оберіть тип дорожньої проблеми.')
      return
    }

    if (needsConsent && !agreeData) {
      setError('Щоб передати фото й коментар службі, потрібна згода на передачу даних.')
      return
    }

    setSending(true)
    try {
      const result = await createReport({
        problemType,
        lat: point.lat,
        lng: point.lng,
        comment,
        address,
        photos,
        mediaSharingConsent: agreeData,
      })
      setCreated(result)
      resetForm()
    } catch (reason) {
      // Повідомлення бекенду: «Ділянка не обслуговується», ліміт 10 заявок на годину тощо
      setError((reason as Error).message)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="rm-report-page">
      <div className="rm-report-heading">
        <div>
          <Link to="/" className="rm-report-back">
            ← Повернутися до карти
          </Link>

          <h1>Повідомити про проблему</h1>
          <p>
            Помітили проблему на дорозі? Заповніть форму,
            щоб повідомити про неї.
          </p>
        </div>

        <span className="rm-report-demo-badge">
          Заявка надійде службі
        </span>
      </div>

      {!isLoggedIn && (
        <p className="rm-report-error" role="alert">
          Щоб надіслати заявку, <Link to="/login">увійдіть</Link> або{' '}
          <Link to="/register">зареєструйтесь</Link> як водій.
        </p>
      )}

      {created && (
        <div className="rm-report-success" role="status">
          <strong>✓ Заявку №{created.number} створено!</strong>
          <p>
            {created.service
              ? `Її отримала служба: ${created.service}.`
              : 'Її опрацює адміністратор.'}{' '}
            Статус і зміни видно в картці заявки.
          </p>
          <p>
            <Link to={`/reports/${created.id}`}>Відкрити картку заявки →</Link>
          </p>
        </div>
      )}

      <form
        className="rm-report-form"
        onSubmit={handleSubmit}
        noValidate
      >
        <section className="rm-report-card">
          <div className="rm-report-section-title">
            <span className="rm-report-step">1</span>
            <div>
              <h2>Місце проблеми</h2>
              <p>Натисніть на карту, щоб встановити позначку.</p>
            </div>
          </div>

          <div className="rm-report-map">
            <MapContainer
              center={LVIV_CENTER}
              zoom={13}
              scrollWheelZoom
              style={{ height: '350px', width: '100%' }}
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />

              <LocationPicker
                point={point}
                onSelect={selectPoint}
              />
            </MapContainer>
          </div>

          <div className="rm-report-location-actions">
            <button
              type="button"
              className="rm-report-secondary-button"
              onClick={detectLocation}
            >
              ◎ Визначити моє місце
            </button>

            {point && (
              <span className="rm-report-coordinates">
                ✓ Точку вибрано: {point.lat.toFixed(5)},{' '}
                {point.lng.toFixed(5)}
              </span>
            )}
          </div>

          {locationMessage && (
            <p className="rm-report-hint" role="status">
              {locationMessage}
            </p>
          )}

          <label
            className="rm-report-label"
            htmlFor="rm-report-address"
          >
            Адреса або орієнтир (необов'язково)
          </label>

          <input
            id="rm-report-address"
            className="rm-report-control"
            placeholder="Наприклад: вул. Городоцька, 120, біля зупинки"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            maxLength={255}
          />
        </section>

        <section className="rm-report-card">
          <div className="rm-report-section-title">
            <span className="rm-report-step">2</span>
            <div>
              <h2>Інформація про проблему</h2>
              <p>Оберіть категорію та за бажанням опишіть ситуацію.</p>
            </div>
          </div>

          <label
            className="rm-report-label"
            htmlFor="rm-report-type"
          >
            Тип дорожньої проблеми *
          </label>

          <select
            id="rm-report-type"
            className="rm-report-control"
            value={problemType}
            onChange={(event) => {
              setProblemType(event.target.value)
              setConfirmMessage('')
            }}
            required
          >
            <option value="">Оберіть тип проблеми</option>

            {problemTypes.map((type) => (
              <option key={type.code} value={type.code}>
                {type.name}
              </option>
            ))}
          </select>

          <label
            className="rm-report-label"
            htmlFor="rm-report-comment"
          >
            Коментар (необов'язково)
          </label>

          <textarea
            id="rm-report-comment"
            className="rm-report-control rm-report-textarea"
            placeholder="Наприклад: велика яма посеред дороги, яка заважає проїзду автомобілів..."
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            maxLength={COMMENT_MAX}
            rows={4}
          />

          <div className="rm-report-counter">
            {comment.length}/{COMMENT_MAX} символів
          </div>
        </section>

        <section className="rm-report-card">
          <div className="rm-report-section-title">
            <span className="rm-report-step">3</span>
            <div>
              <h2>Фотографії</h2>
              <p>
                За бажанням додайте до 3 фото. Формати JPG, PNG або WebP,
                до 5 МБ кожне. Геодані з фото видаляються автоматично.
              </p>
            </div>
          </div>

          <label
            htmlFor="rm-report-photos"
            className="rm-report-upload"
          >
            <span className="rm-report-upload-icon">＋</span>
            <strong>Додати фотографії</strong>
            <span>Обрано {photos.length} із {MAX_PHOTOS}</span>
          </label>

          <input
            id="rm-report-photos"
            className="rm-report-file-input"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            onChange={handlePhotos}
            disabled={photos.length >= MAX_PHOTOS}
          />

          {previews.length > 0 && (
            <div className="rm-report-previews">
              {previews.map((preview, index) => (
                <div
                  className="rm-report-preview"
                  key={`${preview.file.name}-${preview.file.lastModified}-${index}`}
                >
                  <img
                    src={preview.url}
                    alt={`Фото ${index + 1}`}
                  />

                  <button
                    type="button"
                    onClick={() => removePhoto(index)}
                    aria-label={`Видалити фото ${index + 1}`}
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="rm-report-card">
          <div className="rm-report-section-title">
            <span className="rm-report-step">4</span>
            <div>
              <h2>Можливі дублікати поруч</h2>
              <p>
                Перевірте, чи хтось уже повідомляв про схожу проблему.
              </p>
            </div>
          </div>

          {!isLoggedIn ? (
            <p className="rm-report-empty">
              Перевірка дублікатів доступна після входу.
            </p>
          ) : !point || !problemType ? (
            <p className="rm-report-empty">
              Виберіть місце та тип проблеми, щоб побачити
              схожі повідомлення поблизу.
            </p>
          ) : nearby.length === 0 ? (
            <p className="rm-report-empty">
              Схожих відкритих заявок у радіусі 30 м не знайдено.
            </p>
          ) : (
            <div className="rm-report-duplicates">
              <p className="rm-report-duplicate-warning">
                Знайдено схожі заявки поблизу. Якщо це та сама проблема,
                натисніть «Теж бачу» замість створення нової заявки.
              </p>

              {nearby.map((item) => (
                <div
                  className="rm-report-duplicate"
                  key={item.id}
                >
                  <div>
                    <strong>Заявка №{item.number}</strong>
                    <p>{item.address ?? 'Адресу не вказано'}</p>
                  </div>

                  <span>
                    {Math.round(item.distance_m)} м ·{' '}
                    {statusLabels[item.status]} · підтверджень:{' '}
                    {item.confirmations_count}
                  </span>

                  <button
                    type="button"
                    className="rm-report-secondary-button"
                    onClick={() => handleConfirm(item)}
                  >
                    Теж бачу
                  </button>
                </div>
              ))}
            </div>
          )}

          {confirmMessage && (
            <p className="rm-report-hint" role="status">
              {confirmMessage}
            </p>
          )}

          {nearbyError && (
            <p className="rm-report-error" role="alert">
              {nearbyError}
            </p>
          )}
        </section>

        <section className="rm-report-card">
          <label className="rm-report-consent">
            <input
              type="checkbox"
              checked={agreeData}
              onChange={(event) =>
                setAgreeData(event.target.checked)
              }
            />

            <span>
              Надаю згоду на передачу фотографій та коментаря
              службі для опрацювання заявки
              {needsConsent ? ' *' : ' (потрібна, якщо додаєте фото або коментар)'}
            </span>
          </label>

          {error && (
            <p className="rm-report-error" role="alert">
              {error}
            </p>
          )}

          <div className="rm-report-submit-row">
            <Link
              to="/"
              className="rm-report-secondary-button"
            >
              Скасувати
            </Link>

            <button
              type="submit"
              className="rm-report-submit-button"
              disabled={sending || !isLoggedIn}
            >
              {sending ? 'Надсилання…' : 'Надіслати заявку'}
            </button>
          </div>
        </section>
      </form>
    </div>
  )
}

export default ReportCreatePage