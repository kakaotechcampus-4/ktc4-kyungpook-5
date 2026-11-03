// 회원가입 도메인 타입. 서버 스키마가 생기면 shared/api/models.ts의 생성 타입으로 바꾼다(#61).

// 기존 동아리에 참여할지, 새로 만들지. 이 값에 따라 아래 입력란이 통째로 바뀐다.
export type SignupMode = 'JOIN' | 'CREATE'

// 동아리 찾기 결과 한 줄
export interface ClubSearchResult {
  id: string
  name: string
  field: string
  ownerName: string
  executiveCount: number
}

// 분야. 동아리를 새로 만들 때 하나 고른다.
export const CLUB_FIELDS = ['학술', '운동', '봉사', '취미', '기타'] as const
export type ClubField = (typeof CLUB_FIELDS)[number]

// 서비스 역할은 두 종류다. 총무·홍보부장 등의 직책은 내부 명단에서 따로 관리한다.
export const EXECUTIVE_ROLES = ['회장', '임원'] as const
