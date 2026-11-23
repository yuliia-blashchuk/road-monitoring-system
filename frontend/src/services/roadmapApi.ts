// Клієнт API RoadMap: усі запити фронтенду до бекенду, крім входу (authApi.ts)
// і журналу аудиту (auditApi.ts). Назви полів - як у бекенді (README, розділ
// «Читання заявок»); у компонентах карти заявки перетворюються на RoadEvent.

import type { RoadEvent, RoadEventStatus, RoadEventType } from '../data/mapEvents'

const API_URL =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000/api/v1'

// Адреса бекенду без /api/v1 - для посилань на фото (url у картці починається з /api/v1).
export const API_ORIGIN = API_URL.replace(/\/api\/v1\/?$/, '')

export const TOKEN_KEY = 'roadmap_access_token'

export function getToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}

// ---------- типи відповідей бекенду ----------

export type Priority = 'low' | 'medium' | 'high' | 'critical'

export type ProblemType = {
  id: number
  code: RoadEventType
  name: string
  icon: string
  color: string
}

// GET /reports - публічна карта
export type MapReport = {
  id: number
  number: number
  problem_type: RoadEventType
  problem_label: string
  icon: string
  color: string
  status: RoadEventStatus
  status_label: string
  lat: number
  lng: number
  address: string | null
  confirmations_count: number
  created_at: string
}

// GET /reports/my - «Мої звернення»
export type MyReport = MapReport & {
  comment: string | null
  service: string | null
  photos_count: number
  updated_at: string
}

export type Page<T> = {
  total: number
  limit: number
  offset: number
  items: T[]
}

export type PhotoInfo = {
  id: number
  kind: 'before' | 'after' | 'act'
  mime_type: string
  created_at: string
  url: string
}

// GET /reports/{id} - картка (поля, яких ролі не можна, відсутні)
export type ReportCard = MapReport & {
  service: string | null
  comment?: string | null
  priority?: Priority
  copy_service?: string | null
  deadline?: string | null
  progress_percent?: number | null
  reject_reason?: string | null
  is_suspicious?: boolean
  is_reopened?: boolean
  contractor_id?: number | null
  author?: string | null
  author_id?: number | null
  photos: PhotoInfo[]
  next_statuses: RoadEventStatus[]
}

// GET /reports/{id}/history - таймлайн статусів
export type HistoryItem = {
  from_status: RoadEventStatus | null
  to_status: RoadEventStatus
  to_label: string
  comment: string | null
  changed_at: string
  changed_by: number | null
}

export type ReportHistory = {
  id: number
  number: number
  status: RoadEventStatus
  items: HistoryItem[]
}

// GET /queue - черга служби
export type QueueItem = MapReport & {
  priority: Priority
  comment: string | null
  author: string | null
  service: string | null
  is_copy: boolean
  deadline: string | null
  progress_percent: number | null
  is_suspicious: boolean
  is_reopened: boolean
  next_statuses: RoadEventStatus[]
}

// POST /reports - відповідь після створення заявки
export type ReportCreated = {
  id: number
  number: number
  status: RoadEventStatus
  priority: Priority
  problem_type: string
  service: string | null
  copy_service: string | null
  photos_count: number
  created_at: string
}

// PATCH /reports/{id}/status
export type StatusChange = {
  status: RoadEventStatus
  comment?: string
  reject_reason?: string
  deadline?: string // YYYY-MM-DD
}

// GET /work-orders - роботи підрядника
export type WorkOrder = {
  id: number
  number: number
  status: RoadEventStatus
  priority: Priority
  problem_type: string
  address: string | null
  service_id: number | null
  contractor_id: number | null
  contractor_name: string | null
  deadline: string | null
  progress_percent: number | null
  is_overdue: boolean
}

// GET /notifications
export type NotificationItem = {
  id: number
  request_id: number | null
  type: string
  message: string
  is_read: boolean
  created_at: string
}

export type NotificationPage = Page<NotificationItem> & { unread: number }

// ---------- спільний запит ----------

type ApiErrorDetail = string | { loc?: (string | number)[]; msg?: string }[] | undefined

// Текст помилки з відповіді бекенду: detail - рядок або список помилок полів (422).
function errorText(status: number, detail: ApiErrorDetail): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item.msg ?? '').filter(Boolean).join('; ')
  }
  if (status === 401) return 'Сесія завершилась. Увійдіть знову.'
  if (status === 403) return 'Недостатньо прав для цієї дії.'
  if (status === 404) return 'Не знайдено.'
  return `Помилка сервера RoadMap (HTTP ${status}).`
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, options: RequestInit = {}, auth = true): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (auth && token) headers.set('Authorization', `Bearer ${token}`)

  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers })
  } catch {
    throw new ApiError(0, 'Сервер RoadMap недоступний. Перевірте, що бекенд запущено.')
  }

  if (!response.ok) {
    let detail: ApiErrorDetail
    try {
      detail = ((await response.json()) as { detail?: ApiErrorDetail }).detail
    } catch {
      detail = undefined
    }
    throw new ApiError(response.status, errorText(response.status, detail))
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

function query(params: Record<string, string | number | string[] | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue
    if (Array.isArray(value)) value.forEach((item) => search.append(key, item))
    else search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

// ---------- довідники ----------

export function getProblemTypes(): Promise<ProblemType[]> {
  return request<ProblemType[]>('/problem-types', {}, false)
}

// ---------- карта, мої звернення, картка ----------

export function getMapReports(
  filters: { type?: string[]; status?: string[]; bbox?: string; limit?: number } = {},
): Promise<MapReport[]> {
  return request<MapReport[]>(`/reports${query(filters)}`, {}, false)
}

export function getMyReports(limit = 50, offset = 0): Promise<Page<MyReport>> {
  return request<Page<MyReport>>(`/reports/my${query({ limit, offset })}`)
}

export function getReport(id: number): Promise<ReportCard> {
  return request<ReportCard>(`/reports/${id}`)
}

export function getReportHistory(id: number): Promise<ReportHistory> {
  return request<ReportHistory>(`/reports/${id}/history`)
}

// Фото захищені токеном, тому <img src=...> напряму не підходить:
// завантажуємо файл і повертаємо тимчасову адресу для <img>.
export async function getPhotoUrl(photo: PhotoInfo): Promise<string> {
  const token = getToken()
  const response = await fetch(`${API_ORIGIN}${photo.url}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) throw new ApiError(response.status, 'Фото недоступне.')
  return URL.createObjectURL(await response.blob())
}

// ---------- створення заявки ----------

export function createReport(data: {
  problemType: string
  lat: number
  lng: number
  comment?: string
  address?: string
  photos: File[]
  mediaSharingConsent: boolean
}): Promise<ReportCreated> {
  const form = new FormData()
  form.set('problem_type', data.problemType)
  form.set('latitude', String(data.lat))
  form.set('longitude', String(data.lng))
  if (data.comment?.trim()) form.set('comment', data.comment.trim())
  if (data.address?.trim()) form.set('address', data.address.trim())
  form.set('media_sharing_consent', String(data.mediaSharingConsent))
  data.photos.forEach((photo) => form.append('photos', photo))
  // Content-Type для FormData браузер ставить сам (разом із межею multipart).
  return request<ReportCreated>('/reports', { method: 'POST', body: form })
}

// ---------- служба ----------

export function getQueue(status?: string[], limit = 100, offset = 0): Promise<Page<QueueItem>> {
  return request<Page<QueueItem>>(`/queue${query({ status, limit, offset })}`)
}

export function changeStatus(id: number, change: StatusChange): Promise<unknown> {
  return request(`/reports/${id}/status`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(change),
  })
}

// ---------- підрядник ----------

export function getWorkOrders(status?: string, limit = 100): Promise<WorkOrder[]> {
  return request<WorkOrder[]>(`/work-orders${query({ status, limit })}`)
}

export function updateProgress(
  id: number,
  data: { percent: number; comment?: string; photos: File[]; act?: File | null },
): Promise<unknown> {
  const form = new FormData()
  form.set('progress_percent', String(data.percent))
  if (data.comment?.trim()) form.set('comment', data.comment.trim())
  data.photos.forEach((photo) => form.append('photos', photo))
  if (data.act) form.set('act', data.act)
  return request(`/work-orders/${id}/progress`, { method: 'POST', body: form })
}

// ---------- сповіщення ----------

export function getNotifications(unreadOnly = false, limit = 20): Promise<NotificationPage> {
  return request<NotificationPage>(
    `/notifications${query({ unread_only: unreadOnly ? 'true' : undefined, limit })}`,
  )
}

export function markNotificationRead(id: number): Promise<NotificationItem> {
  return request<NotificationItem>(`/notifications/${id}/read`, { method: 'POST' })
}

export function markAllNotificationsRead(): Promise<{ updated: number }> {
  return request<{ updated: number }>('/notifications/read-all', { method: 'POST' })
}

// ---------- перетворення для карти ----------

// Заявка з бекенду -> формат RoadEvent, з яким уже працюють карта й головна сторінка.
export function toRoadEvent(report: MapReport): RoadEvent {
  return {
    id: report.id,
    title: `${report.problem_label} №${report.number}`,
    address: report.address ?? 'Адресу не вказано',
    type: report.problem_type,
    status: report.status,
    lat: report.lat,
    lng: report.lng,
    createdAt: report.created_at,
  }
}