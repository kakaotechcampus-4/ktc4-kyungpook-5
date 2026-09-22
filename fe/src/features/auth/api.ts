// 서버 호출 함수 + 응답 타입
//
// TODO: 로그인·회원가입·동아리 검색 API가 아직 FE API 명세에 없다 (S0/S1/S2는 명세 범위 밖).
// 엔드포인트가 정해지면 shared/api/client 호출로 교체한다. 그 전까지는 화면 동작 확인용 목업이다.
import type { ClubSearchResult, LoginCredentials, SignupPayload } from '@/features/auth/types'

const MOCK_CLUBS: ClubSearchResult[] = [
  { id: 'clb_3a71c0', name: '컴퓨터학부 학술동아리 ○○', category: '학술', ownerName: '김지훈', officerCount: 4 },
]

export async function login(credentials: LoginCredentials): Promise<void> {
  console.debug('[mock] login', credentials)
  await new Promise((resolve) => setTimeout(resolve, 400))
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
