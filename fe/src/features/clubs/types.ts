// 동아리 생성·참여 도메인 타입. 서버 스키마를 그대로 쓰고 화면 문구는 shared/lib/labels.ts에 둔다.
import type { components } from '@/shared/api/schema'

type Schemas = components['schemas']

export type ClubCategory = Schemas['ClubCategory']
export type Club = Schemas['ClubOut']
export type CreateClubInput = Schemas['ClubCreateIn']
export type JoinResult = Schemas['InvitationAcceptOut']

// 선택 버튼 차례와 문구는 shared/lib/labels.ts 가 들고 있다 — 생성과 수정이
// 서로 다른 feature라 둘 다 볼 수 있는 자리에 둔다.
export { CLUB_CATEGORIES } from '@/shared/lib/labels'
