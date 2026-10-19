// 서버 세션과 /me가 반환한 소속만 공유한다. 최종 권한 판단은 서버에 있다.
import { create } from 'zustand'
import { getAccessToken, setAccessToken } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'
import type { AuthUser } from '@/shared/auth/types'

type Me = components['schemas']['MeOut']
type Tokens = components['schemas']['SessionOut']
const CLUB_KEY = 'unyounghae_selected_club_id'
const REFRESH_KEY = 'unyounghae_refresh_token'

function selectedUser(me: Me | null, clubId: string | null): AuthUser | null {
  const club = me?.clubs.find((item) => item.id === clubId)
  if (!me || !club) return null
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
    const savedClubId = get().clubId ?? localStorage.getItem(CLUB_KEY)
    const clubId = me.clubs.some((club) => club.id === savedClubId) ? savedClubId : null
    if (!clubId) localStorage.removeItem(CLUB_KEY)
    set({ me, clubId, user: selectedUser(me, clubId) })
  },
  selectClub: (clubId) => {
    const me = get().me
    if (!me?.clubs.some((club) => club.id === clubId)) return
    localStorage.setItem(CLUB_KEY, clubId)
    set({ clubId, user: selectedUser(me, clubId) })
  },
  setUser: (user) => set({ user }),
  clear: () => {
    setAccessToken(null)
    localStorage.removeItem(REFRESH_KEY)
    localStorage.removeItem(CLUB_KEY)
    set({ token: null, me: null, clubId: null, user: null })
  },
}))
