
import { useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react'
import { Link } from 'react-router'
import { MapContainer, Marker, Popup, TileLayer, useMapEvents } from 'react-leaflet'
import L from 'leaflet'

import { mapEvents, type RoadEventType } from '../data/mapEvents'
import './ReportCreatePage.css'

type Point = {
  lat: number
  lng: number
}

const LVIV_CENTER: [number, number] = [49.8397, 24.0297]

const MAX_PHOTOS = 3
const MAX_PHOTO_SIZE = 5 * 1024 * 1024
const NEARBY_DISTANCE_METERS = 30

const problemTypes: { value: RoadEventType; label: string }[] = [
  { value: 'pothole', label: 'Яма або пошкодження дороги' },
  { value: 'accident', label: 'Дорожня аварія' },
  { value: 'obstacle', label: 'Перешкода на дорозі' },
  { value: 'roadworks', label: 'Проблема з ремонтними роботами' },
  { value: 'traffic_light', label: 'Несправний світлофор' },
]

const statusLabels = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'У роботі',
  resolved: 'Усунена',
}

const selectedIcon = L.divIcon({
  className: 'rm-report-map-marker',
  html: '<div class="rm-report-pin">📍</div>',
  iconSize: [40, 44],
  iconAnchor: [20, 40],
})

function distanceInMeters(a: Point, b: Point): number {
  const radius = 6371000
  const toRadians = (degrees: number) => (degrees * Math.PI) / 180

  const dLat = toRadians(b.lat - a.lat)
  const dLng = toRadians(b.lng - a.lng)

  const value =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRadians(a.lat)) *
      Math.cos(toRadians(b.lat)) *
      Math.sin(dLng / 2) ** 2

  return 2 * radius * Math.asin(Math.sqrt(value))
}

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
  const [point, setPoint] = useState<Point | null>(null)
  const [problemType, setProblemType] = useState<RoadEventType | ''>('')
  const [comment, setComment] = useState('')
  const [photos, setPhotos] = useState<File[]>([])
  const [agreeData, setAgreeData] = useState(false)

  const [locationMessage, setLocationMessage] = useState('')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState(false)

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

  // Пошук можливих повторних повідомлень поруч
  const nearbyEvents = useMemo(() => {
    if (!point || !problemType) return []

    return mapEvents
      .filter((event) => event.type === problemType)
      .map((event) => ({
        ...event,
        distance: distanceInMeters(point, {
          lat: event.lat,
          lng: event.lng,
        }),
      }))
      .filter((event) => event.distance <= NEARBY_DISTANCE_METERS)
      .sort((a, b) => a.distance - b.distance)
      .slice(0, 5)
  }, [point, problemType])

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
        setPoint({
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

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    setError('')
    setSuccess(false)

    if (!point) {
      setError('Позначте місце проблеми на карті.')
      return
    }

    if (!problemType) {
      setError('Оберіть тип дорожньої проблеми.')
      return
    }

    if (photos.length < 1 || photos.length > 3) {
      setError('Додайте від 1 до 3 фотографій.')
      return
    }

    if (comment.trim().length < 10) {
      setError('Опишіть проблему хоча б 10 символами.')
      return
    }

    if (!agreeData) {
      setError('Потрібно надати згоду на передачу даних.')
      return
    }

    // Демонстраційний режим:
    // до підключення бекенду заявка не надсилається.
    setSuccess(true)
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
          Демонстраційна форма
        </span>
      </div>

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
                onSelect={setPoint}
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
        </section>

        <section className="rm-report-card">
          <div className="rm-report-section-title">
            <span className="rm-report-step">2</span>
            <div>
              <h2>Інформація про проблему</h2>
              <p>Оберіть категорію та коротко опишіть ситуацію.</p>
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
            onChange={(event) =>
              setProblemType(event.target.value as RoadEventType | '')
            }
            required
          >
            <option value="">Оберіть тип проблеми</option>

            {problemTypes.map((type) => (
              <option key={type.value} value={type.value}>
                {type.label}
              </option>
            ))}
          </select>

          <label
            className="rm-report-label"
            htmlFor="rm-report-comment"
          >
            Коментар *
          </label>

          <textarea
            id="rm-report-comment"
            className="rm-report-control rm-report-textarea"
            placeholder="Наприклад: велика яма посеред дороги, яка заважає проїзду автомобілів..."
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            maxLength={300}
            rows={4}
            required
          />

          <div className="rm-report-counter">
            {comment.length}/300 символів
          </div>
        </section>

        <section className="rm-report-card">
          <div className="rm-report-section-title">
            <span className="rm-report-step">3</span>
            <div>
              <h2>Фотографії</h2>
              <p>
                Додайте від 1 до 3 фото. Формати JPG, PNG або WebP,
                до 5 МБ кожне.
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

          {!point || !problemType ? (
            <p className="rm-report-empty">
              Виберіть місце та тип проблеми, щоб побачити
              схожі повідомлення поблизу.
            </p>
          ) : nearbyEvents.length === 0 ? (
            <p className="rm-report-empty">
              Серед демонстраційних подій схожих повідомлень
              у радіусі 30 м не знайдено.
            </p>
          ) : (
            <div className="rm-report-duplicates">
              <p className="rm-report-duplicate-warning">
                Знайдено схожі повідомлення поблизу.
                Перегляньте їх перед створенням нової заявки.
              </p>

              {nearbyEvents.map((item) => (
                <div
                  className="rm-report-duplicate"
                  key={item.id}
                >
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.address}</p>
                  </div>

                  <span>
                    {Math.round(item.distance)} м ·{' '}
                    {statusLabels[item.status]}
                  </span>
                </div>
              ))}
            </div>
          )}

          <p className="rm-report-hint">
            Перевірка працює на демонстраційних даних RoadMap.
            Остаточне визначення дублікатів виконуватиметься
            після інтеграції з сервером.
          </p>
        </section>

        <section className="rm-report-card">
          <label className="rm-report-consent">
            <input
              type="checkbox"
              checked={agreeData}
              onChange={(event) =>
                setAgreeData(event.target.checked)
              }
              required
            />

            <span>
              Надаю згоду на передачу місця проблеми,
              фотографій та коментаря для опрацювання заявки.
            </span>
          </label>

          {error && (
            <p className="rm-report-error" role="alert">
              {error}
            </p>
          )}

          {success && (
            <div className="rm-report-success" role="status">
              <strong>✓ Форму заповнено правильно!</strong>
              <p>
                Це демонстраційний режим. Заявку ще не
                надіслано та не збережено на сервері.
              </p>
            </div>
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
            >
              Перевірити заявку
            </button>
          </div>
        </section>
      </form>
    </div>
  )
}

export default ReportCreatePage
