// 도메인 타입 정의
export interface LoginCredentials {
  email: string
  password: string
  keepSignedIn: boolean
}

export type JoinMode = 'JOIN_EXISTING' | 'CREATE_NEW'

export interface ClubSearchResult {
  id: string
  name: string
  category: string
  ownerName: string
  officerCount: number
}

export interface SignupPayload {
  mode: JoinMode
  email: string
  password: string
  name: string
  club: ClubSearchResult | null
  newClubName: string
  role: string
  agreedToTerms: boolean
}
