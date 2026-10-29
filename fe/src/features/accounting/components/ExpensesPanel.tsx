import { useState } from 'react'
import { EXPENSE_PAGE_SIZE } from '@/features/accounting/api'
import { useExpenses } from '@/features/accounting/hooks'
import type { Expense } from '@/features/accounting/types'
import { ApiError } from '@/shared/api/types'
import { formatCurrency, formatDotDate } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'

const SOURCE_LABEL: Record<Expense['source'], string> = {
  MANUAL: '직접 입력',
  CSV_IMPORT: 'CSV 가져오기',
  OCR_IMPORT: '영수 내역 가져오기',
}

function expenseErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'UNAUTHORIZED') return '로그인이 만료됐어요. 다시 로그인해 주세요.'
    if (error.code === 'FORBIDDEN')
      return '이 팀의 지출 내역을 볼 권한이 없어요. 소속을 확인해 주세요.'
  }
  return '지출 내역을 불러오지 못했어요. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

export function ExpensesPanel({ clubId }: { clubId: string }) {
  return <ClubExpensesPanel key={clubId} clubId={clubId} />
}

function ClubExpensesPanel({ clubId }: { clubId: string }) {
  const [page, setPage] = useState(1)
  const expenses = useExpenses(clubId, page)
  const rows = expenses.data?.data
  const totalCount = expenses.data?.meta?.totalCount ?? rows?.length ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / EXPENSE_PAGE_SIZE))

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-[12px] p-[22px]">
        <div className="flex items-center gap-[9px]">
          <h2 className="text-h2 text-ink">지출 내역</h2>
          {expenses.data && <Chip size="sm">{totalCount}건</Chip>}
        </div>
        <Button
          variant="secondary"
          size="sm"
          disabled={expenses.isFetching}
          onClick={() => void expenses.refetch()}
        >
          {expenses.isFetching ? '불러오는 중…' : '새로고침'}
        </Button>
      </div>

      {expenses.isPending && (
        <p role="status" className="border-t border-line px-[22px] py-[30px] text-[13px] text-mute">
          지출 내역을 불러오고 있어요.
        </p>
      )}
      {expenses.isError && (
        <div
          role="alert"
          className="border-t border-line px-[22px] py-[22px] text-[13px] text-failed"
        >
          {expenseErrorMessage(expenses.error)}
          {rows && (
            <p className="mt-[7px] text-[12px] text-mute">
              마지막으로 확인한 내역을 표시하고 있어요.
            </p>
          )}
        </div>
      )}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto border-t border-line">
          <table className="w-full min-w-[620px] text-left text-[12px]">
            <caption className="sr-only">선택한 팀의 지출 내역, 최근 지출일 순</caption>
            <thead className="bg-bg text-[11.5px] text-mute">
              <tr>
                <th scope="col" className="px-[22px] py-[12px] font-medium">
                  지출일
                </th>
                <th scope="col" className="px-[14px] py-[12px] font-medium">
                  사용처 · 내용
                </th>
                <th scope="col" className="px-[14px] py-[12px] font-medium">
                  분류
                </th>
                <th scope="col" className="px-[14px] py-[12px] text-right font-medium">
                  금액
                </th>
                <th scope="col" className="px-[22px] py-[12px] font-medium">
                  기록 방식
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((expense) => (
                <tr key={expense.id} className="border-t border-line">
                  <td className="whitespace-nowrap px-[22px] py-[16px] text-ink2">
                    {formatDotDate(expense.spentAt)}
                  </td>
                  <td className="max-w-[320px] px-[14px] py-[16px]">
                    <p className="break-words font-bold text-ink">
                      {expense.merchant || '사용처 미입력'}
                    </p>
                    {expense.description && (
                      <p className="mt-[4px] break-words leading-[18px] text-mute">
                        {expense.description}
                      </p>
                    )}
                  </td>
                  <td className="px-[14px] py-[16px] text-ink2">{expense.category || '미분류'}</td>
                  <td className="whitespace-nowrap px-[14px] py-[16px] text-right font-bold text-ink">
                    {formatCurrency(expense.amount)}
                  </td>
                  <td className="whitespace-nowrap px-[22px] py-[16px] text-mute">
                    {SOURCE_LABEL[expense.source]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {expenses.isSuccess && rows?.length === 0 && (
        <div className="px-[22px] pb-[22px]">
          <EmptyState
            variant="inline"
            title="지출 내역이 없어요"
            desc="선택한 팀에 저장된 지출 내역이 아직 없어요."
          />
        </div>
      )}
      {rows && totalCount > EXPENSE_PAGE_SIZE && (
        <nav
          aria-label="지출 내역 페이지"
          className="flex items-center justify-between gap-[12px] border-t border-line px-[22px] py-[15px]"
        >
          <Button
            variant="secondary"
            size="sm"
            disabled={page <= 1 || expenses.isFetching}
            onClick={() => setPage((current) => current - 1)}
          >
            이전
          </Button>
          <span className="text-[12px] text-mute">
            {page} / {pageCount} 페이지
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={page >= pageCount || expenses.isFetching}
            onClick={() => setPage((current) => current + 1)}
          >
            다음
          </Button>
        </nav>
      )}
    </Card>
  )
}
