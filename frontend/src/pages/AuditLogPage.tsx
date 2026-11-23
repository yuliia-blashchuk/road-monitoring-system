// KAN-67 — сторінка журналу аудиту для адміністратора і Data Governance (п. 3.8, табл. 18).
// Показує, хто, коли й які дані передав, отримав або змінив. Журнал лише для читання:
// змінити чи видалити запис не може жодна роль.

import { useEffect, useState, type FormEvent } from 'react'

import {
  EMPTY_FILTERS,
  TOKEN_KEY,
  fetchAuditLog,
  type AuditEntry,
  type AuditFilters,
  type AuditPage,
} from '../services/auditApi'
import './AuditLogPage.css'

const PAGE_SIZE = 50

// Події журналу за групами табл. 18.
const ACTION_GROUPS: { group: string; actions: [string, string][] }[] = [
  {
    group: 'Заявки',
    actions: [
      ['REPORT_CREATED', 'Створено заявку'],
      ['REPORT_CONFIRMED', 'Підтверджено «Теж бачу»'],
      ['STATUS_CHANGED', 'Змінено статус'],
      ['REPORT_REDIRECTED', 'Перенаправлено'],
      ['PRIORITY_RECALCULATED', 'Перераховано пріоритет'],
    ],
  },
  {
    group: 'Передача даних',
    actions: [
      ['REPORT_DELIVERED', 'Доставлено службі'],
      ['COPY_SENT', 'Надіслано копію'],
      ['EXTERNAL_TRANSFER', 'Передано в міську систему'],
      ['DATA_EXPORTED', 'Експорт даних'],
    ],
  },
  {
    group: 'Підрядні роботи',
    actions: [
      ['WORK_ASSIGNED', 'Призначено підрядника'],
      ['WORK_PROGRESS', 'Оновлено прогрес'],
      ['ACT_UPLOADED', 'Додано акт'],
      ['CONTRACTOR_ACCESS_CLOSED', 'Закрито доступ підрядника'],
    ],
  },
  {
    group: 'Персональні дані',
    actions: [
      ['CONTACT_REVEALED', 'Розкрито контакт автора'],
      ['PHOTO_ORIGINAL_VIEWED', 'Переглянуто оригінал фото'],
      ['CONSENT_GRANTED', 'Надано згоду'],
      ['CONSENT_REVOKED', 'Відкликано згоду'],
      ['ACCOUNT_DELETED', 'Видалено акаунт'],
    ],
  },
  {
    group: 'Безпека',
    actions: [
      ['LOGIN_SUCCESS', 'Вхід у систему'],
      ['LOGIN_FAILED', 'Невдалий вхід'],
      ['ACCESS_DENIED', 'Відмова в доступі'],
      ['ROLE_CHANGED', 'Змінено роль'],
      ['POLICY_CHANGED', 'Змінено політику доступу'],
      ['AUDIT_VIEWED', 'Переглянуто журнал'],
    ],
  },
  {
    group: 'Службові',
    actions: [['RETENTION_RUN', 'Очищення за термінами зберігання']],
  },
]

const ACTION_LABELS = new Map(ACTION_GROUPS.flatMap((g) => g.actions))

const ROLE_LABELS: Record<string, string> = {
  driver: 'Водій',
  operator: 'Оператор',
  dispatcher: 'Диспетчер',
  police: 'Поліція',
  contractor: 'Підрядник',
  admin: 'Адміністратор',
  data_governance: 'Data Governance',
}

const ENTITY_LABELS: Record<string, string> = {
  request: 'Заявка',
  report: 'Заявка',
  consent: 'Згода',
  photo: 'Фото',
  work: 'Підрядні роботи',
  audit: 'Журнал аудиту',
  access_policy: 'Політика доступу',
  reference: 'Довідники',
  analytics: 'Аналітика',
}

const STATUS_LABELS: Record<string, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'В роботі',
  done: 'Виконана',
  resolved: 'Усунена',
  rejected: 'Відхилена',
}

const CONSENT_LABELS: Record<string, string> = {
  terms: 'правила користування',
  personal_data: 'персональні дані',
  media_sharing: 'передача фото й коментаря',
  contact: 'контакт для уточнення',
  email_notifications: 'сповіщення email',
}

const RESULT_LABELS = { success: 'Успіх', failure: 'Помилка', denied: 'Відмова' } as const

function resultKind(result: string): keyof typeof RESULT_LABELS {
  return result === 'denied' || result === 'failure' ? result : 'success'
}

function text(value: unknown): string {
  return value === null || value === undefined ? '—' : String(value)
}

function denyReason(reason: unknown): string {
  const value = text(reason)
  if (value === 'no_policy') return 'немає дозволу для ролі'
  if (value.startsWith('out_of_scope:')) return 'запис поза областю дії ролі'
  if (value.startsWith('consent_missing:')) {
    const types = value.slice('consent_missing:'.length).split(',')
    return `немає згоди: ${types.map((t) => CONSENT_LABELS[t] ?? t).join(', ')}`
  }
  if (value === 'bad_credentials') return 'невірний email або пароль'
  if (value === 'inactive') return 'акаунт деактивовано'
  return value
}

// Короткий підсумок запису для таблиці.
function summary(entry: AuditEntry): string {
  const oldV = entry.old_value ?? {}
  const newV = entry.new_value ?? {}
  switch (entry.action) {
    case 'STATUS_CHANGED':
      return `${STATUS_LABELS[text(oldV.status)] ?? text(oldV.status)} → ${
        STATUS_LABELS[text(newV.status)] ?? text(newV.status)
      }`
    case 'PRIORITY_RECALCULATED':
      return `Пріоритет ${text(oldV.priority)} → ${text(newV.priority)}`
    case 'ACCESS_DENIED':
      return `${text(newV.endpoint)}: ${denyReason(newV.reason)}`
    case 'LOGIN_FAILED':
      return denyReason(newV.reason)
    case 'CONSENT_GRANTED':
    case 'CONSENT_REVOKED': {
      const type = text(newV.type !== undefined ? newV.type : oldV.type)
      return `${CONSENT_LABELS[type] ?? type}, версія ${text(newV.version ?? oldV.version)}`
    }
    case 'WORK_ASSIGNED':
      return `Підрядник #${text(newV.contractor_id)}, строк ${text(newV.deadline)}`
    case 'REPORT_CREATED':
      return `Тип ${text(newV.problem_type)}, служба #${text(newV.service_id)}`
    case 'AUDIT_VIEWED': {
      const used = Object.keys(newV).filter((k) => k !== 'limit' && k !== 'offset')
      return used.length ? `Фільтри: ${used.join(', ')}` : 'Без фільтрів'
    }
    default:
      return ''
  }
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

type Query = { filters: AuditFilters; snapshot: string; offset: number }
type Result = { query: Query; page: AuditPage | null; error: string }

function AuditLogPage() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_FILTERS)
  const [query, setQuery] = useState<Query>(() => ({
    filters: EMPTY_FILTERS,
    snapshot: new Date().toISOString(),
    offset: 0,
  }))
  const [result, setResult] = useState<Result | null>(null)
  const [expanded, setExpanded] = useState<number | null>(null)

  useEffect(() => {
    const token = sessionStorage.getItem(TOKEN_KEY) ?? ''
    let active = true
    fetchAuditLog(token, query.filters, query.snapshot, PAGE_SIZE, query.offset)
      .then((page) => {
        if (active) setResult({ query, page, error: '' })
      })
      .catch((err: unknown) => {
        if (active) {
          setResult({
            query,
            page: null,
            error: err instanceof Error ? err.message : 'Не вдалося завантажити журнал.',
          })
        }
      })
    return () => {
      active = false
    }
  }, [query])

  const loading = result?.query !== query
  const page = result?.page
  const error = result?.error ?? ''

  function search(filters: AuditFilters) {
    setExpanded(null)
    setQuery({ filters, snapshot: new Date().toISOString(), offset: 0 })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    search(draft)
  }

  function reset() {
    setDraft(EMPTY_FILTERS)
    search(EMPTY_FILTERS)
  }

  // Усі записи однієї операції (correlation_id) - ланцюжок data lineage.
  function showOperation(correlationId: string) {
    const filters = { ...EMPTY_FILTERS, correlationId }
    setDraft(filters)
    search(filters)
  }

  function goTo(offset: number) {
    setExpanded(null)
    setQuery({ ...query, offset })
  }

  function update<K extends keyof AuditFilters>(key: K, value: AuditFilters[K]) {
    setDraft({ ...draft, [key]: value })
  }

  const total = page?.total ?? 0
  const first = total === 0 ? 0 : query.offset + 1
  const last = Math.min(query.offset + PAGE_SIZE, total)

  return (
    <div className="rm-audit-page">
      <header className="rm-audit-heading">
        <p>
          Хто, коли й які дані передав, отримав або змінив. Журнал доступний лише для читання;
          записи зберігаються 2 роки. Кожен перегляд журналу теж фіксується.
        </p>
        <span className="rm-audit-total" aria-live="polite">
          {loading ? 'Завантаження…' : `Записів: ${total}`}
        </span>
      </header>

      <form className="rm-audit-filters" onSubmit={handleSubmit}>
        <label>
          <span>Період з</span>
          <input
            type="datetime-local"
            value={draft.dateFrom}
            onChange={(e) => update('dateFrom', e.target.value)}
          />
        </label>
        <label>
          <span>по</span>
          <input
            type="datetime-local"
            value={draft.dateTo}
            onChange={(e) => update('dateTo', e.target.value)}
          />
        </label>
        <label>
          <span>Подія</span>
          <select value={draft.action} onChange={(e) => update('action', e.target.value)}>
            <option value="">Усі події</option>
            {ACTION_GROUPS.map((group) => (
              <optgroup key={group.group} label={group.group}>
                {group.actions.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <label>
          <span>Результат</span>
          <select
            value={draft.result}
            onChange={(e) => update('result', e.target.value as AuditFilters['result'])}
          >
            <option value="">Усі</option>
            <option value="success">Успіх</option>
            <option value="failure">Помилка</option>
            <option value="denied">Відмова</option>
          </select>
        </label>
        <label>
          <span>Роль</span>
          <select value={draft.actorRole} onChange={(e) => update('actorRole', e.target.value)}>
            <option value="">Усі ролі</option>
            {Object.entries(ROLE_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>ID користувача</span>
          <input
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="напр. 12"
            value={draft.actorId}
            onChange={(e) => update('actorId', e.target.value)}
          />
        </label>
        <label>
          <span>Сутність</span>
          <select value={draft.entityType} onChange={(e) => update('entityType', e.target.value)}>
            <option value="">Усі</option>
            <option value="request">Заявка</option>
            <option value="consent">Згода</option>
            <option value="photo">Фото</option>
            <option value="work">Підрядні роботи</option>
            <option value="audit">Журнал аудиту</option>
            <option value="access_policy">Політика доступу</option>
          </select>
        </label>
        <label>
          <span>ID сутності</span>
          <input
            inputMode="numeric"
            pattern="[0-9]*"
            placeholder="напр. 1001"
            value={draft.entityId}
            onChange={(e) => update('entityId', e.target.value)}
          />
        </label>
        {draft.correlationId && (
          <label className="rm-audit-operation">
            <span>Операція</span>
            <input
              value={draft.correlationId}
              onChange={(e) => update('correlationId', e.target.value)}
            />
          </label>
        )}
        <div className="rm-audit-actions">
          <button type="submit" className="rm-audit-primary">
            Застосувати
          </button>
          <button type="button" className="rm-audit-secondary" onClick={reset}>
            Скинути
          </button>
        </div>
      </form>

      {error && (
        <p className="rm-audit-error" role="alert">
          {error}
        </p>
      )}

      <div className="rm-audit-table-wrap">
        <table className="rm-audit-table">
          <thead>
            <tr>
              <th scope="col">Час</th>
              <th scope="col">Хто</th>
              <th scope="col">Подія</th>
              <th scope="col">Сутність</th>
              <th scope="col">Результат</th>
              <th scope="col">Деталі</th>
            </tr>
          </thead>
          <tbody>
            {page?.items.map((entry) => {
              const open = expanded === entry.id
              return [
                <tr
                  key={entry.id}
                  className={open ? 'open' : undefined}
                  onClick={() => setExpanded(open ? null : entry.id)}
                >
                  <td className="rm-audit-time">{formatTime(entry.created_at)}</td>
                  <td>
                    {entry.actor_id === null ? (
                      <span className="rm-audit-system">Система</span>
                    ) : (
                      <>
                        <strong>#{entry.actor_id}</strong>{' '}
                        {ROLE_LABELS[entry.actor_role ?? ''] ?? entry.actor_role}
                      </>
                    )}
                  </td>
                  <td>
                    <span className="rm-audit-action">
                      {ACTION_LABELS.get(entry.action) ?? entry.action}
                    </span>
                    <code>{entry.action}</code>
                  </td>
                  <td>
                    {entry.entity_type
                      ? `${ENTITY_LABELS[entry.entity_type] ?? entry.entity_type}${
                          entry.entity_id ? ` #${entry.entity_id}` : ''
                        }`
                      : '—'}
                  </td>
                  <td>
                    <span
                      className={`rm-audit-result rm-audit-result--${resultKind(entry.result)}`}
                    >
                      {RESULT_LABELS[resultKind(entry.result)]}
                    </span>
                  </td>
                  <td className="rm-audit-summary">
                    {summary(entry)}
                    <button
                      type="button"
                      className="rm-audit-toggle"
                      aria-expanded={open}
                      aria-label={open ? 'Сховати деталі' : 'Показати деталі'}
                    >
                      {open ? '▾' : '▸'}
                    </button>
                  </td>
                </tr>,
                open && (
                  <tr key={`${entry.id}-details`} className="rm-audit-details">
                    <td colSpan={6}>
                      <div className="rm-audit-values">
                        <div>
                          <h3>Було</h3>
                          <pre>
                            {entry.old_value ? JSON.stringify(entry.old_value, null, 2) : '—'}
                          </pre>
                        </div>
                        <div>
                          <h3>Стало</h3>
                          <pre>
                            {entry.new_value ? JSON.stringify(entry.new_value, null, 2) : '—'}
                          </pre>
                        </div>
                      </div>
                      <p className="rm-audit-meta">
                        Запис #{entry.id}
                        {entry.correlation_id && (
                          <>
                            {' · '}операція <code>{entry.correlation_id}</code>{' '}
                            <button
                              type="button"
                              className="rm-audit-link"
                              onClick={() => showOperation(entry.correlation_id ?? '')}
                            >
                              Показати всі записи операції
                            </button>
                          </>
                        )}
                      </p>
                    </td>
                  </tr>
                ),
              ]
            })}
            {page && page.items.length === 0 && (
              <tr>
                <td colSpan={6} className="rm-audit-empty">
                  За цими фільтрами записів немає.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <nav className="rm-audit-pager" aria-label="Сторінки журналу">
        <span>
          {first}–{last} з {total}
        </span>
        <button
          type="button"
          className="rm-audit-secondary"
          disabled={loading || query.offset === 0}
          onClick={() => goTo(Math.max(0, query.offset - PAGE_SIZE))}
        >
          ← Новіші
        </button>
        <button
          type="button"
          className="rm-audit-secondary"
          disabled={loading || last >= total}
          onClick={() => goTo(query.offset + PAGE_SIZE)}
        >
          Старіші →
        </button>
      </nav>
    </div>
  )
}

export default AuditLogPage
