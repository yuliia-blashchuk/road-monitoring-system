
import {
  useEffect,
  useState,
  type ChangeEvent,
  type ReactNode,
  type SyntheticEvent,
} from 'react'

import {
  BrowserRouter,
  Link,
  Route,
  Routes,
  useNavigate,
  useSearchParams,
} from 'react-router'

import RoadMapMap from './components/RoadMapMap'
import { mapEvents, type RoadEventStatus } from './data/mapEvents'
import AppLayout from './components/AppLayout'

import {
  getCurrentUser,
  loginUser,
  registerUser,
  type UserProfile,
} from './services/authApi'

import 'leaflet/dist/leaflet.css'
import './App.css'
import './RoadMap_KAN52_Figma_Login.css'

const TOKEN_KEY = 'roadmap_access_token'

// Перенаправлення користувача залежно від ролі
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

// Назви статусів для головної сторінки
const EVENT_STATUS: Record<
  RoadEventStatus,
  { label: string; className: string }
> = {
  new: { label: 'Нова', className: 'new' },
  accepted: { label: 'Прийнята', className: 'accepted' },
  in_progress: { label: 'В роботі', className: 'progress' },
  resolved: { label: 'Усунена', className: 'resolved' },
}

// Картка статистики
function StatCard({
  value,
  label,
  symbol,
  tone,
}: {
  value: number
  label: string
  symbol: string
  tone: string
}) {
  return (
    <div className="rm-stat-card">
      <span
        className={`rm-stat-symbol rm-stat-symbol--${tone}`}
        aria-hidden="true"
      >
        {symbol}
      </span>

      <div>
        <strong>{value}</strong>
        <span>{label}</span>
      </div>
    </div>
  )
}

// Головна сторінка з картою у стилі Figma
function MapPage() {
  const [searchParams] = useSearchParams()

  const searchQuery = (searchParams.get('q') ?? '')
    .trim()
    .toLocaleLowerCase('uk')

  // Статистика за демонстраційними даними
  const total = mapEvents.length

  const newCount = mapEvents.filter(
    (event) => event.status === 'new'
  ).length

  const acceptedCount = mapEvents.filter(
    (event) => event.status === 'accepted'
  ).length

  const progressCount = mapEvents.filter(
    (event) => event.status === 'in_progress'
  ).length

  const resolvedCount = mapEvents.filter(
    (event) => event.status === 'resolved'
  ).length

  // Діаграма статусів
  const scale = total || 1

  const p1 = (newCount / scale) * 100

  const p2 =
    ((newCount + acceptedCount) / scale) * 100

  const p3 =
    ((newCount + acceptedCount + progressCount) / scale) * 100

  const ringBackground = `
    conic-gradient(
      #72b8e9 0% ${p1}%,
      #86a3bb ${p1}% ${p2}%,
      #f3b24e ${p2}% ${p3}%,
      #34b49d ${p3}% 100%
    )
  `

  // Дані графіка за категоріями
  const types = [
    { code: 'pothole', name: 'Ями' },
    { code: 'accident', name: 'ДТП' },
    { code: 'obstacle', name: 'Перешкоди' },
    { code: 'roadworks', name: 'Ремонти' },
    { code: 'traffic_light', name: 'Світлофори' },
  ]

  const typeCounts = types.map(
    (type) =>
      mapEvents.filter((event) => event.type === type.code)
        .length
  )

  const linePoints = typeCounts
    .map(
      (count, index) =>
        `${18 + index * 66},${90 - count * 18}`
    )
    .join(' ')

  // Пошук працює в списку демонстраційних подій
  const matchedEvents = mapEvents.filter(
    (event) =>
      !searchQuery ||
      `${event.title} ${event.address}`
        .toLocaleLowerCase('uk')
        .includes(searchQuery)
  )

  const visibleEvents = searchQuery
    ? matchedEvents
    : matchedEvents.slice(0, 4)

  return (
    <div className="rm-dashboard">
      {/* Заголовок */}
      <div className="rm-page-title">
        <h1>RoadMap</h1>
        <p>Моніторинг стану доріг · м. Львів</p>
      </div>

      {/* Блакитний банер */}
      <section className="rm-hero">
        <div className="rm-hero-copy">
          <h2>Єдина карта дорожніх подій</h2>

          <p>
            Повідомляйте про проблеми та стежте
            <br />
            за їх вирішенням у своєму місті.
          </p>
        </div>

        <Link
          className="rm-hero-button"
          to="/login"
          title="Для створення заявки спочатку потрібно увійти"
        >
          <span aria-hidden="true">＋</span>
          Повідомити про проблему
        </Link>

        {/* Декоративний силует міста */}
        <svg
          className="rm-skyline"
          viewBox="0 0 390 112"
          preserveAspectRatio="xMaxYMax meet"
          aria-hidden="true"
        >
          <path
            d="M0 104H390"
            stroke="#a3d9f5"
            strokeWidth="2"
          />

          <g fill="#a7daf4" opacity=".93">
            <rect x="15" y="68" width="25" height="36" rx="2" />
            <rect x="44" y="53" width="28" height="51" rx="2" />
            <rect x="77" y="72" width="30" height="32" rx="2" />
            <rect x="114" y="40" width="32" height="64" rx="2" />
            <rect x="153" y="58" width="23" height="46" rx="2" />
            <rect x="182" y="29" width="29" height="75" rx="2" />
            <rect x="219" y="52" width="24" height="52" rx="2" />
            <rect x="251" y="20" width="19" height="84" rx="2" />
            <rect x="277" y="60" width="24" height="44" rx="2" />
            <rect x="308" y="49" width="25" height="55" rx="2" />
            <rect x="339" y="69" width="22" height="35" rx="2" />
            <rect x="367" y="62" width="20" height="42" rx="2" />
          </g>

          <path
            d="M0 102c45-9 78-16 127-7s102-13 147-8 79-2 116-8"
            fill="none"
            stroke="#ffffff"
            strokeWidth="6"
            opacity=".8"
          />

          <g fill="#e7f6ff" opacity=".9">
            {Array.from({ length: 19 }, (_, i) => (
              <rect
                key={i}
                x={22 + i * 19}
                y={77 + (i % 3) * 4}
                width="4"
                height="5"
                rx="1"
              />
            ))}
          </g>
        </svg>
      </section>

      {/* Статистика */}
      <div
        className="rm-stats"
        aria-label="Статистика демонстраційних подій"
      >
        <StatCard
          value={total}
          label="Усього подій"
          symbol="▤"
          tone="total"
        />

        <StatCard
          value={newCount}
          label="Нові"
          symbol="♧"
          tone="new"
        />

        <StatCard
          value={progressCount}
          label="У роботі"
          symbol="◷"
          tone="progress"
        />

        <StatCard
          value={resolvedCount}
          label="Усунено"
          symbol="✓"
          tone="resolved"
        />
      </div>

      {/* Карта та інформаційні блоки */}
      <div className="rm-content-grid">
        <section
          className="rm-panel rm-map-panel"
          id="roadmap-map"
        >
          <div className="rm-panel-heading">
            <h2>Карта стану доріг</h2>

            <span className="rm-light-tag">
              Демонстраційні події
            </span>
          </div>

          {/* Уже реалізована карта KAN-53 */}
          <RoadMapMap />
        </section>

        <div className="rm-side-panels">
          {/* Кругова діаграма */}
          <section
            className="rm-panel rm-status-panel"
            aria-label="Стани звернень"
          >
            <h2>Стан звернень</h2>

            <div className="rm-status-body">
              <div
                className="rm-donut"
                style={{ background: ringBackground }}
              >
                <div className="rm-donut-center">
                  <strong>{total}</strong>
                  <span>подій</span>
                </div>
              </div>

              <div className="rm-status-legend">
                <div>
                  <i className="rm-dot rm-dot--resolved" />
                  Усунено
                  <strong>{resolvedCount}</strong>
                </div>

                <div>
                  <i className="rm-dot rm-dot--progress" />
                  У роботі
                  <strong>{progressCount}</strong>
                </div>

                <div>
                  <i className="rm-dot rm-dot--new" />
                  Нові
                  <strong>{newCount}</strong>
                </div>

                <div>
                  <i className="rm-dot rm-dot--accepted" />
                  Прийняті
                  <strong>{acceptedCount}</strong>
                </div>
              </div>
            </div>
          </section>

          {/* Лінійний графік */}
          <section className="rm-panel rm-chart-panel">
            <div className="rm-panel-heading">
              <h2>Події за категоріями</h2>

              <span className="rm-small-tag">
                Демо
              </span>
            </div>

            <svg
              className="rm-type-chart"
              viewBox="0 0 305 113"
              role="img"
              aria-label="Кількість подій за категоріями"
            >
              <path
                d="M18 24H284M18 56H284M18 90H284"
                fill="none"
                stroke="#e2eff8"
                strokeWidth="1"
              />

              <polyline
                points={linePoints}
                fill="none"
                stroke="#2389c9"
                strokeWidth="2.7"
                strokeLinejoin="round"
                strokeLinecap="round"
              />

              {typeCounts.map((count, index) => (
                <circle
                  key={index}
                  cx={18 + index * 66}
                  cy={90 - count * 18}
                  r="3.5"
                  fill="#2389c9"
                />
              ))}
            </svg>

            <div className="rm-chart-labels">
              {types.map((type) => (
                <span key={type.code}>
                  {type.name}
                </span>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* Останні події */}
      <section
        className="rm-panel rm-recent-panel"
        id="recent-events"
      >
        <div className="rm-panel-heading">
          <h2>
            {searchQuery
              ? 'Результати пошуку'
              : 'Нещодавні події'}
          </h2>

          <span className="rm-muted-note">
            {searchQuery
              ? `Знайдено: ${matchedEvents.length}`
              : 'Демонстраційні дані'}
          </span>
        </div>

        {searchQuery && (
          <p className="rm-search-note">
            Пошук працює в списку подій.
            Для карти використай фільтри над нею.
          </p>
        )}

        <div className="rm-recent-list">
          {visibleEvents.map((event) => (
            <div
              className="rm-event-row"
              key={event.id}
            >
              <span
                className={`rm-event-icon rm-event-icon--${event.type}`}
                aria-hidden="true"
              >
                ●
              </span>

              <div className="rm-event-info">
                <strong>{event.title}</strong>
                <span>{event.address}</span>
              </div>

              <span
                className={`rm-event-status rm-event-status--${EVENT_STATUS[event.status].className}`}
              >
                {EVENT_STATUS[event.status].label}
              </span>
            </div>
          ))}

          {visibleEvents.length === 0 && (
            <p className="rm-no-results">
              За цим запитом демонстраційних подій не знайдено.
            </p>
          )}
        </div>
      </section>
    </div>
  )
}

// KAN-52 — сторінка входу
function LoginPage() {
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(
    event: SyntheticEvent<HTMLFormElement>
  ) {
    event.preventDefault()
    setMessage('')

    if (password.length < 8) {
      setMessage('Пароль має містити щонайменше 8 символів.')
      return
    }

    setIsLoading(true)

    try {
      const result = await loginUser(email.trim(), password)

      sessionStorage.setItem(
        TOKEN_KEY,
        result.access_token
      )

      const profile = await getCurrentUser(
        result.access_token
      )

      navigate(homeForRole(profile.role), {
        replace: true,
      })
    } catch (error) {
      sessionStorage.removeItem(TOKEN_KEY)

      setMessage(
        error instanceof Error
          ? error.message
          : 'Помилка входу.'
      )
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
        <div
          className="auth-hero-brand"
          aria-hidden="true"
        />

        <h1>Вітаємо в RoadMap!</h1>

        <p className="auth-intro">
          Увійдіть, щоб керувати заявками
        </p>

        <section
          className="auth-card"
          aria-labelledby="login-title"
        >
          <h2 id="login-title">
            Вхід до системи
          </h2>

          <form onSubmit={handleSubmit}>
            <label htmlFor="login-email">
              Електронна пошта:
            </label>

            <input
              id="login-email"
              type="email"
              placeholder="example@email.com"
              autoComplete="email"
              value={email}
              onChange={(
                event: ChangeEvent<HTMLInputElement>
              ) => setEmail(event.target.value)}
              disabled={isLoading}
              required
            />

            <label htmlFor="login-password">
              Пароль:
            </label>

            <input
              id="login-password"
              type={showPassword ? 'text' : 'password'}
              placeholder="Введіть пароль"
              autoComplete="current-password"
              value={password}
              onChange={(
                event: ChangeEvent<HTMLInputElement>
              ) => setPassword(event.target.value)}
              disabled={isLoading}
              required
            />

            <div className="auth-login-actions">
              <button
                type="button"
                className="auth-show-password"
                onClick={() =>
                  setShowPassword((previous) => !previous)
                }
              >
                {showPassword
                  ? 'Приховати пароль'
                  : 'Показати пароль'}
              </button>
            </div>

            {message && (
              <p
                className="auth-message"
                role="alert"
              >
                {message}
              </p>
            )}

            <button
              type="submit"
              className="auth-button"
              disabled={isLoading}
            >
              {isLoading
                ? 'Виконується вхід...'
                : 'Увійти'}
            </button>
          </form>
        </section>

        <div className="auth-login-footer">
          <p>Немає акаунта?</p>
          <Link to="/register">
            Зареєструватися
          </Link>
        </div>

        <p className="auth-login-note">
          <span aria-hidden="true">♢</span>
          <Link to="/">
            Перегляд карти доступний без входу
          </Link>
        </p>
      </div>
    </div>
  )
}

// KAN-52 — сторінка реєстрації
function RegisterPage() {
  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] =
    useState('')

  const [agreeTerms, setAgreeTerms] = useState(false)
  const [agreePrivacy, setAgreePrivacy] = useState(false)

  const [message, setMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isSuccess, setIsSuccess] = useState(false)

  async function handleSubmit(
    event: SyntheticEvent<HTMLFormElement>
  ) {
    event.preventDefault()
    setMessage('')
    setIsSuccess(false)

    if (
      fullName.trim().length < 2 ||
      fullName.trim().length > 150
    ) {
      setMessage(
        "Ім'я та прізвище мають містити від 2 до 150 символів."
      )
      return
    }

    if (
      phone.trim() &&
      !/^\+?[0-9]{10,15}$/.test(phone.trim())
    ) {
      setMessage(
        'Введіть телефон у міжнародному форматі, наприклад +380XXXXXXXXX.'
      )
      return
    }

    if (
      password.length < 8 ||
      password.length > 128
    ) {
      setMessage(
        'Пароль має містити від 8 до 128 символів.'
      )
      return
    }

    if (
      !/\p{L}/u.test(password) ||
      !/\d/.test(password)
    ) {
      setMessage(
        'Пароль повинен містити літери та цифри.'
      )
      return
    }

    if (password !== confirmPassword) {
      setMessage('Паролі не збігаються.')
      return
    }

    if (!agreeTerms || !agreePrivacy) {
      setMessage(
        'Потрібно прийняти обидві обов’язкові згоди.'
      )
      return
    }

    setIsLoading(true)

    try {
      await registerUser({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password,
        ...(phone.trim()
          ? { phone: phone.trim() }
          : {}),
        consents: ['terms', 'personal_data'],
      })

      setIsSuccess(true)

      setMessage(
        'Акаунт створено! Тепер можна увійти до системи.'
      )

      setFullName('')
      setEmail('')
      setPhone('')
      setPassword('')
      setConfirmPassword('')
      setAgreeTerms(false)
      setAgreePrivacy(false)
    } catch (error) {
      setMessage(
        error instanceof Error
          ? error.message
          : 'Помилка реєстрації.'
      )
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
        <div
          className="auth-hero-brand"
          aria-hidden="true"
        />

        <h1>Створити акаунт RoadMap</h1>

        <p className="auth-intro">
          Повідомляйте про проблеми на дорогах
          та відстежуйте заявки
        </p>

        <section
          className="auth-card"
          aria-labelledby="register-title"
        >
          <h2 id="register-title">
            Реєстрація
          </h2>

          <form onSubmit={handleSubmit}>
            <label htmlFor="register-name">
              Ім'я та прізвище
            </label>

            <input
              id="register-name"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setFullName(event.target.value)
              }
              placeholder="Введіть ім'я та прізвище"
              maxLength={150}
              required
              disabled={isLoading}
            />

            <label htmlFor="register-email">
              Електронна пошта
            </label>

            <input
              id="register-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setEmail(event.target.value)
              }
              placeholder="example@email.com"
              required
              disabled={isLoading}
            />

            <label htmlFor="register-phone">
              Телефон (необов'язково)
            </label>

            <input
              id="register-phone"
              type="tel"
              autoComplete="tel"
              value={phone}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setPhone(event.target.value)
              }
              placeholder="+380XXXXXXXXX"
              disabled={isLoading}
            />

            <label htmlFor="register-password">
              Пароль
            </label>

            <input
              id="register-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setPassword(event.target.value)
              }
              placeholder="8–128 символів, літери й цифри"
              minLength={8}
              maxLength={128}
              required
              disabled={isLoading}
            />

            <label htmlFor="register-confirm">
              Підтвердження пароля
            </label>

            <input
              id="register-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(event: ChangeEvent<HTMLInputElement>) =>
                setConfirmPassword(event.target.value)
              }
              placeholder="Повторіть пароль"
              required
              disabled={isLoading}
            />

            <label className="auth-checkbox">
              <input
                type="checkbox"
                checked={agreeTerms}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setAgreeTerms(event.target.checked)
                }
                required
                disabled={isLoading}
              />

              <span>
                Погоджуюся з умовами використання сервісу
              </span>
            </label>

            <label className="auth-checkbox">
              <input
                type="checkbox"
                checked={agreePrivacy}
                onChange={(event: ChangeEvent<HTMLInputElement>) =>
                  setAgreePrivacy(event.target.checked)
                }
                required
                disabled={isLoading}
              />

              <span>
                Надаю згоду на обробку персональних даних
              </span>
            </label>

            {message && (
              <p
                role="status"
                className={`auth-message${
                  isSuccess
                    ? ' auth-message--success'
                    : ''
                }`}
              >
                {message}
              </p>
            )}

            <button
              type="submit"
              className="auth-button"
              disabled={isLoading}
            >
              {isLoading
                ? 'Реєстрація...'
                : 'Зареєструватися'}
            </button>
          </form>
        </section>

        <div className="auth-login-footer">
          <p>Уже маєте акаунт?</p>
          <Link to="/login">
            Увійти
          </Link>
        </div>
      </div>
    </div>
  )
}

// Захист сторінок за ролями користувачів
type ProtectedPageProps = {
  allowedRoles: string[]
  title: string
  children: ReactNode
}

function ProtectedPage({
  allowedRoles,
  title,
  children,
}: ProtectedPageProps) {
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
          navigate(homeForRole(profile.role), {
            replace: true,
          })
          return
        }

        setUser(profile)
      })
      .catch((requestError: unknown) => {
        if (!active) return

        const msg =
          requestError instanceof Error
            ? requestError.message
            : 'Помилка перевірки входу.'

        setError(msg)
      })

    return () => {
      active = false
    }
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

        <button
          className="auth-button"
          type="button"
          onClick={logout}
        >
          Повернутися до входу
        </button>
      </section>
    )
  }

  if (!user) {
    return (
      <p>Перевіряємо вхід до RoadMap...</p>
    )
  }

  return (
    <section className="roadmap-role-page">
      <div className="roadmap-role-header">
        <div>
          <h2>{title}</h2>

          <p>
            Ви увійшли як {user.full_name} ({user.role}).
          </p>
        </div>

        <button
          type="button"
          className="roadmap-logout"
          onClick={logout}
        >
          Вийти
        </button>
      </div>

      {children}
    </section>
  )
}

function Placeholder({ text }: { text: string }) {
  return <p>{text}</p>
}

const ALL_ROLES = [
  'driver',
  'operator',
  'dispatcher',
  'contractor',
  'admin',
  'data_governance',
]

// Маршрути застосунку
function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route
            path="/"
            element={<MapPage />}
          />

          <Route
            path="/overview"
            element={<MapPage />}
          />

          <Route
            path="/login"
            element={<LoginPage />}
          />

          <Route
            path="/register"
            element={<RegisterPage />}
          />

          <Route
            path="/notifications"
            element={
              <ProtectedPage
                allowedRoles={ALL_ROLES}
                title="Сповіщення"
              >
                <Placeholder
                  text="Стрічку сповіщень буде реалізовано окремим завданням."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="/profile"
            element={
              <ProtectedPage
                allowedRoles={ALL_ROLES}
                title="Профіль"
              >
                <Placeholder
                  text="Детальні налаштування профілю з'являться в наступних завданнях."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="/my-reports"
            element={
              <ProtectedPage
                allowedRoles={['driver']}
                title="Мої звернення"
              >
                <Placeholder
                  text="Список власних заявок буде реалізовано окремо. Авторизація та перевірка ролі вже підключені."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="/service"
            element={
              <ProtectedPage
                allowedRoles={['operator', 'dispatcher']}
                title="Кабінет дорожньої служби"
              >
                <Placeholder
                  text="Черга заявок дорожньої служби буде реалізована в окремому завданні."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="/contractor"
            element={
              <ProtectedPage
                allowedRoles={['contractor']}
                title="Кабінет підрядника"
              >
                <Placeholder
                  text="Перегляд призначених робіт буде реалізовано в окремому завданні."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="/admin"
            element={
              <ProtectedPage
                allowedRoles={['admin']}
                title="Панель адміністратора"
              >
                <Placeholder
                  text="Адміністративні функції будуть додані в окремому завданні."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="/governance"
            element={
              <ProtectedPage
                allowedRoles={['data_governance']}
                title="Data Governance"
              >
                <Placeholder
                  text="Робочі інструменти контролю даних будуть додані в окремому завданні."
                />
              </ProtectedPage>
            }
          />

          <Route
            path="*"
            element={<h2>Сторінку не знайдено</h2>}
          />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  )
}

export default App
