import type { components } from '@/shared/api/schema'

export type ClubRecord = components['schemas']['RecordOut']
export type RecordDetail = components['schemas']['RecordDetailOut']
export type RecordCategory = components['schemas']['RecordCategory']
export type RecordParseStatus = components['schemas']['RecordParseStatus']

export interface UploadRecordInput {
  clubId: string
  category: RecordCategory
  file: File
}
