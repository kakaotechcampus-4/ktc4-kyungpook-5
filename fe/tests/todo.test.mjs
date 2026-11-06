import assert from 'node:assert/strict'
import { build } from 'esbuild'
import test from 'node:test'

const { outputFiles } = await build({
  entryPoints: [new URL('../src/features/events/todo.ts', import.meta.url).pathname],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
  alias: { '@': new URL('../src', import.meta.url).pathname },
})
const { currentMark, draftSentences, stepAdvance, todoKind, todoList, toriSummary } = await import(
  `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`
)

const action = (extra = {}) => ({
  id: 'act_1',
  type: 'NOTICE',
  title: '모집 공지 올리기',
  subtitle: null,
  dueDate: null,
  status: 'PENDING',
  stepId: 'stp_2',
  approveNeeded: true,
  ...extra,
})
const steps = [
  { id: 'stp_1', stepOrder: 10, name: '일정 확정', state: 'DONE' },
  { id: 'stp_2', stepOrder: 20, name: '모집 공지', state: 'CURRENT' },
  { id: 'stp_3', stepOrder: 30, name: '사전 안내', state: 'TODO' },
]

test('운영진 차례인 상태만 할 일이 된다', () => {
  assert.equal(todoKind(action({ contentStatus: 'DRAFTING' })), 'drafting')
  assert.equal(todoKind(action({ contentStatus: 'FAILED' })), 'draftFailed')
  assert.equal(todoKind(action({ contentStatus: 'READY', contentSource: 'AI', content: '글' })), 'review')
  assert.equal(todoKind(action({ type: 'TRANSFER', approveNeeded: false })), 'manual')
  assert.equal(todoKind(action({ status: 'APPROVED' })), 'execute')
  assert.equal(todoKind(action({ status: 'FAILED' })), 'failed')
  assert.equal(todoKind(action({ type: 'CONFIRMATION', stepId: null })), 'question')
  assert.equal(todoKind(action({ status: 'DONE' })), null)
  assert.equal(todoKind(action({ status: 'DENIED' })), null)
  assert.equal(todoKind(action({ type: 'CONFIRMATION', status: 'DONE' })), null)
})

test('시작 전 단계의 일은 빼고, 토리가 쓰는 중 → 검토 → 실행 순, 같은 묶음은 기한 순이다', () => {
  const list = todoList(
    [
      action({ id: 'exec', status: 'APPROVED' }),
      action({ id: 'later', dueDate: '2026-11-20' }),
      action({ id: 'sooner', dueDate: '2026-11-08', stepId: 'stp_1' }),
      action({ id: 'nodue' }),
      action({ id: 'future', stepId: 'stp_3' }),
      action({ id: 'writing', contentStatus: 'DRAFTING' }),
      action({ id: 'ask', type: 'CONFIRMATION', stepId: null }),
    ],
    steps,
  )
  assert.deepEqual(
    list.map((i) => i.action.id),
    ['writing', 'ask', 'sooner', 'later', 'nodue', 'exec'],
  )
  assert.equal(list.find((i) => i.action.id === 'sooner').position, 1)
  assert.equal(list.find((i) => i.action.id === 'ask').step, undefined)
})

test('토리 한 줄은 쓰는 중을 먼저 알리고, 승인하거나 고친 초안은 세지 않는다', () => {
  const ready = action({ id: 'r', contentStatus: 'READY', contentSource: 'AI', content: '[장소]에서 만나요', contentUnknowns: ['장소'] })
  const edited = action({ id: 'u', contentStatus: 'READY', contentSource: 'USER', content: '고친 글' })
  const approved = action({ id: 'a', status: 'APPROVED', contentStatus: 'READY', contentSource: 'AI', content: '글' })
  assert.deepEqual(toriSummary(todoList([ready, edited, approved], steps)), {
    drafting: 0,
    ready: 1,
    blanks: 1,
    stepName: '모집 공지',
  })
  const writing = action({ id: 'w', contentStatus: 'DRAFTING', stepId: 'stp_1' })
  assert.deepEqual(toriSummary(todoList([ready, writing], steps)), {
    drafting: 1,
    ready: 1,
    blanks: 1,
    stepName: '일정 확정',
  })
  assert.equal(toriSummary(todoList([edited, approved], steps)), null)
})

test('현재 단계 카드에는 토리가 쓰는 중이거나 써 둔 초안만 덧붙인다', () => {
  assert.deepEqual(
    draftSentences([
      action({ title: '모집 공지', contentStatus: 'READY', contentSource: 'AI', content: '글' }),
      action({ title: '안내 문자', type: 'EXTERNAL_SEND', contentStatus: 'DRAFTING' }),
      action({ title: '고친 공지', contentStatus: 'READY', contentSource: 'USER', content: '글' }),
      action({ title: '이체', type: 'TRANSFER' }),
    ]),
    ['「모집 공지」 초안을 써 뒀어요.', '「안내 문자」 초안을 쓰고 있어요.'],
  )
})

test('현재 단계가 완료로 바뀌면 끝난 단계와 다음 단계를 알려 준다', () => {
  const before = [
    { id: 'a', name: '담당 배치', state: 'CURRENT' },
    { id: 'b', name: '모집 공지', state: 'TODO' },
  ]
  const after = [
    { id: 'a', name: '담당 배치', state: 'DONE' },
    { id: 'b', name: '모집 공지', state: 'CURRENT' },
  ]
  const allDone = after.map((s) => ({ ...s, state: 'DONE' }))
  const mark = currentMark('evt', before)
  assert.deepEqual(stepAdvance(mark, 'evt', after), {
    done: { id: 'a', position: 1, name: '담당 배치' },
    next: { id: 'b', position: 2, name: '모집 공지' },
  })
  // 마지막 단계가 끝나면 다음 단계가 없다
  assert.deepEqual(stepAdvance(currentMark('evt', after), 'evt', allDone), {
    done: { id: 'b', position: 2, name: '모집 공지' },
    next: undefined,
  })
})

test('처음 열었을 때·다른 행사·그대로일 때는 알리지 않는다', () => {
  const steps = [{ id: 'a', name: '담당 배치', state: 'CURRENT' }]
  assert.equal(stepAdvance(null, 'evt', steps), null)
  assert.equal(stepAdvance(currentMark('other', steps), 'evt', steps), null)
  assert.equal(stepAdvance(currentMark('evt', steps), 'evt', steps), null)
  // 직전 현재 단계가 완료가 아닌데 사라진 경우(목록이 바뀜)도 넘어간 것으로 보지 않는다
  assert.equal(stepAdvance({ eventId: 'evt', stepId: 'gone' }, 'evt', steps), null)
})
