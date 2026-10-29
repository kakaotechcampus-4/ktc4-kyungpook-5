import { useQuery } from '@tanstack/react-query'
import { getExpenses } from './api'

export function useExpenses(clubId: string, page: number) {
  return useQuery({
    queryKey: ['accounting', clubId, 'expenses', page],
    queryFn: () => getExpenses(clubId, page),
    enabled: Boolean(clubId),
    retry: false,
  })
}
