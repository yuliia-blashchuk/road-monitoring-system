// KAN-115 — зрозумілі повідомлення про помилки API для користувача.
//
// Бекенд повертає помилки в трьох форматах (див. docs/api/KAN-113-api-check.md):
//   { "detail": "текст" }                                        — 401, 403, 404, 409, 429
//   { "detail": [{ "loc": ["body", "поле"], "msg": "текст" }] }   — 422, помилка в полі
//   { "detail": { "message": "текст", "missing_consents": [...] } } — 403, бракує згоди
// Тут вони перетворюються на ApiError з одним повідомленням українською, без кодів HTTP,
// назв полів у коді чи англійських системних текстів.

export type ApiErrorKind =
  | 'network'
  | 'timeout'
  | 'unauthorized'
  | 'forbidden'
  | 'consent'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'rate_limit'
  | 'server'

export type ErrorMessages = Partial<Record<ApiErrorKind, string>>

export const DEFAULT_MESSAGES: Record<ApiErrorKind, string> = {
  network: 'Немає зв’язку із сервером RoadMap. Перевірте інтернет і спробуйте ще раз.',
  timeout: 'Сервер довго не відповідає. Спробуйте ще раз трохи згодом.',
  unauthorized: 'Сесія завершилась. Увійдіть знову.',
  forbidden: 'Недостатньо прав для цієї дії.',
  consent: 'Для цієї дії потрібна ваша згода.',
  not_found: 'Запис не знайдено. Можливо, посилання застаріло.',
  conflict: 'Цю дію зараз виконати не можна. Оновіть сторінку й спробуйте ще раз.',
  validation: 'Перевірте правильність заповнення полів.',
  rate_limit: 'Забагато спроб. Спробуйте трохи пізніше.',
  server: 'На сервері сталася помилка. Спробуйте трохи пізніше.',
}

// Назви полів так, як їх бачить користувач у формах.
const FIELD_LABELS: Record<string, string> = {
  email: 'Email',
  username: 'Email',
  password: 'Пароль',
  full_name: 'Ім’я',
  phone: 'Телефон',
  consents: 'Згоди',
  problem_type: 'Тип проблеми',
  latitude: 'Місце на карті',
  longitude: 'Місце на карті',
  location: 'Місце на карті',
  address: 'Адреса',
  comment: 'Коментар',
  photos: 'Фото',
  device_created_at: 'Час створення',
  status: 'Статус',
  reject_reason: 'Причина відхилення',
  deadline: 'Строк виконання',
  progress_percent: 'Прогрес',
  contractor_id: 'Підрядник',
  date_from: 'Початок періоду',
  date_to: 'Кінець періоду',
  actor_id: 'Користувач',
  entity_id: 'ID',
  bbox: 'Область карти',
}

const CONSENT_LABELS: Record<string, string> = {
  terms: 'правила користування',
  personal_data: 'обробка персональних даних',
  media_sharing: 'передача фото й коментаря службам',
  contact: 'зв’язок диспетчера з вами',
  email_notifications: 'сповіщення на email',
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status: number | null
  // поле форми -> повідомлення (лише для validation)
  readonly fieldErrors: Record<string, string>
  // коди згод, яких бракує (лише для consent)
  readonly missingConsents: string[]

  constructor(
    kind: ApiErrorKind,
    message: string,
    options: {
      status?: number | null
      fieldErrors?: Record<string, string>
      missingConsents?: string[]
    } = {},
  ) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = options.status ?? null
    this.fieldErrors = options.fieldErrors ?? {}
    this.missingConsents = options.missingConsents ?? []
  }

  // Чи має сенс кнопка «Спробувати ще»: помилка тимчасова, а не в даних чи правах.
  get retryable(): boolean {
    return ['network', 'timeout', 'server', 'rate_limit'].includes(this.kind)
  }
}

const CYRILLIC = /[А-Яа-яІіЇїЄєҐґ]/

// Текст сервера показуємо, лише якщо він написаний для людини (українською й коротко).
function readable(text: unknown): string | null {
  if (typeof text !== 'string') return null
  const trimmed = text.trim()
  return trimmed && trimmed.length <= 300 && CYRILLIC.test(trimmed) ? trimmed : null
}

export function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? 'Поле форми'
}

export function consentLabel(code: string): string {
  return CONSENT_LABELS[code] ?? code
}

function kindForStatus(status: number): ApiErrorKind {
  if (status === 401) return 'unauthorized'
  if (status === 403) return 'forbidden'
  if (status === 404) return 'not_found'
  if (status === 409) return 'conflict'
  if (status === 422 || status === 400) return 'validation'
  if (status === 429) return 'rate_limit'
  return 'server'
}

type Issue = { loc?: unknown; msg?: unknown }

function fieldErrorsFrom(issues: Issue[]): Record<string, string> {
  const result: Record<string, string> = {}
  for (const issue of issues) {
    const loc = Array.isArray(issue.loc) ? issue.loc : []
    const field = String(loc[loc.length - 1] ?? '')
    if (!field || field in result) continue
    // Англійські системні тексти Pydantic замінюємо загальним «перевірте поле».
    result[field] = readable(issue.msg) ?? `Перевірте поле «${fieldLabel(field)}».`
  }
  return result
}

// Перетворює відповідь із помилкою на ApiError.
// messages — свої тексти для окремих випадків (наприклад, для 403 на сторінці журналу).
export function errorFromBody(
  status: number,
  body: unknown,
  messages: ErrorMessages = {},
): ApiError {
  let kind = kindForStatus(status)
  const detail = (body as { detail?: unknown } | null)?.detail

  if (kind === 'validation' && Array.isArray(detail)) {
    const fieldErrors = fieldErrorsFrom(detail as Issue[])
    const fields = Object.keys(fieldErrors)
    const labels = [...new Set(fields.map(fieldLabel))]
    // Якщо сервер пояснив кожне поле українською - показуємо його пояснення.
    const allReadable = (detail as Issue[]).every((issue) => readable(issue.msg))
    const message =
      messages.validation ??
      (fields.length === 1
        ? fieldErrors[fields[0]]
        : fields.length > 1 && allReadable
          ? Object.values(fieldErrors).join('; ')
          : fields.length > 1
            ? `Перевірте поля: ${labels.join(', ')}.`
            : DEFAULT_MESSAGES.validation)
    return new ApiError(kind, message, { status, fieldErrors })
  }

  if (status === 403 && detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const consent = detail as { message?: unknown; missing_consents?: unknown }
    if (Array.isArray(consent.missing_consents)) {
      kind = 'consent'
      const missing = consent.missing_consents.map(String)
      const message =
        messages.consent ??
        readable(consent.message) ??
        `${DEFAULT_MESSAGES.consent} Потрібно: ${missing.map(consentLabel).join(', ')}.`
      return new ApiError(kind, message, { status, missingConsents: missing })
    }
  }

  // Для 401 і збоїв сервера текст сервера не показуємо: він технічний або
  // стосується токена, а користувачу треба знати, що робити далі.
  const serverText = kind === 'server' || kind === 'unauthorized' ? null : readable(detail)
  const message = messages[kind] ?? serverText ?? DEFAULT_MESSAGES[kind]
  return new ApiError(kind, message, { status })
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

export type RequestOptions = {
  messages?: ErrorMessages
  // скільки чекати відповіді, мс (за замовчуванням 15 с)
  timeoutMs?: number
}

// fetch з єдиною обробкою помилок: успіх — тіло JSON (або null), помилка — ApiError.
export async function requestApi<T>(
  url: string,
  init: RequestInit = {},
  { messages = {}, timeoutMs = 15_000 }: RequestOptions = {},
): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let response: Response
  try {
    response = await fetch(url, { ...init, signal: controller.signal })
  } catch (error) {
    const timedOut = error instanceof DOMException && error.name === 'AbortError'
    const kind: ApiErrorKind = timedOut ? 'timeout' : 'network'
    throw new ApiError(kind, messages[kind] ?? DEFAULT_MESSAGES[kind])
  } finally {
    clearTimeout(timer)
  }

  const body = await readJson(response)
  if (!response.ok) throw errorFromBody(response.status, body, messages)
  return body as T
}

// Текст для будь-якої помилки з catch: ApiError, звичайна Error або щось інше.
export function errorMessage(error: unknown, fallback = DEFAULT_MESSAGES.server): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error && readable(error.message)) return error.message
  return fallback
}
