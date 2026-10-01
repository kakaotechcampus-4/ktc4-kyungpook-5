// 서버 호출 함수 + 응답 타입
//
// TODO: 마이 페이지(S2) API는 아직 FE API 명세에 없다. 화면 동작 확인용 목업이며,
// 엔드포인트가 정해지면 shared/api/client 호출로 교체한다.
import type {
  ActivityLogItem,
  ActivityStats,
  ClubInfo,
  ClubRecordSummary,
  JoinRequest,
  MyProfile,
  NotificationSettings,
  OfficerRow,
} from '@/features/mypage/types'

export function getProfile(): MyProfile {
  return {
    name: '박수겸',
    role: '총무',
    email: 'sgpark901@knu.ac.kr',
    clubName: '컴퓨터학부 학술동아리 ○○',
    memberSince: '2026년 2월부터',
  }
}

export function getActivityStats(): ActivityStats {
  return {
    periodLabel: '2026년 상반기',
    approvedCount: 12,
    confirmationCount: 7,
    activeEventCount: 3,
    createdPlanCount: 2,
  }
}

export function getActivityLog(): ActivityLogItem[] {
  return [
    { id: 'log_1', description: '펜션 계약금 100,000원 이체', statusLabel: '승인함', timestamp: '3/10 14:20' },
    { id: 'log_2', description: '미납자 4명 2차 안내 문자', statusLabel: '승인함', timestamp: '3/10 09:40' },
    { id: 'log_3', description: '"박지영 母" 입금 45,000원', statusLabel: '확인함', timestamp: '3/10 09:32' },
  ]
}

export function getNotificationSettings(): NotificationSettings {
  return { onApprovalRequest: true, onDeadlineApproaching: true, onAgentAutoHandled: false }
}

export function getClubInfo(): ClubInfo {
  return { name: '컴퓨터학부 학술동아리 ○○', division: '학술', myRole: '총무', officerCount: 3 }
}

export function getJoinRequests(): JoinRequest[] {
  return [
    { id: 'req_1', name: '최유진', email: 'yujin@knu.ac.kr' },
    { id: 'req_2', name: '한도현', email: 'dohyun@knu.ac.kr' },
  ]
}

export function getOfficers(): OfficerRow[] {
  return [
    { id: 'mbr_01', name: '김지훈', role: '회장', isMe: false, canBulkApprove: true },
    { id: 'mbr_02', name: '박수겸', role: '총무', isMe: true, canBulkApprove: true },
    { id: 'mbr_03', name: '이서연', role: '부회장', isMe: false, canBulkApprove: true },
    { id: 'mbr_04', name: '정우성', role: '기획', isMe: false, canBulkApprove: false },
  ]
}

export function getClubRecordSummary(): ClubRecordSummary {
  return { ledgerCount: 0, eventRecordCount: 0, hasBylaws: false }
}
