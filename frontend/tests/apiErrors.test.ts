// KAN-115: перевірка перетворення помилок API на повідомлення для користувача.
// Запуск: npm test (вбудований тест-раннер Node.js, без додаткових залежностей).

import assert from 'node:assert/strict'
import { afterEach, describe, it } from 'node:test'

import {
  ApiError,
  DEFAULT_MESSAGES,
  errorFromBody,
  errorMessage,
  requestApi,
} from '../src/services/apiErrors.ts'

const realFetch = globalThis.fetch

function mockFetch(handler: (init?: RequestInit) => Promise<Response>) {
  globalThis.fetch = ((_url: string, init?: RequestInit) => handler(init)) as typeof fetch
}

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  globalThis.fetch = realFetch
})

describe('формати помилок бекенду', () => {
  it('TC-UI-01: 403 — показує текст сервера українською', () => {
    const error = errorFromBody(403, { detail: 'Недостатньо прав для цієї дії' })
    assert.equal(error.kind, 'forbidden')
    assert.equal(error.message, 'Недостатньо прав для цієї дії')
  })

  it('TC-UI-02: 422 з одним полем — повідомлення саме про це поле', () => {
    const error = errorFromBody(422, {
      detail: [{ loc: ['body', 'location'], msg: 'Ділянка не обслуговується' }],
    })
    assert.equal(error.kind, 'validation')
    assert.equal(error.message, 'Ділянка не обслуговується')
    assert.deepEqual(error.fieldErrors, { location: 'Ділянка не обслуговується' })
  })

  it('TC-UI-03: 422 англійською від Pydantic — замість системного тексту назва поля', () => {
    const error = errorFromBody(422, {
      detail: [
        { loc: ['body', 'password'], msg: 'String should have at least 8 characters' },
        { loc: ['body', 'email'], msg: 'value is not a valid email address' },
      ],
    })
    assert.equal(error.message, 'Перевірте поля: Пароль, Email.')
    assert.deepEqual(error.fieldErrors, {
      password: 'Перевірте поле «Пароль».',
      email: 'Перевірте поле «Email».',
    })
  })

  it('TC-UI-03a: 422 українською в кількох полях — пояснення сервера через «;»', () => {
    const error = errorFromBody(422, {
      detail: [
        { loc: ['body', 'location'], msg: 'Ділянка не обслуговується' },
        { loc: ['body', 'comment'], msg: 'Коментар довший за 500 символів' },
      ],
    })
    assert.equal(error.message, 'Ділянка не обслуговується; Коментар довший за 500 символів')
  })

  it('TC-UI-04: 403 через відсутню згоду — перелік згод зрозумілими словами', () => {
    const error = errorFromBody(403, {
      detail: { message: 'not readable', missing_consents: ['contact', 'media_sharing'] },
    })
    assert.equal(error.kind, 'consent')
    assert.deepEqual(error.missingConsents, ['contact', 'media_sharing'])
    assert.match(error.message, /зв’язок диспетчера з вами, передача фото й коментаря службам/)
  })

  it('TC-UI-05: 401 — завжди «Сесія завершилась», а не текст про токен', () => {
    const error = errorFromBody(401, { detail: 'Недійсний або прострочений токен' })
    assert.equal(error.kind, 'unauthorized')
    assert.equal(error.message, DEFAULT_MESSAGES.unauthorized)
  })

  it('TC-UI-06: 500 — без технічних деталей і кодів HTTP', () => {
    const error = errorFromBody(500, { detail: 'Traceback: sqlalchemy.exc.OperationalError' })
    assert.equal(error.kind, 'server')
    assert.equal(error.message, DEFAULT_MESSAGES.server)
    assert.doesNotMatch(error.message, /HTTP|500|Traceback/)
    assert.ok(error.retryable)
  })

  it('TC-UI-07: свій текст для сторінки має пріоритет над текстом сервера', () => {
    const error = errorFromBody(
      403,
      { detail: 'Недостатньо прав для цієї дії' },
      { forbidden: 'Журнал аудиту доступний лише адміністратору.' },
    )
    assert.equal(error.message, 'Журнал аудиту доступний лише адміністратору.')
  })

  it('TC-UI-08: 409 і 429 — текст сервера; 429 можна повторити', () => {
    assert.equal(
      errorFromBody(409, { detail: 'Ви вже підтвердили цю заявку' }).message,
      'Ви вже підтвердили цю заявку',
    )
    const limit = errorFromBody(429, { detail: 'Перевищено ліміт: не більше 10 заявок на годину' })
    assert.equal(limit.kind, 'rate_limit')
    assert.ok(limit.retryable)
  })
})

describe('requestApi', () => {
  it('TC-UI-09: сервер недоступний — повідомлення про зв’язок', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    await assert.rejects(requestApi('http://api/test'), (error: unknown) => {
      assert.ok(error instanceof ApiError)
      assert.equal(error.kind, 'network')
      assert.equal(error.message, DEFAULT_MESSAGES.network)
      return true
    })
  })

  it('TC-UI-10: сервер не відповідає довше за ліміт — повідомлення про таймаут', async () => {
    // «Сервер» відповідає лише тоді, коли запит скасовано, як справжній fetch.
    mockFetch(
      (init) =>
        new Promise<Response>((_, reject) => {
          init?.signal?.addEventListener('abort', () =>
            reject(new DOMException('aborted', 'AbortError')),
          )
        }),
    )
    await assert.rejects(requestApi('http://api/test', {}, { timeoutMs: 5 }), {
      kind: 'timeout',
    })
  })

  it('TC-UI-11: відповідь не JSON (HTML від проксі) — загальна помилка сервера', async () => {
    mockFetch(() => Promise.resolve(new Response('<html>Bad Gateway</html>', { status: 502 })))
    await assert.rejects(requestApi('http://api/test'), {
      kind: 'server',
      message: DEFAULT_MESSAGES.server,
    })
  })

  it('TC-UI-12: успішна відповідь повертає тіло', async () => {
    mockFetch(() => Promise.resolve(json(200, { total: 1 })))
    assert.deepEqual(await requestApi<{ total: number }>('http://api/test'), { total: 1 })
  })
})

describe('errorMessage', () => {
  it('TC-UI-13: англійська помилка JavaScript не потрапляє до користувача', () => {
    assert.equal(errorMessage(new TypeError('x is undefined')), DEFAULT_MESSAGES.server)
    assert.equal(errorMessage(new Error('Оберіть тип проблеми')), 'Оберіть тип проблеми')
  })
})
