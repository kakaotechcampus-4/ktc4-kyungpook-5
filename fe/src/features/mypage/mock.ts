// 마이 페이지 시연용 예시. 주소에 ?demo가 있을 때만 쓴다(다른 화면과 같은 방식).
// TODO(연동): GET /me · GET /clubs/{clubId}
import type { ClubInfo, JoinRequest, Member, Profile } from '@/features/mypage/types'

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

// TODO(연동): GET /clubs/{clubId}/members · GET /clubs/{clubId}/join-requests
export const DEMO_MEMBERS: Member[] = [
  {
    id: 'mem_01',
    name: '박수겸',
    group: '임원',
    subtitle: '대표 · 나',
    contact: 'sgpark@university.ac.kr',
    account: 'JOINED',
    accountNote: '오늘 09:12',
  },
  {
    id: 'mem_02',
    name: '김지훈',
    group: '임원',
    subtitle: '회장',
    contact: 'jh.kim@university.ac.kr',
    account: 'JOINED',
    accountNote: '어제 21:40',
  },
  {
    id: 'mem_03',
    name: '이서연',
    group: '임원',
    subtitle: '홍보부장',
    contact: 'seoyeon@university.ac.kr',
    account: 'INVITED',
    accountNote: '3월 8일 초대',
  },
  {
    id: 'mem_04',
    name: '박지영',
    group: '동아리원',
    subtitle: '20학번',
    contact: '010-••••-1234',
    account: 'NONE',
  },
  {
    id: 'mem_05',
    name: '최민준',
    group: '동아리원',
    subtitle: '21학번',
    contact: '010-••••-5678',
    account: 'NONE',
  },
  { id: 'mem_06', name: '정하늘', group: '동아리원', subtitle: '22학번', account: 'NONE' },
  {
    id: 'mem_07',
    name: '윤서아',
    group: '동아리원',
    subtitle: '22학번',
    contact: 'seoa@university.ac.kr',
    account: 'JOINED',
    accountNote: '3월 5일',
  },
]

export const DEMO_JOIN_REQUESTS: JoinRequest[] = [
  { id: 'req_01', name: '한도윤', role: '부회장', requestedAt: '3/11 09:12' },
]

// 명단 전체 수. 목록은 앞 몇 명만 보여주고 나머지는 「더 보기」로 둔다.
export const DEMO_MEMBER_TOTAL = 31
