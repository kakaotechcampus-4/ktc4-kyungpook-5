// 마이 페이지 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

export type MemberOut = components['schemas']['MemberOut']

export const getMembers = (clubId: string) =>
  apiGet<MemberOut[]>(`/clubs/${encodeURIComponent(clubId)}/members`)
