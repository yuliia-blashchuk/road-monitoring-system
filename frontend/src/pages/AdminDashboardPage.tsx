import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'

import type { RoadEventStatus } from '../data/mapEvents'
import {
  assignContractor,
  getContractors,
  getQueue,
  getWorkOrders,
  type Contractor,
  type Priority,
  type QueueItem,
  type WorkOrder,
} from '../services/roadmapApi'

import './ServiceDashboardPage.css'

const ALL_STATUSES: RoadEventStatus[] = [
  'new',
  'accepted',
  'in_progress',
  'done',
  'resolved',
  'rejected',
]

const statusLabels: Record<RoadEventStatus, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'В роботі',
  done: 'Виконана',
  resolved: 'Усунена',
  rejected: 'Відхилена',
}

const priorityLabels: Record<Priority, string> = {
  critical: 'Критичний',
  high: 'Високий',
  medium: 'Середній',
  low: 'Низький',
}

// Підрядника можна призначити лише на «Прийняту» або «В роботі» заявку
const ASSIGNABLE: RoadEventStatus[] = ['accepted', 'in_progress']

function priorityClass(priority: Priority): string {
    return priority
}

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

// Поля форми призначення (форма використовує стилі блоку з кабінету служби)
const fieldStyle = {
  display: 'block',
  width: '100%',
  maxWidth: 360,
  minHeight: 42,
  marginBottom: 13,
  padding: '9px 12px',
  border: '1px solid #c9e4f6',
  borderRadius: 9,
  background: '#ffffff',
  color: '#264e6d',
  font: 'inherit',
  fontSize: 13,
} as const

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

// Панель адміністратора: усі заявки міста (GET /queue),
// призначення підрядника (POST /work-orders) і журнал аудиту.
function AdminDashboardPage() {
  const [reports, setReports] = useState<QueueItem[]>([])
  const [works, setWorks] = useState<WorkOrder[]>([])
  const [contractors, setContractors] = useState<Contractor[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const [statusFilter, setStatusFilter] = useState('open')
  const [search, setSearch] = useState('')
  const [onlyUnassigned, setOnlyUnassigned] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)

  // Форма призначення
  const [contractorId, setContractorId] = useState('')
  const [deadline, setDeadline] = useState('')
  const [scope, setScope] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  // Панель заявки під таблицею: прокручуємо до неї після вибору рядка
  const detailsRef = useRef<HTMLElement>(null)

  useEffect(() => {
    getContractors()
      .then(setContractors)
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    let cancelled = false
    Promise.all([getQueue(ALL_STATUSES, 100), getWorkOrders(undefined, 100)])
      .then(([page, orders]) => {
        if (!cancelled) {
          setReports(page.items)
          setWorks(orders)
          setLoadError('')
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setLoadError(reason.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  // Підрядник і строк для кожної заявки (з GET /work-orders)
  const workByReport = useMemo(
    () => new Map(works.map((work) => [work.id, work])),
    [works]
  )

  const filteredReports = useMemo(() => {
    const query = search.trim().toLowerCase()

    return reports.filter((report) => {
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'open'
          ? !['resolved', 'rejected'].includes(report.status)
          : report.status === statusFilter)

      const matchesSearch =
        !query ||
        report.problem_label.toLowerCase().includes(query) ||
        (report.address ?? '').toLowerCase().includes(query) ||
        (report.service ?? '').toLowerCase().includes(query) ||
        String(report.number).includes(query)

      const matchesAssigned =
        !onlyUnassigned ||
        (ASSIGNABLE.includes(report.status) && !workByReport.has(report.id))

      return matchesStatus && matchesSearch && matchesAssigned
    })
  }, [reports, search, statusFilter, onlyUnassigned, workByReport])

  const selectedReport =
    filteredReports.find((report) => report.id === selectedId) ??
    filteredReports[0]

  const selectedWork = selectedReport
    ? workByReport.get(selectedReport.id)
    : undefined

  const newCount = reports.filter((r) => r.status === 'new').length
  const waitingContractor = reports.filter(
    (r) => ASSIGNABLE.includes(r.status) && !workByReport.has(r.id)
  ).length
  const doneCount = reports.filter((r) => r.status === 'done').length
  const overdueCount = works.filter((w) => w.is_overdue).length

  function selectReport(report: QueueItem) {
    setSelectedId(report.id)
    const work = workByReport.get(report.id)
    setContractorId(work?.contractor_id ? String(work.contractor_id) : '')
    setDeadline(work?.deadline ?? '')
    setScope('')
    setError('')
    setMessage('')
    window.setTimeout(() =>
      detailsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    )
  }

  async function assign() {
    if (!selectedReport) return

    if (!contractorId) {
      setError('Оберіть підрядника.')
      return
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(deadline)) {
      setError('Вкажіть кінцевий строк робіт.')
      return
    }
    if (deadline < todayIso()) {
      setError('Строк не може бути в минулому.')
      return
    }

    setSaving(true)
    setError('')
    setMessage('')
    try {
      const work = await assignContractor({
        request_id: selectedReport.id,
        contractor_id: Number(contractorId),
        deadline,
        scope: scope.trim() || undefined,
      })
      setSelectedId(selectedReport.id)
      setMessage(
        `Заявку №${work.number} призначено: ${work.contractor_name}, ` +
          `строк до ${formatDate(work.deadline)}.`
      )
      setScope('')
      // Щоб щойно призначена заявка не зникла зі списку
      setOnlyUnassigned(false)
      setReloadKey((key) => key + 1)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const canAssign =
    selectedReport && ASSIGNABLE.includes(selectedReport.status)

  return (
    <div className="rm-service-page">
      <div className="rm-service-stats">
        <div className="rm-service-stat">
          <span>Усього заявок</span>
          <strong>{reports.length}</strong>
          <small>Усі служби міста</small>
        </div>

        <div className="rm-service-stat">
          <span>Нові</span>
          <strong>{newCount}</strong>
          <small>Чекають на службу</small>
        </div>

        <div className="rm-service-stat">
          <span>Без підрядника</span>
          <strong>{waitingContractor}</strong>
          <small>Прийняті, підрядника не призначено</small>
        </div>

        <div className="rm-service-stat">
          <span>На перевірці</span>
          <strong>{doneCount}</strong>
          <small>Підрядник здав роботи</small>
        </div>

        <div className="rm-service-stat">
          <span>Прострочені роботи</span>
          <strong>{overdueCount}</strong>
          <small>Строк підрядника минув</small>
        </div>
      </div>

      <section className="rm-service-card">
        <div className="rm-service-section-heading">
          <div>
            <h2>Усі заявки</h2>
            <p>
              Оберіть заявку, щоб призначити підрядника.{' '}
              <Link to="/audit">Журнал аудиту →</Link>
            </p>
          </div>

          <span className="rm-service-count">
            {filteredReports.length} із {reports.length}
          </span>
        </div>

        <div className="rm-service-filters">
          <label>
            Пошук
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Тип, адреса, служба або номер..."
            />
          </label>

          <label>
            Статус
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="open">Відкриті</option>
              <option value="all">Усі статуси</option>
              {ALL_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </select>
          </label>

          <label>
            Підрядник
            <select
              value={onlyUnassigned ? 'none' : 'all'}
              onChange={(event) =>
                setOnlyUnassigned(event.target.value === 'none')
              }
            >
              <option value="all">Усі заявки</option>
              <option value="none">Потребують підрядника</option>
            </select>
          </label>

          <button
            type="button"
            className="rm-service-reset"
            onClick={() => {
              setSearch('')
              setStatusFilter('open')
              setOnlyUnassigned(false)
            }}
          >
            Скинути
          </button>
        </div>

        {loading && <p className="rm-service-empty">Завантаження заявок…</p>}

        {loadError && (
          <p className="rm-service-error" role="alert">
            {loadError}
          </p>
        )}

        {!loading && !loadError && (
          <div className="rm-service-table-wrap">
            <table className="rm-service-table">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Проблема</th>
                  <th>Адреса</th>
                  <th>Служба</th>
                  <th>Пріоритет</th>
                  <th>Статус</th>
                  <th>Підрядник</th>
                  <th>Створено</th>
                </tr>
              </thead>

              <tbody>
                {filteredReports.map((report) => {
                  const work = workByReport.get(report.id)
                  return (
                    <tr
                      key={report.id}
                      className={
                        selectedReport?.id === report.id ? 'selected' : ''
                      }
                      onClick={() => selectReport(report)}
                    >
                      <td>№{report.number}</td>
                      <td>
                        <button
                          type="button"
                          className="rm-service-row-link"
                          onClick={() => selectReport(report)}
                        >
                          {report.problem_label}
                        </button>
                      </td>
                      <td>{report.address ?? 'Адресу не вказано'}</td>
                      <td>{report.service ?? '—'}</td>
                      <td>
                        <span
                          className={
                            `rm-service-priority ` +
                            `rm-service-priority--${priorityClass(report.priority)}`
                          }
                        >
                          {priorityLabels[report.priority]}
                        </span>
                      </td>
                      <td>
                        <span
                          className={
                            `rm-service-status ` +
                            `rm-service-status--${report.status}`
                          }
                        >
                          {statusLabels[report.status]}
                        </span>
                      </td>
                      <td
                        style={
                          work?.is_overdue
                            ? { color: '#d32f2f', fontWeight: 600 }
                            : undefined
                        }
                      >
                        {work?.contractor_name ?? '—'}
                        {work?.is_overdue && ' ⚠'}
                      </td>
                      <td>{formatDate(report.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>

            {filteredReports.length === 0 && (
              <p className="rm-service-empty">
                За вибраними фільтрами заявок немає.
              </p>
            )}
          </div>
        )}
      </section>

      {selectedReport && (
        <section className="rm-service-card" ref={detailsRef}>
          <div className="rm-service-section-heading">
            <div>
              <h2>Заявка №{selectedReport.number}</h2>
              <p>
                {selectedReport.problem_label} ·{' '}
                <Link to={`/reports/${selectedReport.id}`}>
                  Відкрити повну картку з фото та історією →
                </Link>
              </p>
            </div>

            <span
              className={
                `rm-service-status ` +
                `rm-service-status--${selectedReport.status}`
              }
            >
              {statusLabels[selectedReport.status]}
            </span>
          </div>

          <div className="rm-service-detail-list">
            <div>
              <span>Адреса</span>
              <strong>{selectedReport.address ?? 'Адресу не вказано'}</strong>
            </div>

            <div>
              <span>Служба</span>
              <strong>{selectedReport.service ?? '—'}</strong>
            </div>

            <div>
              <span>Пріоритет</span>
              <strong>{priorityLabels[selectedReport.priority]}</strong>
            </div>

            <div>
              <span>Підрядник</span>
              <strong>{selectedWork?.contractor_name ?? 'Не призначено'}</strong>
            </div>

            {selectedWork && (
              <>
                <div>
                  <span>Кінцевий строк</span>
                  <strong>
                    {formatDate(selectedWork.deadline)}
                    {selectedWork.is_overdue && ' (прострочено)'}
                  </strong>
                </div>

                <div>
                  <span>Прогрес підрядника</span>
                  <strong>{selectedWork.progress_percent ?? 0} %</strong>
                </div>
              </>
            )}
          </div>

          <h3>Призначення підрядника</h3>

          {!canAssign && (
            <p className="rm-service-empty">
              Підрядника можна призначити лише на заявку зі статусом
              «Прийнята» або «В роботі». Спочатку служба має прийняти заявку.
            </p>
          )}

          {canAssign && (
            <div
              className="rm-service-reject-form"
              style={{ borderColor: '#cce7f8', background: '#f5fbff' }}
            >
              <label htmlFor="admin-contractor">Підрядник</label>
              <select
                id="admin-contractor"
                value={contractorId}
                onChange={(event) => setContractorId(event.target.value)}
                style={fieldStyle}
              >
                <option value="">— оберіть підрядника —</option>
                {contractors.map((contractor) => (
                  <option key={contractor.id} value={contractor.id}>
                    {contractor.name}
                  </option>
                ))}
              </select>

              <label htmlFor="admin-deadline">Кінцевий строк робіт</label>
              <input
                id="admin-deadline"
                type="date"
                min={todayIso()}
                value={deadline}
                onChange={(event) => setDeadline(event.target.value)}
                style={fieldStyle}
              />

              <label htmlFor="admin-scope">Обсяг робіт (необов'язково)</label>
              <textarea
                id="admin-scope"
                rows={2}
                maxLength={300}
                value={scope}
                onChange={(event) => setScope(event.target.value)}
                placeholder="Наприклад: ямковий ремонт, 12 м²"
              />

              <div className="rm-service-actions">
                <button
                  type="button"
                  className="rm-service-primary"
                  onClick={assign}
                  disabled={saving}
                >
                  {saving
                    ? 'Збереження…'
                    : selectedWork
                      ? 'Змінити підрядника або строк'
                      : 'Призначити підрядника'}
                </button>
              </div>
            </div>
          )}

          {error && (
            <p className="rm-service-error" role="alert">
              {error}
            </p>
          )}

          {message && (
            <p className="rm-service-complete" role="status">
              {message}
            </p>
          )}
        </section>
      )}
    </div>
  )
}

export default AdminDashboardPage