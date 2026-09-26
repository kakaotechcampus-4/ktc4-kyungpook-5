import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Chip } from '@/shared/ui/Chip'
import { formatMonthDay } from '@/shared/lib/format'
import type { EventAction } from '@/features/events/types'

interface ConfirmationRequestsCardProps {
  requests: EventAction[]
  onResolve: (actionId: string, choice: string) => void
}

export function ConfirmationRequestsCard({ requests, onResolve }: ConfirmationRequestsCardProps) {
  return (
    <Card className="flex w-full flex-col overflow-hidden">
      <div className="flex w-full items-center gap-[8px] px-[20px] py-[15px]">
        <p className="text-[14px] font-semibold text-[#242424]">확인 요청 {requests.length}건</p>
        <Chip variant="subtle">되돌릴 수 있어 승인은 아닙니다</Chip>
      </div>

      {requests.length === 0 ? (
        <p className="border-t border-[#ededed] px-[20px] py-[14px] text-[12px] text-[#737373]">
          확인할 요청이 없습니다.
        </p>
      ) : (
        requests.map((request) => (
          <div
            key={request.id}
            className="flex w-full flex-col gap-[10px] border-t border-[#ededed] px-[20px] py-[14px]"
          >
            <div className="flex w-full items-center gap-[8px]">
              <p className="text-[12.5px] font-medium whitespace-nowrap text-[#2e2e2e]">
                {request.title}
              </p>
              <div className="h-px flex-1" />
              {request.dueDate && (
                <p className="text-[11px] whitespace-nowrap text-[#808080]">
                  {formatMonthDay(request.dueDate)}
                </p>
              )}
            </div>

            {request.subtitle && <p className="text-[12px] text-[#595959]">{request.subtitle}</p>}

            <div className="flex items-start gap-[8px]">
              {request.options?.map((option, index) => (
                <Button
                  key={option.key}
                  size="pill"
                  variant={index === 0 ? 'primary' : 'secondary'}
                  onClick={() => onResolve(request.id, option.key)}
                >
                  {option.label}
                </Button>
              ))}
              {request.allowManual && (
                <Button
                  size="pill"
                  variant="secondary"
                  onClick={() => onResolve(request.id, 'MANUAL')}
                >
                  직접 처리
                </Button>
              )}
            </div>
          </div>
        ))
      )}
    </Card>
  )
}
