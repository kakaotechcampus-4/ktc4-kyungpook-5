import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const require = createRequire(import.meta.url)
const axios = require('axios')
const compile = async (path) => ts.transpileModule(
  (await readFile(new URL(path, import.meta.url), 'utf8'))
    .replace('import.meta.env.VITE_API_BASE_URL', "''"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } },
).outputText
const files = {
  tokens: '../src/shared/auth/tokens.ts',
  roles: '../src/shared/auth/types.ts',
  store: '../src/shared/auth/store.ts',
  types: '../src/shared/api/types.ts',
  sse: '../src/shared/api/sse.ts',
  client: '../src/shared/api/client.ts',
  api: '../src/features/auth/api.ts',
  hooks: '../src/features/auth/hooks.ts',
}
const sources = Object.fromEntries(await Promise.all(
  Object.entries(files).map(async ([name, path]) => [name, await compile(path)]),
))
const accessKey = 'unyounghae_access_token'
const refreshKey = 'unyounghae_refresh_token'
const clubKey = 'unyounghae_selected_club_id'
const oldTokens = { accessToken: 'access-old', refreshToken: 'refresh-old' }
const newTokens = { accessToken: 'access-new', refreshToken: 'refresh-new' }
const me = { id: 'account', email: 'demo@example.com', clubs: [{ id: 'club', role: 'OWNER' }] }
const defer = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const ok = (config, data, status = 200) => ({ config, data: { data, meta: null }, status, headers: {} })
const denied = (config, status = 401) => new axios.AxiosError('rejected', 'ERR_BAD_REQUEST', config, {}, {
  config, status, headers: {}, data: { error: { code: 'UNAUTHORIZED', message: 'expired' } },
})
const dataOf = (config) => typeof config.data === 'string' ? JSON.parse(config.data) : config.data

function setup({ request, refresh, fetch: fetcher } = {}) {
  const storage = new Map()
  const calls = []
  const refreshes = []
  const context = {
    localStorage: {
      getItem: (key) => storage.get(key) ?? null,
      setItem: (key, value) => storage.set(key, value),
      removeItem: (key) => storage.delete(key),
    },
    TextDecoder, URL, Blob,
    fetch: fetcher,
  }
  const modules = {}
  const run = (name, dependencies = {}) => {
    const exports = {}
    vm.runInNewContext(sources[name], {
      ...context, exports,
      require: (path) => {
        if (path in dependencies) return dependencies[path]
        throw new Error(`Unexpected module: ${path}`)
      },
    })
    modules[name] = exports
    return exports
  }
  run('tokens')
  run('roles')
  const store = run('store', {
    zustand: require('zustand'), '@/shared/auth/tokens': modules.tokens,
    '@/shared/auth/types': modules.roles,
  }).useAuthStore
  run('types')
  run('sse')
  const scopedAxios = {
    isAxiosError: axios.isAxiosError,
    create: (config) => axios.create({ ...config, adapter: async (req) => {
      calls.push(req)
      return request(req)
    } }),
    post: async (url, body) => {
      refreshes.push({ url, body })
      return refresh ? refresh(url, body) : { data: { data: newTokens } }
    },
  }
  const client = run('client', {
    axios: { default: scopedAxios }, '@/shared/api/types': modules.types,
    '@/shared/api/sse': modules.sse, '@/shared/auth/store': modules.store,
    '@/shared/auth/tokens': modules.tokens,
  })
  run('api', { '@/shared/api/client': client })
  const queryClient = { clear() {}, fetchQuery: ({ queryFn }) => queryFn() }
  const hookState = []
  let hookIndex = 0
  const react = {
    useRef: (initial) => { const index = hookIndex++; return hookState[index] ??= { current: initial } },
    useState: (initial) => {
      const index = hookIndex++
      if (!(index in hookState)) hookState[index] = initial
      return [hookState[index], (value) => { hookState[index] = value }]
    },
    useEffect: (effect) => effect(),
  }
  const useStore = Object.assign((selector) => selector(store.getState()), { getState: store.getState })
  const hooks = run('hooks', {
    react, '@tanstack/react-query': {
      useQuery: (options) => options, useMutation: (options) => options,
      useQueryClient: () => queryClient,
    },
    'react-router-dom': {}, '@/features/auth/api': modules.api,
    '@/shared/api/types': modules.types,
    '@/shared/auth/store': { ...modules.store, useAuthStore: useStore },
    './destination': {},
  })
  store.getState().setSession(oldTokens)
  store.getState().setMe(me)
  store.getState().selectClub('club')
  return {
    client, store, storage, calls, refreshes, hooks, tokens: modules.tokens,
    notificationClub: (clubId) => { hookIndex = 0; return hooks.useNotificationClub(clubId) },
  }
}

test('concurrent 401 reads, mutation and blob share one rotation and retain the selected club', async () => {
  const gate = defer()
  const env = setup({
    refresh: () => gate.promise,
    request: async (config) => {
      if (config.headers.Authorization === 'Bearer access-old') throw denied(config)
      return config.responseType === 'blob'
        ? { ...ok(config), data: new Blob(['document']) }
        : ok(config, { title: 'saved' })
    },
  })
  const pending = Promise.all([
    env.client.apiGet('/me'), env.client.apiPost('/tasks', { title: 'once' }),
    env.client.apiGetBlob('/records/original'),
  ])
  await new Promise(setImmediate)
  assert.equal(env.refreshes.length, 1)
  assert.equal(env.refreshes[0].url, '/api/v1/auth/refresh')
  assert.equal(env.refreshes[0].body.refreshToken, 'refresh-old')
  gate.resolve({ data: { data: newTokens } })
  const results = await pending
  assert.equal(await results[2].text(), 'document')
  assert.equal(env.calls.length, 6)
  assert.equal(env.storage.get(accessKey), 'access-new')
  assert.equal(env.storage.get(refreshKey), 'refresh-new')
  assert.equal(env.store.getState().clubId, 'club')
  assert.equal(env.store.getState().user.id, me.id)
  assert.equal(env.storage.get(clubKey), 'club')
  const writes = env.calls.filter((call) => call.url === '/tasks')
  assert.deepEqual(writes.map(dataOf), [{ title: 'once' }, { title: 'once' }])
  assert.equal(writes[1].headers.Authorization, 'Bearer access-new')
})

test('a late old-token 401 uses the already rotated token instead of rotating twice', async () => {
  const late = defer()
  const env = setup({ request: async (config) => {
    if (config.url === '/slow' && config.headers.Authorization === 'Bearer access-old') {
      await late.promise
      throw denied(config)
    }
    if (config.headers.Authorization === 'Bearer access-old') throw denied(config)
    return ok(config, 'done')
  } })
  const slow = env.client.apiGet('/slow')
  await env.client.apiGet('/fast')
  late.resolve()
  assert.equal(await slow, 'done')
  assert.equal(env.refreshes.length, 1)
})

test('login failures, forbidden responses and uncertain mutation failures never trigger replay', async () => {
  const env = setup({ request: async (config) => {
    if (config.url === '/auth/login') throw denied(config)
    if (config.url === '/forbidden') throw denied(config, 403)
    throw new axios.AxiosError('connection lost', 'ERR_NETWORK', config)
  } })
  await assert.rejects(env.client.apiPost('/auth/login', { email: 'bad' }))
  await assert.rejects(env.client.apiGet('/forbidden'))
  await assert.rejects(env.client.apiPost('/tasks', { title: 'uncertain' }))
  assert.equal(env.refreshes.length, 0)
  assert.equal(env.calls.length, 3)
  assert.equal(env.store.getState().clubId, 'club')
})

test('invalid refresh or a second 401 ends the session without a retry loop', async () => {
  for (const refreshFails of [true, false]) {
    const env = setup({
      request: async (config) => { throw denied(config) },
      refresh: async () => {
        if (refreshFails) throw denied({ url: '/auth/refresh' })
        return { data: { data: newTokens } }
      },
    })
    await assert.rejects(env.client.apiGet('/me'))
    assert.equal(env.refreshes.length, 1)
    assert.equal(env.calls.length, refreshFails ? 1 : 2)
    assert.equal(env.storage.has(accessKey), false)
    assert.equal(env.storage.has(refreshKey), false)
    assert.equal(env.store.getState().clubId, null)
  }
})

test('a missing refresh token ends an expired session without calling refresh', async () => {
  const env = setup({ request: async (config) => { throw denied(config) } })
  env.storage.delete(refreshKey)
  await assert.rejects(env.client.apiGet('/me'))
  assert.equal(env.refreshes.length, 0)
  assert.equal(env.store.getState().token, null)
})

test('transient refresh failure retains the session so a later request can recover', async () => {
  let attempts = 0
  const env = setup({
    request: async (config) => {
      if (config.headers.Authorization === 'Bearer access-old') throw denied(config)
      return ok(config, 'recovered')
    },
    refresh: async () => {
      if (++attempts === 1) throw new Error('offline')
      return { data: { data: newTokens } }
    },
  })
  await assert.rejects(env.client.apiGet('/me'), /offline/)
  assert.equal(env.store.getState().clubId, 'club')
  assert.equal(await env.client.apiGet('/me'), 'recovered')
  assert.equal(attempts, 2)
})

test('logout or a different login during refresh cannot restore or replay the old session', async () => {
  for (const switchAccount of [false, true]) {
    const gate = defer()
    const env = setup({
      request: async (config) => { throw denied(config) }, refresh: () => gate.promise,
    })
    const pending = env.client.apiPost('/tasks', { title: 'old account' })
    await new Promise(setImmediate)
    if (switchAccount) env.store.getState().setSession({ accessToken: 'other', refreshToken: 'other-refresh' })
    else env.store.getState().clear()
    gate.resolve({ data: { data: newTokens } })
    await assert.rejects(pending, /로그인 상태가 변경/)
    assert.equal(env.storage.get(accessKey), switchAccount ? 'other' : undefined)
    assert.equal(env.calls.length, 1)
  }
})

test('a late 401 cannot replay an old-account mutation with another tab\'s token', async () => {
  const gate = defer()
  const nextMe = { ...me, id: 'other-account', clubs: [{ id: 'other-club', role: 'OWNER' }] }
  const env = setup({ request: async (config) => {
    if (config.url === '/tasks') { await gate.promise; throw denied(config) }
    return ok(config, nextMe)
  } })
  const oldKey = env.hooks.useMe().queryKey
  const oldWrite = env.client.apiPost('/tasks', { title: 'old account' })
  env.storage.set(accessKey, 'other-tab-access')
  env.storage.set(refreshKey, 'other-tab-refresh')
  gate.resolve()
  await assert.rejects(oldWrite, /로그인 상태가 변경/)
  assert.equal(env.calls.length, 1)
  assert.equal(env.refreshes.length, 0)
  assert.equal(env.store.getState().token, 'other-tab-access')
  assert.equal(env.store.getState().user, null)
  assert.equal(env.store.getState().clubId, null)
  const nextQuery = env.hooks.useMe()
  assert.notDeepEqual(Array.from(nextQuery.queryKey), Array.from(oldKey))
  await nextQuery.queryFn()
  assert.equal(env.store.getState().me.id, 'other-account')
  assert.equal(env.store.getState().clubId, null)
  assert.equal(env.storage.has(clubKey), false)
})

test('a stale refresh success or failure never overwrites or clears another tab\'s new login', async () => {
  for (const fails of [false, true]) {
    const gate = defer()
    const env = setup({ request: async (config) => { throw denied(config) }, refresh: () => gate.promise })
    const pending = env.client.apiGet('/me')
    await new Promise(setImmediate)
    env.storage.set(accessKey, 'other-tab-access')
    env.storage.set(refreshKey, 'other-tab-refresh')
    if (fails) gate.reject(denied({ url: '/auth/refresh' }))
    else gate.resolve({ data: { data: newTokens } })
    await assert.rejects(pending)
    assert.equal(env.storage.get(accessKey), 'other-tab-access')
    assert.equal(env.storage.get(refreshKey), 'other-tab-refresh')
    assert.equal(env.store.getState().token, 'other-tab-access')
    assert.equal(env.store.getState().me, null)
    assert.equal(env.store.getState().clubId, null)
    assert.equal(env.calls.length, 1)
  }
})

test('a newly detected cross-tab login aborts the current mutation before sending it', async () => {
  const env = setup({ request: async (config) => ok(config, 'unexpected write') })
  env.storage.set(accessKey, 'other-tab-access')
  env.storage.set(refreshKey, 'other-tab-refresh')
  await assert.rejects(env.client.apiPost('/tasks', { title: 'old screen' }), /로그인 상태가 변경/)
  assert.equal(env.calls.length, 0)
  assert.equal(env.store.getState().user, null)
})

test('an old successful save cannot start a second mutation under a newer account', async () => {
  const gate = defer()
  const env = setup({ request: async (config) => {
    if (config.url === '/save') await gate.promise
    return ok(config, { id: 'candidate', version: 2 })
  } })
  const chain = env.client.apiPatch('/save', { title: 'old account' })
    .then((saved) => env.client.apiPost('/accept', { expectedVersion: saved.version }))
  env.storage.set(accessKey, 'other-tab-access')
  env.storage.set(refreshKey, 'other-tab-refresh')
  gate.resolve()
  await assert.rejects(chain, /로그인 상태가 변경/)
  assert.equal(env.calls.length, 1)
  assert.equal(env.store.getState().token, 'other-tab-access')
  assert.equal(env.store.getState().me, null)
})

test('/me still populates after token rotation but an older account response cannot replace a new login', async () => {
  const stale = defer()
  const env = setup({ request: async (config) => {
    if (config.headers.Authorization === 'Bearer access-old') throw denied(config)
    return ok(config, me)
  } })
  await env.hooks.useMe().queryFn()
  assert.equal(env.store.getState().me.id, 'account')
  assert.equal(env.store.getState().clubId, 'club')

  const other = setup({ request: async (config) => { await stale.promise; return ok(config, me) } })
  const load = other.hooks.useMe().queryFn()
  other.store.getState().setSession({ accessToken: 'other', refreshToken: 'other-refresh' })
  stale.resolve()
  await assert.rejects(load, /로그인 상태가 변경/)
  assert.equal(other.store.getState().token, 'other')
  assert.equal(other.store.getState().me, null)
})

test('rotation does not reapply an already handled Push club hint over a manual selection', () => {
  const env = setup()
  env.store.getState().setMe({ ...me, clubs: [...me.clubs, { id: 'other-club', role: 'OWNER' }] })
  env.notificationClub('club')
  env.store.getState().selectClub('other-club')
  const sessionId = env.store.getState().sessionId
  assert.equal(env.store.getState().rotateSession(newTokens, sessionId, 'refresh-old'), true)
  env.notificationClub('club')
  assert.equal(env.store.getState().clubId, 'other-club')
})

test('SSE retries only the unauthorized opening and keeps its body and idempotency key', async () => {
  const streams = []
  const events = []
  const env = setup({ fetch: async (url, config) => {
    streams.push({ url, ...config, headers: { ...config.headers } })
    if (config.headers.Authorization === 'Bearer access-old') return new Response('', { status: 401 })
    return new Response('event: done\ndata: {"ok":true}\n\n', { status: 200 })
  } })
  await env.client.apiPostStream('/plan/chat/stream', { message: 'keep' }, {
    idempotencyKey: 'request-one', onEvent: (event) => events.push(event),
  })
  assert.equal(env.refreshes.length, 1)
  assert.equal(streams.length, 2)
  assert.equal(streams[1].headers.Authorization, 'Bearer access-new')
  assert.equal(streams[1].headers['Idempotency-Key'], 'request-one')
  assert.equal(streams[0].body, streams[1].body)
  assert.equal(events.length, 1)
})

test('an opened stream read failure is not replayed', async () => {
  let requests = 0
  const env = setup({ fetch: async () => {
    requests += 1
    return { status: 200, ok: true, body: { getReader: () => ({ read: async () => { throw new Error('closed') } }) } }
  } })
  await assert.rejects(env.client.apiPostStream('/plan/chat/stream', {}, { onEvent() {} }), /closed/)
  assert.equal(requests, 1)
  assert.equal(env.refreshes.length, 0)
})

test('an opened stream stops delivering old-session events when the account changes', async () => {
  let requests = 0
  const events = []
  const env = setup({ fetch: async () => {
    requests += 1
    return new Response('event: progress\ndata: {"old":1}\n\nevent: done\ndata: {"old":2}\n\n')
  } })
  await assert.rejects(env.client.apiPostStream('/plan/chat/stream', {}, {
    onEvent: (event) => {
      events.push(event)
      env.store.getState().setSession({ accessToken: 'other', refreshToken: 'other-refresh' })
    },
  }), /로그인 상태가 변경/)
  assert.equal(events.length, 1)
  assert.equal(requests, 1)
  assert.equal(env.refreshes.length, 0)
})

test('logout after access expiry revokes the rotated refresh token and clears the local session', async () => {
  const env = setup({ request: async (config) => {
    if (config.headers.Authorization === 'Bearer access-old') throw denied(config)
    assert.equal(dataOf(config).refreshToken, 'refresh-new')
    return ok(config, undefined, 204)
  } })
  await env.hooks.useLogout().mutationFn()
  assert.equal(env.calls.length, 2)
  assert.equal(env.storage.has(accessKey), false)
  assert.equal(env.store.getState().clubId, null)
})

test('a pending logout or login cannot clear or replace a newer session', async () => {
  const logoutGate = defer()
  const env = setup({ request: async (config) => { await logoutGate.promise; return ok(config, undefined, 204) } })
  const logout = env.hooks.useLogout().mutationFn()
  env.store.getState().setSession({ accessToken: 'other', refreshToken: 'other-refresh' })
  logoutGate.resolve()
  await assert.rejects(logout, /로그인 상태가 변경/)
  assert.equal(env.store.getState().token, 'other')

  const loginGate = defer()
  const pending = setup({ request: async (config) => { await loginGate.promise; return ok(config, newTokens) } })
  const login = pending.hooks.useLogin().mutationFn({ email: 'demo', password: 'unused' })
  pending.store.getState().clear()
  loginGate.resolve()
  await assert.rejects(login, /로그인 상태가 변경/)
  assert.equal(pending.store.getState().token, null)
})
