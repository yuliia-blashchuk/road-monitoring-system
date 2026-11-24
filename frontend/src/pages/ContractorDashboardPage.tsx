import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from 'react'
import { Link } from 'react-router'

import type { RoadEventStatus } from '../data/mapEvents'
import {
  changeStatus,
  getProblemTypes,
  getWorkOrders,
  updateProgress,
  type Priority,
  type WorkOrder,
} from '../services/roadmapApi'
import './ContractorDashboardPage.css'

type WorkPhoto = {
  id: string
  file: File
  url: string
}

const statusLabels: Partial<Record<RoadEventStatus, string>> = {
  accepted: 'Очікує початку',
  in_progress: 'В роботі',
  done: 'Виконана (на перевірці)',
  resolved: 'Усунена',
  rejected: 'Відхилена',
}

// Кольори бейджів із ContractorDashboardPage.css
const statusClasses: Partial<Record<RoadEventStatus, string>> = {
  accepted: 'assigned',
  in_progress: 'in_progress',
  done: 'done',
  resolved: 'done',
}

const priorityLabels: Record<Priority, string> = {
  critical: 'Критичний',
  high: 'Високий',
  medium: 'Середній',
  low: 'Низький',
}

const PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const ACT_TYPES = [...PHOTO_TYPES, 'application/pdf']
const MAX_SIZE = 5 * 1024 * 1024

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString('uk-UA') : '—'
}

function statusLabel(status: RoadEventStatus) {
  return statusLabels[status] ?? status
}

function statusClass(status: RoadEventStatus) {
  return `rm-contractor-status rm-contractor-status--${statusClasses[status] ?? 'assigned'}`
}

// Кабінет підрядника (UC-04, UC-06): призначені роботи з бази
// (GET /work-orders), початок робіт (PATCH /reports/{id}/status)
// і прогрес з фото «після» та актом (POST /work-orders/{id}/progress).
function ContractorDashboardPage() {
  const [works, setWorks] = useState<WorkOrder[]>([])
  const [typeNames, setTypeNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [statusFilter, setStatusFilter] = useState('open')
  const [search, setSearch] = useState('')

  // Форма прогресу. Чернетка прогресу прив'язана до роботи, щоб не переносилась на іншу
  const [draft, setDraft] = useState<{ id: number; value: number } | null>(null)
  const [comment, setComment] = useState('')
  const [photos, setPhotos] = useState<WorkPhoto[]>([])
  const [act, setAct] = useState<File | null>(null)

  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const photoUrls = useRef<Set<string>>(new Set())

  // Назви типів проблем (у роботах приходить лише код, напр. pothole)
  useEffect(() => {
    getProblemTypes()
      .then((types) =>
        setTypeNames(
          Object.fromEntries(types.map((type) => [type.code, type.name]))
        )
      )
      .catch(() => undefined)
  }, [])

  // Роботи підрядника; reloadKey змінюється після кожної дії
  useEffect(() => {
    let cancelled = false
    getWorkOrders(undefined, 100)
      .then((items) => {
        if (!cancelled) {
          setWorks(items)
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

  // Звільняємо тимчасові адреси фотографій
  useEffect(() => {
    const urls = photoUrls.current
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url))
      urls.clear()
    }
  }, [])

  function typeName(code: string) {
    return typeNames[code] ?? code
  }

  const filteredWorks = useMemo(() => {
    const query = search.trim().toLowerCase()

    return works.filter((work) => {
      const matchesStatus =
        statusFilter === 'all' ||
        (statusFilter === 'open'
          ? ['accepted', 'in_progress'].includes(work.status)
          : work.status === statusFilter)

      const matchesSearch =
        !query ||
        (typeNames[work.problem_type] ?? work.problem_type)
          .toLowerCase()
          .includes(query) ||
        (work.address ?? '').toLowerCase().includes(query) ||
        String(work.number).includes(query)

      return matchesStatus && matchesSearch
    })
  }, [works, search, statusFilter, typeNames])

  const selectedWork =
    filteredWorks.find((work) => work.id === selectedId) ??
    filteredWorks[0]

  const savedProgress = selectedWork?.progress_percent ?? 0
  const progress =
    selectedWork && draft?.id === selectedWork.id
      ? Math.max(draft.value, savedProgress)
      : savedProgress

  const waitingCount = works.filter((w) => w.status === 'accepted').length
  const activeCount = works.filter((w) => w.status === 'in_progress').length
  const doneCount = works.filter((w) =>
    ['done', 'resolved'].includes(w.status)
  ).length
  const overdueCount = works.filter((w) => w.is_overdue).length

  function clearPhotos() {
    photos.forEach((photo) => {
      URL.revokeObjectURL(photo.url)
      photoUrls.current.delete(photo.url)
    })
    setPhotos([])
  }

  function resetForm() {
    clearPhotos()
    setDraft(null)
    setComment('')
    setAct(null)
  }

  function selectWork(work: WorkOrder) {
    setSelectedId(work.id)
    resetForm()
    setError('')
    setMessage('')
  }

  async function startWork() {
    if (!selectedWork) return
    setSaving(true)
    setError('')
    setMessage('')
    try {
      await changeStatus(selectedWork.id, {
        status: 'in_progress',
        comment: 'Роботи розпочато',
      })
      setSelectedId(selectedWork.id)
      resetForm()
      setMessage('Роботи розпочато. Тепер можна оновлювати прогрес.')
      setStatusFilter('open')
      setReloadKey((key) => key + 1)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function addPhotos(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (!files.length) return

    if (photos.length + files.length > 3) {
      setError('За один раз можна додати не більше трьох фотографій.')
      return
    }

    for (const file of files) {
      if (!PHOTO_TYPES.includes(file.type)) {
        setError('Дозволені формати фотографій: JPG, PNG, WebP.')
        return
      }
      if (file.size > MAX_SIZE) {
        setError('Розмір кожної фотографії не може перевищувати 5 МБ.')
        return
      }
    }

    const newPhotos = files.map((file) => {
      const url = URL.createObjectURL(file)
      photoUrls.current.add(url)
      return { id: crypto.randomUUID(), file, url }
    })

    setPhotos([...photos, ...newPhotos])
    setError('')
  }

  function removePhoto(photoId: string) {
    const photo = photos.find((item) => item.id === photoId)
    if (photo) {
      URL.revokeObjectURL(photo.url)
      photoUrls.current.delete(photo.url)
    }
    setPhotos(photos.filter((item) => item.id !== photoId))
  }

  function chooseAct(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null
    event.target.value = ''
    if (!file) return

    if (!ACT_TYPES.includes(file.type)) {
      setError('Акт має бути у форматі PDF, JPG, PNG або WebP.')
      return
    }
    if (file.size > MAX_SIZE) {
      setError('Розмір акта не може перевищувати 5 МБ.')
      return
    }
    setAct(file)
    setError('')
  }

  async function saveProgress() {
    if (!selectedWork) return

    if (
      progress === savedProgress &&
      photos.length === 0 &&
      !act &&
      !comment.trim()
    ) {
      setError('Змініть прогрес або додайте фото, акт чи коментар.')
      return
    }

    setSaving(true)
    setError('')
    setMessage('')
    try {
      await updateProgress(selectedWork.id, {
        percent: progress,
        comment,
        photos: photos.map((photo) => photo.file),
        act,
      })
      setMessage(
        progress === 100
          ? 'Роботи здано. Статус «Виконана»: служба перевірить фотозвіт і підтвердить усунення.'
          : `Прогрес ${progress}% збережено.`
      )
      resetForm()
      if (progress === 100) setStatusFilter('all')
      setReloadKey((key) => key + 1)
    } catch (reason) {
      setError((reason as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rm-contractor-page">
      <header className="rm-contractor-heading">
        <div>
          <p className="rm-contractor-eyebrow">RoadMap / Робочий простір</p>
          <h1>Кабінет підрядника</h1>
          <p>Призначені вам ремонти та оновлення ходу робіт.</p>
        </div>

        {works[0]?.contractor_name && (
          <span className="rm-contractor-demo">{works[0].contractor_name}</span>
        )}
      </header>

      <section className="rm-contractor-stats">
        <div className="rm-contractor-stat">
          <span>Очікують початку</span>
          <strong>{waitingCount}</strong>
          <small>Призначені, ще не розпочаті</small>
        </div>

        <div className="rm-contractor-stat">
          <span>У роботі</span>
          <strong>{activeCount}</strong>
          <small>Ремонт триває</small>
        </div>

        <div className="rm-contractor-stat">
          <span>Прострочені</span>
          <strong>{overdueCount}</strong>
          <small>Строк минув</small>
        </div>

        <div className="rm-contractor-stat">
          <span>Виконано</span>
          <strong>{doneCount}</strong>
          <small>Здані роботи</small>
        </div>
      </section>

      <section className="rm-contractor-card">
        <div className="rm-contractor-section-heading">
          <div>
            <h2>Мої роботи</h2>
            <p>Оберіть об'єкт для перегляду та опрацювання.</p>
          </div>

          <span className="rm-contractor-count">
            {filteredWorks.length} із {works.length}
          </span>
        </div>

        <div className="rm-contractor-filters">
          <label>
            Пошук роботи
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Тип, адреса або номер..."
            />
          </label>

          <label>
            Статус
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="open">Активні</option>
              <option value="all">Усі статуси</option>
              <option value="accepted">Очікує початку</option>
              <option value="in_progress">В роботі</option>
              <option value="done">Виконана (на перевірці)</option>
              <option value="resolved">Усунена</option>
            </select>
          </label>

          <button
            type="button"
            className="rm-contractor-secondary"
            onClick={() => {
              setSearch('')
              setStatusFilter('open')
            }}
          >
            Скинути
          </button>
        </div>

        {loading && <p className="rm-contractor-empty">Завантаження робіт…</p>}

        {loadError && (
          <p role="alert" className="rm-contractor-error">
            {loadError}
          </p>
        )}

        {!loading && !loadError && (
          <div className="rm-contractor-table-wrap">
            <table className="rm-contractor-table">
              <thead>
                <tr>
                  <th>№</th>
                  <th>Ремонтний об'єкт</th>
                  <th>Адреса</th>
                  <th>Пріоритет</th>
                  <th>Статус</th>
                  <th>Прогрес</th>
                  <th>Строк</th>
                </tr>
              </thead>

              <tbody>
                {filteredWorks.map((work) => (
                  <tr
                    key={work.id}
                    className={selectedWork?.id === work.id ? 'selected' : ''}
                    onClick={() => selectWork(work)}
                  >
                    <td>№{work.number}</td>

                    <td>
                      <button
                        type="button"
                        className="rm-contractor-row-link"
                        onClick={() => selectWork(work)}
                      >
                        {typeName(work.problem_type)}
                      </button>
                    </td>

                    <td>{work.address ?? 'Адресу не вказано'}</td>

                    <td>{priorityLabels[work.priority]}</td>

                    <td>
                      <span className={statusClass(work.status)}>
                        {statusLabel(work.status)}
                      </span>
                    </td>

                    <td>
                      <div className="rm-contractor-progress-cell">
                        <div className="rm-contractor-progress-track">
                          <div style={{ width: `${work.progress_percent ?? 0}%` }} />
                        </div>
                        <strong>{work.progress_percent ?? 0}%</strong>
                      </div>
                    </td>

                    <td
                      style={work.is_overdue ? { color: '#d32f2f', fontWeight: 600 } : undefined}
                      title={work.is_overdue ? 'Строк минув' : undefined}
                    >
                      {formatDate(work.deadline)}
                      {work.is_overdue && ' ⚠'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {works.length === 0 && (
              <p className="rm-contractor-empty">Вам ще не призначено жодної роботи.</p>
            )}

            {works.length > 0 && filteredWorks.length === 0 && (
              <p className="rm-contractor-empty">
                За вибраними параметрами робіт немає.
              </p>
            )}
          </div>
        )}
      </section>

      {selectedWork && (
        <section className="rm-contractor-card rm-contractor-details">
          <div className="rm-contractor-section-heading">
            <div>
              <h2>Робота №{selectedWork.number}</h2>
              <p>
                {typeName(selectedWork.problem_type)} ·{' '}
                <Link to={`/reports/${selectedWork.id}`}>
                  Відкрити картку заявки →
                </Link>
              </p>
            </div>

            <span className={statusClass(selectedWork.status)}>
              {statusLabel(selectedWork.status)}
            </span>
          </div>

          <div className="rm-contractor-detail-grid">
            <div>
              <span>Адреса</span>
              <strong>{selectedWork.address ?? 'Адресу не вказано'}</strong>
            </div>

            <div>
              <span>Кінцевий строк</span>
              <strong>
                {formatDate(selectedWork.deadline)}
                {selectedWork.is_overdue && ' (прострочено)'}
              </strong>
            </div>

            <div>
              <span>Пріоритет</span>
              <strong>{priorityLabels[selectedWork.priority]}</strong>
            </div>

            <div>
              <span>Виконано</span>
              <strong>{savedProgress}%</strong>
            </div>
          </div>

          <div className="rm-contractor-divider" />

          <h3>Хід виконання робіт</h3>

          <div className="rm-contractor-progress-heading">
            <span>Прогрес ремонту</span>
            <strong>
              {progress}%
            </strong>
          </div>

          <div className="rm-contractor-progress-large">
            <div
              style={{
                width: `${progress}%`,
              }}
            />
          </div>

          {selectedWork.status === 'accepted' && (
            <div className="rm-contractor-actions">
              <button
                type="button"
                className="rm-contractor-primary"
                onClick={startWork}
                disabled={saving}
              >
                {saving ? 'Збереження…' : 'Розпочати роботи'}
              </button>
            </div>
          )}

          {selectedWork.status === 'in_progress' && (
            <>
              <label className="rm-contractor-slider-label">
                Оновити відсоток виконання (не менше {savedProgress}%)
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={progress}
                  onChange={(event) =>
                    setDraft({ id: selectedWork.id, value: Number(event.target.value) })
                  }
                />
              </label>

              <label className="rm-contractor-slider-label">
                Коментар (необов'язково)
                <textarea
                  value={comment}
                  maxLength={300}
                  rows={2}
                  style={{
                    display: 'block',
                    width: '100%',
                    marginTop: 8,
                    padding: '10px 12px',
                    border: '1px solid #cbe5f8',
                    borderRadius: 10,
                    font: 'inherit',
                    resize: 'vertical',
                  }}
                  onChange={(event) => setComment(event.target.value)}
                  placeholder="Що зроблено на цьому етапі..."
                />
              </label>

              <div className="rm-contractor-photo-section">
                <h3>Фотографії «після»</h3>
                <p>
                  До 3 фото за раз: JPG, PNG або WebP, до 5 МБ кожне.
                  {progress === 100 && ' Для здачі робіт потрібне хоча б одне фото «після».'}
                </p>

                <label className="rm-contractor-upload">
                  <span>+ Додати фотографії</span>
                  <input
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    multiple
                    onChange={addPhotos}
                  />
                </label>
              </div>

              {photos.length > 0 && (
                <div className="rm-contractor-photo-grid">
                  {photos.map((photo) => (
                    <div key={photo.id} className="rm-contractor-photo">
                      <img src={photo.url} alt={photo.file.name} />
                      <button
                        type="button"
                        aria-label={`Видалити ${photo.file.name}`}
                        onClick={() => removePhoto(photo.id)}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="rm-contractor-photo-section">
                <h3>Акт виконаних робіт</h3>
                <p>
                  PDF або фото, до 5 МБ.
                  {progress === 100 && ' Для здачі робіт акт обов’язковий.'}
                </p>

                <label className="rm-contractor-upload">
                  <span>{act ? `📄 ${act.name}` : '+ Додати акт'}</span>
                  <input
                    type="file"
                    accept="application/pdf,image/jpeg,image/png,image/webp"
                    onChange={chooseAct}
                  />
                </label>
              </div>

              <div className="rm-contractor-actions">
                <button
                  type="button"
                  className="rm-contractor-primary"
                  onClick={saveProgress}
                  disabled={saving}
                >
                  {saving
                    ? 'Збереження…'
                    : progress === 100
                      ? 'Здати роботи (100%)'
                      : 'Зберегти прогрес'}
                </button>
              </div>
            </>
          )}

          {error && (
            <p role="alert" className="rm-contractor-error">
              {error}
            </p>
          )}

          {message && (
            <p role="status" className="rm-contractor-success">
              {message}
            </p>
          )}

          {selectedWork.status === 'done' && (
            <div className="rm-contractor-finished">
              <strong>Роботу здано!</strong>
              <p>
                Фотозвіт і акт надіслано. Остаточний статус «Усунена»
                встановлює служба після перевірки результату.
              </p>
            </div>
          )}

          {selectedWork.status === 'resolved' && (
            <div className="rm-contractor-finished">
              <strong>Служба підтвердила усунення.</strong>
              <p>Заявку закрито.</p>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default ContractorDashboardPage