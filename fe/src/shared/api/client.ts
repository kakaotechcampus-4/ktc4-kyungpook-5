// 모든 API 호출은 이 파일을 통과한다. fetch를 직접 부르는 곳은 여기뿐이어야 한다.
import { ApiError, type ApiSuccess } from '@/shared/api/types'

const BASE_URL = `${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1`
const TOKEN_KEY = 'unyounghae_access_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiSuccess<T>> {
  const token = getAccessToken()
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  })

  if (res.status === 204) return { data: undefined as T, meta: null }

  const body = await res.json()
  if (!res.ok) throw new ApiError(body.error)
  return body as ApiSuccess<T>
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path).then((body) => body.data)
}

// 목록 조회는 meta.totalCount("12건 중 5건 표시")까지 필요해서 봉투째 돌려준다.
export function apiGetPage<T>(path: string): Promise<ApiSuccess<T[]>> {
  return request<T[]>(path)
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
