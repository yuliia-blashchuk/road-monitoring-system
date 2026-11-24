import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router'

import type { RoadEventStatus } from '../data/mapEvents'
import { getMyReports, type MyReport } from '../services/roadmapApi'

// Таблиці й картки - у тому самому стилі, що й кабінет служби
import './ServiceDashboardPage.css'

const statusLabels: Record<RoadEventStatus, string> = {
  new: 'Нова',
  accepted: 'Прийнята',
  in_progress: 'В роботі',
  done: 'Виконана',
  resolved: 'Усунена',
  rejected: 'Відхилена',
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('uk-UA', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  })
}

// «Мої звернення» водія (UC-03): власні заявки з бази (GET /reports/my)
function MyReportsPage() {
  const [reports, setReports] = useState<MyReport[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')

  useEffect(() => {
    let cancelled = false
    getMyReports(100)
      .then((page) => {
        if (!cancelled) {
          setReports(page.items)
          setTotal(page.total)
        }
      })
      .catch((reason: Error) => {
        if (!cancelled) setError(reason.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const filteredReports = useMemo(
    () =>
      reports.filter(
        (report) => statusFilter === 'all' || report.status === statusFilter
      ),
    [reports, statusFilter]
  )

  const openCount = reports.filter(
    (report) => !['resolved', 'rejected'].includes(report.status)
  ).length
  const resolvedCount = reports.filter(
    (report) => report.status === 'resolved'
  ).length

  return (
    <div className="rm-service-page">
      <div className="rm-service-stats">
        <div className="rm-service-stat">
          <span>Усього звернень</span>
          <strong>{total}</strong>
          <small>Створені вами заявки</small>
        </div>

        <div className="rm-service-stat">
          <span>Відкриті</span>
          <strong>{openCount}</strong>
          <small>Ще опрацьовуються</small>
        </div>

        <div className="rm-service-stat">
          <span>Усунені</span>
          <strong>{resolvedCount}</strong>
          <small>Проблему виправлено</small>
        </div>
      </div>

      <section className="rm-service-card">
        <div className="rm-service-section-heading">
          <div>
            <h2>Мої звернення</h2>
            <p>Статус кожної заявки й посилання на її картку з історією.</p>
          </div>

          <Link to="/report/new" className="rm-service-primary">
            ＋ Повідомити про проблему
          </Link>
        </div>

        <div className="rm-service-filters">
          <label>
            Статус
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="all">Усі статуси</option>
              {Object.entries(statusLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {loading && <p className="rm-service-empty">Завантаження заявок…</p>}

        {error && (
          <p className="rm-service-error" role="alert">
            {error}
          </p>
        )}

        {!loading && !error && reports.length === 0 && (
          <p className="rm-service-empty">
            Ви ще не створювали заявок.{' '}
            <Link to="/report/new">Повідомити про першу проблему →</Link>
          </p>
        )}

        {filteredReports.length > 0 && (
          <div className="rm-service-table-wrap">
            <table className="rm-service-table">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Проблема</th>
                  <th>Адреса</th>
                  <th>Статус</th>
                  <th>Служба</th>
                  <th>Фото</th>
                  <th>Створено</th>
                  <th>Оновлено</th>
                </tr>
              </thead>

              <tbody>
                {filteredReports.map((report) => (
                  <tr key={report.id}>
                    <td>№{report.number}</td>
                    <td>
                      <Link
                        to={`/reports/${report.id}`}
                        className="rm-service-row-link"
                        title="Відкрити картку заявки"
                      >
                        {report.problem_label}
                      </Link>
                    </td>
                    <td>{report.address ?? 'Адресу не вказано'}</td>
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
                    <td>{report.service ?? '—'}</td>
                    <td>{report.photos_count}</td>
                    <td>{formatDate(report.created_at)}</td>
                    <td>{formatDate(report.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {!loading && reports.length > 0 && filteredReports.length === 0 && (
          <p className="rm-service-empty">Заявок із таким статусом немає.</p>
        )}
      </section>
    </div>
  )
}

export default MyReportsPage