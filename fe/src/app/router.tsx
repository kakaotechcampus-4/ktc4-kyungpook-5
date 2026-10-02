// 라우트 정의. 각 페이지는 담당 화면 이슈(#77~#83)에서 채운다.
import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import LoginPage from '@/pages/LoginPage'
import SignupPage from '@/pages/SignupPage'
import MainPage from '@/pages/MainPage'
import PlanningPage from '@/pages/PlanningPage'
import EventListPage from '@/pages/EventListPage'
import EventDetailPage from '@/pages/EventDetailPage'
import MyPage from '@/pages/MyPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <MainPage /> },
      { path: 'planning', element: <PlanningPage /> },
      { path: 'events', element: <EventListPage /> },
      { path: 'events/:eventId', element: <EventDetailPage /> },
      { path: 'mypage', element: <MyPage /> },
    ],
  },
])
