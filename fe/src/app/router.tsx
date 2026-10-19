// 라우트 정의. 각 페이지는 담당 화면 이슈(#77~#83)에서 채운다.
import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/app/layout/AppLayout'
import RecordsPage from '@/pages/RecordsPage'
import AccountingPage from '@/pages/AccountingPage'
import MeetingsPage from '@/pages/MeetingsPage'
import LoginPage from '@/pages/LoginPage'
import SignupPage from '@/pages/SignupPage'
import MainPage from '@/pages/MainPage'
import PlanningPage from '@/pages/PlanningPage'
import PlanStepsPage from '@/pages/PlanStepsPage'
import EventListPage from '@/pages/EventListPage'
import EventDetailPage from '@/pages/EventDetailPage'
import EventCancelPage from '@/pages/EventCancelPage'
import MyPage from '@/pages/MyPage'
import DevUiPage from '@/pages/DevUiPage'
import NotFoundPage from '@/pages/NotFoundPage'

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <AppLayout />,
    children: [
      { index: true, element: <MainPage /> },
      { path: 'meetings', element: <MeetingsPage /> },
      { path: 'records', element: <RecordsPage /> },
      { path: 'accounting', element: <AccountingPage /> },
      { path: 'meetings/:meetingId', element: <MeetingsPage /> },
      { path: 'planning', element: <PlanningPage /> },
      { path: 'planning/steps', element: <PlanStepsPage /> },
      { path: 'events', element: <EventListPage /> },
      { path: 'events/:eventId', element: <EventDetailPage /> },
      { path: 'events/:eventId/cancel', element: <EventCancelPage /> },
      { path: 'mypage', element: <MyPage /> },
      { path: 'dev/ui', element: <DevUiPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
