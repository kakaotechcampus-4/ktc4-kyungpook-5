// 동아리 찾기 시연용 예시. 주소에 ?demo가 있을 때만 쓴다(다른 화면과 같은 방식).
// TODO(연동): GET /clubs?query= 로 바꾼다.
import type { ClubSearchResult } from '@/features/auth/types'

export const DEMO_CLUBS: ClubSearchResult[] = [
  {
    id: 'clb_3a71c0',
    name: '컴퓨터학부 학술동아리 큰나무',
    field: '학술',
    ownerName: '김지훈',
    executiveCount: 4,
  },
  {
    id: 'clb_8b22d1',
    name: '큰나무 봉사단',
    field: '봉사',
    ownerName: '이서연',
    executiveCount: 2,
  },
]
