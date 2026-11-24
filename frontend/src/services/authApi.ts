// Інтеграція з готовим бекендом RoadMap (KAN-49).
// Власну базу даних або сервер для KAN-52 створювати не потрібно.
import { requestApi, type ErrorMessages } from './apiErrors'

const API_URL = 'http://localhost:8000/api/v1'

export type AuthToken = {
  access_token: string
  token_type: string
  expires_in: number
  role: string
}

export type UserProfile = {
  id: number
  email: string
  full_name: string
  phone: string | null
  role: string
  service_id: number | null
  contractor_id: number | null
}

export type RegisterData = {
  email: string
  password: string
  full_name: string
  phone?: string
  consents: Array<'terms' | 'personal_data'>
}

// Помилки перетворюються на зрозумілі повідомлення в apiErrors.ts (KAN-115).
function callApi(path: string, options: RequestInit, messages: ErrorMessages = {}) {
  return requestApi<unknown>(`${API_URL}${path}`, options, { messages })
}

export async function loginUser(email: string, password: string): Promise<AuthToken> {
  const form = new URLSearchParams()
  form.set('username', email.trim())
  form.set('password', password)

  const data = await callApi(
    '/auth/login',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    },
    { unauthorized: 'Невірний email або пароль.' },
  )
  const token = data as AuthToken | null
  if (!token || typeof token.access_token !== 'string' || !token.access_token) {
    throw new Error('Сервер не повернув токен доступу.')
  }
  return token
}

export async function registerUser(payload: RegisterData): Promise<void> {
  await callApi('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getCurrentUser(accessToken: string): Promise<UserProfile> {
  const data = await callApi('/auth/me', {
    method: 'GET',
    headers: { Authorization: `Bearer ${accessToken}` },
  })
  const user = data as UserProfile | null
  if (!user || typeof user.role !== 'string') {
    throw new Error('Не вдалося отримати роль користувача із сервера.')
  }
  return user
}
