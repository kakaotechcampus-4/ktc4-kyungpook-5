// 카테고리 카드 하나. 머리의 "8건"은 meta.categoryCounts에서 오므로 줄 수와 다를 수 있다.
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { cn } from '@/shared/lib/cn'
import { RecordRow, type RecordRowActions } from '@/features/records/components/RecordRow'
import { CATEGORY_DESCRIPTION, CATEGORY_LABEL, UPLOAD_ACCEPT } from '@/features/records/labels'
import type { RecordCategory, RecordDetail, RecordListItem } from '@/features/records/types'

interface RecordCategoryCardProps extends RecordRowActions {
  category: RecordCategory
  count: number
  records: RecordListItem[]
  details: Record<string, RecordDetail>
  pickingIds: Set<string>
  onTogglePickCategory: (recordId: string, picking: boolean) => void
  onUpload: (file: File, category: RecordCategory) => void
}

export function RecordCategoryCard({
  category,
  count,
  records,
  details,
  pickingIds,
  onTogglePickCategory,
  onUpload,
  ...rowActions
}: RecordCategoryCardProps) {
  // 기타는 "되도록 쓰지 마세요" 카드라 한 톤 가라앉혀 그린다.
  const muted = category === 'ETC'

  return (
    <Card className={cn('flex w-full flex-col overflow-hidden', muted && 'border-[#d6d6d6]')}>
      <div className={cn('flex w-full flex-col', muted && 'bg-[#f8f8f8]')}>
        <div className="flex w-full items-center gap-[10px] px-[22px] py-[15px]">
          <span
            className={cn(
              'size-[26px] shrink-0 rounded-[8px]',
              muted ? 'bg-[#dbdbdb]' : 'bg-[#e6e6e6]',
            )}
          />
          <p
            className={cn(
              'text-[14.5px] font-semibold whitespace-nowrap',
              muted ? 'text-[#595959]' : 'text-[#242424]',
            )}
          >
            {CATEGORY_LABEL[category]}
          </p>
          <Chip variant="subtle">{count}건</Chip>
          {muted && <Chip variant="notice">되도록 쓰지 마세요</Chip>}

          <div className="h-px flex-1" />

          <label className="shrink-0 cursor-pointer text-[11.5px] font-medium whitespace-nowrap text-[#6b6b6b] hover:text-[#333]">
            올리기 &nbsp;+
            <input
              type="file"
              accept={UPLOAD_ACCEPT}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) onUpload(file, category)
              }}
            />
          </label>
        </div>

        <p className="px-[22px] pb-[12px] text-[11.5px] text-[#737373]">
          {CATEGORY_DESCRIPTION[category]}
        </p>
      </div>

      {records.length === 0 ? (
        <p className="border-t border-[#ededed] px-[22px] py-[14px] text-[12px] text-[#737373]">
          아직 올린 파일이 없습니다.
        </p>
      ) : (
        records.map((record) => (
          <RecordRow
            key={record.id}
            record={record}
            detail={details[record.id]}
            pickingCategory={pickingIds.has(record.id)}
            onTogglePickCategory={onTogglePickCategory}
            {...rowActions}
          />
        ))
      )}
    </Card>
  )
}
