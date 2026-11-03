import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/shared/auth/store'
import {
  createOperationCase,
  generateOperationResult,
  getOperationCase,
  listOperationCases,
  retryOperationQuestion,
} from './operationCasesApi'

export function useOperationCases(eventId: string | undefined) {
  const userId = useAuthStore((state) => state.me?.id)
  const clubId = useAuthStore((state) => state.clubId)
  return useQuery({
    queryKey: ['events', userId, clubId, eventId, 'operation-cases'],
    queryFn: () => listOperationCases(eventId!),
    enabled: !!eventId && !!userId && !!clubId,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some(
        (item) =>
          item.questionStatus === 'PENDING' ||
          item.questionStatus === 'PROCESSING' ||
          item.resultStatus === 'PROCESSING',
      )
        ? 2500
        : false,
  })
}

export function useOperationCaseActions(eventId: string) {
  const client = useQueryClient()
  const refresh = () => client.invalidateQueries({ queryKey: ['events'] })
  const create = useMutation({
    mutationFn: (input: { clientRequestId: string; situation: string }) =>
      createOperationCase(eventId, input),
    onSettled: refresh,
  })
  const question = useMutation({
    mutationFn: (caseId: string) => retryOperationQuestion(eventId, caseId),
    onSettled: refresh,
  })
  const result = useMutation({
    mutationFn: (caseId: string) => generateOperationResult(eventId, caseId),
    onSettled: refresh,
  })
  const recover = useMutation({
    mutationFn: (caseId: string) => getOperationCase(eventId, caseId),
    onSettled: refresh,
  })
  return { create, question, result, recover }
}
