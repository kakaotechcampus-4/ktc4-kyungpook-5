// S2 · 동아리 자료 탭. 분류 네 개를 길게 늘어놓고 각 분류 안에 파일을 쌓는다.
// 분류가 없으면 AI가 제대로 활용하지 못해, 올릴 때 분류를 함께 고르게 한다.
import type { ClubRecord, ParseStatus, RecordCategory } from '@/features/mypage/types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'

const CATEGORIES: Array<{ value: RecordCategory; label: string; desc: string }> = [
  { value: 'PLAN', label: '회칙 · 규칙', desc: '회칙, 환불·승인 기준이 담긴 문서' },
  { value: 'NOTICE', label: '과거 행사 기록', desc: '지난 행사의 결과보고와 명단' },
  { value: 'LEDGER', label: '입출금 장부', desc: '회비 수납과 지출 내역' },
  { value: 'ETC', label: '기타', desc: '위 세 가지에 속하지 않는 파일' },
]

const PARSE: Record<
  ParseStatus,
  { label: string; tone: 'done' | 'approved' | 'pending' | 'failed' }
> = {
  INDEXED: { label: '읽음', tone: 'done' },
  PARSING: { label: '읽는 중', tone: 'approved' },
  NEEDS_REVIEW: { label: '형식 확인 필요', tone: 'pending' },
  FAILED: { label: '읽지 못함', tone: 'failed' },
}

function RecordRow({ record }: { record: ClubRecord }) {
  const parse = PARSE[record.parseStatus]
  return (
    <div className="flex items-center gap-[14px] border-t border-line px-[22px] py-[13px]">
      <span className="rounded-[7px] bg-blue-50 px-[8px] py-[6px] text-[9.5px] font-bold text-blue-700">
        {record.fileType}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
        <span className="truncate text-[13px] font-medium text-ink">{record.fileName}</span>
        <span className="text-[10.5px] text-mute">
          {record.size} · {record.uploadedAt}
        </span>
      </span>
      <Chip tone={parse.tone} size="sm">
        {parse.label}
      </Chip>
      <button type="button" aria-label="더 보기" className="text-[13px] text-mute hover:text-ink2">
        ⋯
      </button>
    </div>
  )
}

export function RecordsTab({ records }: { records: ClubRecord[] }) {
  return (
    <div className="flex flex-col gap-[16px]">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-[9px]">
          <h2 className="text-h2 text-ink">동아리 자료</h2>
          <Chip tone="approved">{records.length}건</Chip>
        </span>
        {/* TODO(연동): POST /records (multipart). 분류는 올릴 때 함께 고른다. */}
        <Button>+ 자료 올리기</Button>
      </div>

      {CATEGORIES.map((category) => {
        const rows = records.filter((r) => r.category === category.value)
        return (
          <Card key={category.value} className="flex flex-col">
            <div className="flex items-start justify-between gap-[12px] px-[22px] pt-[20px] pb-[16px]">
              <span className="flex flex-col gap-[6px]">
                <span className="flex items-center gap-[8px]">
                  <span className="text-h3 text-ink">{category.label}</span>
                  <Chip size="sm">{rows.length}건</Chip>
                </span>
                <span className="text-[11.5px] text-mute">{category.desc}</span>
              </span>
              <Button variant="secondary" size="sm">
                올리기 +
              </Button>
            </div>
            {rows.length > 0 ? (
              rows.map((record) => <RecordRow key={record.id} record={record} />)
            ) : (
              <p className="border-t border-line px-[22px] py-[18px] text-[12px] text-mute">
                자료 없음
              </p>
            )}
          </Card>
        )
      })}
    </div>
  )
}
