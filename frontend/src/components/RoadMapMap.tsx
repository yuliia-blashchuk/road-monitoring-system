
import { useState } from 'react'
import { MapContainer, TileLayer, Marker, Popup } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'

import {
  mapEvents,
  type RoadEvent,
  type RoadEventType,
  type RoadEventStatus,
} from '../data/mapEvents'

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
    label: 'Пошкодження дороги',
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
  resolved: {
    label: 'Усунена',
    color: '#37A576',
  },
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
  // Фільтр за типом дорожньої події
  const [selectedType, setSelectedType] =
    useState<RoadEventType | 'all'>('all')

  // Фільтр за статусом заявки
  const [selectedStatus, setSelectedStatus] =
    useState<RoadEventStatus | 'all'>('all')

  // Застосування обох фільтрів
  const filteredEvents = mapEvents.filter((event) => {
    const matchesType =
      selectedType === 'all' || event.type === selectedType

    const matchesStatus =
      selectedStatus === 'all' || event.status === selectedStatus

    return matchesType && matchesStatus
  })

  return (
    <div>
      {/* Панель фільтрації дорожніх подій */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: '12px',
          marginBottom: '16px',
          alignItems: 'center',
        }}
      >
        {/* Фільтр за категорією */}
        <select
          value={selectedType}
          onChange={(e) =>
            setSelectedType(
              e.target.value as RoadEventType | 'all'
            )
          }
          aria-label="Фільтр за типом події"
          style={{
            padding: '10px 14px',
            borderRadius: '10px',
            border: '1px solid #cbd5e1',
            backgroundColor: '#f4faff',
            color: '#17365d',
            fontSize: '14px',
            cursor: 'pointer',
          }}
        >
          <option value="all">Усі категорії</option>
          <option value="pothole">
            Пошкодження дороги
          </option>
          <option value="accident">Аварії</option>
          <option value="obstacle">Перешкоди</option>
          <option value="roadworks">
            Ремонтні роботи
          </option>
          <option value="traffic_light">
            Світлофори
          </option>
        </select>

        {/* Фільтр за статусом */}
        <select
          value={selectedStatus}
          onChange={(e) =>
            setSelectedStatus(
              e.target.value as RoadEventStatus | 'all'
            )
          }
          aria-label="Фільтр за статусом"
          style={{
            padding: '10px 14px',
            borderRadius: '10px',
            border: '1px solid #cbd5e1',
            backgroundColor: '#f4faff',
            color: '#17365d',
            fontSize: '14px',
            cursor: 'pointer',
          }}
        >
          <option value="all">Усі статуси</option>
          <option value="new">Нові</option>
          <option value="accepted">Прийняті</option>
          <option value="in_progress">В роботі</option>
          <option value="resolved">Усунені</option>
        </select>

        {/* Кількість знайдених подій */}
        <span
          style={{
            color: '#64748b',
            fontSize: '13px',
          }}
        >
          Знайдено подій: {filteredEvents.length}
        </span>
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
        {/* Карта OpenStreetMap */}
        <TileLayer
          attribution="&copy; OpenStreetMap contributors"
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {/* Кластеризація маркерів */}
        <MarkerClusterGroup
          chunkedLoading
          showCoverageOnHover={false}
        >
          {filteredEvents.map((event) => (
            <Marker
              key={event.id}
              position={[event.lat, event.lng]}
              icon={createEventIcon(event)}
            >
              {/* Інформація про дорожню подію */}
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
                </div>
              </Popup>
            </Marker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      {/* Повідомлення про демонстраційні дані */}
      <p
        style={{
          fontSize: '12px',
          color: '#64748b',
          marginTop: '10px',
        }}
      >
        Демонстраційні дорожні події.
        Інформація не відображає реальний стан доріг.
      </p>
    </div>
  )
}

export default RoadMapMap
