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
