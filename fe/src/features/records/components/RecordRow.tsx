// 파일 한 줄. 파싱이 멈춘 파일은 그 아래에 "왜 못 읽었나" 박스가 함께 펼쳐진다.
import { useState } from 'react'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { cn } from '@/shared/lib/cn'
import { formatDotDate } from '@/shared/lib/format'
import {
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  PARSE_ERROR_COPY,
  PARSE_STATUS_LABEL,
  UPLOAD_ACCEPT,
  columnHint,
  needsParseReason,
  normalizeParseErrorReason,
  parseStatusChipVariant,
} from '@/features/records/labels'
import type {
  ParseErrorParams,
  RecordCategory,
  RecordDetail,
  RecordListItem,
} from '@/features/records/types'

export interface RecordRowActions {
  onChangeCategory: (recordId: string, category: RecordCategory) => void
  onDelete: (recordId: string) => void
  onUploadNew: (file: File, category: RecordCategory) => void
  onSubmitColumnMapping: (recordId: string, mapping: Record<string, string>) => void
  onDownloadTemplate: () => void
}

interface RecordRowProps extends RecordRowActions {
  record: RecordListItem
  detail: RecordDetail | undefined
  pickingCategory: boolean
  onTogglePickCategory: (recordId: string, picking: boolean) => void
}

// 표준 열마다 이 파일의 실제 열을 하나씩 고른다. 입금·출금이 한 열(금액)에 섞인 경우가
// 흔해서 같은 값을 두 번 고를 수 있게 둔다.
function ColumnMappingForm({
  params,
  onSubmit,
  onCancel,
}: {
  params: ParseErrorParams | null
  onSubmit: (mapping: Record<string, string>) => void
  onCancel: () => void
}) {
  const expected = params?.expectedColumns ?? []
  const actual = params?.actualColumns ?? []
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const complete = expected.length > 0 && expected.every((column) => mapping[column])

  return (
    <div className="flex w-full flex-col gap-[8px] rounded-[9px] border border-[#e3e3e3] bg-[#fbfbfb] px-[11px] py-[10px]">
      <p className="text-[10.5px] font-semibold text-[#6b6b6b]">
        표준 열마다 이 파일의 열을 하나씩 골라 주세요
      </p>

      {expected.map((column) => (
        <label key={column} className="flex w-full items-center gap-[8px]">
          <span className="w-[52px] shrink-0 text-[11.5px] text-[#404040]">{column}</span>
          <select
            value={mapping[column] ?? ''}
            onChange={(event) => setMapping((prev) => ({ ...prev, [column]: event.target.value }))}
            className="min-w-px flex-1 rounded-[8px] border border-[#dbdbdb] bg-white px-[9px] py-[6px] text-[11.5px] text-[#333]"
          >
            <option value="">고르기</option>
            {actual.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      ))}

      <div className="flex items-start gap-[8px]">
        <Button size="sm" disabled={!complete} onClick={() => onSubmit(mapping)}>
          이대로 다시 읽기
        </Button>
        <Button size="sm" variant="secondary" onClick={onCancel}>
          취소
        </Button>
      </div>
    </div>
  )
}

function ParseReasonBox({
  detail,
  onDelete,
  onUploadNew,
  onSubmitColumnMapping,
  onDownloadTemplate,
}: {
  detail: RecordDetail
  onDelete: () => void
  onUploadNew: (file: File) => void
  onSubmitColumnMapping: (mapping: Record<string, string>) => void
  onDownloadTemplate: () => void
}) {
  const [mapping, setMapping] = useState(false)
  if (!detail.parseError) return null

  // 명세: 모르는 reason은 UNKNOWN으로 취급하고, debugMessage는 화면에 쓰지 않는다.
  const reason = normalizeParseErrorReason(detail.parseError.reason)
  const copy = PARSE_ERROR_COPY[reason]
  const hint =
    copy.hint ??
    columnHint(detail.parseError.params?.expectedColumns, detail.parseError.params?.actualColumns)

  return (
    <div className="flex w-full flex-col gap-[8px] rounded-[10px] border border-[#e0e0e0] bg-white px-[14px] py-[12px]">
      <p className="text-[10.5px] font-semibold text-[#6b6b6b]">왜 못 읽었나</p>
      <p className="text-[12px] text-[#404040]">{copy.message}</p>
      {hint && <p className="text-[11.5px] whitespace-pre-wrap text-[#737373]">{hint}</p>}

      {mapping ? (
        <ColumnMappingForm
          params={detail.parseError.params}
          onSubmit={(value) => {
            setMapping(false)
            onSubmitColumnMapping(value)
          }}
          onCancel={() => setMapping(false)}
        />
      ) : (
        <div className="flex items-start gap-[8px]">
          {copy.actions.includes('COLUMN_MAPPING') && (
            <Button size="sm" onClick={() => setMapping(true)}>
              열 직접 맞추기
            </Button>
          )}
          {copy.actions.includes('TEMPLATE') && (
            <Button size="sm" variant="secondary" onClick={onDownloadTemplate}>
              양식 받아서 다시 만들기
            </Button>
          )}
          {copy.actions.includes('UPLOAD_NEW') && (
            <label className="inline-flex cursor-pointer items-center rounded-[10px] border border-[#262626] bg-[#262626] px-[13px] py-[8px] text-[12px] font-medium whitespace-nowrap text-[#fafafa] transition-colors hover:bg-[#1a1a1a]">
              새 파일 올리기
              <input
                type="file"
                accept={UPLOAD_ACCEPT}
                className="hidden"
                onChange={(event) => {
                  const file = event.target.files?.[0]
                  event.target.value = ''
                  if (file) onUploadNew(file)
                }}
              />
            </label>
          )}
          {copy.actions.includes('DELETE') && (
            <Button size="sm" variant="secondary" onClick={onDelete}>
              이 파일 삭제
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

export function RecordRow({
  record,
  detail,
  pickingCategory,
  onTogglePickCategory,
  onChangeCategory,
  onDelete,
  onUploadNew,
  onSubmitColumnMapping,
  onDownloadTemplate,
}: RecordRowProps) {
  // 분류 변경·열 매핑으로 다시 읽는 중이면(PARSING) 이유 박스를 내린다.
  // 단건을 다시 받기 전까지 parseError가 남아 있기 때문이다.
  const reason = needsParseReason(record.parseStatus) && detail?.parseError ? detail : null

  // 삭제는 되돌릴 수 없어 한 번 묻는다. 시안에 대화상자가 없어 브라우저 기본을 쓴다.
  function confirmDelete() {
    if (window.confirm(`${record.fileName}을(를) 삭제할까요? 되돌릴 수 없습니다.`)) {
      onDelete(record.id)
    }
  }

  return (
    <div
      className={cn(
        'flex w-full flex-col gap-[10px] border-t border-[#ededed] px-[22px]',
        reason ? 'bg-[#f9f9f9] pt-[12px] pb-[14px]' : 'py-[12px]',
      )}
    >
      <div className="flex w-full items-center gap-[12px]">
        <span className="h-[24px] w-[20px] shrink-0 rounded-[4px] bg-[#ededed]" />
        <p className="min-w-px truncate text-[12.5px] font-medium text-[#333]">{record.fileName}</p>
        <div className="h-px flex-1" />

        <p className="shrink-0 text-[11px] whitespace-nowrap text-[#808080]">
          {formatDotDate(record.createdAt)}
        </p>

        {pickingCategory ? (
          <select
            autoFocus
            value={record.category}
            onChange={(event) => onChangeCategory(record.id, event.target.value as RecordCategory)}
            onBlur={() => onTogglePickCategory(record.id, false)}
            className="shrink-0 rounded-[6px] border border-[#dbdbdb] bg-white px-[8px] py-[3px] text-[10.5px] text-[#333]"
          >
            {CATEGORY_ORDER.map((category) => (
              <option key={category} value={category}>
                {CATEGORY_LABEL[category]}
              </option>
            ))}
          </select>
        ) : (
          <Chip variant={parseStatusChipVariant(record.parseStatus)}>
            {PARSE_STATUS_LABEL[record.parseStatus] ?? record.parseStatus}
          </Chip>
        )}

        {/* ponytail: 네이티브 <details>라 바깥 클릭으로는 안 닫힌다. 거슬리면 그때 JS를 붙인다. */}
        <details className="relative shrink-0">
          <summary className="cursor-pointer list-none text-[13px] font-medium text-[#808080] [&::-webkit-details-marker]:hidden">
            ⋯
          </summary>
          <div className="absolute top-full right-0 z-10 mt-[6px] flex w-[128px] flex-col rounded-[10px] border border-[#e3e3e3] bg-white py-[4px] shadow-[0px_8px_20px_-6px_rgba(0,0,0,0.12)]">
            <button
              type="button"
              className="px-[12px] py-[7px] text-left text-[11.5px] text-[#404040] hover:bg-[#f5f5f5]"
              onClick={() => onTogglePickCategory(record.id, true)}
            >
              분류 바꾸기
            </button>
            <button
              type="button"
              className="px-[12px] py-[7px] text-left text-[11.5px] text-[#404040] hover:bg-[#f5f5f5]"
              onClick={confirmDelete}
            >
              이 파일 삭제
            </button>
          </div>
        </details>
      </div>

      {reason && (
        <ParseReasonBox
          detail={reason}
          onDelete={confirmDelete}
          // 교체 API를 두지 않고 같은 분류에 새 파일로 추가한다.
          onUploadNew={(file) => onUploadNew(file, record.category)}
          onSubmitColumnMapping={(value) => onSubmitColumnMapping(record.id, value)}
          onDownloadTemplate={onDownloadTemplate}
        />
      )}
    </div>
  )
}
