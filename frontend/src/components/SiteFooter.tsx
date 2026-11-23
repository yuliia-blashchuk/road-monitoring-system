// KAN-110: футер з посиланням на політику приватності й налаштування cookie.
import { Link } from 'react-router'

import { openCookieSettings } from '../privacy/cookieConsent'

function SiteFooter() {
  return (
    <footer className="rm-site-footer">
      <span>© {new Date().getFullYear()} RoadMap · навчальний проєкт</span>
      <Link to="/privacy">Політика приватності</Link>
      <button
        type="button"
        className="rm-site-footer__link"
        onClick={openCookieSettings}
        aria-haspopup="dialog"
      >
        Налаштування cookie
      </button>
    </footer>
  )
}

export default SiteFooter
