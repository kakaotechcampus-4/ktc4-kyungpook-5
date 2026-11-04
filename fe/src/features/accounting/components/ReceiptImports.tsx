import { useState, type FormEvent } from 'react'
import { useReceiptActions, useReceiptDetail, useReceiptImports, useRetryReceiptImport } from '../hooks'
import type { ReceiptImport } from '../types'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { ApiError } from '@/shared/api/types'
import { formatKstDateInput } from '@/shared/lib/format'

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.code === 'FORBIDDEN') return '이 영수증을 처리할 권한이 없어요.'
  if (error instanceof ApiError && error.code === 'UNAUTHORIZED') return '로그인 상태를 확인해 주세요.'
  if (error instanceof ApiError && error.code === 'VERSION_CONFLICT') return '다른 곳에서 변경됐어요. 입력을 복사해 둔 뒤 목록을 새로고침해 확인해 주세요.'
  return '처리 결과를 확인하지 못했어요. 연결을 확인하고 다시 시도해 주세요.'
}

function ReceiptReview({ clubId, item, onDone }: { clubId: string; item: ReceiptImport; onDone: () => void }) {
  const [version, setVersion] = useState(item.version)
  const [rows, setRows] = useState(() => item.expenseRows.map((row) => ({
    rowNo: row.rowNo, date: formatKstDateInput(row.spentAt), originalDate: formatKstDateInput(row.spentAt), originalTime: row.spentAt,
    merchant: row.merchant ?? '', amount: row.amount == null ? '' : String(row.amount), category: row.category ?? '', description: row.description ?? '',
  })))
  const [message, setMessage] = useState('')
  const [ack, setAck] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const actions = useReceiptActions(clubId)
  const busy = actions.draft.isPending || actions.confirm.isPending
  const change = (index: number, field: 'date' | 'merchant' | 'amount' | 'category' | 'description', value: string) => {
    setRows((current) => current.map((row, i) => i === index ? { ...row, [field]: value } : row))
    setAck(false)
  }
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (busy || !ack || uncertain) return
    setMessage('')
    try {
      const saved = await actions.draft.mutateAsync({ id: item.id, body: { expectedVersion: version, expenseRows: rows.map((row) => ({
        rowNo: row.rowNo, spentAt: row.date === row.originalDate && row.originalTime ? row.originalTime : new Date(`${row.date}T00:00:00+09:00`).toISOString(),
        merchant: row.merchant, amount: Number(row.amount), category: row.category, description: row.description,
      })) } })
      setVersion(saved.version)
      if (saved.errors.length) { setMessage('검토가 필요한 항목이 있어요. 내용을 다시 확인해 주세요.'); return }
      try {
        await actions.confirm.mutateAsync({ id: item.id, version: saved.version })
        onDone()
      } catch (error) {
        setUncertain(true)
        setMessage(`${errorMessage(error)} 확정 결과는 목록을 새로고침해 확인해 주세요. 입력은 이 화면에 남아 있어요.`)
      }
    } catch (error) {
      setUncertain(true)
      setMessage(`${errorMessage(error)} 저장 결과는 목록을 새로고침해 확인해 주세요. 입력은 이 화면에 남아 있어요.`)
    }
  }
  return (
    <form className="space-y-4 border-t border-line pt-4" onSubmit={(event) => void submit(event)}>
      <p className="text-caption text-ink2">읽은 내용을 확인하고 수정해 주세요. 확정 전에는 지출에 반영되지 않아요.</p>
      {rows.map((row, index) => <fieldset key={row.rowNo} className="space-y-3 rounded-lg border border-line p-4">
        <legend className="px-1 font-bold">내역 {index + 1}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label="지출일 · 한국시간" type="date" required value={row.date} onChange={(e) => change(index, 'date', e.target.value)} />
          <Input label="금액 (원)" type="number" min="0" step="1" required value={row.amount} onChange={(e) => change(index, 'amount', e.target.value)} />
          <Input label="사용처" value={row.merchant} onChange={(e) => change(index, 'merchant', e.target.value)} />
          <Input label="분류" value={row.category} onChange={(e) => change(index, 'category', e.target.value)} />
        </div>
        <Input label="내용" value={row.description} onChange={(e) => change(index, 'description', e.target.value)} />
      </fieldset>)}
      {!rows.length && <p role="alert" className="text-failed">읽은 내역이 없어요. 영수증을 다시 확인해 주세요.</p>}
      <label className="flex items-start gap-2 text-caption"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />내용과 날짜, 금액을 확인했어요.</label>
      {message && <p role="alert" className="text-caption text-failed">{message}</p>}
      <Button type="submit" disabled={busy || !ack || uncertain || !rows.length}>{busy ? '저장하는 중…' : '확인 후 지출로 저장'}</Button>
    </form>
  )
}

function ReceiptDetails({ clubId, id, onDone }: { clubId: string; id: string; onDone: () => void }) {
  const detail = useReceiptDetail(clubId, id)
  return <div className="space-y-3">
    {detail.isPending && <p role="status">영수증을 불러오고 있어요.</p>}
    {detail.isError && <p role="alert" className="text-failed">{errorMessage(detail.error)} <button className="underline" onClick={() => void detail.refetch()}>다시 시도</button></p>}
    {detail.data?.status === 'NEEDS_REVIEW' && <ReceiptReview key={detail.data.id} clubId={clubId} item={detail.data} onDone={onDone} />}
    {detail.data?.status === 'FAILED' && <p role="alert" className="text-failed">영수증을 읽지 못했어요. 목록에서 다시 시도해 주세요.</p>}
    {detail.data?.status === 'PROCESSING' && <p role="status">영수증을 읽고 있어요.</p>}
    {detail.data?.status === 'CONFIRMED' && <p>확정된 영수증이에요. 지출 내역에서 확인해 주세요.</p>}
  </div>
}

export function ReceiptImports({ clubId }: { clubId: string }) {
  const query = useReceiptImports(clubId)
  const retry = useRetryReceiptImport(clubId)
  const actions = useReceiptActions(clubId)
  const [selected, setSelected] = useState<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [notice, setNotice] = useState('')
  const items = query.data?.data.filter((item) => item.type === 'RECEIPT_IMAGE') ?? []
  return <Card className="space-y-4 p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="text-h2">영수증으로 지출 등록</h2><p className="mt-1 text-caption text-mute">사진을 올리고 읽은 내용을 확인한 뒤 저장해요.</p></div><Button variant="secondary" size="sm" onClick={() => void query.refetch()}>새로고침</Button></div>
    <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); if (!file || actions.upload.isPending) return; setNotice(''); actions.upload.mutate(file, {onSuccess: (item) => {setSelected(item.id); setFile(null); setNotice('영수증을 받았어요. 처리 상태를 확인해 주세요.')}, onError: () => setNotice('업로드 결과를 확인하지 못했어요. 목록을 새로고침한 뒤 다시 시도해 주세요.')}) }}>
      <div className="min-w-0 flex-1"><Input type="file" label="영수증 사진" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
      <Button type="submit" disabled={!file || actions.upload.isPending}>{actions.upload.isPending ? '올리는 중…' : '영수증 올리기'}</Button>
    </form>
    {notice && <p role="status" className="text-caption">{notice}</p>}
    {query.isPending && <p role="status">불러오는 중이에요.</p>}
    {query.isError && <p role="alert" className="text-failed">상태를 불러오지 못했어요. 새로고침해 주세요.</p>}
    {query.isSuccess && !items.length && <p className="text-caption text-mute">최근 영수증 처리 내역이 없어요.</p>}
    {items.map((item, index) => <div key={item.id} className="space-y-2 border-t border-line pt-3 text-caption">
      <p>최근 영수증 {index + 1} · {item.status === 'PROCESSING' ? '읽는 중' : item.status === 'FAILED' ? '읽기 실패' : item.status === 'NEEDS_REVIEW' ? '검토 필요' : item.status === 'CONFIRMED' ? '확정됨' : '처리 대기'}</p>
      <div className="flex flex-wrap gap-2"><Button variant="secondary" size="sm" onClick={() => setSelected(item.id)}>내용 확인</Button>
      {(item.status === 'FAILED' || item.status === 'PROCESSING') && <Button variant="secondary" size="sm" disabled={retry.isPending} onClick={() => retry.mutate(item.id, { onSuccess: () => setSelected(item.id) })}>읽기 다시 시도</Button>}</div>
      {retry.isError && retry.variables === item.id && <p role="alert" className="text-failed">{errorMessage(retry.error)} 처리 중인 경우 잠시 후 다시 시도해 주세요.</p>}
      {selected === item.id && <ReceiptDetails key={item.id} clubId={clubId} id={item.id} onDone={() => { setSelected(null); setNotice('지출로 저장했어요. 아래 지출 내역에서 확인해 주세요.') }} />}
    </div>)}
    {query.data && query.data.meta && query.data.meta.totalCount > 20 && <p className="text-caption text-mute">최근 20건만 표시합니다.</p>}
  </Card>
}
