// 로그인 사용자 전역 상태. TopBar·마이페이지 등 여러 화면이 공유해야 해서 zustand로 뺀다.
// 그 외 상태(폼 입력값, 목록 데이터 등)는 그대로 각 화면 hooks.ts의 useState로 관리한다.
import { create } from 'zustand'
import type { AuthUser } from '@/shared/auth/types'

interface AuthState {
  user: AuthUser | null
  setUser: (user: AuthUser) => void
  clear: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  clear: () => set({ user: null }),
}))
