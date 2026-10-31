// 마이 페이지 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet, apiPatch } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type MemberOut = components['schemas']['MemberOut']

export const getMembers = (clubId: string) =>
  apiGet<MemberOut[]>(`/clubs/${encodeURIComponent(clubId)}/members`)

export type ClubUpdateIn = components['schemas']['ClubUpdateIn']
export type ClubOut = components['schemas']['ClubOut']

// 보낸 밭만 바뀐다. 회장·임원만 고칠 수 있다.
export const updateClub = (clubId: string, body: ClubUpdateIn) =>
  apiPatch<ClubOut>(`/clubs/${encodeURIComponent(clubId)}`, body)
