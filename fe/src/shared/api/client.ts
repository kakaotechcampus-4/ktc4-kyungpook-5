// 모든 API 호출은 이 파일을 통과한다. fetch를 직접 부르는 곳은 여기뿐이어야 한다.
import { ApiError, type ApiMeta, type ApiSuccess } from '@/shared/api/types'

const BASE_URL = `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`
const TOKEN_KEY = 'unyounghae_access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request<T, M = ApiMeta>(
  path: string,
  init?: RequestInit,
): Promise<ApiSuccess<T, M>> {
  const token = getAccessToken()
  // multipart는 브라우저가 boundary까지 넣어 Content-Type을 만들어야 해서 직접 정하지 않는다.
  const isForm = init?.body instanceof FormData
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })

  if (res.status === 204) return { data: undefined as T, meta: null }

  const body = await res.json()
  if (!res.ok) throw new ApiError(body.error)
  return body as ApiSuccess<T, M>
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path).then((body) => body.data)
}

// 목록 조회는 meta.totalCount("12건 중 5건 표시")까지 필요해서 봉투째 돌려준다.
export function apiGetPage<T, M = ApiMeta>(path: string): Promise<ApiSuccess<T[], M>> {
  return request<T[], M>(path)
}

export function apiPost<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'POST', body: body ? JSON.stringify(body) : undefined }).then(
    (res) => res.data,
  )
}

export function apiPatch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: body ? JSON.stringify(body) : undefined }).then(
    (res) => res.data,
  )
}

export function apiDelete<T>(path: string): Promise<T> {
  return request<T>(path, { method: 'DELETE' }).then((res) => res.data)
}

// multipart/form-data 업로드(POST /records). Content-Type은 request가 알아서 비운다.
export function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: form }).then((res) => res.data)
}

// GET /records/template 처럼 봉투가 아니라 파일 스트림을 주는 엔드포인트.
// 토큰이 필요해 <a href>로는 못 받고, 받아서 blob으로 저장한다.
export async function apiDownload(path: string, fileName: string): Promise<void> {
  const token = getAccessToken()
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) throw new Error('파일을 받지 못했습니다.')

  const url = URL.createObjectURL(await res.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}
