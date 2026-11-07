// 모든 API 호출은 이 파일을 통과한다. axios를 직접 쓰는 곳은 여기뿐이어야 한다.
import axios, { AxiosError, type AxiosRequestConfig, type InternalAxiosRequestConfig } from 'axios'
import { ApiError, type ApiErrorBody, type ApiMeta, type ApiSuccess } from '@/shared/api/types'
import { createSseParser, type SseEvent } from '@/shared/api/sse'
import { syncSessionFromStorage, useAuthStore } from '@/shared/auth/store'
import { getAccessToken as getStoredAccessToken, getRefreshToken } from '@/shared/auth/tokens'
import type { components } from '@/shared/api/schema'

export { setAccessToken } from '@/shared/auth/tokens'

export function getAccessToken(): string | null {
  syncSessionFromStorage()
  return getStoredAccessToken()
}

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
}

const BASE_URL = `${getApiBaseUrl()}/api/v1`
type Tokens = components['schemas']['SessionOut']
type AuthRequest = InternalAxiosRequestConfig & {
  sessionId?: number
  accessToken?: string | null
  authRetried?: boolean
}

let refreshing: { sessionId: number; promise: Promise<void> } | null = null

function canRefresh(path: string): boolean {
  return !path.startsWith('/auth/') || path === '/auth/logout'
}

function clearSession(sessionId: number): void {
  syncSessionFromStorage()
  if (useAuthStore.getState().sessionId === sessionId) useAuthStore.getState().clear()
}

async function refreshSession(sessionId: number, accessToken: string): Promise<void> {
  syncSessionFromStorage()
  if (useAuthStore.getState().sessionId !== sessionId) throw new Error('로그인 상태가 변경되었습니다.')
  // 늦게 도착한 같은 세션의 401은 이미 회전한 토큰을 재사용한다.
  if (getAccessToken() !== accessToken) return
  if (refreshing?.sessionId === sessionId) return refreshing.promise
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    clearSession(sessionId)
    throw new ApiError({ code: 'UNAUTHORIZED', message: '다시 로그인해 주세요.' })
  }
  const promise = (async () => {
    try {
      // 이 호출은 인증 재시도 interceptor를 거치지 않는다.
      const response = await axios.post<ApiSuccess<Tokens>>(`${BASE_URL}/auth/refresh`, { refreshToken })
      const tokens = response.data.data
      if (!tokens?.accessToken || !tokens.refreshToken) throw new Error('세션 갱신 응답을 확인하지 못했습니다.')
      syncSessionFromStorage()
      if (!useAuthStore.getState().rotateSession(tokens, sessionId, refreshToken)) {
        throw new Error('로그인 상태가 변경되었습니다.')
      }
    } catch (error) {
      if (axios.isAxiosError(error) && [401, 403].includes(error.response?.status ?? 0)) clearSession(sessionId)
      throw error
    }
  })()
  refreshing = { sessionId, promise }
  try {
    await promise
  } finally {
    if (refreshing?.promise === promise) refreshing = null
  }
}

const http = axios.create({ baseURL: BASE_URL })

http.interceptors.request.use((config) => {
  const authConfig = config as AuthRequest
  if (syncSessionFromStorage()) throw new Error('로그인 상태가 변경되었습니다. 다시 확인해 주세요.')
  const sessionId = useAuthStore.getState().sessionId
  if (authConfig.sessionId !== undefined && authConfig.sessionId !== sessionId) {
    throw new Error('로그인 상태가 변경되었습니다.')
  }
  const token = getAccessToken()
  authConfig.sessionId = sessionId
  authConfig.accessToken = token
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
}, (error: unknown) => { throw error }, { synchronous: true })

http.interceptors.response.use(undefined, async (error: unknown) => {
  if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) throw error
  const config = error.config as AuthRequest
  if (!canRefresh(config.url ?? '') || !config.accessToken || config.sessionId === undefined) throw error
  if (useAuthStore.getState().sessionId !== config.sessionId) throw error
  if (config.authRetried) {
    if (getAccessToken() === config.accessToken) clearSession(config.sessionId)
    throw error
  }
  // BE의 인증 의존성이 본문 실행 전에 거절한 401만 재시도한다. 네트워크 오류는 재실행하지 않는다.
  await refreshSession(config.sessionId, config.accessToken)
  if (useAuthStore.getState().sessionId !== config.sessionId) throw error
  config.authRetried = true
  if (config.url === '/auth/logout') config.data = { refreshToken: getRefreshToken() }
  return http.request(config)
})

async function request<T, M = ApiMeta>(
  path: string,
  config?: AxiosRequestConfig,
): Promise<ApiSuccess<T, M>> {
  try {
    const res = await http.request<ApiSuccess<T, M>>({ url: path, ...config })
    if (res.status === 204) return { data: undefined as T, meta: null }
    return res.data
  } catch (err) {
    // axios는 2xx가 아니면 예외를 던진다. 그 안의 서버 에러 봉투를 꺼내 ApiError로 통일한다.
    if (axios.isAxiosError(err)) {
      const errorBody = (err as AxiosError<{ error: ApiErrorBody }>).response?.data?.error
      if (errorBody) throw new ApiError(errorBody)
    }
    throw err
  }
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path).then((body) => body.data)
}

export function apiGetEnvelope<T, M = ApiMeta>(path: string): Promise<ApiSuccess<T, M>> {
  return request<T, M>(path)
}

// 목록 조회는 meta.totalCount("12건 중 5건 표시")까지 필요해서 봉투째 돌려준다.
export function apiGetPage<T, M = ApiMeta>(path: string): Promise<ApiSuccess<T[], M>> {
  return request<T[], M>(path)
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', data: body }).then((res) => res.data)
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'PATCH', data: body }).then((res) => res.data)
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' }).then((res) => res.data)
}

// SSE 응답을 받는 POST(#285). axios는 브라우저에서 응답을 조금씩 읽지 못해 fetch를 쓴다.
// 스트림을 열기 전 오류(4xx)는 다른 호출처럼 ApiError로 던진다. 스트림이 열린 뒤에는
// 이벤트를 onEvent로 넘기기만 하고, done/error 같은 의미는 호출하는 기능 코드가 해석한다.
// 네트워크가 끊기면 fetch·read가 예외를 던지고, 서버가 그냥 닫으면 정상 종료된다.
export async function apiPostStream(
  path: string,
  body: unknown,
  options: {
    idempotencyKey?: string
    onEvent: (event: SseEvent) => void
    signal?: AbortSignal
  },
): Promise<void> {
  if (syncSessionFromStorage()) throw new Error('로그인 상태가 변경되었습니다. 다시 확인해 주세요.')
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  const sessionId = useAuthStore.getState().sessionId
  const token = getAccessToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey
  const send = () => fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  })
  let res = await send()
  // 헤더 단계의 401만 다시 연다. 열린 스트림이나 수신한 이벤트는 재생하지 않는다.
  if (res.status === 401 && token && canRefresh(path)) {
    await refreshSession(sessionId, token)
    if (useAuthStore.getState().sessionId !== sessionId) throw new Error('로그인 상태가 변경되었습니다.')
    headers.Authorization = `Bearer ${getAccessToken()}`
    res = await send()
    if (res.status === 401) clearSession(sessionId)
  }
  if (!res.ok || !res.body) {
    const errorBody = await res
      .json()
      .then((json: { error?: ApiErrorBody }) => json.error)
      .catch(() => undefined)
    if (errorBody) throw new ApiError(errorBody)
    throw new Error(`스트림 요청 실패 (HTTP ${res.status})`)
  }
  const parser = createSseParser(options.onEvent)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    parser.push(decoder.decode(value, { stream: true }))
  }
  parser.push(decoder.decode())
  parser.end()
}

// multipart/form-data 업로드(POST /records). Content-Type(boundary 포함)은 axios가 자동 설정한다.
export function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', data: form }).then((res) => res.data)
}

// GET /records/template 처럼 봉투가 아니라 파일 스트림을 주는 엔드포인트.
// 토큰이 필요해 <a href>로는 못 받고, 받아서 blob으로 저장한다.
export async function apiDownload(path: string, fileName: string): Promise<void> {
  const res = await http.get<Blob>(path, { responseType: 'blob' }).catch(() => {
    throw new Error('파일을 받지 못했습니다.')
  })

  const url = URL.createObjectURL(res.data)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function apiGetBlob(path: string): Promise<Blob> {
  return http.get<Blob>(path, { responseType: 'blob' }).then((res) => res.data)
}
