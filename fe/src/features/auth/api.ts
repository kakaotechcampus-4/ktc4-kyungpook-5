// 서버 호출 함수 + 응답 타입
//
// TODO: 로그인·회원가입·동아리 검색 API가 아직 FE API 명세에 없다 (S0/S1/S2는 명세 범위 밖).
// 엔드포인트가 정해지면 shared/api/client 호출로 교체한다. 그 전까지는 화면 동작 확인용 목업이다.
import type { ClubSearchResult, LoginCredentials, SignupPayload } from '@/features/auth/types'
import type { AuthUser } from '@/shared/auth/types'

const MOCK_CLUBS: ClubSearchResult[] = [
  { id: 'clb_3a71c0', name: '컴퓨터학부 학술동아리 ○○', category: '학술', ownerName: '김지훈', officerCount: 4 },
]

// TODO: 목데이터다. 실제 로그인 엔드포인트가 생기면 이 함수 안만 apiPost 호출로 교체한다
// (이메일·비밀번호와 무관하게 항상 같은 사용자를 돌려준다).
export async function login(credentials: LoginCredentials): Promise<AuthUser> {
  console.debug('[mock] login', credentials)
  await new Promise((resolve) => setTimeout(resolve, 400))
  return {
    id: 'mbr_01',
    clubId: 'clb_3a71c0',
    name: '박수겸',
    role: 'MANAGER',
    email: credentials.email,
  }
}

export async function signup(payload: SignupPayload): Promise<void> {
  console.debug('[mock] signup', payload)
  await new Promise((resolve) => setTimeout(resolve, 400))
}

export async function searchClubs(keyword: string): Promise<ClubSearchResult[]> {
  await new Promise((resolve) => setTimeout(resolve, 200))
  if (!keyword.trim()) return []
  return MOCK_CLUBS.filter((club) => club.name.includes(keyword))
}
