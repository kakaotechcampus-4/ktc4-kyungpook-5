import { useMemo, useState } from 'react'
import { EXPENSE_PAGE_SIZE } from '@/features/accounting/api'
import { ExpenseForm } from '@/features/accounting/components/ExpenseForm'
import { eventLabels } from '@/features/accounting/eventLabels'
import { expenseFormErrorMessage, useDeleteExpense, useExpenses } from '@/features/accounting/hooks'
import type { Expense } from '@/features/accounting/types'
import { useEvents } from '@/features/events/hooks'
import { ApiError } from '@/shared/api/types'
import { formatCurrency, formatDotDate } from '@/shared/lib/format'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { EmptyState } from '@/shared/ui/EmptyState'
import { Skeleton } from '@/shared/ui/Skeleton'
import { staggerDelay } from '@/shared/lib/stagger'

const SOURCE_LABEL: Record<Expense['source'], string> = {
  MANUAL: '직접 입력',
  CSV_IMPORT: 'CSV 가져오기',
  OCR_IMPORT: '영수 내역 가져오기',
  // 행사 송금 행동을 실행 완료하면 서버가 남긴다 (#348, #367).
  ACTION: '자동 기록',
}

function expenseErrorMessage(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === 'UNAUTHORIZED') return '로그인이 만료됐어요. 다시 로그인해 주세요.'
    if (error.code === 'FORBIDDEN')
      return '이 팀의 지출 내역을 볼 권한이 없어요. 소속을 확인해 주세요.'
  }
  return '지출 내역을 불러오지 못했어요. 연결 상태를 확인한 뒤 다시 시도해 주세요.'
}

// 행사에 연결되지 않았거나 목록에서 찾지 못한 지출은 빈칸이다. ID를 대신 보이지 않는다.
function EventCell({ label }: { label: string | undefined }) {
  return (
    <td className="max-w-[180px] px-[14px] py-[16px] text-ink2">
      {label && (
        <span className="block truncate" title={label}>
          {label}
        </span>
      )}
    </td>
  )
}

export function ExpensesPanel({ clubId }: { clubId: string }) {
  return <ClubExpensesPanel key={clubId} clubId={clubId} />
}

function ClubExpensesPanel({ clubId }: { clubId: string }) {
  const [page, setPage] = useState(1)
  const [adding, setAdding] = useState(false)
  // 고치는 중인 한 건. 등록 폼과 동시에 열지 않는다.
  const [editingId, setEditingId] = useState<string | null>(null)
  const remove = useDeleteExpense(clubId)
  const expenses = useExpenses(clubId, page)
  const rows = expenses.data?.data
  const totalCount = expenses.data?.meta?.totalCount ?? rows?.length ?? 0
  const pageCount = Math.max(1, Math.ceil(totalCount / EXPENSE_PAGE_SIZE))
  // 행사 이름은 이 목록으로만 붙인다. 못 받았거나 받는 중이면 행사 칸만 비고 장부는 그대로 보인다.
  const events = useEvents()
  const eventLabelById = useMemo(() => eventLabels(events.data ?? []), [events.data])

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-[12px] p-[22px]">
        <div className="flex items-center gap-[9px]">
          <h2 className="text-h2 text-ink">지출 내역</h2>
          {expenses.data && <Chip size="sm">{totalCount}건</Chip>}
        </div>
        <div className="flex gap-[8px]">
          <Button
            variant="secondary"
            size="sm"
            disabled={expenses.isFetching}
            onClick={() => void expenses.refetch()}
          >
            {expenses.isFetching ? '불러오는 중…' : '새로고침'}
          </Button>
          <Button
            size="sm"
            aria-expanded={adding}
            onClick={() => {
              setEditingId(null)
              setAdding((open) => !open)
            }}
          >
            지출 등록
          </Button>
        </div>
      </div>

      {adding && (
        <ExpenseForm
          clubId={clubId}
          onDone={() => {
            setAdding(false)
            // 새 지출은 첫 페이지에 들어간다. 뒤쪽을 보고 있었다면 거기로 데려간다.
            setPage(1)
          }}
        />
      )}

      {remove.isError && (
        <div
          role="alert"
          className="border-t border-line px-[22px] py-[14px] text-[13px] text-failed"
        >
          {expenseFormErrorMessage(remove.error, '삭제')}
        </div>
      )}

      {expenses.isPending && (
        <div className="border-t border-line" role="status" aria-busy>
          <p className="sr-only">지출 내역을 불러오고 있어요.</p>
          {/* 표가 들어올 자리를 행 높이 그대로 잡아 둔다. 숫자는 오른쪽에 붙는다. */}
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="flex items-center gap-[14px] border-t border-line px-[22px] py-[16px] first:border-0"
            >
              <Skeleton className="h-[17px] w-[72px] shrink-0" />
              <Skeleton className="h-[17px] flex-1" />
              <Skeleton className="h-[17px] w-[64px] shrink-0" />
              <Skeleton className="h-[17px] w-[88px] shrink-0" />
            </div>
          ))}
        </div>
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
          <table className="w-full min-w-[740px] text-center text-[12px]">
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
                  행사
                </th>
                <th scope="col" className="px-[14px] py-[12px] font-medium">
                  분류
                </th>
                <th scope="col" className="px-[14px] py-[12px] font-medium">
                  금액
                </th>
                <th scope="col" className="px-[22px] py-[12px] font-medium">
                  기록 방식
                </th>
                <th scope="col" className="px-[22px] py-[12px] font-medium">
                  <span className="sr-only">수정·삭제</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((expense, i) =>
                editingId === expense.id ? (
                  <tr key={expense.id} className="border-t border-line">
                    <td colSpan={7} className="p-0 text-left">
                      <ExpenseForm
                        key={expense.version}
                        clubId={clubId}
                        expense={expense}
                        onDone={() => setEditingId(null)}
                      />
                    </td>
                  </tr>
                ) : (
                  <tr
                    key={expense.id}
                    className="border-t border-line animate-turn-in motion-reduce:animate-none"
                    style={{ animationDelay: staggerDelay(i) }}
                  >
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
                    <EventCell
                      label={expense.eventId ? eventLabelById.get(expense.eventId) : undefined}
                    />
                    <td className="px-[14px] py-[16px] text-ink2">
                      {expense.category || '미분류'}
                    </td>
                    <td className="whitespace-nowrap px-[14px] py-[16px] font-bold text-ink">
                      {formatCurrency(expense.amount)}
                    </td>
                    <td className="whitespace-nowrap px-[22px] py-[16px] text-mute">
                      {SOURCE_LABEL[expense.source]}
                    </td>
                    <td className="whitespace-nowrap px-[22px] py-[16px]">
                      <span className="flex justify-center gap-[6px]">
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={remove.isPending}
                          onClick={() => {
                            setAdding(false)
                            setEditingId(expense.id)
                          }}
                        >
                          수정
                        </Button>
                        {/* 되돌릴 수 없어 금액과 사용처를 확인 문구에 넣는다. */}
                        <Button
                          variant="danger"
                          size="sm"
                          disabled={remove.isPending}
                          onClick={() => {
                            if (
                              window.confirm(
                                `${formatDotDate(expense.spentAt)} ${formatCurrency(expense.amount)} (${expense.merchant || '사용처 미입력'}) 지출을 지울까요? 되돌릴 수 없어요.`,
                              )
                            ) {
                              remove.mutate(expense.id)
                            }
                          }}
                        >
                          삭제
                        </Button>
                      </span>
                    </td>
                  </tr>
                ),
              )}
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
