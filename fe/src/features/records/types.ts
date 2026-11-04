import type { components } from '@/shared/api/schema'

export type ClubRecord = components['schemas']['RecordOut']
export type RecordDetail = components['schemas']['RecordDetailOut']
export type RecordCategory = components['schemas']['RecordCategory']
export type RecordParseStatus = components['schemas']['RecordParseStatus']
// 자료 목록 칩. 'ALL'은 분류 조건 없이 전부 본다.
export type RecordFilter = RecordCategory | 'ALL'

export interface UploadRecordInput {
  clubId: string
  category: RecordCategory
  file: File
}
