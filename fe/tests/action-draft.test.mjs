import assert from 'node:assert/strict'
import { build } from 'esbuild'
import test from 'node:test'

const { outputFiles } = await build({
  entryPoints: [new URL('../src/features/events/actionDraft.ts', import.meta.url).pathname],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
})
const {
  DRAFT_POLL_MS,
  blanksIn,
  blanksLine,
  canSave,
  draftPollInterval,
  draftView,
  editorText,
  isDirty,
  outcomeOf,
  redraftNotice,
  splitBlanks,
  startEdit,
} = await import(`data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`)

const action = (extra = {}) => ({
  id: 'act_1',
  type: 'NOTICE',
  title: '모집 공지 올리기',
  subtitle: null,
  dueDate: null,
  status: 'PENDING',
  version: 4,
  content: null,
  contentStatus: 'NONE',
  contentSource: null,
  contentUnknowns: [],
  canRequestDraft: false,
  ...extra,
})

test('card shows each draft state from the contract table', () => {
  assert.equal(draftView(action({ contentStatus: 'DRAFTING' }), 'CURRENT'), 'DRAFTING')
  assert.equal(
    draftView(action({ contentStatus: 'READY', contentSource: 'AI', content: '📢 봄 MT' }), 'CURRENT'),
    'READY_AI',
  )
  assert.equal(
    draftView(action({ contentStatus: 'READY', contentSource: 'USER', content: '📢 봄 MT' }), 'CURRENT'),
    'READY_USER',
  )
  assert.equal(draftView(action({ contentStatus: 'FAILED', canRequestDraft: true }), 'CURRENT'), 'FAILED')
  assert.equal(draftView(action(), 'CURRENT'), 'NONE')
})

test('a notice in a step that has not started says the draft comes later', () => {
  assert.equal(draftView(action(), 'TODO'), 'UPCOMING')
  assert.equal(draftView(action({ type: 'EXTERNAL_SEND' }), 'TODO'), 'UPCOMING')
  // 미리 승인했으면 초안이 오지 않으니 안내하지 않는다
  assert.equal(draftView(action({ status: 'APPROVED' }), 'TODO'), 'NONE')
  // 끝난 단계는 "시작되면"이 맞지 않는다
  assert.equal(draftView(action(), 'DONE'), 'NONE')
})

test('only notice and external send take drafts; older responses stay as before', () => {
  assert.equal(draftView(action({ type: 'TRANSFER', contentStatus: 'DRAFTING' }), 'CURRENT'), 'NONE')
  assert.equal(draftView(action({ type: 'CONFIRMATION' }), 'TODO'), 'NONE')
  const legacy = action({ content: '안내 문구' })
  delete legacy.contentStatus
  delete legacy.contentSource
  assert.equal(draftView(legacy, 'CURRENT'), 'NONE')
})

test('refetch runs only while some action is being drafted', () => {
  assert.equal(draftPollInterval(undefined), false)
  assert.equal(draftPollInterval([]), false)
  assert.equal(draftPollInterval([action(), action({ contentStatus: 'READY' })]), false)
  assert.equal(draftPollInterval([action(), action({ id: 'act_2', contentStatus: 'DRAFTING' })]), DRAFT_POLL_MS)
  assert.equal(DRAFT_POLL_MS, 3000)
})

test('blanks match the bracketed text of the body', () => {
  const body = '📢 봄 MT 참가자 모집\n신청 방법: [신청 링크]\n장소: [장소 미정] / 다시 [신청 링크]'
  assert.deepEqual(blanksIn(body), ['신청 링크', '장소 미정'])
  assert.deepEqual(blanksIn('신청: https://forms.gle/abc'), [])
  assert.equal(blanksLine(['신청 링크']), '비워 둔 곳: 신청 링크')
  assert.equal(blanksLine([]), undefined)
  assert.deepEqual(splitBlanks('신청: [신청 링크]까지'), [
    { text: '신청: ', blank: false },
    { text: '[신청 링크]', blank: true },
    { text: '까지', blank: false },
  ])
})

test('typed text survives a refetch that brings a new draft', () => {
  const drafting = action({ contentStatus: 'DRAFTING', version: 3 })
  const edit = startEdit(drafting, null, '제가 직접 씁니다')
  assert.equal(edit.baseVersion, 3)
  // 그사이 토리 초안이 도착해 목록이 version 4로 바뀜
  const arrived = action({ contentStatus: 'READY', contentSource: 'AI', content: '📢 토리 초안', version: 4 })
  assert.equal(editorText(arrived, edit), '제가 직접 씁니다')
  assert.equal(isDirty(arrived, edit), true)
  // 계속 입력해도 고치기 시작한 version을 지켜 저장이 409로 막힌다
  assert.equal(startEdit(arrived, edit, '제가 직접 씁니다!').baseVersion, 3)
  // [토리 초안 보기]는 고친 글을 버리고 도착한 초안을 보인다
  assert.equal(editorText(arrived, null), '📢 토리 초안')
})

test('save needs a real change that is not blank', () => {
  const ready = action({ contentStatus: 'READY', contentSource: 'AI', content: '본문' })
  assert.equal(canSave(ready, null), false)
  assert.equal(canSave(ready, startEdit(ready, null, '본문')), false)
  assert.equal(canSave(ready, startEdit(ready, null, '   ')), false)
  assert.equal(canSave(ready, startEdit(ready, null, '고친 본문')), true)
  // 다른 Action의 고친 글은 섞이지 않는다
  const other = action({ id: 'act_2', content: '다른 본문' })
  assert.equal(editorText(other, startEdit(ready, null, '고친 본문')), '다른 본문')
})

test('409 responses are read by their code', () => {
  assert.equal(outcomeOf({ code: 'VERSION_CONFLICT', message: '' }), 'conflict')
  assert.equal(outcomeOf({ code: 'VALIDATION_ERROR', message: '' }), 'failed')
  assert.equal(outcomeOf(new Error('network')), 'failed')
  assert.equal(redraftNotice({ code: 'VERSION_CONFLICT' })?.title, '다른 변경이 있어요')
  assert.equal(redraftNotice({ code: 'DRAFT_NOT_ALLOWED' })?.title, '다른 변경이 있어요')
  assert.equal(redraftNotice({ code: 'ACTION_NOT_FOUND' }), undefined)
})
