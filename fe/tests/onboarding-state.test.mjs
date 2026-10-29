// Run from fe/: node --test tests/onboarding-state.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/onboarding/model.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
})
const KEY = 'unyounghae_onboarding_preview_v2'
const VENUE = 'preview-venue'
const SUPPLIES = 'preview-supplies'
function model(storage = new Map()) {
  const exports = {}
  vm.runInNewContext(outputText, {
    exports,
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
  })
  return exports
}
const ids = (items) => Array.from(items, (item) => item.id)

test('first login starts fresh and save/reset affect only the dedicated v2 preview key', () => {
  const storage = new Map([
    ['unyounghae_access_token', 'existing-session'],
    ['other-preview', 'preserve'],
    ['unyounghae_onboarding_preview_v1', JSON.stringify({ saved: true, setupDone: true })],
  ])
  const { INITIAL_ONBOARDING, loadOnboarding, saveOnboarding, resetOnboarding } = model(storage)
  assert.equal(loadOnboarding().signedIn, false)
  assert.equal(loadOnboarding().clubSelected, false)
  assert.equal(loadOnboarding().savedItems.length, 0)
  assert.equal(loadOnboarding().meetingCreated, false)
  assert.equal(loadOnboarding().meetingTitle, '가을 행사 준비 회의')
  assert.deepEqual(ids(loadOnboarding().candidates), [VENUE, SUPPLIES])
  saveOnboarding({
    ...INITIAL_ONBOARDING,
    signedIn: true,
    clubSelected: true,
    setupDone: true,
    teamName: '테스트 운영팀',
    meetingCreated: true,
    meetingTitle: '홍보 준비 회의',
    accessToken: 'must-never-save-token',
    password: 'must-never-save-password',
  })
  assert.equal(storage.has(KEY), true)
  assert.equal(loadOnboarding().teamName, '테스트 운영팀')
  assert.equal(loadOnboarding().setupDone, true)
  assert.equal(loadOnboarding().signedIn, true)
  assert.equal(loadOnboarding().clubSelected, true)
  assert.equal(loadOnboarding().meetingCreated, true)
  assert.equal(loadOnboarding().meetingTitle, '홍보 준비 회의')
  assert.equal(storage.get(KEY).includes('must-never-save'), false)
  const reset = resetOnboarding()
  assert.equal(storage.has(KEY), false)
  assert.equal(storage.get('unyounghae_access_token'), 'existing-session')
  assert.equal(storage.get('other-preview'), 'preserve')
  assert.equal(JSON.parse(storage.get('unyounghae_onboarding_preview_v1')).saved, true)
  assert.equal(reset.signedIn, false)
  assert.equal(reset.clubSelected, false)
  assert.equal(reset.meetingCreated, false)
  assert.equal(reset.meetingTitle, '가을 행사 준비 회의')
  assert.equal(reset.setupDone, false)
  assert.equal(reset.savedItems.length, 0)
  assert.equal(reset.selectedCandidateId, VENUE)
  reset.candidates[0].title = '화면에서 수정'
  assert.equal(INITIAL_ONBOARDING.candidates[0].title, '행사장 예약 확인')
})

test('invalid JSON, schema values, and denied storage normalize safely', () => {
  const storage = new Map([[KEY, '{invalid']])
  const { loadOnboarding } = model(storage)
  assert.equal(loadOnboarding().role, 'MANAGER')
  storage.set(
    KEY,
    JSON.stringify({
      signedIn: 'true',
      clubSelected: 1,
      meetingCreated: 'yes',
      meetingTitle: 25,
      role: 'MEMBER',
      guideEnabled: 'false',
      savedItems: 1,
      recordsAdded: true,
      selectedCandidateId: 'unknown',
      teamName: '보존할 팀',
      candidates: [{ id: VENUE, title: 12, dueAt: null, recipient: '이서연' }, { id: 'unknown' }],
    }),
  )
  const state = loadOnboarding()
  assert.equal(state.signedIn, false)
  assert.equal(state.clubSelected, false)
  assert.equal(state.meetingCreated, false)
  assert.equal(state.meetingTitle, '가을 행사 준비 회의')
  assert.equal(state.role, 'MANAGER')
  assert.equal(state.guideEnabled, true)
  assert.equal(state.savedItems.length, 0)
  assert.equal(state.recordsAdded, true)
  assert.equal(state.teamName, '보존할 팀')
  assert.equal(state.selectedCandidateId, VENUE)
  assert.equal(state.candidates[0].title, '행사장 예약 확인')
  assert.equal(state.candidates[0].dueAt, '2026-10-23T16:00')
  assert.equal(state.candidates[0].recipient, '이서연')
  assert.deepEqual(ids(state.candidates), [VENUE, SUPPLIES])
  const denied = model({
    get() {
      throw new Error('denied')
    },
    set() {
      throw new Error('denied')
    },
    delete() {
      throw new Error('denied')
    },
  })
  assert.equal(denied.loadOnboarding().guideEnabled, true)
  assert.doesNotThrow(() => denied.saveOnboarding(denied.INITIAL_ONBOARDING))
  assert.doesNotThrow(() => denied.resetOnboarding())
})

test('mock re-login and guide-off resume completed steps and the reviewed candidates', () => {
  const {
    INITIAL_ONBOARDING,
    loadOnboarding,
    saveOnboarding,
    updatePreviewCandidate,
    savePreviewCandidate,
  } = model()
  const edited = updatePreviewCandidate(
    {
      ...INITIAL_ONBOARDING,
      signedIn: true,
      clubSelected: true,
      setupDone: true,
      recordsAdded: true,
      meetingCreated: true,
      meetingTitle: '홍보 준비 회의',
      meetingPlayed: true,
    },
    VENUE,
    { title: '안내문 확인', assignee: '이서연', recipient: '박지훈' },
  )
  const progressed = saveOnboarding(savePreviewCandidate(edited, VENUE))
  saveOnboarding({ ...progressed, signedIn: false, clubSelected: false })
  const signedOut = loadOnboarding()
  assert.equal(signedOut.signedIn, false)
  assert.equal(signedOut.savedItems.length, 1)
  saveOnboarding({ ...signedOut, signedIn: true, clubSelected: true, guideEnabled: false })
  const restored = loadOnboarding()
  assert.equal(restored.signedIn, true)
  assert.equal(restored.clubSelected, true)
  assert.equal(restored.guideEnabled, false)
  assert.equal(restored.meetingCreated, true)
  assert.equal(restored.meetingTitle, '홍보 준비 회의')
  assert.equal(restored.setupDone && restored.recordsAdded && restored.meetingPlayed, true)
  assert.equal(restored.candidates[0].title, '안내문 확인')
  assert.equal(restored.savedItems[0].assignee, '이서연')
  assert.equal(restored.savedItems[0].recipient, '박지훈')
})

test('selecting and editing one draft leaves the other draft and stored snapshots intact', () => {
  const { loadOnboarding, selectPreviewCandidate, updatePreviewCandidate, savePreviewCandidate } =
    model()
  const saved = savePreviewCandidate(loadOnboarding(), VENUE)
  const selected = selectPreviewCandidate(saved, SUPPLIES)
  const edited = updatePreviewCandidate(selected, SUPPLIES, {
    title: '현수막 준비',
    description: '출력 업체 확인',
  })
  assert.equal(edited.selectedCandidateId, SUPPLIES)
  assert.equal(edited.candidates[0].title, '행사장 예약 확인')
  assert.equal(edited.candidates[1].title, '현수막 준비')
  assert.equal(edited.savedItems[0].title, '행사장 예약 확인')
  const changedSavedDraft = updatePreviewCandidate(edited, VENUE, {
    title: '아직 확인하지 않은 수정',
  })
  assert.equal(changedSavedDraft.savedItems[0].title, '행사장 예약 확인')
  assert.equal(selectPreviewCandidate(edited, 'unknown'), edited)
  assert.equal(updatePreviewCandidate(edited, 'unknown', { title: '무시' }), edited)
})

test('saving both candidates accumulates and repeated save upserts only the matching id', () => {
  const { loadOnboarding, saveOnboarding, updatePreviewCandidate, savePreviewCandidate } = model()
  let state = savePreviewCandidate(loadOnboarding(), VENUE)
  state = savePreviewCandidate(state, SUPPLIES)
  assert.deepEqual(ids(state.savedItems), [VENUE, SUPPLIES])
  state = updatePreviewCandidate(state, VENUE, { title: '최종 예약 확인' })
  state = savePreviewCandidate(state, VENUE)
  state = savePreviewCandidate(state, VENUE)
  const restored = saveOnboarding(state)
  assert.deepEqual(ids(restored.savedItems), [VENUE, SUPPLIES])
  assert.equal(restored.savedItems[0].title, '최종 예약 확인')
  assert.equal(restored.savedItems[1].title, '행사 운영 물품 준비')
})

test('notes retain line breaks and optional blank values only after explicit re-save', () => {
  const { loadOnboarding, saveOnboarding, updatePreviewCandidate, savePreviewCandidate } = model()
  const note = '첫 줄 확인\n둘째 줄 담당\n\n마지막 줄'
  let state = updatePreviewCandidate(loadOnboarding(), VENUE, { description: note })
  state = saveOnboarding(savePreviewCandidate(state, VENUE))
  assert.equal(loadOnboarding().savedItems[0].description, note)
  state = updatePreviewCandidate(state, VENUE, { description: '' })
  state = saveOnboarding(state)
  assert.equal(loadOnboarding().candidates[0].description, '')
  assert.equal(loadOnboarding().savedItems[0].description, note)
  saveOnboarding(savePreviewCandidate(state, VENUE))
  assert.equal(loadOnboarding().savedItems[0].description, '')
})

test('legacy v2 single saved candidate migrates without losing progress or notes', () => {
  const description = '예약 담당 연락\n방문 전 확인'
  const storage = new Map([
    [
      KEY,
      JSON.stringify({
        signedIn: true,
        clubSelected: true,
        setupDone: true,
        recordsAdded: true,
        meetingCreated: true,
        meetingPlayed: true,
        guideEnabled: false,
        saved: true,
        meetingTitle: '기존 준비 회의',
        candidate: {
          title: '기존 예약',
          assignee: '이서연',
          dueAt: '2026-10-23T14:00',
          reminderAt: '2026-10-23T13:30',
          recipient: '박지훈',
          description,
        },
      }),
    ],
  ])
  const { loadOnboarding, saveOnboarding } = model(storage)
  const migrated = loadOnboarding()
  assert.equal(migrated.signedIn && migrated.clubSelected && migrated.meetingPlayed, true)
  assert.equal(migrated.guideEnabled, false)
  assert.equal(migrated.meetingTitle, '기존 준비 회의')
  assert.equal(migrated.candidates[0].title, '기존 예약')
  assert.equal(migrated.candidates[0].description, description)
  assert.equal(migrated.candidates[1].id, SUPPLIES)
  assert.equal(migrated.savedItems.length, 1)
  assert.equal(migrated.savedItems[0].id, VENUE)
  assert.equal(migrated.savedItems[0].description, description)
  saveOnboarding(migrated)
  assert.equal(loadOnboarding().savedItems[0].description, description)
  assert.equal('saved' in JSON.parse(storage.get(KEY)), false)
  assert.equal('candidate' in JSON.parse(storage.get(KEY)), false)
})
