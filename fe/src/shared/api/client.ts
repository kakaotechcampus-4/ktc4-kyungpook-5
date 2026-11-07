// 모든 API 호출은 이 파일을 통과한다. axios를 직접 쓰는 곳은 여기뿐이어야 한다.
import axios, { AxiosError, type AxiosRequestConfig } from 'axios'
import { ApiError, type ApiErrorBody, type ApiMeta, type ApiSuccess } from '@/shared/api/types'
import { createSseParser, type SseEvent } from '@/shared/api/sse'

export function getApiBaseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
}

const BASE_URL = `${getApiBaseUrl()}/api/v1`
const TOKEN_KEY = 'unyounghae_access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

const http = axios.create({ baseURL: BASE_URL })

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
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
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Accept: 'text/event-stream',
  }
  const token = getAccessToken()
  if (token) headers.Authorization = `Bearer ${token}`
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: options.signal,
  })
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
