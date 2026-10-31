import type { ReactNode } from 'react'
import { NavLink } from 'react-router'

type AppLayoutProps = {
  children: ReactNode
}

function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="app">
      <header className="app-header">
        <h1>RoadMap</h1>
        <p>Система моніторингу стану доріг і ремонтних робіт</p>

        <nav className="app-nav" aria-label="Основна навігація">
          <NavLink to="/" end>
            Карта
          </NavLink>

          <NavLink to="/my-reports">Мої звернення</NavLink>

          <NavLink to="/login">Вхід</NavLink>
        </nav>
      </header>

      <main className="app-main">{children}</main>
    </div>
  )
}

export default AppLayout
