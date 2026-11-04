// 계획 대화·버튼 생성의 SSE를 받아 화면 상태로 넘긴다 (#266, #285).
//
// "인원 60명으로 바꿔줘" → POST /events/{id}/plan/chat/stream
//   progress     → onProgress  (같은 operationId의 running 줄을 결과 줄로 바꿔 표시)
//   reply_delta  → onReply     (토리 답변 조각을 이어 붙임)
//   reply_reset  → onReply('') (지금까지 받은 답변 조각을 버림)
//   done         → PlanViewOut을 돌려줌 (저장까지 끝난 결과)
//   error        → ApiError로 던짐 (저장하지 않은 결과)
//
// done/error 없이 끊기면 같은 Idempotency-Key·같은 본문으로 다시 요청한다. 서버는 연결이
// 끊겨도 작업을 끝까지 저장하므로, 처리 중이면 409(IDEMPOTENCY_IN_PROGRESS)가 오고
// 끝났으면 저장된 결과가 done 하나로 온다.
import { apiPostStream } from '@/shared/api/client'
import { ApiError, type ApiErrorBody } from '@/shared/api/types'
import type { components } from '@/shared/api/schema'
import type { PlanProgress } from './types'

type PlanView = components['schemas']['PlanViewOut']

export interface PlanStreamHandlers {
  onProgress: (event: PlanProgress) => void
  onReply: (text: string) => void
  // 끊겨서 다시 확인하는 중. 화면은 임시 표시를 지우고 확인 중임을 알린다.
  onReconnect: () => void
}

class StreamCut extends Error {}

// 재시도 간격. 서버 작업(최대 수십 초)이 끝날 때까지 기다릴 수 있게 합쳐 약 1분이다.
const RETRY_DELAYS_MS = [1000, 2000, 3000, 5000, 5000, 8000, 8000, 10000, 10000, 10000]

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

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
        } else if (event === 'done') result = JSON.parse(data) as PlanView
        else if (event === 'error') failure = JSON.parse(data) as ApiErrorBody
      },
    })
  } catch (cause) {
    // 스트림을 열기 전 4xx(ApiError)는 그대로, 네트워크 끊김은 다시 확인할 대상으로 본다.
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
  for (let attempt = 0; ; attempt++) {
    try {
      return await once(path, body, idempotencyKey, handlers)
    } catch (cause) {
      const retryable =
        cause instanceof StreamCut ||
        // 앞 요청이 아직 처리 중이다(끊긴 뒤 다시 물었을 때). 끝날 때까지 기다린다.
        (cause instanceof ApiError && cause.code === 'IDEMPOTENCY_IN_PROGRESS' && attempt > 0)
      if (!retryable || attempt >= RETRY_DELAYS_MS.length) throw cause
      handlers.onReconnect()
      await sleep(RETRY_DELAYS_MS[attempt])
    }
  }
}
