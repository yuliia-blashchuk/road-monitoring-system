import { useState, type CSSProperties } from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import { Link } from 'react-router'

import {
  type RoadEvent,
  type RoadEventType,
  type RoadEventStatus,
} from '../data/mapEvents'
import { useRoadEvents } from '../services/useRoadEvents'

import 'leaflet/dist/leaflet.css'
import 'react-leaflet-cluster/dist/assets/MarkerCluster.css'
import 'react-leaflet-cluster/dist/assets/MarkerCluster.Default.css'

// Кольори та позначення типів дорожніх подій
const eventStyles: Record<
  RoadEventType,
  { color: string; symbol: string; label: string }
> = {
  pothole: {
    color: '#E89B27',
    symbol: '⚠',
    label: 'Яма',
  },
  damaged_surface: {
    color: '#C77A1C',
    symbol: '≈',
    label: 'Пошкоджене покриття',
  },
  accident: {
    color: '#E05252',
    symbol: '!',
    label: 'Аварія',
  },
  obstacle: {
    color: '#8B65CC',
    symbol: '!',
    label: 'Перешкода',
  },
  roadworks: {
    color: '#247ED0',
    symbol: '⚒',
    label: 'Ремонтні роботи',
  },
  traffic_light: {
    color: '#DA8040',
    symbol: '●',
    label: 'Світлофор',
  },
  other: {
    color: '#6B7A89',
    symbol: '?',
    label: 'Інше',
  },
}

// Назви та кольори статусів
const statuses: Record<
  RoadEventStatus,
  { label: string; color: string }
> = {
  new: {
    label: 'Нова',
    color: '#E05252',
  },
  accepted: {
    label: 'Прийнята',
    color: '#E89B27',
  },
  in_progress: {
    label: 'В роботі',
    color: '#247ED0',
  },
  done: {
    label: 'Виконана',
    color: '#2BA0A0',
  },
  resolved: {
    label: 'Усунена',
    color: '#37A576',
  },
  rejected: {
    label: 'Відхилена',
    color: '#8A94A6',
  },
}

// Періоди фільтрації
type DateFilter = 'all' | '7' | '30' | '90' | 'custom'

// Стиль фільтрів у кольорах RoadMap
const filterStyle: CSSProperties = {
  padding: '10px 12px',
  borderRadius: '10px',
  border: '1px solid #cbdfee',
  backgroundColor: '#f4faff',
  color: '#17365d',
  fontSize: '13px',
  cursor: 'pointer',
  minHeight: '40px',
  maxWidth: '100%',
}

const labelStyle: CSSProperties = {
  display: 'block',
  fontSize: '11px',
  fontWeight: 600,
  color: '#6686a2',
  marginBottom: '5px',
}

// Перетворення дати на формат YYYY-MM-DD
function toDateString(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

// Створення кольорової позначки на карті
function createEventIcon(event: RoadEvent) {
  const style = eventStyles[event.type]
  const status = statuses[event.status]

  return L.divIcon({
    className: 'roadmap-event-marker',
    html: `
      <div style="
        width: 36px;
        height: 36px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: ${style.color};
        border: 3px solid ${status.color};
        border-radius: 50%;
        color: white;
        font-size: 21px;
        font-weight: bold;
        box-shadow: 0 3px 10px rgba(0,0,0,0.25);
      ">
        ${style.symbol}
      </div>
    `,
    iconSize: [42, 42],
    iconAnchor: [21, 21],
    popupAnchor: [0, -20],
  })
}

// Основний компонент карти
function RoadMapMap() {
  // Заявки з бекенду (GET /reports) замість демо-даних
  const { events: mapEvents } = useRoadEvents()

  // Фільтр за типом дорожньої події
  const [selectedType, setSelectedType] =
    useState<RoadEventType | 'all'>('all')

  // Фільтр за статусом
  const [selectedStatus, setSelectedStatus] =
    useState<RoadEventStatus | 'all'>('all')

  // Фільтр за періодом
  const [selectedPeriod, setSelectedPeriod] =
    useState<DateFilter>('all')

  // Власний період
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // Поточна дата
  const today = toDateString(new Date())

  // Початок вибраного періоду
  let periodStart = ''

  if (
    selectedPeriod === '7' ||
    selectedPeriod === '30' ||
    selectedPeriod === '90'
  ) {
    const startDate = new Date()

    startDate.setDate(
      startDate.getDate() - Number(selectedPeriod) + 1
    )

    periodStart = toDateString(startDate)
  }

  // Перевірка власного діапазону
  const invalidDateRange =
    selectedPeriod === 'custom' &&
    dateFrom !== '' &&
    dateTo !== '' &&
    dateFrom > dateTo

  // Одночасна фільтрація за типом, статусом і датою
  const filteredEvents = mapEvents.filter((event) => {
    const matchesType =
      selectedType === 'all' ||
      event.type === selectedType

    const matchesStatus =
      selectedStatus === 'all' ||
      event.status === selectedStatus

    const eventDate = event.createdAt.slice(0, 10)

    let matchesDate = true

    // Готові періоди: 7, 30 або 90 днів
    if (
      selectedPeriod === '7' ||
      selectedPeriod === '30' ||
      selectedPeriod === '90'
    ) {
      matchesDate =
        eventDate >= periodStart &&
        eventDate <= today
    }

    // Власний діапазон дат
    if (selectedPeriod === 'custom') {
      matchesDate =
        !invalidDateRange &&
        (dateFrom === '' || eventDate >= dateFrom) &&
        (dateTo === '' || eventDate <= dateTo)
    }

    return matchesType && matchesStatus && matchesDate
  })

  // Чи вибрано хоча б один фільтр
  const hasActiveFilters =
    selectedType !== 'all' ||
    selectedStatus !== 'all' ||
    selectedPeriod !== 'all' ||
    dateFrom !== '' ||
    dateTo !== ''

  // Скидання всіх фільтрів
  function resetFilters() {
    setSelectedType('all')
    setSelectedStatus('all')
    setSelectedPeriod('all')
    setDateFrom('')
    setDateTo('')
  }

  return (
    <div>
      {/* Панель фільтрів */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          marginBottom: '14px',
          alignItems: 'flex-end',
        }}
      >
        {/* Фільтр за типом */}
        <div>
          <label
            htmlFor="map-filter-type"
            style={labelStyle}
          >
            Тип проблеми
          </label>

          <select
            id="map-filter-type"
            value={selectedType}
            onChange={(event) =>
              setSelectedType(
                event.target.value as RoadEventType | 'all'
              )
            }
            style={filterStyle}
          >
            <option value="all">Усі категорії</option>
            <option value="pothole">Ями</option>
            <option value="damaged_surface">
              Пошкоджене покриття
            </option>
            <option value="accident">Аварії</option>
            <option value="obstacle">Перешкоди</option>
            <option value="traffic_light">Світлофори</option>
            <option value="other">Інше</option>
          </select>
        </div>

        {/* Фільтр за статусом */}
        <div>
          <label
            htmlFor="map-filter-status"
            style={labelStyle}
          >
            Статус
          </label>

          <select
            id="map-filter-status"
            value={selectedStatus}
            onChange={(event) =>
              setSelectedStatus(
                event.target.value as RoadEventStatus | 'all'
              )
            }
            style={filterStyle}
          >
            <option value="all">Усі статуси</option>
            <option value="new">Нові</option>
            <option value="accepted">Прийняті</option>
            <option value="in_progress">В роботі</option>
            <option value="done">Виконані</option>
          </select>
        </div>

        {/* Фільтр за періодом */}
        <div>
          <label
            htmlFor="map-filter-period"
            style={labelStyle}
          >
            Період
          </label>

          <select
            id="map-filter-period"
            value={selectedPeriod}
            onChange={(event) =>
              setSelectedPeriod(
                event.target.value as DateFilter
              )
            }
            style={filterStyle}
          >
            <option value="all">
              За весь час
            </option>
            <option value="7">
              Останні 7 днів
            </option>
            <option value="30">
              Останні 30 днів
            </option>
            <option value="90">
              Останні 90 днів
            </option>
            <option value="custom">
              Власний період
            </option>
          </select>
        </div>

        {/* Скидання фільтрів */}
        {hasActiveFilters && (
          <button
            type="button"
            onClick={resetFilters}
            style={{
              ...filterStyle,
              backgroundColor: '#e4f3ff',
              color: '#257eb6',
              border: '1px solid #c6e4f9',
              fontWeight: 600,
            }}
          >
            ↻ Скинути
          </button>
        )}
      </div>

      {/* Вибір власного періоду */}
      {selectedPeriod === 'custom' && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '12px',
            marginBottom: '14px',
            alignItems: 'flex-end',
          }}
        >
          <div>
            <label
              htmlFor="map-date-from"
              style={labelStyle}
            >
              Дата від
            </label>

            <input
              id="map-date-from"
              type="date"
              value={dateFrom}
              onChange={(event) =>
                setDateFrom(event.target.value)
              }
              style={filterStyle}
            />
          </div>

          <div>
            <label
              htmlFor="map-date-to"
              style={labelStyle}
            >
              Дата до
            </label>

            <input
              id="map-date-to"
              type="date"
              value={dateTo}
              onChange={(event) =>
                setDateTo(event.target.value)
              }
              style={filterStyle}
            />
          </div>
        </div>
      )}

      {/* Помилка діапазону */}
      {invalidDateRange && (
        <p
          role="alert"
          style={{
            color: '#d9534f',
            fontSize: '12px',
            marginBottom: '12px',
          }}
        >
          Дата початку не може бути пізнішою
          за дату завершення.
        </p>
      )}

      {/* Кількість знайдених подій */}
      <div
        aria-live="polite"
        style={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '6px',
          marginBottom: '12px',
          color: '#597c98',
          fontSize: '12px',
        }}
      >
        <span
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            backgroundColor: '#37a576',
          }}
        />

        Знайдено подій:
        <strong>{filteredEvents.length}</strong>
        <span>із {mapEvents.length}</span>
      </div>

      {/* Інтерактивна карта Львова */}
      <MapContainer
        center={[49.8397, 24.0297]}
        zoom={13}
        scrollWheelZoom={true}
        style={{
          height: '450px',
          width: '100%',
          borderRadius: '12px',
        }}
      >
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Маркери та кластеризація */}
        <MarkerClusterGroup
          key={`${selectedType}-${selectedStatus}-${selectedPeriod}-${dateFrom}-${dateTo}`}
          chunkedLoading
          showCoverageOnHover={false}
        >
          {filteredEvents.map((event) => (
            <Marker
              key={event.id}
              position={[event.lat, event.lng]}
              icon={createEventIcon(event)}
            >
              <Popup>
                <div style={{ minWidth: '180px' }}>
                  <strong>{event.title}</strong>

                  <p>{event.address}</p>

                  <p>
                    Тип: {eventStyles[event.type].label}
                  </p>

                  <p>
                    Статус:{' '}
                    <strong
                      style={{
                        color: statuses[event.status].color,
                      }}
                    >
                      {statuses[event.status].label}
                    </strong>
                  </p>

                  <p>
                    Дата створення:{' '}
                    {new Date(
                      event.createdAt
                    ).toLocaleDateString('uk-UA')}
                  </p>

                  <Link
                    to={`/reports/${event.id}`}
                    style={{
                      display: 'inline-block',
                      marginTop: '8px',
                      padding: '9px 14px',
                      borderRadius: '8px',
                      backgroundColor: '#2589c4',
                      color: '#ffffff',
                      fontSize: '12px',
                      fontWeight: 600,
                      textDecoration: 'none',
                    }}
                  >
                    Переглянути заявку →
                  </Link>
                </div>
              </Popup>
            </Marker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      {/* Повідомлення про відсутність результатів */}
      {filteredEvents.length === 0 && !invalidDateRange && (
        <p
          role="status"
          style={{
            fontSize: '13px',
            color: '#64748b',
            marginTop: '12px',
          }}
        >
          За вибраними фільтрами подій не знайдено.
          Спробуйте змінити параметри.
        </p>
      )}

      {/* Примітка про демонстраційні дані */}
      <p
        style={{
          fontSize: '12px',
          color: '#64748b',
          marginTop: '10px',
        }}
      >
        Показано відкриті заявки з бази RoadMap.
        Усунені й відхилені заявки з карти прибираються.
      </p>
    </div>
  )
}

export default RoadMapMap