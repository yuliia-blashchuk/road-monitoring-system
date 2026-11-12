import { useEffect, useState, type ChangeEvent, type ReactNode, type SyntheticEvent } from 'react'
import { BrowserRouter, Link, Route, Routes, useNavigate } from 'react-router'
import { MapContainer, TileLayer } from 'react-leaflet'
import {
  getCurrentUser,
  loginUser,
  registerUser,
  type UserProfile,
} from './services/authApi'
import AppLayout from './components/AppLayout'

import 'leaflet/dist/leaflet.css'
import './App.css'
import './RoadMap_KAN52_Figma_Login.css'

const TOKEN_KEY = 'roadmap_access_token'

function homeForRole(role: string): string {
  switch (role) {
    case 'driver':
      return '/my-reports'
    case 'operator':
    case 'dispatcher':
      return '/service'
    case 'contractor':
      return '/contractor'
    case 'admin':
      return '/admin'
    case 'data_governance':
      return '/governance'
    default:
      return '/'
  }
}

// Карта з KAN-28 залишається без змін.
function MapPage() {
  return (
    <>
      <h2>Карта стану доріг</h2>
      <p>Інтерактивна карта міста з повідомленнями про ями, аварії та дорожні перешкоди.</p>
      <MapContainer
        center={[49.8397, 24.0297]}
        zoom={13}
        scrollWheelZoom={true}
        style={{ height: '450px', width: '100%', borderRadius: '12px' }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
      </MapContainer>
    </>
  )
}

// Вхід: запит до готового API, JWT та перенаправлення за реальною роллю з /auth/me.
function LoginPage() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')

    if (password.length < 8) {
      setMessage('Пароль має містити щонайменше 8 символів.')
      return
    }

    setIsLoading(true)
    try {
      const result = await loginUser(email.trim(), password)
      sessionStorage.setItem(TOKEN_KEY, result.access_token)
      // Дані ролі беремо з сервера, а не з введення користувача.
      const profile = await getCurrentUser(result.access_token)
      navigate(homeForRole(profile.role), { replace: true })
    } catch (error) {
      sessionStorage.removeItem(TOKEN_KEY)
      setMessage(error instanceof Error ? error.message : 'Помилка входу.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="auth-page auth-page--figma auth-page--login">
      <header className="auth-topbar">
        <img src="/roadmap-icon.png" alt="" />
        <span>RoadMap</span>
      </header>

      <div className="auth-shell">
        <div className="auth-hero-brand" aria-hidden="true" />
        <h1>Вітаємо в RoadMap!</h1>
        <p className="auth-intro">Увійдіть, щоб керувати заявками</p>

        <section className="auth-card" aria-labelledby="login-title">
          <h2 id="login-title">Вхід до системи</h2>
          <form onSubmit={handleSubmit}>
            <label htmlFor="login-email">Електронна пошта:</label>
            <input
              id="login-email"
              type="email"
              placeholder="example@email.com"
              autoComplete="email"
              value={email}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setEmail(event.target.value)}
              disabled={isLoading}
              required
            />

            <label htmlFor="login-password">Пароль:</label>
            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Введіть пароль"
              autoComplete="current-password"
              value={password}
              onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)}
              disabled={isLoading}
              required
            />

            <div className="auth-login-actions">
              <button
                type="button"
                className="auth-show-password"
                onClick={() => setShowPassword((previous) => !previous)}
              >
                {showPassword ? 'Приховати пароль' : 'Показати пароль'}
              </button>
            </div>

            {message && <p className="auth-message" role="alert">{message}</p>}

            <button type="submit" className="auth-button" disabled={isLoading}>
              {isLoading ? 'Виконується вхід...' : 'Увійти'}
            </button>
          </form>
        </section>

        <div className="auth-login-footer">
          <p>Немає акаунта?</p>
          <Link to="/register">Зареєструватися</Link>
        </div>
        <p className="auth-login-note">
          <span aria-hidden="true">♢</span>
          <Link to="/">Перегляд карти доступний без входу</Link>
        </p>
      </div>
    </div>
  )
}

// Реєстрація: валідація та передавання реальних згод API.
function RegisterPage() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [agreeTerms, setAgreeTerms] = useState(false)
  const [agreePrivacy, setAgreePrivacy] = useState(false)
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

  async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
    event.preventDefault()
    setMessage('')
    setIsSuccess(false)

    if (fullName.trim().length < 2 || fullName.trim().length > 150) {
      setMessage("Ім'я та прізвище мають містити від 2 до 150 символів.")
      return
    }
    if (phone.trim() && !/^\+?[0-9]{10,15}$/.test(phone.trim())) {
      setMessage('Введіть телефон у міжнародному форматі, наприклад +380XXXXXXXXX.')
      return
    }
    if (password.length < 8 || password.length > 128) {
      setMessage('Пароль має містити від 8 до 128 символів.')
      return
    }
    if (!/\p{L}/u.test(password) || !/\d/.test(password)) {
      setMessage('Пароль повинен містити літери та цифри.')
      return
    }
    if (password !== confirmPassword) {
      setMessage('Паролі не збігаються.')
      return
    }
    if (!agreeTerms || !agreePrivacy) {
      setMessage('Потрібно прийняти обидві обов’язкові згоди.')
      return
    }

    setIsLoading(true)
    try {
      await registerUser({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password,
        ...(phone.trim() ? { phone: phone.trim() } : {}),
        consents: ['terms', 'personal_data'],
      })

      setIsSuccess(true)
      setMessage('Акаунт створено! Тепер можна увійти до системи.')
      setFullName('')
      setEmail('')
      setPhone('')
      setPassword('')
      setConfirmPassword('')
      setAgreeTerms(false)
      setAgreePrivacy(false)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Помилка реєстрації.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="auth-page auth-page--figma auth-page--register">
      <header className="auth-topbar">
        <img src="/roadmap-icon.png" alt="" />
        <span>RoadMap</span>
      </header>
      <div className="auth-shell">
        <div className="auth-hero-brand" aria-hidden="true" />
        <h1>Створити акаунт RoadMap</h1>
        <p className="auth-intro">Повідомляйте про проблеми на дорогах та відстежуйте заявки</p>

        <section className="auth-card" aria-labelledby="register-title">
          <h2 id="register-title">Реєстрація</h2>
          <form onSubmit={handleSubmit}>
            <label htmlFor="register-name">Ім'я та прізвище</label>
            <input id="register-name" type="text" autoComplete="name"
              value={fullName} onChange={(event: ChangeEvent<HTMLInputElement>) => setFullName(event.target.value)}
              placeholder="Введіть ім'я та прізвище" maxLength={150} required disabled={isLoading} />

            <label htmlFor="register-email">Електронна пошта</label>
            <input id="register-email" type="email" autoComplete="email"
              value={email} onChange={(event: ChangeEvent<HTMLInputElement>) => setEmail(event.target.value)}
              placeholder="example@email.com" required disabled={isLoading} />

            <label htmlFor="register-phone">Телефон (необов'язково)</label>
            <input id="register-phone" type="tel" autoComplete="tel"
              value={phone} onChange={(event: ChangeEvent<HTMLInputElement>) => setPhone(event.target.value)}
              placeholder="+380XXXXXXXXX" disabled={isLoading} />

            <label htmlFor="register-password">Пароль</label>
            <input id="register-password" type="password" autoComplete="new-password"
              value={password} onChange={(event: ChangeEvent<HTMLInputElement>) => setPassword(event.target.value)}
              placeholder="8–128 символів, літери й цифри" minLength={8} maxLength={128}
              required disabled={isLoading} />

            <label htmlFor="register-confirm">Підтвердження пароля</label>
            <input id="register-confirm" type="password" autoComplete="new-password"
              value={confirmPassword} onChange={(event: ChangeEvent<HTMLInputElement>) => setConfirmPassword(event.target.value)}
              placeholder="Повторіть пароль" required disabled={isLoading} />

            <label className="auth-checkbox">
              <input type="checkbox" checked={agreeTerms}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setAgreeTerms(event.target.checked)}
                required disabled={isLoading} />
              <span>Погоджуюся з умовами використання сервісу</span>
            </label>
            <label className="auth-checkbox">
              <input type="checkbox" checked={agreePrivacy}
                onChange={(event: ChangeEvent<HTMLInputElement>) => setAgreePrivacy(event.target.checked)}
                required disabled={isLoading} />
              <span>Надаю згоду на обробку персональних даних</span>
            </label>

            {message && <p role="status" className={`auth-message${isSuccess ? ' auth-message--success' : ''}`}>{message}</p>}
            <button type="submit" className="auth-button" disabled={isLoading}>
              {isLoading ? 'Реєстрація...' : 'Зареєструватися'}
            </button>
          </form>
        </section>
        <div className="auth-login-footer">
          <p>Уже маєте акаунт?</p>
          <Link to="/login">Увійти</Link>
        </div>
      </div>
    </div>
  )
}

type ProtectedPageProps = {
  allowedRoles: string[]
  title: string
  children: ReactNode
}

// Перевіряємо токен через сервер, а не просто довіряємо sessionStorage.
function ProtectedPage({ allowedRoles, title, children }: ProtectedPageProps) {
  const navigate = useNavigate()
  const [user, setUser] = useState<UserProfile | null>(null)
  const [error, setError] = useState('')

  const allowed = allowedRoles.join(',')

  useEffect(() => {
    const token = sessionStorage.getItem(TOKEN_KEY)
    if (!token) {
      navigate('/login', { replace: true })
      return
    }

    let active = true
    getCurrentUser(token)
      .then((profile) => {
        if (!active) return
        if (!allowed.split(',').includes(profile.role)) {
          navigate(homeForRole(profile.role), { replace: true })
          return
        }
        setUser(profile)
      })
      .catch((requestError: unknown) => {
        if (!active) return
        const msg = requestError instanceof Error ? requestError.message : 'Помилка перевірки входу.'
        setError(msg)
      })
    return () => { active = false }
  }, [allowed, navigate])

  function logout() {
    sessionStorage.removeItem(TOKEN_KEY)
    navigate('/login', { replace: true })
  }

  if (error) {
    return (
      <section className="roadmap-role-page">
        <h2>Не вдалося перевірити доступ</h2>
        <p role="alert">{error}</p>
        <button className="auth-button" type="button" onClick={logout}>Повернутися до входу</button>
      </section>
    )
  }
  if (!user) return <p>Перевіряємо вхід до RoadMap...</p>

  return (
    <section className="roadmap-role-page">
      <div className="roadmap-role-header">
        <div>
          <h2>{title}</h2>
          <p>Ви увійшли як {user.full_name} ({user.role}).</p>
        </div>
        <button type="button" className="roadmap-logout" onClick={logout}>Вийти</button>
      </div>
      {children}
    </section>
  )
}

// Кабінети інших ролей додадуться окремими задачами; тут лише маршрути для KAN-52.
function Placeholder({ text }: { text: string }) {
  return <p>{text}</p>
}

function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<MapPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/my-reports" element={
            <ProtectedPage allowedRoles={['driver']} title="Мої звернення">
              <Placeholder text="Список власних заявок буде реалізовано окремо. Авторизація та перевірка ролі вже підключені." />
            </ProtectedPage>
          } />
          <Route path="/service" element={
            <ProtectedPage allowedRoles={['operator', 'dispatcher']} title="Кабінет дорожньої служби">
              <Placeholder text="Черга заявок дорожньої служби буде реалізована в окремому завданні." />
            </ProtectedPage>
          } />
          <Route path="/contractor" element={
            <ProtectedPage allowedRoles={['contractor']} title="Кабінет підрядника">
              <Placeholder text="Перегляд призначених робіт буде реалізовано в окремому завданні." />
            </ProtectedPage>
          } />
          <Route path="/admin" element={
            <ProtectedPage allowedRoles={['admin']} title="Панель адміністратора">
              <Placeholder text="Адміністративні функції будуть додані в окремому завданні." />
            </ProtectedPage>
          } />
          <Route path="/governance" element={
            <ProtectedPage allowedRoles={['data_governance']} title="Data Governance">
              <Placeholder text="Робочі інструменти контролю даних будуть додані в окремому завданні." />
            </ProtectedPage>
          } />
          <Route path="*" element={<h2>Сторінку не знайдено</h2>} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
