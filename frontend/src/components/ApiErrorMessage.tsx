// KAN-115 — блок з повідомленням про помилку API.
// Показує зрозумілий текст, поля з помилками й дію, яка допоможе:
// «Спробувати ще» для тимчасових збоїв, «Увійти знову» для завершеної сесії.

import { Link } from 'react-router'
import { ApiError, fieldLabel } from '../services/apiErrors'
import './ApiErrorMessage.css'

const TITLES: Record<ApiError['kind'], string> = {
  network: 'Немає зв’язку',
  timeout: 'Сервер не відповідає',
  unauthorized: 'Потрібно увійти',
  forbidden: 'Немає доступу',
  consent: 'Потрібна згода',
  not_found: 'Не знайдено',
  conflict: 'Дію не виконано',
  validation: 'Перевірте дані',
  rate_limit: 'Забагато спроб',
  server: 'Помилка сервера',
}

type Props = {
  error: unknown
  onRetry?: () => void
}

function ApiErrorMessage({ error, onRetry }: Props) {
  if (!error) return null
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError('server', error instanceof Error ? error.message : String(error))
  const fields = Object.entries(apiError.fieldErrors)
  // Якщо помилка одна, вона вже в основному тексті — список не дублюємо.
  const showFields = fields.length > 1

  return (
    <div className={`rm-api-error rm-api-error--${apiError.kind}`} role="alert">
      <strong className="rm-api-error__title">{TITLES[apiError.kind]}</strong>
      <p className="rm-api-error__text">{apiError.message}</p>
      {showFields && (
        <ul className="rm-api-error__fields">
          {fields.map(([field, message]) => (
            <li key={field}>
              <b>{fieldLabel(field)}:</b> {message}
            </li>
          ))}
        </ul>
      )}
      {apiError.kind === 'unauthorized' && (
        <Link className="rm-api-error__action" to="/login">
          Увійти знову
        </Link>
      )}
      {apiError.retryable && onRetry && (
        <button className="rm-api-error__action" type="button" onClick={onRetry}>
          Спробувати ще
        </button>
      )}
    </div>
  )
}

export default ApiErrorMessage
