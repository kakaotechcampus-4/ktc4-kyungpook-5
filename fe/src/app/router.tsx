// 라우트 정의
import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import S0LoginPage from '@/pages/S0LoginPage'
import S1SignupPage from '@/pages/S1SignupPage'
import S2MyPage from '@/pages/S2MyPage'
import M1DashboardPage from '@/pages/M1DashboardPage'
import L1EventListPage from '@/pages/L1EventListPage'
import L2EventDetailPage from '@/pages/L2EventDetailPage'
import P1P2PlanningPage from '@/pages/P1P2PlanningPage'
import R1RecordsPage from '@/pages/R1RecordsPage'
import ComingSoonPage from '@/pages/ComingSoonPage'

export const router = createBrowserRouter([
  { path: '/login', element: <S0LoginPage /> },
  { path: '/signup', element: <S1SignupPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <M1DashboardPage /> },
      // P1·P2는 같은 Event 한 행을 다루므로 한 페이지가 stage로 나뉜다.
      // :eventId는 "임시 저장한 계획 이어서 하기"로 들어올 때 붙는다.
      { path: 'planning', element: <P1P2PlanningPage /> },
      { path: 'planning/:eventId', element: <P1P2PlanningPage /> },
      { path: 'events', element: <L1EventListPage /> },
      { path: 'events/:eventId', element: <L2EventDetailPage /> },
      { path: 'records', element: <R1RecordsPage /> },
      { path: 'mypage', element: <S2MyPage /> },
      { path: '*', element: <ComingSoonPage /> },
    ],
  },
])
