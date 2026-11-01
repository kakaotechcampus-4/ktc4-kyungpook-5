import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = (
  await readFile(new URL('../src/features/auth/kakao.ts', import.meta.url), 'utf8')
).replace('import.meta.env.VITE_KAKAO_REST_API_KEY', "'client-key'")
const destinationSource = await readFile(
  new URL('../src/features/auth/destination.ts', import.meta.url),
  'utf8',
)
const destinationCode = ts.transpileModule(destinationSource, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
function setup() {
  const values = new Map()
  let destination = ''
  const crypto = { getRandomValues: (data) => data.fill(7) }
  const context = {
    exports: {},
    URL,
    URLSearchParams,
    Uint8Array,
    crypto,
    sessionStorage: {
      setItem: (k, v) => values.set(k, v),
      getItem: (k) => values.get(k) ?? null,
      removeItem: (k) => values.delete(k),
    },
    window: {
      crypto,
      location: {
        origin: 'https://example.test',
        assign: (v) => {
          destination = v
        },
      },
    },
  }
  const destinationExports = {}
  vm.runInNewContext(destinationCode, { exports: destinationExports, URL, window: context.window })
  context.require = (name) => {
    if (name === './destination') return destinationExports
    throw new Error(name)
  }
  vm.runInNewContext(code, context)
  return { auth: context.exports, values, destination: () => destination }
}
test('authorization contains fresh state and matching same-origin callback', () => {
  const { auth, destination } = setup()
  auth.beginKakaoLogin()
  const url = new URL(destination())
  assert.equal(url.origin, 'https://kauth.kakao.com')
  assert.equal(url.searchParams.get('redirect_uri'), 'https://example.test/auth/kakao/callback')
  assert.equal(url.searchParams.get('state').length, 64)
  const callback = auth.consumeKakaoCallback(`?state=${url.searchParams.get('state')}&code=ok`)
  assert.equal(callback.code, 'ok')
  assert.equal(callback.next, '/dashboard')
  assert.throws(() => auth.consumeKakaoCallback(`?state=${url.searchParams.get('state')}&code=ok`))
})
test('mismatched state or denied consent never accepts a code', () => {
  const { auth, values } = setup()
  auth.beginKakaoLogin()
  assert.throws(() => auth.consumeKakaoCallback('?state=wrong&code=ok'))
  assert.equal(values.size, 0)
  auth.beginKakaoLogin()
  const state = values.get('unyounghae_kakao_oauth_state')
  assert.throws(() => auth.consumeKakaoCallback(`?state=${state}&error=access_denied`))
})

test('Kakao preserves safe next only after valid state and clears it after a rejected callback', () => {
  const { auth, values } = setup()
  auth.beginKakaoLogin('/meetings/example?clubId=club#item')
  const state = values.get('unyounghae_kakao_oauth_state')
  assert.equal(
    auth.consumeKakaoCallback(`?state=${state}&code=ok`).next,
    '/meetings/example?clubId=club#item',
  )
  auth.beginKakaoLogin('https://evil.example/path')
  assert.throws(() => auth.consumeKakaoCallback('?state=bad&code=ok'))
  assert.equal(values.size, 0)
})
