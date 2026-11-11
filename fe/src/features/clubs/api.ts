// 동아리 생성·참여 서버 호출. 화면은 이 파일을 직접 쓰지 않고 hooks.ts를 거친다.
import { apiGet, apiPatch, apiPost } from '@/shared/api/client'
import type {
  Club,
  ClubUpdateInput,
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

// 수정 화면이 분야·소개의 현재 값을 채우려면 필요하다(#223). /me 는 이름과 역할만 준다.
export const getClub = (clubId: string) =>
  apiGet<Club>(`/clubs/${encodeURIComponent(clubId)}`)

// 보낸 밭만 바뀐다. null 을 보내면 그 값을 비운다. 회장만 고칠 수 있다.
export const updateClub = (clubId: string, body: ClubUpdateInput) =>
  apiPatch<Club>(`/clubs/${encodeURIComponent(clubId)}`, body)
