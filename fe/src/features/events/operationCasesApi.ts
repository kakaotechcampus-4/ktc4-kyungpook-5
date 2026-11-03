import { apiGet, apiGetPage, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

type S = components['schemas']
export type OperationCase = S['OperationCaseOut']
const path = (eventId: string) => `/events/${encodeURIComponent(eventId)}/operation-cases`
export async function listOperationCases(eventId: string): Promise<OperationCase[]> {
  const result: OperationCase[] = []
  for (let page = 1; ; page++) {
    const response = await apiGetPage<OperationCase>(`${path(eventId)}?page=${page}&size=100`)
    result.push(...response.data)
    if (!response.meta || result.length >= response.meta.totalCount || !response.data.length)
      return result
  }
}
export const createOperationCase = (eventId: string, input: S['OperationCaseIn']) =>
  apiPost<OperationCase>(path(eventId), input)
export const getOperationCase = (eventId: string, caseId: string) =>
  apiGet<OperationCase>(`${path(eventId)}/${encodeURIComponent(caseId)}`)
export const retryOperationQuestion = (eventId: string, caseId: string) =>
  apiPost<OperationCase>(`${path(eventId)}/${encodeURIComponent(caseId)}/question`, {})
export const generateOperationResult = (eventId: string, caseId: string) =>
  apiPost<OperationCase>(`${path(eventId)}/${encodeURIComponent(caseId)}/result`, {})
