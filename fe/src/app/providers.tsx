// QueryClient, 인증 컨텍스트 등 전역 래퍼
import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false, // BE mock API가 아직 대부분 없어서, 실패를 계속 재시도하지 않고 바로 보여준다.
    },
  },
})

export function AppProviders({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
