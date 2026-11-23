// Заявки для карти й головної сторінки з бекенду (GET /reports) замість демо-даних.
import { useEffect, useState } from 'react'

import type { RoadEvent } from '../data/mapEvents'
import { getMapReports, toRoadEvent } from './roadmapApi'

export function useRoadEvents(): {
  events: RoadEvent[]
  loading: boolean
  error: string
} {
  const [events, setEvents] = useState<RoadEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    getMapReports({ limit: 1000 })
      .then((reports) => {
        if (!cancelled) setEvents(reports.map(toRoadEvent))
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

  return { events, loading, error }
}