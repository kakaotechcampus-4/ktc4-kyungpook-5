// 도메인 타입 정의
export interface MyProfile {
  name: string
  role: string
  email: string
  clubName: string
  memberSince: string
}

export interface ActivityStats {
  periodLabel: string
  approvedCount: number
  confirmationCount: number
  activeEventCount: number
  createdPlanCount: number
}

export interface ActivityLogItem {
  id: string
  description: string
  statusLabel: string
  timestamp: string
}

export interface NotificationSettings {
  onApprovalRequest: boolean
  onDeadlineApproaching: boolean
  onAgentAutoHandled: boolean
}

export interface ClubInfo {
  name: string
  division: string
  myRole: string
  officerCount: number
}

export interface JoinRequest {
  id: string
  name: string
  email: string
}

export interface OfficerRow {
  id: string
  name: string
  role: string
  isMe: boolean
  canBulkApprove: boolean
}

export interface ClubRecordSummary {
  ledgerCount: number
  eventRecordCount: number
  hasBylaws: boolean
}
