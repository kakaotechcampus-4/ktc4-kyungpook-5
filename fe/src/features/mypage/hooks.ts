// useMyPage 등 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import { useState } from 'react'
import * as mypageApi from '@/features/mypage/api'
import type { NotificationSettings } from '@/features/mypage/types'

export function useMyPage() {
  const [profile] = useState(mypageApi.getProfile)
  const [stats] = useState(mypageApi.getActivityStats)
  const [activityLog] = useState(mypageApi.getActivityLog)
  const [notifications, setNotifications] = useState<NotificationSettings>(mypageApi.getNotificationSettings)
  const [clubInfo] = useState(mypageApi.getClubInfo)
  const [joinRequests, setJoinRequests] = useState(mypageApi.getJoinRequests)
  const [officers] = useState(mypageApi.getOfficers)
  const [recordSummary] = useState(mypageApi.getClubRecordSummary)

  function toggleNotification(key: keyof NotificationSettings, value: boolean) {
    setNotifications((prev) => ({ ...prev, [key]: value }))
  }

  function resolveJoinRequest(id: string) {
    setJoinRequests((prev) => prev.filter((request) => request.id !== id))
  }

  return {
    profile,
    stats,
    activityLog,
    notifications,
    toggleNotification,
    clubInfo,
    joinRequests,
    resolveJoinRequest,
    officers,
    recordSummary,
  }
}
