import { useQuery } from '@tanstack/react-query'
import { dashboardApi } from './api'
export function useDashboardOverview(clubId: string | null, userId: string | undefined) {
  const enabled = Boolean(clubId && userId)
  const tasks = useQuery({
    queryKey: ['dashboard', userId, clubId, 'tasks'],
    queryFn: () => dashboardApi.tasks(clubId!),
    enabled,
    retry: false,
  })
  const events = useQuery({
    queryKey: ['dashboard', userId, clubId, 'events'],
    queryFn: () => dashboardApi.events(clubId!),
    enabled,
    retry: false,
  })
  return { tasks, events }
}
