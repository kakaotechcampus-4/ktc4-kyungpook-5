// 로그인 사용자 타입. features/auth, features/mypage, app/layout이 함께 쓴다.
export type MemberRole = 'OWNER' | 'MANAGER' | 'MEMBER'

// BE Member 모델(id/name/role/email)을 그대로 따른다.
export interface AuthUser {
  id: string
  clubId: string
  name: string
  role: MemberRole
  email: string | null
}
