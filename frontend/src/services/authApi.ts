// Інтеграція з готовим бекендом RoadMap (KAN-49).
// Власну базу даних або сервер для KAN-52 створювати не потрібно.
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

async function parseResponse(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

async function callApi(path: string, options: RequestInit): Promise<unknown> {
  let response: Response
  try {
    response = await fetch(`${API_URL}${path}`, options)
  } catch {
    throw new Error('Сервер RoadMap недоступний. Для перевірки потрібен запущений бекенд команди.')
  }
  const data = await parseResponse(response)

  if (!response.ok) {
    if (response.status === 401) throw new Error('Невірний email або пароль чи завершена сесія.')
    if (response.status === 403) throw new Error('Доступ заборонено або акаунт деактивовано.')
    if (response.status === 409) throw new Error('Користувач із таким email уже зареєстрований.')
    if (response.status === 422) throw new Error('Некоректні дані. Перевірте поля та обов’язкові згоди.')
    throw new Error(`Помилка сервера RoadMap (HTTP ${response.status}).`)
  }
  return data
}

export async function loginUser(email: string, password: string): Promise<AuthToken> {
  const form = new URLSearchParams()
  form.set('username', email.trim())
  form.set('password', password)

  const data = await callApi('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })
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
