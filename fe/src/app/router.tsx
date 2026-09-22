// 라우트 정의
import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import S0LoginPage from '@/pages/S0LoginPage'
import S1SignupPage from '@/pages/S1SignupPage'
import S2MyPage from '@/pages/S2MyPage'
import M1DashboardPage from '@/pages/M1DashboardPage'
import L1EventListPage from '@/pages/L1EventListPage'
import L2EventDetailPage from '@/pages/L2EventDetailPage'
import R1RecordsPage from '@/pages/R1RecordsPage'
import ComingSoonPage from '@/pages/ComingSoonPage'

// TODO: 행사 계획(P1·P2)은 아직 화면 구현 전이라 라우트에 없다.
// 완성되는 대로 AppLayout 하위에 추가한다.
export const router = createBrowserRouter([
  { path: '/login', element: <S0LoginPage /> },
  { path: '/signup', element: <S1SignupPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <M1DashboardPage /> },
      { path: 'events', element: <L1EventListPage /> },
      { path: 'events/:eventId', element: <L2EventDetailPage /> },
      { path: 'records', element: <R1RecordsPage /> },
      { path: 'mypage', element: <S2MyPage /> },
      { path: '*', element: <ComingSoonPage /> },
    ],
  },
])
