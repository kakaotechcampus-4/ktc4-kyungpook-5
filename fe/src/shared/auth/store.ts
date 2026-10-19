// 서버 세션과 /me가 반환한 소속만 공유한다. 최종 권한 판단은 서버에 있다.
import { create } from 'zustand'
import { getAccessToken, setAccessToken } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import { isServiceRole, type AuthUser } from '@/shared/auth/types'

type Me = components['schemas']['MeOut']
type Tokens = components['schemas']['SessionOut']
const CLUB_KEY = 'unyounghae_selected_club_id'
const REFRESH_KEY = 'unyounghae_refresh_token'

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
  token: string | null
  me: Me | null
  clubId: string | null
  user: AuthUser | null
  setSession: (tokens: Tokens) => void
  setMe: (me: Me) => void
  selectClub: (clubId: string) => void
  setUser: (user: AuthUser) => void
  clear: () => void
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: getAccessToken(),
  me: null,
  // /me로 소속을 확인하기 전에는 저장된 선택을 노출하지 않는다.
  clubId: null,
  user: null,
  setSession: (tokens) => {
    setAccessToken(tokens.accessToken)
    localStorage.setItem(REFRESH_KEY, tokens.refreshToken)
    localStorage.removeItem(CLUB_KEY)
    set({ token: tokens.accessToken, me: null, user: null, clubId: null })
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
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(CLUB_KEY)
    set({ token: null, me: null, clubId: null, user: null })
  },
}))
