// Журнал аудиту (KAN-67): сторінка над API GET /audit з KAN-60, лише для адміністратора
// і Data Governance.
// Права перевіряє бекенд; кожен перегляд журналу сам записується як AUDIT_VIEWED.

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000/api/v1'

export const TOKEN_KEY = 'roadmap_access_token'

export type AuditEntry = {
  id: number
  created_at: string
  actor_id: number | null
  actor_role: string | null
  action: string
  entity_type: string | null
  entity_id: number | null
  result: 'success' | 'failure' | 'denied' | string
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  correlation_id: string | null
}

export type AuditFilters = {
  dateFrom: string // значення поля datetime-local
  dateTo: string
  action: string
  actorRole: string
  actorId: string
  entityType: string
  entityId: string
  result: '' | 'success' | 'failure' | 'denied'
  correlationId: string
}

export const EMPTY_FILTERS: AuditFilters = {
  dateFrom: '',
  dateTo: '',
  action: '',
  actorRole: '',
  actorId: '',
  entityType: '',
  entityId: '',
  result: '',
  correlationId: '',
}

// Відповідь GET /audit (KAN-60): записи від новіших до старіших і кількість за фільтром.
export type AuditPage = {
  total: number
  limit: number
  offset: number
  items: AuditEntry[]
}

// Локальний час з поля datetime-local -> ISO з часовим поясом для API.
function toIso(local: string): string {
  return new Date(local).toISOString()
}

export function buildQuery(
  filters: AuditFilters,
  snapshot: string,
  limit: number,
  offset: number,
): URLSearchParams {
  const params = new URLSearchParams()
  // Верхня межа - не пізніше моменту першого завантаження, щоб нові записи
  // (зокрема AUDIT_VIEWED від самого перегляду) не зсували сторінки.
  const userTo = filters.dateTo ? toIso(filters.dateTo) : ''
  params.set('date_to', userTo && userTo < snapshot ? userTo : snapshot)
  if (filters.dateFrom) params.set('date_from', toIso(filters.dateFrom))
  if (filters.action) params.set('action', filters.action)
  if (filters.actorRole) params.set('actor_role', filters.actorRole)
  if (filters.actorId.trim()) params.set('actor_id', filters.actorId.trim())
  if (filters.entityType) params.set('entity_type', filters.entityType)
  if (filters.entityId.trim()) params.set('entity_id', filters.entityId.trim())
  if (filters.result) params.set('result', filters.result)
  if (filters.correlationId.trim()) params.set('correlation_id', filters.correlationId.trim())
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  return params
}

export async function fetchAuditLog(
  token: string,
  filters: AuditFilters,
  snapshot: string,
  limit: number,
  offset: number,
): Promise<AuditPage> {
  let response: Response
  try {
    response = await fetch(`${API_URL}/audit?${buildQuery(filters, snapshot, limit, offset)}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
  } catch {
    throw new Error('Сервер RoadMap недоступний. Перевірте, що бекенд запущено.')
  }

  if (response.status === 401) throw new Error('Сесія завершилась. Увійдіть знову.')
  if (response.status === 403)
    throw new Error('Журнал аудиту доступний лише адміністратору й Data Governance.')
  if (response.status === 422)
    throw new Error(
      'Перевірте фільтри: наприклад, кінець періоду раніший за початок або ID не число.',
    )
  if (!response.ok) throw new Error(`Помилка сервера RoadMap (HTTP ${response.status}).`)

  return (await response.json()) as AuditPage
}
