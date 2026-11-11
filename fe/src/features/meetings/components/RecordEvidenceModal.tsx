import { useMutation, useQuery } from '@tanstack/react-query'
import { downloadRecord, getRecord } from '@/features/records/api'
import { recordErrorMessage } from '@/features/records/presentation'
import { Button } from '@/shared/ui/Button'
import { Modal } from '@/shared/ui/Modal'
import { recordEvidenceBlocks, recordMatchesCitation, type RecordCitation } from '../evidence'

export function RecordEvidenceModal({
  clubId,
  citation,
  onClose,
}: {
  clubId: string
  citation: RecordCitation | null
  onClose: () => void
}) {
  const record = useQuery({
    queryKey: ['records', clubId, citation?.recordId],
    queryFn: () => getRecord(citation!.recordId),
    enabled: !!citation && !!clubId,
    staleTime: 0,
    retry: false,
  })
  const current =
    !record.isFetching &&
    !record.isError &&
    record.data &&
    citation &&
    recordMatchesCitation(record.data, citation, clubId)
      ? record.data
      : null
  const context = recordEvidenceBlocks(current?.parseResult, citation?.locationLabel ?? '')
  const download = useMutation({
    mutationFn: () => downloadRecord(current!.id, current!.fileName),
  })
  return (
    <Modal
      open={!!citation}
      onClose={onClose}
      title="답변의 자료 원문"
      subtitle={current?.fileName ?? citation?.fileName}
      footerNote="현재 저장된 자료의 본문을 보여 줍니다."
      footer={
        <>
          {current && (
            <Button
              variant="secondary"
              loading={download.isPending}
              onClick={() => download.mutate()}
            >
              원본 다운로드
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            회의로 돌아가기
          </Button>
        </>
      }
      width={720}
    >
      {(record.isPending || record.isFetching) && (
        <p role="status">자료의 접근 권한과 본문을 확인하고 있어요.</p>
      )}
      {!record.isFetching && record.isError && (
        <div role="alert" className="space-y-3 text-failed">
          <p>
            {recordErrorMessage(record.error)} 삭제 여부와 현재 소속의 접근 권한을 확인해 주세요.
          </p>
          <Button variant="secondary" onClick={() => void record.refetch()}>
            다시 확인
          </Button>
        </div>
      )}
      {!record.isFetching && !record.isError && record.data && !current && (
        <p role="alert" className="text-failed">
          현재 소속의 출처 자료와 일치하지 않아 열 수 없어요.
        </p>
      )}
      {current && (
        <>
          {citation?.locationLabel && (
            <p className="text-caption font-bold">답변 출처 위치: {citation.locationLabel}</p>
          )}
          {!context.locationFound && (
            <p role="status" className="text-caption text-pending">
              답변에 표시된 위치를 현재 자료에서 찾지 못했어요. 아래에서 현재 본문을 확인해 주세요.
            </p>
          )}
          {context.blocks.length ? (
            context.blocks.map((block, index) => (
              <section key={index} className="space-y-2 rounded-lg border border-line bg-bg p-4">
                {block.locationLabel && (
                  <h3 className="text-caption font-bold">{block.locationLabel}</h3>
                )}
                <p className="whitespace-pre-wrap break-words leading-7">{block.text}</p>
              </section>
            ))
          ) : (
            <p className="text-ink2">
              자료 본문을 아직 읽을 수 없어요. 원본 파일을 내려받아 확인해 주세요.
            </p>
          )}
        </>
      )}
      {download.isError && (
        <p role="alert" className="text-failed">
          원본을 받지 못했어요. 접근 권한과 파일 상태를 확인해 주세요.
        </p>
      )}
    </Modal>
  )
}
