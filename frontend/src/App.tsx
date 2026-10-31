import { BrowserRouter, Routes, Route } from 'react-router'
import { MapContainer, TileLayer } from 'react-leaflet'
import AppLayout from './components/AppLayout'
import 'leaflet/dist/leaflet.css'
import './App.css'

function MapPage() {
  return (
    <>
      <h2>Карта стану доріг</h2>
      <p>Інтерактивна карта міста з повідомленнями про ями, аварії та дорожні перешкоди.</p>

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
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
      </MapContainer>
    </>
  )
}

function MyReportsPage() {
  return (
    <>
      <h2>Мої звернення</h2>
      <p>Тут користувач зможе переглядати свої звернення та їхні статуси.</p>
    </>
  )
}

function LoginPage() {
  return (
    <>
      <h2>Вхід до системи</h2>
      <p>Тут буде форма авторизації користувача.</p>
    </>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/my-reports" element={<MyReportsPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="*" element={<h2>Сторінку не знайдено</h2>} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
