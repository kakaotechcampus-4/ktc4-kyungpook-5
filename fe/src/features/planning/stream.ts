// 계획 대화·버튼 생성의 SSE를 받아 화면 상태로 넘긴다 (#266, #285).
//
// "인원 60명으로 바꿔줘" → POST /events/{id}/plan/chat/stream
//   progress     → onProgress  (같은 operationId의 running 줄을 결과 줄로 바꿔 표시)
//   reply_delta  → onReply     (토리 답변 조각을 이어 붙임)
//   reply_reset  → onReply('') (지금까지 받은 답변 조각을 버림)
//   done         → PlanViewOut을 돌려줌 (저장까지 끝난 결과)
//   error        → ApiError로 던짐 (오류 종류에 따라 저장 거절/결과 불명 구분)
//
// 연결 결과가 불명일 때 POST를 반복하면 실패/만료 키가 모델을 다시 실행할 수 있다.
// 요청별 읽기 전용 결과 조회 계약 전에는 같은 키여도 자동 재전송하지 않는다 (#326).
import { apiPostStream } from '@/shared/api/client'
import { ApiError, type ApiErrorBody } from '@/shared/api/types'
import type { components } from '@/shared/api/schema'
import type { PlanProgress } from './types'
import { validDraft } from './generation'

type PlanView = components['schemas']['PlanViewOut']

export interface PlanStreamHandlers {
  onProgress: (event: PlanProgress) => void
  onReply: (text: string) => void
  // 결과를 받기 전에 연결이 끊겼다. 화면은 새 요청을 잠그고 결과 불명을 알린다.
  onReconnect: () => void
}

class StreamCut extends Error {}

async function once(
  path: string,
  body: unknown,
  idempotencyKey: string,
  handlers: PlanStreamHandlers,
): Promise<PlanView> {
  let reply = ''
  let result: PlanView | undefined
  let failure: ApiErrorBody | undefined
  try {
    await apiPostStream(path, body, {
      idempotencyKey,
      onEvent: ({ event, data }) => {
        if (event === 'progress') handlers.onProgress(JSON.parse(data) as PlanProgress)
        else if (event === 'reply_delta') {
          reply += (JSON.parse(data) as { text: string }).text
          handlers.onReply(reply)
        } else if (event === 'reply_reset') {
          reply = ''
          handlers.onReply('')
        } else if (event === 'done') {
          const candidate = JSON.parse(data) as PlanView
          if (
            !Number.isInteger(candidate?.baseRevision) ||
            candidate.baseRevision < 0 ||
            !validDraft(candidate.draft) ||
            !Array.isArray(candidate.changedFields) ||
            typeof candidate.generationReadiness?.canGenerate !== 'boolean' ||
            !Array.isArray(candidate.generationReadiness.reasons) ||
            (candidate.reply !== null && typeof candidate.reply !== 'string') ||
            (candidate.generationResult !== null &&
              !['generated', 'failed', 'needs_clarification'].includes(
                candidate.generationResult?.status,
              ))
          ) {
            throw new StreamCut()
          }
          result = candidate
        } else if (event === 'error') failure = JSON.parse(data) as ApiErrorBody
      },
    })
  } catch (cause) {
    // 스트림을 열기 전 4xx(ApiError)는 그대로, 네트워크 끊김은 다시 확인할 대상으로 본다.
    if (result) return result
    if (cause instanceof ApiError) throw cause
    throw new StreamCut()
  }
  if (failure) throw new ApiError(failure)
  if (!result) throw new StreamCut()
  return result
}

export async function streamPlan(
  path: string,
  body: unknown,
  idempotencyKey: string,
  handlers: PlanStreamHandlers,
): Promise<PlanView> {
  try {
    return await once(path, body, idempotencyKey, handlers)
  } catch (cause) {
    if (cause instanceof StreamCut) handlers.onReconnect()
    throw cause
  }
}
