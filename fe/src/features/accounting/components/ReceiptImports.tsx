import { useReceiptImports, useRetryReceiptImport } from '../hooks'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { ApiError } from '@/shared/api/types'

export function ReceiptImports({ clubId }: { clubId: string }) {
  const query = useReceiptImports(clubId)
  const retry = useRetryReceiptImport(clubId)
  const items = query.data?.data.filter((item) => item.type === 'RECEIPT_IMAGE') ?? []
  return (
    <Card className="space-y-4 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><h2 className="text-h2">영수증 처리 상태</h2><p className="mt-1 text-caption text-mute">최근 가져온 영수증의 처리 상태를 확인합니다.</p></div>
        <Button variant="secondary" size="sm" onClick={() => void query.refetch()}>새로고침</Button>
      </div>
      {query.isPending && <p role="status">불러오는 중이에요.</p>}
      {query.isError && <p role="alert" className="text-failed">상태를 불러오지 못했어요. 새로고침해 주세요.</p>}
      {query.isSuccess && !items.length && <p className="text-caption text-mute">최근 영수증 처리 내역이 없어요.</p>}
      {items.map((item) => (
        <div key={item.id} className="space-y-2 border-t border-line pt-3 text-caption">
          <p className="break-all">영수증 · {item.id}</p>
          <p>{item.status === 'PROCESSING' ? '읽는 중이에요. 오래 걸리면 다시 시도할 수 있어요.' : item.status === 'FAILED' ? '읽기에 실패했어요.' : item.status === 'NEEDS_REVIEW' ? '읽기 완료 · 검토 필요 (아직 지출에 반영되지 않았어요)' : item.status === 'CONFIRMED' ? '확정됨' : '처리 대기'}</p>
          {(item.status === 'FAILED' || item.status === 'PROCESSING') && <Button variant="secondary" size="sm" disabled={retry.isPending} onClick={() => retry.mutate(item.id)}>읽기 다시 시도</Button>}
          {retry.isError && retry.variables === item.id && <p role="alert" className="text-failed">{retry.error instanceof ApiError && retry.error.code === 'FORBIDDEN' ? '이 영수증을 처리할 권한이 없어요.' : '다시 시작하지 못했어요. 처리 중인 경우 잠시 후 다시 시도해 주세요.'}</p>}
        </div>
      ))}
      {query.data && query.data.meta && query.data.meta.totalCount > 20 && <p className="text-caption text-mute">최근 20건만 표시합니다.</p>}
      <p className="text-caption text-mute">읽은 내역의 검토·수정 화면은 아직 준비 중입니다. 지출은 직접 등록할 수 있어요.</p>
    </Card>
  )
}
