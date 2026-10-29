// Run from fe/: node --test tests/onboarding-entry.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const compile = async (path) =>
  ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
const model = {}
const storage = new Map()
const localStorage = {
  getItem: (key) => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: (key) => storage.delete(key),
}
vm.runInNewContext(await compile('../src/features/onboarding/model.ts'), {
  exports: model,
  localStorage,
})
const entry = {}
vm.runInNewContext(await compile('../src/features/onboarding/entry.ts'), {
  exports: entry,
  require: () => model,
})

test('first visit opens guidance and verified session enters the service', () => {
  storage.clear()
  assert.equal(entry.onboardingEntry(false), '/onboarding')
  assert.equal(entry.onboardingEntry(true), '/dashboard')
})

test('dismissal or completing a preview prevents automatic replay; reset restores it', () => {
  storage.clear()
  model.saveOnboarding({ ...model.loadOnboarding(), guideEnabled: false })
  assert.equal(entry.onboardingEntry(false), '/login')
  model.resetOnboarding()
  const state = model.loadOnboarding()
  model.saveOnboarding(model.savePreviewCandidate(state, state.candidates[0].id))
  assert.equal(entry.onboardingEntry(false), '/login')
  model.resetOnboarding()
  assert.equal(entry.onboardingEntry(false), '/onboarding')
})

test('an unfinished preview continues and unrelated session keys remain untouched', () => {
  storage.clear()
  storage.set('unyounghae_access_token', 'original')
  model.saveOnboarding({ ...model.loadOnboarding(), signedIn: true, recordsAdded: true })
  assert.equal(entry.onboardingEntry(false), '/onboarding')
  assert.equal(storage.get('unyounghae_access_token'), 'original')
})
