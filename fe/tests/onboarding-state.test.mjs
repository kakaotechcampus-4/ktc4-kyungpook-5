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

test('first login starts fresh and save/reset affect only the dedicated v2 preview key', () => {
  const storage = new Map([
    ['unyounghae_access_token', 'existing-session'],
    ['other-preview', 'preserve'],
    ['unyounghae_onboarding_preview_v1', JSON.stringify({ saved: true, setupDone: true })],
  ])
  const { INITIAL_ONBOARDING, loadOnboarding, saveOnboarding, resetOnboarding } = model(storage)
  assert.equal(loadOnboarding().signedIn, false)
  assert.equal(loadOnboarding().clubSelected, false)
  assert.equal(loadOnboarding().saved, false)
  assert.equal(loadOnboarding().meetingCreated, false)
  assert.equal(loadOnboarding().meetingTitle, '가을 행사 준비 회의')
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
  reset.candidate.title = '화면에서 수정'
  assert.equal(INITIAL_ONBOARDING.candidate.title, '행사장 예약 확인')
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
      saved: 1,
      recordsAdded: true,
      teamName: '보존할 팀',
      candidate: { title: 12, dueAt: null, recipient: '이서연' },
    }),
  )
  const state = loadOnboarding()
  assert.equal(state.signedIn, false)
  assert.equal(state.clubSelected, false)
  assert.equal(state.meetingCreated, false)
  assert.equal(state.meetingTitle, '가을 행사 준비 회의')
  assert.equal(state.role, 'MANAGER')
  assert.equal(state.guideEnabled, true)
  assert.equal(state.saved, false)
  assert.equal(state.recordsAdded, true)
  assert.equal(state.teamName, '보존할 팀')
  assert.equal(state.candidate.title, '행사장 예약 확인')
  assert.equal(state.candidate.dueAt, '2026-10-23T16:00')
  assert.equal(state.candidate.recipient, '이서연')
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

test('mock re-login and guide-off resume completed steps and the reviewed candidate', () => {
  const { INITIAL_ONBOARDING, loadOnboarding, saveOnboarding } = model()
  const progressed = saveOnboarding({
    ...INITIAL_ONBOARDING,
    signedIn: true,
    clubSelected: true,
    setupDone: true,
    recordsAdded: true,
    meetingCreated: true,
    meetingTitle: '홍보 준비 회의',
    meetingPlayed: true,
    saved: true,
    candidate: {
      ...INITIAL_ONBOARDING.candidate,
      title: '안내문 확인',
      assignee: '이서연',
      recipient: '박지훈',
    },
  })
  saveOnboarding({ ...progressed, signedIn: false, clubSelected: false })
  const signedOut = loadOnboarding()
  assert.equal(signedOut.signedIn, false)
  assert.equal(signedOut.saved, true)
  saveOnboarding({ ...signedOut, signedIn: true, clubSelected: true, guideEnabled: false })
  const restored = loadOnboarding()
  assert.equal(restored.signedIn, true)
  assert.equal(restored.clubSelected, true)
  assert.equal(restored.guideEnabled, false)
  assert.equal(restored.meetingCreated, true)
  assert.equal(restored.meetingTitle, '홍보 준비 회의')
  assert.equal(
    restored.setupDone && restored.recordsAdded && restored.meetingPlayed && restored.saved,
    true,
  )
  assert.equal(restored.candidate.title, '안내문 확인')
  assert.equal(restored.candidate.assignee, '이서연')
  assert.equal(restored.candidate.recipient, '박지훈')
})
