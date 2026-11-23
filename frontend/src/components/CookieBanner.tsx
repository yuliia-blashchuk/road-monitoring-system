// KAN-110: банер згоди на cookie та дані в браузері і вікно налаштувань.
//
// Доступність: банер - це область сторінки, а не модальне вікно, тому він не забирає
// фокус і не блокує форму входу; вікно «Налаштувати» - нативний <dialog>
// (фокус усередині, Esc закриває, після закриття фокус повертається на кнопку).
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import {
  BROWSER_STORAGE,
  CONSENT_STORAGE_KEY,
  OPEN_SETTINGS_EVENT,
  PRIVACY_POLICY_VERSION,
  formatConsentDate,
  hasOptionalTools,
  isConsentCurrent,
  loadOptionalScripts,
  readConsent,
  saveConsent,
  type CookieConsent,
} from '../privacy/cookieConsent'

import './CookieBanner.css'

const STORAGE_LABELS = {
  sessionStorage: 'sessionStorage',
  localStorage: 'localStorage',
  cookie: 'cookie',
} as const

function CookieBanner() {
  const [consent, setConsent] = useState<CookieConsent | null>(readConsent)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [analyticsDraft, setAnalyticsDraft] = useState(false)

  const bannerRef = useRef<HTMLElement>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)

  const showBanner = !isConsentCurrent(consent)

  // Додаткові скрипти - лише якщо згоду вже надано раніше.
  useEffect(() => {
    loadOptionalScripts(readConsent())
  }, [])

  // «Налаштування cookie» у футері відкриває вікно з будь-якої сторінки;
  // зміна вибору в іншій вкладці одразу видна і тут.
  useEffect(() => {
    function openSettings() {
      setAnalyticsDraft(readConsent()?.categories.analytics ?? false)
      setSettingsOpen(true)
    }
    function syncFromOtherTab(event: StorageEvent) {
      if (event.key === CONSENT_STORAGE_KEY) setConsent(readConsent())
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, openSettings)
    window.addEventListener('storage', syncFromOtherTab)
    return () => {
      window.removeEventListener(OPEN_SETTINGS_EVENT, openSettings)
      window.removeEventListener('storage', syncFromOtherTab)
    }
  }, [])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (settingsOpen && !dialog.open) dialog.showModal()
    if (!settingsOpen && dialog.open) dialog.close()
  }, [settingsOpen])

  // Під банером лишаємо місце внизу сторінки, щоб він не закривав кнопки форм.
  useEffect(() => {
    const root = document.documentElement
    const banner = bannerRef.current
    if (!showBanner || !banner) {
      root.style.removeProperty('--rm-cookie-banner-space')
      return
    }
    const update = () =>
      root.style.setProperty('--rm-cookie-banner-space', `${banner.offsetHeight + 16}px`)
    update()
    const observer = new ResizeObserver(update)
    observer.observe(banner)
    return () => {
      observer.disconnect()
      root.style.removeProperty('--rm-cookie-banner-space')
    }
  }, [showBanner])

  function choose(analytics: boolean) {
    setConsent(saveConsent(analytics))
    setSettingsOpen(false)
  }

  function openFromBanner() {
    setAnalyticsDraft(consent?.categories.analytics ?? false)
    setSettingsOpen(true)
  }

  const necessaryItems = BROWSER_STORAGE.filter((item) => item.category === 'necessary')

  return (
    <>
      {showBanner && (
        <section
          ref={bannerRef}
          className="rm-cookie-banner"
          aria-labelledby="rm-cookie-banner-title"
          aria-describedby="rm-cookie-banner-text"
        >
          <div className="rm-cookie-banner__body">
            <h2 id="rm-cookie-banner-title" className="rm-cookie-banner__title">
              Cookie та дані в браузері
            </h2>
            <p id="rm-cookie-banner-text" className="rm-cookie-banner__text">
              RoadMap зберігає у вашому браузері лише те, без чого сайт не працює: токен входу та
              ваш вибір щодо cookie. Додаткових cookie (аналітики) зараз немає; якщо вони
              з&apos;являться, увімкнемо їх тільки з вашої згоди.{' '}
              <Link to="/privacy">Політика приватності</Link>
            </p>
          </div>

          <div className="rm-cookie-banner__actions">
            <button type="button" className="rm-cookie-btn" onClick={() => choose(true)}>
              Прийняти все
            </button>
            <button type="button" className="rm-cookie-btn" onClick={() => choose(false)}>
              Лише необхідні
            </button>
            <button
              type="button"
              className="rm-cookie-btn rm-cookie-btn--ghost"
              onClick={openFromBanner}
              aria-haspopup="dialog"
            >
              Налаштувати
            </button>
          </div>
        </section>
      )}

      <dialog
        ref={dialogRef}
        className="rm-cookie-dialog"
        aria-labelledby="rm-cookie-dialog-title"
        onClose={() => setSettingsOpen(false)}
      >
        <div className="rm-cookie-dialog__head">
          <h2 id="rm-cookie-dialog-title">Налаштування cookie</h2>
          <button
            type="button"
            className="rm-cookie-dialog__close"
            onClick={() => setSettingsOpen(false)}
            aria-label="Закрити налаштування cookie"
          >
            ×
          </button>
        </div>

        <fieldset className="rm-cookie-category">
          <legend>
            <span>Необхідні</span>
            <span className="rm-cookie-badge">Завжди увімкнені</span>
          </legend>
          <p>
            Без цих даних не працюють вхід і запам&apos;ятовування вашого вибору. За законом на них
            згода не потрібна, але ми їх описуємо.
          </p>
          <ul className="rm-cookie-items">
            {necessaryItems.map((item) => (
              <li key={item.name}>
                <code>{item.name}</code>
                <span className="rm-cookie-items__where">{STORAGE_LABELS[item.storage]}</span>
                <span>{item.purpose}</span>
                <span className="rm-cookie-items__life">Термін: {item.lifetime}</span>
              </li>
            ))}
          </ul>
        </fieldset>

        <fieldset className="rm-cookie-category">
          <legend>
            <span>Додаткові (аналітика)</span>
          </legend>
          <label className="rm-cookie-toggle">
            <input
              type="checkbox"
              checked={analyticsDraft}
              disabled={!hasOptionalTools}
              aria-describedby="rm-cookie-analytics-note"
              onChange={(event) => setAnalyticsDraft(event.target.checked)}
            />
            <span>Дозволити аналітичні cookie та скрипти</span>
          </label>
          <p id="rm-cookie-analytics-note">
            {hasOptionalTools
              ? 'Допомагають зрозуміти, як користуються сайтом. Завантажуються лише після вашої згоди.'
              : 'Зараз RoadMap не використовує жодних додаткових cookie чи скриптів, тому вмикати нічого. Якщо вони з’являться, ми оновимо політику й спитаємо вас знову.'}
          </p>
        </fieldset>

        {isConsentCurrent(consent) && (
          <p className="rm-cookie-dialog__current" role="status">
            Ваш поточний вибір: {consent.categories.analytics ? 'усі категорії' : 'лише необхідні'},
            збережено {formatConsentDate(consent.decidedAt)} (версія політики {consent.version}).
          </p>
        )}

        <div className="rm-cookie-dialog__actions">
          <button type="button" className="rm-cookie-btn" onClick={() => choose(analyticsDraft)}>
            Зберегти вибір
          </button>
          <button type="button" className="rm-cookie-btn" onClick={() => choose(true)}>
            Прийняти все
          </button>
          <button type="button" className="rm-cookie-btn" onClick={() => choose(false)}>
            Лише необхідні
          </button>
        </div>

        <p className="rm-cookie-dialog__policy">
          Докладніше - у{' '}
          <Link to="/privacy" onClick={() => setSettingsOpen(false)}>
            Політиці приватності
          </Link>{' '}
          (версія {PRIVACY_POLICY_VERSION}).
        </p>
      </dialog>
    </>
  )
}

export default CookieBanner
