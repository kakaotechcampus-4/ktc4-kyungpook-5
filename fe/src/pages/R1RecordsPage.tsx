// R1 동아리 기록 — 조립만 한다. 로직은 features/ 로.
import { useState } from 'react'
import { RecordCategoryCard } from '@/features/records/components/RecordCategoryCard'
import { RecordsChatBar } from '@/features/records/components/RecordsChatBar'
import { RecordsChatPanel } from '@/features/records/components/RecordsChatPanel'
import { useRecords, useRecordsChat } from '@/features/records/hooks'
import { CATEGORY_ORDER, UPLOAD_ACCEPT } from '@/features/records/labels'

export default function R1RecordsPage() {
  const {
    records,
    meta,
    details,
    error,
    upload,
    changeCategory,
    remove,
    submitColumnMapping,
    downloadTemplate,
  } = useRecords()
  const chat = useRecordsChat()

  // 분류를 고르는 중인 줄. 머리의 "분류 다시 하기"는 전체를, ⋯ 메뉴는 그 줄 하나를 연다.
  const [pickingIds, setPickingIds] = useState<Set<string>>(new Set())

  function togglePickCategory(recordId: string, picking: boolean) {
    setPickingIds((prev) => {
      const next = new Set(prev)
      if (picking) next.add(recordId)
      else next.delete(recordId)
      return next
    })
  }

  return (
    <div className="flex w-full">
      <div className="flex min-w-px flex-1 flex-col gap-[16px] px-[26px] pt-[22px] pb-[28px]">
        <div className="flex w-full items-center gap-[10px]">
          <div className="flex flex-col gap-[2px]">
            <p className="text-[20px] font-bold text-[#212121]">동아리 기록</p>
            <p className="text-[12px] text-[#737373]">
              총 {meta.totalCount}건 &nbsp;·&nbsp; AI가 읽은 문서 {meta.indexedCount}건
            </p>
          </div>

          <div className="h-px flex-1" />

          <button
            type="button"
            onClick={() =>
              setPickingIds((prev) =>
                prev.size > 0 ? new Set() : new Set(records.map((record) => record.id)),
              )
            }
            className="inline-flex shrink-0 items-center rounded-[20px] border border-[#dbdbdb] bg-white px-[13px] py-[8px] text-[12px] font-medium whitespace-nowrap text-[#525252] transition-colors hover:bg-[#f7f7f7]"
          >
            {pickingIds.size > 0 ? '분류 그만 바꾸기' : '분류 다시 하기'}
          </button>

          {/* 카테고리를 안 보내면 AI가 분류하고 ETC로 기본 처리한다(명세 POST /records). */}
          <label className="inline-flex shrink-0 cursor-pointer items-center rounded-[20px] border border-[#262626] bg-[#262626] px-[13px] py-[8px] text-[12px] font-medium whitespace-nowrap text-[#fafafa] transition-colors hover:bg-[#1a1a1a]">
            + &nbsp;파일 올리기
            <input
              type="file"
              accept={UPLOAD_ACCEPT}
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (file) upload(file)
              }}
            />
          </label>
        </div>

        {error && <p className="text-[12px] text-[#8c6b3a]">{error}</p>}

        {CATEGORY_ORDER.map((category) => (
          <RecordCategoryCard
            key={category}
            category={category}
            count={meta.categoryCounts[category] ?? 0}
            records={records.filter((record) => record.category === category)}
            details={details}
            pickingIds={pickingIds}
            onTogglePickCategory={togglePickCategory}
            onUpload={upload}
            onChangeCategory={(recordId, target) => {
              togglePickCategory(recordId, false)
              changeCategory(recordId, target)
            }}
            onDelete={remove}
            onReplace={(_recordId, file, target) => upload(file, target)}
            onSubmitColumnMapping={submitColumnMapping}
            onDownloadTemplate={downloadTemplate}
          />
        ))}

        <RecordsChatBar pending={chat.pending} onAsk={chat.ask} />
      </div>

      {chat.open && (
        <RecordsChatPanel
          turns={chat.turns}
          suggestions={chat.suggestions}
          pending={chat.pending}
          onAsk={chat.ask}
          onClose={chat.close}
        />
      )}
    </div>
  )
}
