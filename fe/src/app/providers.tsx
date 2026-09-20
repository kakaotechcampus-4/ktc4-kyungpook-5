// QueryClient, 인증 컨텍스트 등 전역 래퍼
import type { ReactNode } from 'react'

// 서버 상태 관리 방식이 정해지면 이 자리에 Provider를 추가한다.
export function AppProviders({ children }: { children: ReactNode }) {
  return children
}
