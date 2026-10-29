import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { getMe, login, loginWithKakao, logout, type LoginInput } from '@/features/auth/api'
import { ApiError } from '@/shared/api/types'
import { getRefreshToken, useAuthStore } from '@/shared/auth/store'

const ME_KEY = ['auth', 'me'] as const

async function loadMe(token: string | null) {
  try {
    const me = await getMe()
    // 로그아웃한 뒤 도착한 이전 /me 응답은 다음 세션에 반영하지 않는다.
    if (useAuthStore.getState().token === token) useAuthStore.getState().setMe(me)
    return me
  } catch (error) {
    if (error instanceof ApiError && error.code === 'UNAUTHORIZED') {
      if (useAuthStore.getState().token === token) useAuthStore.getState().clear()
    }
    throw error
  }
}

export function useMe() {
  const token = useAuthStore((state) => state.token)
  return useQuery({
    queryKey: ME_KEY,
    enabled: Boolean(token),
    queryFn: () => loadMe(token),
    staleTime: 60_000,
    gcTime: 0,
    retry: false,
  })
}

async function establishSession(
  queryClient: ReturnType<typeof useQueryClient>,
  tokens: Awaited<ReturnType<typeof login>>,
) {
  queryClient.clear()
  useAuthStore.getState().setSession(tokens)
  return queryClient.fetchQuery({
    queryKey: ME_KEY,
    queryFn: () => loadMe(tokens.accessToken),
    retry: false,
    staleTime: 60_000,
  })
}

export function useKakaoLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (code: string) => establishSession(queryClient, await loginWithKakao(code)),
  })
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: LoginInput) => {
      return establishSession(queryClient, await login(body))
    },
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async () => {
      const refreshToken = getRefreshToken()
      if (refreshToken) await logout(refreshToken)
    },
    onSettled: () => {
      useAuthStore.getState().clear()
      queryClient.clear()
    },
  })
}

export function authErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.code === 'UNAUTHORIZED') return '이메일과 비밀번호를 확인한 뒤 다시 로그인해 주세요.'
    if (error.code === 'FORBIDDEN')
      return '이 계정으로 접근할 수 없어요. 소속과 권한을 확인해 주세요.'
    if (error.code === 'VALIDATION_FAILED') return '이메일과 비밀번호 입력을 확인해 주세요.'
    return '로그인 정보를 확인하지 못했어요. 잠시 뒤 다시 시도해 주세요.'
  }
  return '서버에 연결하지 못했어요. API 주소와 서버 실행 상태를 확인해 주세요.'
}

function safeDestination(next: string | null): string {
  if (!next) return '/meetings'
  try {
    const url = new URL(next, window.location.origin)
    if (
      url.origin !== window.location.origin ||
      url.pathname === '/login' ||
      url.pathname === '/signup'
    ) {
      return '/meetings'
    }
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return '/meetings'
  }
}

export function useClubSelection() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const selectClub = useAuthStore((state) => state.selectClub)
  return (clubId: string) => {
    selectClub(clubId)
    if (useAuthStore.getState().clubId === clubId) {
      navigate(safeDestination(params.get('next')), { replace: true })
    }
  }
}

interface NotificationClubResult {
  status: 'idle' | 'waiting' | 'selected' | 'error'
  error: string | null
}

// Push의 조직 힌트는 /me 소속 확인 후 한 번만 적용한다. URL만으로 권한을 부여하지 않는다.
export function useNotificationClub(requestedClubId: string | null): NotificationClubResult {
  const token = useAuthStore((state) => state.token)
  const me = useAuthStore((state) => state.me)
  const selectClub = useAuthStore((state) => state.selectClub)
  const handled = useRef(new Map<string, NotificationClubResult>())
  const [outcome, setOutcome] = useState<{
    identity: string
    result: NotificationClubResult
  } | null>(null)
  const identity = token && requestedClubId ? JSON.stringify([token, requestedClubId]) : null

  useEffect(() => {
    if (!identity || !requestedClubId || !me) return
    const previous = handled.current.get(identity)
    if (previous) {
      setOutcome({ identity, result: previous })
      return
    }
    const belongs = me.clubs.some((club) => club.id === requestedClubId)
    const result: NotificationClubResult = belongs
      ? { status: 'selected', error: null }
      : {
          status: 'error',
          error: '이 알림의 팀·조직에 소속되어 있지 않아요. 계정과 초대 상태를 확인해 주세요.',
        }
    handled.current.set(identity, result)
    if (belongs) selectClub(requestedClubId)
    setOutcome({ identity, result })
  }, [identity, requestedClubId, me, selectClub])

  if (!requestedClubId) return { status: 'idle', error: null }
  if (!identity || !me || outcome?.identity !== identity) return { status: 'waiting', error: null }
  return outcome.result
}
