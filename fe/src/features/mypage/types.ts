// 마이 페이지 도메인 타입. 서버 스키마가 생기면 shared/api/models.ts의 생성 타입으로 바꾼다(#61).

export interface Profile {
  name: string
  role: string
  email: string
}

export interface ClubInfo {
  name: string
  memberCount: number
  myRole: string
  joinedAt: string
}

// 알림은 되돌릴 수 없는 일만 골라 보내기 때문에 종류가 둘뿐이다.
export interface NotificationSettings {
  pendingApproval: boolean
  stepDelayed: boolean
}

// 동아리원. 계정이 없어도 명단에 둘 수 있다. 참가·미납 집계에 쓰기 위해서다.
// 역할(임원/동아리원)과 계정 유무는 따로 움직인다 — 계정 없는 임원도 있을 수 있다.
export type MemberGroup = '임원' | '동아리원'
export type AccountStatus = 'JOINED' | 'INVITED' | 'NONE'

export interface Member {
  id: string
  name: string
  group: MemberGroup
  // 임원은 직책(총무 등), 동아리원은 학번
  subtitle: string
  // 이메일 또는 전화번호. 없으면 비운다.
  contact?: string
  account: AccountStatus
  // 계정 있음이면 최근 접속, 초대했으면 보낸 날
  accountNote?: string
}

// 아직 허가하지 않은 참여 요청
export interface JoinRequest {
  id: string
  name: string
  role: string
  requestedAt: string
}
