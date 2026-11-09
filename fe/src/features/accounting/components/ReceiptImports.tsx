import { useState, type FormEvent } from 'react'
import { useReceiptActions, useReceiptDetail, useReceiptImports, useRetryReceiptImport } from '../hooks'
import type { ReceiptImport } from '../types'
import { EventSelectField } from './EventSelectField'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { ApiError } from '@/shared/api/types'
import { formatKstDateInput } from '@/shared/lib/format'
import { getReceiptImport } from '../api'

function errorMessage(error: unknown) {
  if (error instanceof ApiError && error.code === 'FORBIDDEN') return '이 영수증을 처리할 권한이 없어요.'
  if (error instanceof ApiError && error.code === 'UNAUTHORIZED') return '로그인 상태를 확인해 주세요.'
  if (error instanceof ApiError && error.code === 'VERSION_CONFLICT') return '다른 곳에서 변경됐어요. 입력을 복사해 둔 뒤 서버 상태를 다시 확인해 주세요.'
  return '처리 결과를 확인하지 못했어요. 연결을 확인하고 다시 시도해 주세요.'
}
function validationMessage(error: ApiError) {
  const fields = Object.entries(error.fields ?? {}).map(([field, value]) => `${field.replace(/rows\[(\d+)\]/g, '내역 $1')}: ${value}`)
  return [error.message, ...fields].filter(Boolean).join(' ')
}

// 확정으로 만들어진 지출 ID. 장부에서 그 행을 찾아 보여 주는 데 쓴다.
const confirmedIds = (item: ReceiptImport) => item.expenseRows.flatMap((row) => row.confirmedExpenseId ? [row.confirmedExpenseId] : [])

function ReceiptReview({ clubId, item, onDone }: { clubId: string; item: ReceiptImport; onDone: (expenseIds: string[]) => void }) {
  const [version, setVersion] = useState(item.version)
  const [rows, setRows] = useState(() => item.expenseRows.map((row) => ({
    rowNo: row.rowNo, date: formatKstDateInput(row.spentAt), originalDate: formatKstDateInput(row.spentAt), originalTime: row.spentAt,
    merchant: row.merchant ?? '', amount: row.amount == null ? '' : String(row.amount), category: row.category ?? '', description: row.description ?? '',
  })))
  const [message, setMessage] = useState('')
  const [ack, setAck] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [checking, setChecking] = useState(false)
  const [latest, setLatest] = useState<ReceiptImport | null>(null)
  const [errors, setErrors] = useState(item.errors)
  // 확정으로 만드는 지출을 연결할 행사(#367). '' 는 연결 안 함.
  const [eventId, setEventId] = useState('')
  const actions = useReceiptActions(clubId)
  const busy = actions.draft.isPending || actions.confirm.isPending || checking
  const change = (index: number, field: 'date' | 'merchant' | 'amount' | 'category' | 'description', value: string) => {
    setRows((current) => current.map((row, i) => i === index ? { ...row, [field]: value } : row))
    setAck(false)
    const key = field === 'date' ? 'spent_at' : field
    setErrors((current) => current.filter((error) => error.rowNo !== rows[index].rowNo || ![key, field === 'date' ? 'spentAt' : field].includes(error.field)))
  }
  const checkLatest = async () => {
    setChecking(true)
    try {
      const current = await getReceiptImport(clubId, item.id)
      setLatest(current)
      if (current.status === 'CONFIRMED') { onDone(confirmedIds(current)); return }
      setMessage(current.status === 'NEEDS_REVIEW' ? '서버의 최신 내용과 아래 입력을 비교해 주세요.' : '현재 서버 상태를 확인해 주세요. 입력은 보존됩니다.')
    } catch { setMessage('서버 상태를 확인하지 못했어요. 입력을 유지한 채 다시 확인해 주세요.') }
    finally { setChecking(false) }
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
      setErrors(saved.errors)
      if (saved.errors.length) { setMessage('검토가 필요한 항목이 있어요. 내용을 다시 확인해 주세요.'); return }
      try {
        const confirmed = await actions.confirm.mutateAsync({ id: item.id, version: saved.version, eventId: eventId || null })
        onDone(confirmed.expenseIds)
      } catch (error) {
        if (error instanceof ApiError && ['VALIDATION_ERROR', 'VALIDATION_FAILED'].includes(error.code)) { setMessage(validationMessage(error)); setAck(false); return }
        setUncertain(true)
        setMessage(`${errorMessage(error)} 확정 결과는 아래 '서버 상태 다시 확인'으로 확인해 주세요. 입력은 이 화면에 남아 있어요.`)
      }
    } catch (error) {
      if (error instanceof ApiError && ['VALIDATION_ERROR', 'VALIDATION_FAILED'].includes(error.code)) { setMessage(validationMessage(error)); setAck(false); return }
      setUncertain(true)
      setMessage(`${errorMessage(error)} 저장 결과는 아래 '서버 상태 다시 확인'으로 확인해 주세요. 입력은 이 화면에 남아 있어요.`)
    }
  }
  return (
    <form className="space-y-4 border-t border-line pt-4" onSubmit={(event) => void submit(event)}>
      <p className="text-caption text-ink2">읽은 내용을 확인하고 수정해 주세요. 확정 전에는 지출에 반영되지 않아요.</p>
      {rows.map((row, index) => <fieldset key={row.rowNo} className="space-y-3 rounded-lg border border-line p-4">
        <legend className="px-1 font-bold">내역 {index + 1}</legend>
        {errors.filter((error) => error.rowNo === row.rowNo).map((error, i) => <p key={`${error.field}-${i}`} role="alert" className="text-caption text-failed">{({spent_at:'지출일', spentAt:'지출일', amount:'금액', merchant:'사용처', category:'분류', description:'내용'} as Record<string,string>)[error.field] ?? error.field}: {error.message}</p>)}
        <div className="grid gap-3 sm:grid-cols-2">
          <Input label="지출일 · 한국시간" type="date" required value={row.date} onChange={(e) => change(index, 'date', e.target.value)} />
          <Input label="금액 (원)" type="number" min="0" step="1" required value={row.amount} onChange={(e) => change(index, 'amount', e.target.value)} />
          <Input label="사용처" value={row.merchant} onChange={(e) => change(index, 'merchant', e.target.value)} />
          <Input label="분류" value={row.category} onChange={(e) => change(index, 'category', e.target.value)} />
        </div>
        <Input label="내용" value={row.description} onChange={(e) => change(index, 'description', e.target.value)} />
      </fieldset>)}
      {!rows.length && <p role="alert" className="text-failed">읽은 내역이 없어요. 영수증을 다시 확인해 주세요.</p>}
      {rows.length > 0 && <EventSelectField value={eventId} onChange={setEventId} disabled={busy} failedHint="행사 목록을 못 불러와 연결 없이 저장돼요" />}
      <label className="flex items-start gap-2 text-caption"><input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />내용과 날짜, 금액을 확인했어요.</label>
      {message && <p role="alert" className="text-caption text-failed">{message}</p>}
      {uncertain && <div className="space-y-2"><Button type="button" variant="secondary" disabled={busy} onClick={() => void checkLatest()}>{checking ? '확인 중…' : '서버 상태 다시 확인'}</Button>
        {latest?.status === 'NEEDS_REVIEW' && <div className="space-y-2 text-caption"><p>서버에 저장된 내용</p>{latest.expenseRows.map((row) => <p key={row.rowNo} className="break-words">내역 {row.rowNo} · {formatKstDateInput(row.spentAt) || '날짜 미정'} · {row.merchant || '사용처 미정'} · {row.amount == null ? '금액 미정' : `${row.amount.toLocaleString()}원`} · {row.category || '분류 미정'} · {row.description || '내용 없음'}</p>)}<Button type="button" variant="secondary" onClick={() => { setVersion(latest.version); setLatest(null); setUncertain(false); setAck(false); setMessage('입력 내용을 다시 확인한 뒤 저장해 주세요.') }}>비교했어요 · 내 입력 계속 수정</Button></div>}</div>}
      <Button type="submit" disabled={busy || !ack || uncertain || !rows.length}>{busy ? '저장하는 중…' : '확인 후 지출로 저장'}</Button>
    </form>
  )
}

// 영수증 한 장. 상태에 따라 읽는 중 안내, 검토·확정 화면, 실패 안내와 다시 읽기를 바로 보인다.
function ReceiptDetails({ clubId, id, onDone }: { clubId: string; id: string; onDone: (expenseIds: string[]) => void }) {
  const detail = useReceiptDetail(clubId, id)
  const retry = useRetryReceiptImport(clubId)
  const status = detail.data?.status
  return <div className="space-y-3">
    {detail.isPending && <p role="status">영수증을 불러오고 있어요.</p>}
    {detail.isError && <p role="alert" className="text-failed">{errorMessage(detail.error)} <button className="underline" onClick={() => void detail.refetch()}>다시 시도</button></p>}
    {detail.data?.status === 'NEEDS_REVIEW' && <ReceiptReview key={detail.data.id} clubId={clubId} item={detail.data} onDone={onDone} />}
    {status === 'FAILED' && <p role="alert" className="text-failed">영수증을 읽지 못했어요. 다시 읽어 보거나 사진을 새로 올려 주세요.</p>}
    {status === 'PROCESSING' && <p role="status">영수증을 읽고 있어요.</p>}
    {status === 'CONFIRMED' && <p>확정된 영수증이에요. 지출 내역에서 확인해 주세요.</p>}
    {(status === 'FAILED' || status === 'PROCESSING') && <Button variant="secondary" size="sm" disabled={retry.isPending} onClick={() => retry.mutate(id)}>{retry.isPending ? '다시 읽는 중…' : '읽기 다시 시도'}</Button>}
    {retry.isError && <p role="alert" className="text-failed">{errorMessage(retry.error)} 처리 중인 경우 잠시 후 다시 시도해 주세요.</p>}
  </div>
}

// 영수증으로 지출 등록. 가장 최근에 올린 영수증의 읽기·검토 화면을 바로 펼치고,
// 확정하면 장부의 그 행을 보여 준다.
export function ReceiptImports({ clubId, onConfirmed }: { clubId: string; onConfirmed?: (expenseIds: string[]) => void }) {
  const query = useReceiptImports(clubId)
  const actions = useReceiptActions(clubId)
  const [file, setFile] = useState<File | null>(null)
  // 파일 칸은 브라우저가 값을 쥐고 있어 state만 비우면 이름이 남는다. 올리고 나면 key로 새로 그려 비운다.
  const [fileInputKey, setFileInputKey] = useState(0)
  const [notice, setNotice] = useState('')
  // 업로드 응답을 못 받아 올라갔는지 모를 때. 목록을 다시 받아 보면 알 수 있다.
  const [uploadUnknown, setUploadUnknown] = useState(false)
  const reload = () => { setUploadUnknown(false); void query.refetch() }
  const reloadButton = <button type="button" className="ml-1 font-bold underline" onClick={reload}>다시 불러오기</button>
  // 가장 최근에 올린 영수증 한 장만 다룬다(목록은 최근 순). 새 사진을 올렸으면 그 전 영수증은
  // 읽기 실패든 검토 대기든 더 볼 일이 없다고 보고 화면에서 뺀다. 확정됐으면 장부에 있으니 비운다.
  const latest = query.data?.data.find((item) => item.type === 'RECEIPT_IMAGE')
  const items = latest && latest.status !== 'CONFIRMED' ? [latest] : []
  return <Card className="space-y-4 p-5">
    <div><h2 className="text-h2">영수증으로 지출 등록</h2><p className="mt-1 text-caption text-mute">사진을 올리고 읽은 내용을 확인한 뒤 저장해요.</p></div>
    <form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); if (!file || actions.upload.isPending) return; setNotice(''); setUploadUnknown(false); actions.upload.mutate(file, {onSuccess: () => {setFile(null); setFileInputKey((key) => key + 1); setNotice('영수증을 받았어요. 다 읽으면 아래에서 내용을 확인해 주세요.')}, onError: () => setUploadUnknown(true)}) }}>
      <div className="min-w-0 flex-1"><Input key={fileInputKey} type="file" label="영수증 사진" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></div>
      <Button type="submit" disabled={!file || actions.upload.isPending}>{actions.upload.isPending ? '올리는 중…' : '영수증 올리기'}</Button>
    </form>
    {notice && <p role="status" className="text-caption">{notice}</p>}
    {uploadUnknown && <p role="alert" className="text-caption text-failed">업로드 결과를 확인하지 못했어요. 목록을 다시 불러와 올라갔는지 본 뒤, 없으면 다시 올려 주세요.{reloadButton}</p>}
    {query.isPending && <p role="status">불러오는 중이에요.</p>}
    {query.isError && <p role="alert" className="text-failed">영수증 상태를 불러오지 못했어요.{reloadButton}</p>}
    {query.isSuccess && !items.length && <p className="text-caption text-mute">검토할 영수증이 없어요. 확정한 영수증은 아래 지출 내역에 있어요.</p>}
    {items.map((item) => <div key={item.id} className="border-t border-line pt-3 text-caption">
      <ReceiptDetails clubId={clubId} id={item.id} onDone={(expenseIds) => { setNotice(expenseIds.length ? `지출 ${expenseIds.length}건을 저장했어요. 아래 지출 내역에서 확인해 주세요.` : '지출로 저장했어요. 아래 지출 내역에서 확인해 주세요.'); onConfirmed?.(expenseIds) }} />
    </div>)}
  </Card>
}
