// 마이 페이지 시연용 예시. 주소에 ?demo가 있을 때만 쓴다(다른 화면과 같은 방식).
// TODO(연동): GET /me · GET /clubs/{clubId}
import type { ClubInfo, Profile } from '@/features/mypage/types'

export const DEMO_PROFILE: Profile = {
  name: '박수겸',
  role: '총무',
  email: 'sgpark@university.ac.kr',
}

export const DEMO_CLUB: ClubInfo = {
  name: '큰나무 동아리',
  memberCount: 32,
  myRole: '총무',
  joinedAt: '2026. 3. 2.',
}

// 가입 직후(초기 화면). 아직 혼자고 동아리원을 등록하기 전이다.
export const EMPTY_CLUB: ClubInfo = {
  name: '동아리 이름',
  memberCount: 1,
  myRole: '대표',
  joinedAt: '오늘',
}
