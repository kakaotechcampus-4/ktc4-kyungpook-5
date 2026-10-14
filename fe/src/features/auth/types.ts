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

// 임원 역할. 계정을 만드는 사람은 임원뿐이라 일반 동아리원은 여기 없다.
export const EXECUTIVE_ROLES = ['대표', '부대표', '총무', '홍보부장', '기타'] as const
