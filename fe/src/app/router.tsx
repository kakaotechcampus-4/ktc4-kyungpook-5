// 라우트 정의
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import LoginPage from '@/pages/LoginPage'
import SignupPage from '@/pages/SignupPage'
import MyPage from '@/pages/MyPage'
import ComingSoonPage from '@/pages/ComingSoonPage'

// TODO: 메인(M1) / 행사 계획(P1·P2) / 행사 목록(L1) / 행사 상세(L2) / 동아리 기록(R1)은
// 아직 화면 구현 전이라 라우트에 없다. 완성되는 대로 AppLayout 하위에 추가한다.
export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/mypage" replace /> },
      { path: 'mypage', element: <MyPage /> },
      { path: '*', element: <ComingSoonPage /> },
    ],
  },
])
