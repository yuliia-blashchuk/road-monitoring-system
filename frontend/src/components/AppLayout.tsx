
import {
  useState,
  type FormEvent,
  type ReactNode,
} from 'react'

import {
  Link,
  NavLink,
  useLocation,
  useNavigate,
} from 'react-router'

type AppLayoutProps = {
  children: ReactNode
}

type IconName =
  | 'home'
  | 'map'
  | 'file'
  | 'bell'
  | 'user'
  | 'search'

// Іконки навігації
function MenuIcon({
  name,
  size = 19,
}: {
  name: IconName
  size?: number
}) {
  const common = {
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true as const,
  }

  return (
    <svg {...common}>
      {name === 'home' && (
        <>
          <path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1Z" />
          <path d="M9 21v-8h6v8" />
        </>
      )}

      {name === 'map' && (
        <>
          <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3Z" />
          <path d="M9 3v15M15 6v15" />
        </>
      )}

      {name === 'file' && (
        <>
          <path d="M6 3h9l4 4v14H6Z" />
          <path d="M15 3v5h4M9 12h7M9 16h7" />
        </>
      )}

      {name === 'bell' && (
        <>
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
          <path d="M10 21h4" />
        </>
      )}

      {name === 'user' && (
        <>
          <circle cx="12" cy="8" r="4" />
          <path d="M4 21v-2a8 8 0 0 1 16 0v2" />
        </>
      )}

      {name === 'search' && (
        <>
          <circle cx="11" cy="11" r="7" />
          <path d="m16 16 5 5" />
        </>
      )}
    </svg>
  )
}

// Основний макет застосунку
function AppLayout({ children }: AppLayoutProps) {
  const location = useLocation()
  const navigate = useNavigate()

  const [search, setSearch] = useState('')

  const isAuthPage =
    location.pathname === '/login' ||
    location.pathname === '/register'

  const isLoggedIn = Boolean(
    sessionStorage.getItem('roadmap_access_token')
  )

  // Для KAN-52 залишаємо початкове оформлення
  if (isAuthPage) {
    return (
      <div className="app">
        <main className="app-main">
          {children}
        </main>
      </div>
    )
  }

  // Пошук серед демонстраційних подій
  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    const query = search.trim()

    navigate(
      query
        ? `/?q=${encodeURIComponent(query)}`
        : '/'
    )
  }

  return (
    <div className="rm-shell">
      {/* Ліва панель */}
      <aside className="rm-sidebar">
        <Link
          className="rm-brand"
          to="/"
          aria-label="RoadMap — на головну"
        >
          <img
            src="/roadmap-icon.png"
            alt=""
          />

          <span>RoadMap</span>
        </Link>

        <div className="rm-nav-caption">
          НАВІГАЦІЯ
        </div>

        <nav
          className="rm-sidebar-nav"
          aria-label="Основна навігація"
        >
          <NavLink
            to="/overview"
            className={({ isActive }) =>
              `rm-nav-link${isActive ? ' active' : ''}`
            }
          >
            <MenuIcon name="home" />
            <span>Головна</span>
          </NavLink>

          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `rm-nav-link${isActive ? ' active' : ''}`
            }
          >
            <MenuIcon name="map" />
            <span>Карта доріг</span>
          </NavLink>

          <NavLink
            to="/my-reports"
            className={({ isActive }) =>
              `rm-nav-link${isActive ? ' active' : ''}`
            }
          >
            <MenuIcon name="file" />
            <span>Мої заявки</span>
          </NavLink>

          <NavLink
            to="/notifications"
            className={({ isActive }) =>
              `rm-nav-link${isActive ? ' active' : ''}`
            }
          >
            <MenuIcon name="bell" />
            <span>Сповіщення</span>
          </NavLink>

          <NavLink
            to="/profile"
            className={({ isActive }) =>
              `rm-nav-link${isActive ? ' active' : ''}`
            }
          >
            <MenuIcon name="user" />
            <span>Профіль</span>
          </NavLink>
        </nav>

        {/* Декоративна частина */}
        <div
          className="rm-sidebar-bottom"
          aria-hidden="true"
        >
          <span>
            Львів · міські дороги
          </span>

          <div className="rm-cityscape">
            <i />
            <i />
            <i />
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
        </div>
      </aside>

      {/* Основна область */}
      <div className="rm-workspace">
        {/* Верхній рядок */}
        <header className="rm-topbar">
          <form
            className="rm-search"
            onSubmit={handleSearch}
            role="search"
          >
            <MenuIcon
              name="search"
              size={18}
            />

            <input
              aria-label="Пошук серед демонстраційних дорожніх подій"
              placeholder="Пошук серед демоподій..."
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
            />

            <button
              type="submit"
              aria-label="Знайти події"
            >
              Знайти
            </button>
          </form>

          <div className="rm-top-actions">
            <Link
              to="/notifications"
              className="rm-top-icon"
              title="Сповіщення"
              aria-label="Сповіщення"
            >
              <MenuIcon
                name="bell"
                size={19}
              />
            </Link>

            <Link
              to={
                isLoggedIn
                  ? '/profile'
                  : '/login'
              }
              className="rm-account"
              title={
                isLoggedIn
                  ? 'Профіль'
                  : 'Увійти'
              }
            >
              <span className="rm-avatar">
                <MenuIcon
                  name="user"
                  size={20}
                />
              </span>

              <span className="rm-account-label">
                <strong>
                  {isLoggedIn
                    ? 'Акаунт'
                    : 'Гість'}
                </strong>

                <small>RoadMap</small>
              </span>
            </Link>
          </div>
        </header>

        {/* Вміст сторінки */}
        <main className="rm-content">
          {children}
        </main>
      </div>
    </div>
  )
}

export default AppLayout
