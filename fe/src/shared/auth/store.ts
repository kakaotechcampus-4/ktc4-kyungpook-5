// 서버 세션과 /me가 반환한 소속만 공유한다. 최종 권한 판단은 서버에 있다.
import { create } from 'zustand'
import { getAccessToken, setAccessToken, getRefreshToken, setRefreshToken } from '@/shared/auth/tokens'
import type { components } from '@/shared/api/schema'
import { isServiceRole, type AuthUser } from '@/shared/auth/types'

type Me = components['schemas']['MeOut']
type Tokens = components['schemas']['SessionOut']
const CLUB_KEY = 'unyounghae_selected_club_id'
export { getRefreshToken } from '@/shared/auth/tokens'

function selectedUser(me: Me | null, clubId: string | null): AuthUser | null {
  const club = me?.clubs.find((item) => item.id === clubId)
  if (!me || !club || !isServiceRole(club.role)) return null
  return {
    id: me.id,
    clubId: club.id,
    name: me.email.split('@')[0],
    email: me.email,
    role: club.role,
  }
}

interface AuthState {
  sessionId: number
  token: string | null
  me: Me | null
  clubId: string | null
  user: AuthUser | null
  setSession: (tokens: Tokens) => void
  rotateSession: (tokens: Tokens, sessionId: number, refreshToken: string) => boolean
  setMe: (me: Me) => void
  selectClub: (clubId: string) => void
  setUser: (user: AuthUser) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  sessionId: 0,
  token: getAccessToken(),
  me: null,
  // /me로 소속을 확인하기 전에는 저장된 선택을 노출하지 않는다.
  clubId: null,
  user: null,
  setSession: (tokens) => {
    setAccessToken(tokens.accessToken)
    setRefreshToken(tokens.refreshToken)
    localStorage.removeItem(CLUB_KEY)
    set({ sessionId: get().sessionId + 1, token: tokens.accessToken, me: null, user: null, clubId: null })
  },
  rotateSession: (tokens, sessionId, refreshToken) => {
    if (get().sessionId !== sessionId || getRefreshToken() !== refreshToken) return false
    setAccessToken(tokens.accessToken)
    setRefreshToken(tokens.refreshToken)
    // 회전은 같은 로그인이다. 확인한 소속과 사용자 정보는 그대로 유지한다.
    set({ token: tokens.accessToken })
    return true
  },
  setMe: (me) => {
    // 서비스 화면에는 회장·팀 대표와 임원 소속만 제공한다. 원본 응답/명단은 수정하지 않는다.
    const serviceMe = { ...me, clubs: me.clubs.filter((club) => isServiceRole(club.role)) }
    const savedClubId = get().clubId ?? localStorage.getItem(CLUB_KEY)
    const clubId = serviceMe.clubs.some((club) => club.id === savedClubId) ? savedClubId : null
    if (!clubId) localStorage.removeItem(CLUB_KEY)
    set({ me: serviceMe, clubId, user: selectedUser(serviceMe, clubId) })
  },
  selectClub: (clubId) => {
    const me = get().me
    if (!me?.clubs.some((club) => club.id === clubId && isServiceRole(club.role))) return
    localStorage.setItem(CLUB_KEY, clubId)
    set({ clubId, user: selectedUser(me, clubId) })
  },
  setUser: (user) => {
    if (isServiceRole(user.role)) set({ user })
  },
  clear: () => {
    setAccessToken(null)
    setRefreshToken(null)
    localStorage.removeItem(CLUB_KEY)
    set({ sessionId: get().sessionId + 1, token: null, me: null, clubId: null, user: null })
  },
}))

// 다른 탭의 로그인·로그아웃은 토큰을 지우지 않고 /me 소속 확인부터 다시 한다.
export function syncSessionFromStorage(): boolean {
  const token = getAccessToken()
  const current = useAuthStore.getState()
  if (current.token === token) return false
  useAuthStore.setState({ sessionId: current.sessionId + 1, token, me: null, user: null, clubId: null })
  return true
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key === null || event.key === 'unyounghae_access_token') syncSessionFromStorage()
  })
}
