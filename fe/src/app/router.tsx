// 라우트 정의
import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import S0LoginPage from '@/pages/S0LoginPage'
import S1SignupPage from '@/pages/S1SignupPage'
import S2MyPage from '@/pages/S2MyPage'
import M1DashboardPage from '@/pages/M1DashboardPage'
import L1EventListPage from '@/pages/L1EventListPage'
import ComingSoonPage from '@/pages/ComingSoonPage'

// TODO: 행사 계획(P1·P2) / 행사 상세(L2) / 동아리 기록(R1)은 아직 화면 구현 전이라
// 라우트에 없다. 완성되는 대로 AppLayout 하위에 추가한다.
export const router = createBrowserRouter([
  { path: '/login', element: <S0LoginPage /> },
  { path: '/signup', element: <S1SignupPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <M1DashboardPage /> },
      { path: 'events', element: <L1EventListPage /> },
      { path: 'mypage', element: <S2MyPage /> },
      { path: '*', element: <ComingSoonPage /> },
    ],
  },
])
