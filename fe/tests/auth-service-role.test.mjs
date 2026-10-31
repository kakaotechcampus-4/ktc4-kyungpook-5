// Run from fe/: node --test tests/auth-service-role.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const compile = async (path) =>
  ts.transpileModule(await readFile(new URL(path, import.meta.url), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText
const typeSource = await compile('../src/shared/auth/types.ts')
const storeSource = await compile('../src/shared/auth/store.ts')
const roleExports = {}
vm.runInNewContext(typeSource, { exports: roleExports })
const CLUB_KEY = 'unyounghae_selected_club_id'

function session(savedClubId) {
  const storage = new Map(savedClubId ? [[CLUB_KEY, savedClubId]] : [])
  const localStorage = {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  }
  const exports = {}
  vm.runInNewContext(storeSource, {
    exports,
    localStorage,
    require: (name) => {
      if (name === 'zustand') return require('zustand')
      if (name === '@/shared/auth/types') return roleExports
      if (name === '@/shared/api/client')
        return { getAccessToken: () => 'session', setAccessToken() {} }
      throw new Error(`Unexpected module: ${name}`)
    },
  })
  return { store: exports.useAuthStore, storage }
}

const me = {
  id: 'account',
  email: 'person@example.com',
  emailVerified: true,
  clubs: [
    { id: 'owned', name: '대표 소속', role: 'OWNER' },
    { id: 'managed', name: '임원 소속', role: 'MANAGER' },
    { id: 'roster-only', name: '내부 명단', role: 'MEMBER' },
  ],
}

test('legacy MEMBER selection is removed while the original /me response stays intact', () => {
  const { store, storage } = session('roster-only')
  store.getState().setMe(me)
  assert.deepEqual(
    Array.from(store.getState().me.clubs, (club) => club.id),
    ['owned', 'managed'],
  )
  assert.equal(store.getState().clubId, null)
  assert.equal(store.getState().user, null)
  assert.equal(storage.has(CLUB_KEY), false)
  assert.equal(me.clubs.length, 3)
})

test('service selection restores and manual or Push-hint MEMBER selection cannot replace it', () => {
  const { store, storage } = session('managed')
  store.getState().setMe(me)
  assert.equal(store.getState().clubId, 'managed')
  assert.equal(store.getState().user.role, 'MANAGER')
  store.getState().selectClub('owned')
  store.getState().selectClub('roster-only')
  assert.equal(store.getState().clubId, 'owned')
  assert.equal(store.getState().user.role, 'OWNER')
  assert.equal(storage.get(CLUB_KEY), 'owned')
})

test('a MEMBER-only account has no service selection and cannot populate legacy service user state', () => {
  const { store } = session('roster-only')
  store.getState().setMe({ ...me, clubs: [me.clubs[2]] })
  store.getState().selectClub('roster-only')
  store.getState().setUser({
    id: me.id,
    clubId: 'roster-only',
    name: '내부 명단',
    email: me.email,
    role: 'MEMBER',
  })
  assert.equal(store.getState().me.clubs.length, 0)
  assert.equal(store.getState().clubId, null)
  assert.equal(store.getState().user, null)
})
