import { Card } from '@/shared/ui/Card'

const RECORD_METHODS = [
  { title: '지난 정산 문서 올리기', description: '엑셀·한글·사진 모두 가능합니다', recommended: true },
  { title: '통장 내역 불러오기', description: '은행 연동으로 과거 입출금을 가져옵니다', recommended: false },
  { title: '이번 예산만 직접 입력', description: '기록 없이도 계획 대비 잔액은 볼 수 있습니다', recommended: false },
]

export function EmptyBudgetForecastCard() {
  return (
    <Card className="flex w-full flex-col gap-[20px] p-[26px]">
      <div className="flex w-full items-center gap-[10px]">
        <div className="flex flex-col gap-[2px]">
          <p className="text-[17px] font-bold text-[#212121]">예산 전망</p>
          <p className="text-[12px] text-[#737373]">앞으로의 입출금을 예측하려면 지난 행사 기록이 필요합니다</p>
        </div>
        <div className="h-px flex-1" />
        <span className="rounded-[6px] border border-[#e3e3e3] bg-[#f9f9f9] px-[8px] py-[4px] text-[10.5px] font-medium text-[#666]">
          참고할 기록 0건
        </span>
      </div>

      <div className="flex w-full items-start gap-[26px]">
        <div className="flex w-[360px] shrink-0 flex-col gap-[16px]">
          <div className="flex flex-col gap-[5px]">
            <p className="text-[20px] font-bold text-[#333]">아직 예측할 수 없습니다</p>
            <p className="w-[320px] text-[12.5px] text-[#666]">
              지난 행사 정산 기록이 한 건이라도 있으면, 항목별 평균 지출을 기준으로 이번 행사가 끝났을 때 남을 돈을 계산해
              드립니다.
            </p>
          </div>
          <div className="flex w-full flex-col gap-[9px]">
            <p className="text-[11.5px] font-semibold text-[#666]">기록을 채우는 방법</p>
            {RECORD_METHODS.map((method) => (
              <button
                key={method.title}
                type="button"
                className="flex w-full items-center gap-[12px] rounded-[12px] border border-[#e0e0e0] bg-white px-[14px] py-[12px] text-left hover:bg-[#fafafa]"
              >
                <span className="size-[26px] shrink-0 rounded-[9px] bg-[#e6e6e6]" />
                <span className="flex flex-col gap-[2px]">
                  <span className="flex items-center gap-[6px]">
                    <span className="text-[12.5px] font-medium text-[#2e2e2e]">{method.title}</span>
                    {method.recommended && (
                      <span className="rounded-[6px] border border-[#e3e3e3] bg-[#ededed] px-[8px] py-[4px] text-[10.5px] font-medium text-[#333]">
                        추천
                      </span>
                    )}
                  </span>
                  <span className="text-[11px] text-[#7a7a7a]">{method.description}</span>
                </span>
                <span className="h-px flex-1" />
                <span className="text-[14px] text-[#808080]">›</span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-[12px]">
          <div className="flex w-full items-center gap-[8px]">
            <p className="text-[11.5px] font-semibold text-[#737373]">잔고 흐름</p>
            <div className="h-px flex-1" />
            <p className="text-[11px] text-[#8c8c8c]">기록이 들어오면 여기에 표시됩니다</p>
          </div>
          <div className="flex w-full flex-col items-center justify-center gap-[14px] rounded-[14px] border-[1.5px] border-dashed border-[#dbdbdb] bg-[#f9f9f9] py-[34px]">
            <div className="flex items-end gap-[12px]">
              {[70, 96, 58, 110, 84, 124].map((height, i) => (
                <span key={i} className="w-[58px] rounded-[8px] bg-[#ececec]" style={{ height }} />
              ))}
            </div>
            <p className="text-[13px] font-medium text-[#737373]">데이터를 더 추가해 주세요</p>
          </div>
        </div>
      </div>
    </Card>
  )
}
