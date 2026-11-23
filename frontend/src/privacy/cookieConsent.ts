// KAN-110: згода на cookie та дані в браузері (GDPR ст. 7, ePrivacy ст. 5(3)).
//
// Правила:
// - необхідні дані (токен входу, сам вибір щодо cookie) працюють без згоди;
// - додаткові скрипти й cookie завантажуються лише після згоди на їхню категорію;
// - вибір зберігається з датою і версією політики; нова версія політики = нове питання.

export const CONSENT_STORAGE_KEY = 'roadmap_cookie_consent'

// Змініть версію, якщо змінився склад даних у браузері або текст політики:
// банер з'явиться знову для всіх користувачів.
export const PRIVACY_POLICY_VERSION = '1.0'
export const PRIVACY_POLICY_DATE = '2026-11-23'

export const CONSENT_CHANGE_EVENT = 'roadmap:cookie-consent-change'
export const OPEN_SETTINGS_EVENT = 'roadmap:open-cookie-settings'

export type CookieCategory = 'necessary' | 'analytics'

export type CookieConsent = {
  version: string
  decidedAt: string
  categories: {
    necessary: true
    analytics: boolean
  }
}

export type BrowserStorageItem = {
  name: string
  storage: 'sessionStorage' | 'localStorage' | 'cookie'
  category: CookieCategory
  purpose: string
  lifetime: string
}

// Інвентаризація даних у браузері. Єдине джерело правди для банера,
// сторінки політики й документації: додаючи новий ключ чи cookie, опишіть його тут.
export const BROWSER_STORAGE: BrowserStorageItem[] = [
  {
    name: 'roadmap_access_token',
    storage: 'sessionStorage',
    category: 'necessary',
    purpose: 'Токен входу (JWT): підтверджує серверу, що ви увійшли, і визначає вашу роль.',
    lifetime: 'До виходу або закриття вкладки; сам токен дійсний 60 хв',
  },
  {
    name: CONSENT_STORAGE_KEY,
    storage: 'localStorage',
    category: 'necessary',
    purpose: 'Ваш вибір щодо cookie: категорії, дата вибору й версія політики.',
    lifetime:
      'Доки ви не зміните вибір, не очистите дані браузера або не зміниться версія політики',
  },
]

export type OptionalScript = {
  id: string
  name: string
  category: Exclude<CookieCategory, 'necessary'>
  src: string
}

// Додаткові скрипти (аналітика тощо). Зараз RoadMap їх не використовує.
// Додаючи сюди скрипт, опишіть його cookie в BROWSER_STORAGE і підніміть PRIVACY_POLICY_VERSION.
export const OPTIONAL_SCRIPTS: OptionalScript[] = []

export const hasOptionalTools = OPTIONAL_SCRIPTS.length > 0

// Якщо localStorage недоступне (приватний режим, заборона браузера),
// вибір живе до перезавантаження сторінки, і банер не з'являється знову в цій сесії.
let memoryConsent: CookieConsent | null = null

function isConsent(value: unknown): value is CookieConsent {
  if (!value || typeof value !== 'object') return false
  const item = value as Partial<CookieConsent>
  return (
    typeof item.version === 'string' &&
    typeof item.decidedAt === 'string' &&
    !!item.categories &&
    item.categories.necessary === true &&
    typeof item.categories.analytics === 'boolean'
  )
}

export function readConsent(): CookieConsent | null {
  try {
    const raw = localStorage.getItem(CONSENT_STORAGE_KEY)
    if (raw) {
      const parsed: unknown = JSON.parse(raw)
      if (isConsent(parsed)) return parsed
    }
  } catch {
    // пошкоджений JSON або заборонене сховище - питаємо знову
  }
  return memoryConsent
}

export function isConsentCurrent(consent: CookieConsent | null): consent is CookieConsent {
  return consent !== null && consent.version === PRIVACY_POLICY_VERSION
}

export function saveConsent(analytics: boolean): CookieConsent {
  const previous = readConsent()
  const consent: CookieConsent = {
    version: PRIVACY_POLICY_VERSION,
    decidedAt: new Date().toISOString(),
    categories: { necessary: true, analytics },
  }
  memoryConsent = consent
  try {
    localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(consent))
  } catch {
    // залишаємо вибір у пам'яті
  }

  window.dispatchEvent(new CustomEvent(CONSENT_CHANGE_EVENT, { detail: consent }))

  // Уже завантажений скрипт не можна «вивантажити» - після відкликання згоди
  // перезавантажуємо сторінку, щоб він більше не працював.
  const withdrawn = previous?.categories.analytics === true && !analytics
  if (withdrawn && document.querySelector('script[data-consent-category]')) {
    window.location.reload()
  } else {
    loadOptionalScripts(consent)
  }
  return consent
}

export function loadOptionalScripts(consent: CookieConsent | null): void {
  if (!isConsentCurrent(consent)) return
  for (const script of OPTIONAL_SCRIPTS) {
    if (!consent.categories[script.category]) continue
    if (document.querySelector(`script[data-consent-id="${script.id}"]`)) continue
    const element = document.createElement('script')
    element.src = script.src
    element.async = true
    element.dataset.consentId = script.id
    element.dataset.consentCategory = script.category
    document.head.appendChild(element)
  }
}

export function openCookieSettings(): void {
  window.dispatchEvent(new Event(OPEN_SETTINGS_EVENT))
}

export function formatConsentDate(iso: string): string {
  return new Date(iso).toLocaleString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
