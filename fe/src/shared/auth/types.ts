// 로그인 사용자 타입. features/auth, features/mypage, app/layout이 함께 쓴다.
// MEMBER는 내부 명단과 기존 DB/API 호환용이다. 서비스 계정 역할과 구분한다.
export type MemberRole = 'OWNER' | 'MANAGER' | 'MEMBER'
export type ServiceRole = Extract<MemberRole, 'OWNER' | 'MANAGER'>

export function isServiceRole(role: unknown): role is ServiceRole {
  return role === 'OWNER' || role === 'MANAGER'
}

// BE Member 모델(id/name/role/email)을 그대로 따른다.
export interface AuthUser {
  id: string
  clubId: string
  name: string
  role: ServiceRole
  email: string | null
}
