// 동아리 생성·참여 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet, apiPost } from '@/shared/api/client'
import type {
  Club,
  ClubMember,
  CreateClubInput,
  InvitationCreateInput,
  InvitationCreateResult,
  JoinResult,
} from '@/features/clubs/types'

export const createClub = (body: CreateClubInput) => apiPost<Club>('/clubs', body)

export const acceptInvitation = (token: string) =>
  apiPost<JoinResult>('/invitations/accept', { token })

export const listClubMembers = (clubId: string) =>
  apiGet<ClubMember[]>(`/clubs/${encodeURIComponent(clubId)}/members`)

export const createInvitation = (clubId: string, body: InvitationCreateInput) =>
  apiPost<InvitationCreateResult>(`/clubs/${encodeURIComponent(clubId)}/invitations`, body)
