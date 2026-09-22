// useRecords... 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
//
// BE에 /records가 아직 하나도 없어서 M1·L2와 같이 목업으로만 움직인다. 서버 호출은
// api.ts에 명세대로 준비해 뒀고, 엔드포인트가 생기는 것부터 아래 함수 안을
// 그 호출 + 재조회로 갈아끼우면 된다.
import { useState } from 'react'
import * as recordsApi from '@/features/records/api'
import { fileTypeOf, rejectUploadReason } from '@/features/records/labels'
import type {
  ChatTurn,
  RecordCategory,
  RecordDetail,
  RecordListItem,
  RecordListMeta,
} from '@/features/records/types'

interface RecordsState extends recordsApi.RecordListResult {
  // 파싱이 멈춘 파일의 parseError. 목록 응답에는 없고 단건(GET /records/{id})에만 있다.
  details: Record<string, RecordDetail>
}

function mockState(): RecordsState {
  return { ...recordsApi.getRecordsMock(), details: recordsApi.getRecordDetailsMock() }
}

// 카드 머리의 건수는 서버가 세어 주는 값이라 화면에 그린 줄 수와 따로 움직인다.
function shiftCounts(
  meta: RecordListMeta,
  changes: Array<[RecordCategory, number]>,
  totalDelta: number,
): RecordListMeta {
  const categoryCounts = { ...meta.categoryCounts }
  for (const [category, delta] of changes) {
    categoryCounts[category] = Math.max(0, (categoryCounts[category] ?? 0) + delta)
  }
  return { ...meta, categoryCounts, totalCount: Math.max(0, meta.totalCount + totalDelta) }
}

export function useRecords() {
  const [state, setState] = useState<RecordsState>(mockState)
  const [error, setError] = useState<string | null>(null)

  // TODO: POST /records. 카테고리를 안 주면 AI가 분류하고 ETC로 기본 처리한다.
  function upload(file: File, category: RecordCategory = 'ETC') {
    const rejected = rejectUploadReason(file.name)
    if (rejected) {
      setError(rejected)
      return
    }
    setError(null)

    const added: RecordListItem = {
      id: `rec_new_${Date.now()}`,
      fileName: file.name,
      // rejectUploadReason을 통과했으니 형식이 반드시 나온다.
      fileType: fileTypeOf(file.name) ?? 'PDF',
      category,
      size: file.size,
      parseStatus: 'PARSING',
      createdAt: new Date().toISOString(),
    }
    setState((prev) => ({
      ...prev,
      records: [added, ...prev.records],
      meta: shiftCounts(prev.meta, [[category, 1]], 1),
    }))
  }

  // TODO: PATCH /records/{id}
  function changeCategory(recordId: string, category: RecordCategory) {
    setState((prev) => {
      const target = prev.records.find((record) => record.id === recordId)
      if (!target || target.category === category) return prev
      return {
        ...prev,
        // 분류가 바뀌면 파서가 달라져 parseStatus가 PARSING으로 돌아간다(명세).
        records: prev.records.map((record) =>
          record.id === recordId ? { ...record, category, parseStatus: 'PARSING' } : record,
        ),
        meta: shiftCounts(
          prev.meta,
          [
            [target.category, -1],
            [category, 1],
          ],
          0,
        ),
      }
    })
  }

  // TODO: DELETE /records/{id}
  function remove(recordId: string) {
    setState((prev) => {
      const target = prev.records.find((record) => record.id === recordId)
      if (!target) return prev
      return {
        ...prev,
        records: prev.records.filter((record) => record.id !== recordId),
        meta: shiftCounts(prev.meta, [[target.category, -1]], -1),
      }
    })
  }

  // TODO: POST /records/{id}/column-mapping
  function submitColumnMapping(recordId: string, mapping: Record<string, string>) {
    console.info('[records] 열 연결 저장', recordId, mapping)
    // 매핑을 저장하면 재파싱이 돌아 parseStatus가 PARSING으로 간다(명세).
    setState((prev) => ({
      ...prev,
      records: prev.records.map((record) =>
        record.id === recordId ? { ...record, parseStatus: 'PARSING' } : record,
      ),
    }))
  }

  // TODO: GET /records/template — text/csv 스트림을 받아 내려준다.
  function downloadTemplate() {
    console.info('[records] 장부 양식 내려받기')
  }

  return { ...state, error, upload, changeCategory, remove, submitColumnMapping, downloadTemplate }
}

// R1 하단 챗봇 바 + R1-b 패널. 세션을 저장하지 않으므로 상태는 이 훅 안에서만 산다.
export function useRecordsChat() {
  const [open, setOpen] = useState(false)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [suggestions, setSuggestions] = useState<string[]>([])
  const [pending, setPending] = useState(false)

  // TODO: POST /records/chat. 세션이 없어 이전 대화 전체 + 이번 질문을 매번 보낸다.
  function ask(question: string) {
    const content = question.trim()
    if (!content || pending) return

    setOpen(true)
    setTurns((prev) => [...prev, { role: 'USER', content }])
    setSuggestions([])
    setPending(true)

    // 답을 기다리는 상태도 화면에 있어야 해서 한 박자 뒤에 목업을 붙인다.
    window.setTimeout(() => {
      const answer = recordsApi.getChatAnswerMock()
      setTurns((prev) => [
        ...prev,
        {
          role: 'ASSISTANT',
          content: answer.content,
          sources: answer.sources,
          notFound: answer.notFound,
        },
      ])
      setSuggestions(answer.suggestions)
      setPending(false)
    }, 400)
  }

  return { open, turns, suggestions, pending, ask, close: () => setOpen(false) }
}
