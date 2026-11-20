
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from 'react'

import { mapEvents } from '../data/mapEvents'
import './ContractorDashboardPage.css'

type WorkStatus = 'assigned' | 'in_progress' | 'done'

type WorkPhoto = {
  id: string
  name: string
  url: string
}

type WorkState = {
  status: WorkStatus
  progress: number
  photos: WorkPhoto[]
  startedAt?: string
  finishedAt?: string
}

const statusLabels: Record<WorkStatus, string> = {
  assigned: 'Призначена',
  in_progress: 'В роботі',
  done: 'Виконана',
}

const initialState: WorkState = {
  status: 'assigned',
  progress: 0,
  photos: [],
}

// Для демонстрації обираємо п'ять дорожніх подій,
// які умовно призначені одному підряднику.
// Реальні призначення надходитимуть через API.
const demoAssignedWorks = mapEvents
  .filter(
    (event) =>
      event.type === 'pothole' ||
      event.type === 'roadworks'
  )
  .slice(0, 5)

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('uk-UA')
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('uk-UA')
}

function ContractorDashboardPage() {
  const [workStates, setWorkStates] = useState<
    Record<number, WorkState>
  >({})

  const [selectedId, setSelectedId] = useState(
    demoAssignedWorks[0]?.id ?? 0
  )

  const [statusFilter, setStatusFilter] = useState('all')
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const photoUrls = useRef<Set<string>>(new Set())

  // Звільняємо тимчасові адреси фотографій.
  useEffect(() => {
    const urls = photoUrls.current

    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url))
      urls.clear()
    }
  }, [])

  function getWorkState(id: number): WorkState {
    return workStates[id] ?? initialState
  }

  function updateWork(
    id: number,
    changes: Partial<WorkState>
  ) {
    setWorkStates((previous) => {
      const current = previous[id] ?? initialState

      return {
        ...previous,
        [id]: {
          ...current,
          ...changes,
        },
      }
    })
  }

  const filteredWorks = useMemo(() => {
    const query = search.trim().toLowerCase()

    return demoAssignedWorks
      .filter((work) => {
        const matchesStatus =
          statusFilter === 'all' ||
          (workStates[work.id]?.status ?? 'assigned') ===
            statusFilter

        const matchesSearch =
          !query ||
          work.title.toLowerCase().includes(query) ||
          work.address.toLowerCase().includes(query) ||
          String(work.id).includes(query)

        return matchesStatus && matchesSearch
      })
      .sort(
        (a, b) =>
          new Date(b.createdAt).getTime() -
          new Date(a.createdAt).getTime()
      )
  }, [search, statusFilter, workStates])

  const selectedWork =
    filteredWorks.find((work) => work.id === selectedId) ??
    filteredWorks[0]

  const selectedState = selectedWork
    ? getWorkState(selectedWork.id)
    : initialState

  const totalCount = demoAssignedWorks.length

  const assignedCount = demoAssignedWorks.filter(
    (work) => getWorkState(work.id).status === 'assigned'
  ).length

  const activeCount = demoAssignedWorks.filter(
    (work) => getWorkState(work.id).status === 'in_progress'
  ).length

  const doneCount = demoAssignedWorks.filter(
    (work) => getWorkState(work.id).status === 'done'
  ).length

  function selectWork(id: number) {
    setSelectedId(id)
    setError('')
    setMessage('')
  }

  function startWork() {
    if (!selectedWork) return

    if (selectedState.status !== 'assigned') {
      setError('Цю роботу вже розпочато або завершено.')
      return
    }

    updateWork(selectedWork.id, {
      status: 'in_progress',
      progress: 0,
      startedAt: new Date().toISOString(),
    })

    setError('')
    setMessage('Роботи розпочато.')
  }

  function changeProgress(value: number) {
    if (!selectedWork) return
    if (selectedState.status !== 'in_progress') return

    const progress = Math.max(0, Math.min(100, value))

    updateWork(selectedWork.id, { progress })

    setError('')
    setMessage('')
  }

  function addPhotos(event: ChangeEvent<HTMLInputElement>) {
    if (!selectedWork) return

    const files = Array.from(event.target.files ?? [])
    event.target.value = ''

    if (!files.length) return

    if (selectedState.status !== 'in_progress') {
      setError(
        'Фотографії можна додавати після початку робіт.'
      )
      return
    }

    if (selectedState.photos.length + files.length > 3) {
      setError('Можна додати не більше трьох фотографій.')
      return
    }

    const allowedTypes = [
      'image/jpeg',
      'image/png',
      'image/webp',
    ]

    for (const file of files) {
      if (!allowedTypes.includes(file.type)) {
        setError(
          'Дозволені формати фотографій: JPG, PNG, WebP.'
        )
        return
      }

      if (file.size > 5 * 1024 * 1024) {
        setError(
          'Розмір кожної фотографії не може перевищувати 5 МБ.'
        )
        return
      }
    }

    const newPhotos: WorkPhoto[] = files.map((file) => {
      const url = URL.createObjectURL(file)
      photoUrls.current.add(url)

      return {
        id: crypto.randomUUID(),
        name: file.name,
        url,
      }
    })

    updateWork(selectedWork.id, {
      photos: [...selectedState.photos, ...newPhotos],
    })

    setError('')
    setMessage('Фотографії додано.')
  }

  function removePhoto(photoId: string) {
    if (!selectedWork) return
    if (selectedState.status === 'done') return

    const photo = selectedState.photos.find(
      (item) => item.id === photoId
    )

    if (photo) {
      URL.revokeObjectURL(photo.url)
      photoUrls.current.delete(photo.url)
    }

    updateWork(selectedWork.id, {
      photos: selectedState.photos.filter(
        (item) => item.id !== photoId
      ),
    })

    setMessage('')
  }

  function finishWork() {
    if (!selectedWork) return

    if (selectedState.status !== 'in_progress') {
      setError('Спочатку потрібно розпочати роботи.')
      return
    }

    if (selectedState.progress !== 100) {
      setError(
        'Для завершення встановіть прогрес виконання 100%.'
      )
      return
    }

    if (selectedState.photos.length === 0) {
      setError(
        'Для завершення потрібно додати хоча б одне фото «після».'
      )
      return
    }

    updateWork(selectedWork.id, {
      status: 'done',
      finishedAt: new Date().toISOString(),
    })

    setError('')
    setMessage(
      'Роботу позначено як виконану. Остаточне підтвердження має надати диспетчер.'
    )
  }

  return (
    <div className="rm-contractor-page">
      <header className="rm-contractor-heading">
        <div>
          <p className="rm-contractor-eyebrow">
            RoadMap / Робочий простір
          </p>
          <h1>Кабінет підрядника</h1>
          <p>
            Перегляд призначених ремонтів та оновлення
            виконання робіт.
          </p>
        </div>

        <span className="rm-contractor-demo">
          Демонстраційний режим
        </span>
      </header>

      <div className="rm-contractor-notice">
        Призначення робіт і зміни прогресу є
        демонстраційними. Вони не зберігаються на
        сервері та скидаються після оновлення сторінки.
      </div>

      <section className="rm-contractor-stats">
        <div className="rm-contractor-stat">
          <span>Усього призначено</span>
          <strong>{totalCount}</strong>
          <small>Демонстраційні об'єкти</small>
        </div>

        <div className="rm-contractor-stat">
          <span>Очікують початку</span>
          <strong>{assignedCount}</strong>
          <small>Ще не розпочаті</small>
        </div>

        <div className="rm-contractor-stat">
          <span>У роботі</span>
          <strong>{activeCount}</strong>
          <small>Ремонт триває</small>
        </div>

        <div className="rm-contractor-stat">
          <span>Виконано</span>
          <strong>{doneCount}</strong>
          <small>Очікують підтвердження</small>
        </div>
      </section>

      <section className="rm-contractor-card">
        <div className="rm-contractor-section-heading">
          <div>
            <h2>Мої роботи</h2>
            <p>Оберіть об'єкт для перегляду та опрацювання.</p>
          </div>

          <span className="rm-contractor-count">
            {filteredWorks.length} із {totalCount}
          </span>
        </div>

        <div className="rm-contractor-filters">
          <label>
            Пошук роботи
            <input
              type="search"
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder="Назва, адреса або номер..."
            />
          </label>

          <label>
            Статус
            <select
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value)
              }
            >
              <option value="all">Усі статуси</option>
              <option value="assigned">Призначена</option>
              <option value="in_progress">В роботі</option>
              <option value="done">Виконана</option>
            </select>
          </label>

          <button
            type="button"
            className="rm-contractor-secondary"
            onClick={() => {
              setSearch('')
              setStatusFilter('all')
            }}
          >
            Скинути
          </button>
        </div>

        <div className="rm-contractor-table-wrap">
          <table className="rm-contractor-table">
            <thead>
              <tr>
                <th>№</th>
                <th>Ремонтний об'єкт</th>
                <th>Адреса</th>
                <th>Статус</th>
                <th>Прогрес</th>
                <th>Дата</th>
              </tr>
            </thead>

            <tbody>
              {filteredWorks.map((work) => {
                const state = getWorkState(work.id)

                return (
                  <tr
                    key={work.id}
                    className={
                      selectedWork?.id === work.id
                        ? 'selected'
                        : ''
                    }
                    onClick={() => selectWork(work.id)}
                  >
                    <td>#{work.id}</td>

                    <td>
                      <button
                        type="button"
                        className="rm-contractor-row-link"
                        onClick={() => selectWork(work.id)}
                      >
                        {work.title}
                      </button>
                    </td>

                    <td>{work.address}</td>

                    <td>
                      <span
                        className={
                          'rm-contractor-status ' +
                          `rm-contractor-status--${state.status}`
                        }
                      >
                        {statusLabels[state.status]}
                      </span>
                    </td>

                    <td>
                      <div className="rm-contractor-progress-cell">
                        <div className="rm-contractor-progress-track">
                          <div
                            style={{
                              width: `${state.progress}%`,
                            }}
                          />
                        </div>

                        <strong>{state.progress}%</strong>
                      </div>
                    </td>

                    <td>{formatDate(work.createdAt)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {filteredWorks.length === 0 && (
            <p className="rm-contractor-empty">
              За вибраними параметрами робіт немає.
            </p>
          )}
        </div>
      </section>

      {selectedWork && (
        <section className="rm-contractor-card rm-contractor-details">
          <div className="rm-contractor-section-heading">
            <div>
              <h2>Робота №{selectedWork.id}</h2>
              <p>{selectedWork.title}</p>
            </div>

            <span
              className={
                'rm-contractor-status ' +
                `rm-contractor-status--${selectedState.status}`
              }
            >
              {statusLabels[selectedState.status]}
            </span>
          </div>

          <div className="rm-contractor-detail-grid">
            <div>
              <span>Адреса</span>
              <strong>{selectedWork.address}</strong>
            </div>

            <div>
              <span>Дата призначення (демо)</span>
              <strong>
                {formatDate(selectedWork.createdAt)}
              </strong>
            </div>

            <div>
              <span>Статус</span>
              <strong>
                {statusLabels[selectedState.status]}
              </strong>
            </div>

            <div>
              <span>Виконано</span>
              <strong>{selectedState.progress}%</strong>
            </div>
          </div>

          {selectedState.startedAt && (
            <p className="rm-contractor-date-note">
              Роботи розпочато:{' '}
              {formatDateTime(selectedState.startedAt)}
            </p>
          )}

          {selectedState.finishedAt && (
            <p className="rm-contractor-date-note">
              Роботу завершено:{' '}
              {formatDateTime(selectedState.finishedAt)}
            </p>
          )}

          <div className="rm-contractor-divider" />

          <h3>Хід виконання робіт</h3>

          <div className="rm-contractor-progress-heading">
            <span>Прогрес ремонту</span>
            <strong>{selectedState.progress}%</strong>
          </div>

          <div className="rm-contractor-progress-large">
            <div
              style={{
                width: `${selectedState.progress}%`,
              }}
            />
          </div>

          {selectedState.status === 'assigned' && (
            <div className="rm-contractor-actions">
              <button
                type="button"
                className="rm-contractor-primary"
                onClick={startWork}
              >
                Розпочати роботи
              </button>
            </div>
          )}

          {selectedState.status === 'in_progress' && (
            <>
              <label className="rm-contractor-slider-label">
                Оновити відсоток виконання
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={selectedState.progress}
                  onChange={(event) =>
                    changeProgress(
                      Number(event.target.value)
                    )
                  }
                />
              </label>

              <div className="rm-contractor-photo-section">
                <h3>Фотографії «після»</h3>
                <p>
                  Додайте від 1 до 3 фотографій результату
                  ремонту. JPG, PNG або WebP, до 5 МБ кожна.
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

              <div className="rm-contractor-actions">
                <button
                  type="button"
                  className="rm-contractor-primary"
                  onClick={finishWork}
                >
                  Завершити роботи
                </button>
              </div>
            </>
          )}

          {selectedState.photos.length > 0 && (
            <div className="rm-contractor-photo-grid">
              {selectedState.photos.map((photo) => (
                <div
                  key={photo.id}
                  className="rm-contractor-photo"
                >
                  <img
                    src={photo.url}
                    alt={photo.name}
                  />

                  {selectedState.status !== 'done' && (
                    <button
                      type="button"
                      aria-label={`Видалити ${photo.name}`}
                      onClick={() =>
                        removePhoto(photo.id)
                      }
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}

          {error && (
            <p
              role="alert"
              className="rm-contractor-error"
            >
              {error}
            </p>
          )}

          {message && (
            <p
              role="status"
              className="rm-contractor-success"
            >
              {message}
            </p>
          )}

          {selectedState.status === 'done' && (
            <div className="rm-contractor-finished">
              <strong>Роботу виконано!</strong>
              <p>
                Фотозвіт підготовлено. Остаточний статус
                «Усунена» може встановити лише диспетчер
                після перевірки результату.
              </p>
            </div>
          )}
        </section>
      )}
    </div>
  )
}

export default ContractorDashboardPage
