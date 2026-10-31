// 동아리 생성·참여 도메인 타입. 서버 스키마를 그대로 쓰고 화면 문구는 shared/lib/labels.ts에 둔다.
import type { components } from '@/shared/api/schema'

type Schemas = components['schemas']

export type ClubCategory = Schemas['ClubCategory']
export type Club = Schemas['ClubOut']
export type CreateClubInput = Schemas['ClubCreateIn']
export type JoinResult = Schemas['InvitationAcceptOut']

// 선택 버튼을 그릴 순서. 서버 enum을 그대로 쓰고 문구만 labels에서 가져온다.
export const CLUB_CATEGORIES: ClubCategory[] = [
  'ACADEMIC',
  'SPORTS',
  'VOLUNTEER',
  'HOBBY',
  'ETC',
]
