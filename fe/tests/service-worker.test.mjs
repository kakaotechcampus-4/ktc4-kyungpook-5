// Run from fe/: node --test tests/*.test.mjs
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'

const workerSource = await readFile(new URL('../public/sw.js', import.meta.url), 'utf8')
const origin = 'https://meeting.example'
const fallback = `${origin}/meetings`

function worker(windows = []) {
  const handlers = new Map()
  const notifications = []
  const opened = []
  let closed = 0
  const context = {
    URL,
    self: {
      location: { origin },
      addEventListener: (type, handler) => handlers.set(type, handler),
      skipWaiting: async () => {},
      clients: {
        claim: async () => {},
        matchAll: async () => windows,
        openWindow: async (url) => opened.push(url),
      },
      registration: {
        showNotification: async (title, options) => notifications.push({ title, options }),
      },
    },
  }
  vm.runInNewContext(workerSource, context)
  async function dispatch(type, data) {
    let completion
    handlers.get(type)({
      ...data,
      waitUntil: (promise) => {
        completion = promise
      },
    })
    await completion
  }
  return {
    notifications,
    opened,
    get closed() {
      return closed
    },
    push: (payload) => dispatch('push', { data: { json: () => payload } }),
    malformedPush: () =>
      dispatch('push', {
        data: {
          json: () => {
            throw new SyntaxError('bad payload')
          },
        },
      }),
    click: (data) =>
      dispatch('notificationclick', {
        notification: {
          data,
          close: () => {
            closed++
          },
        },
      }),
  }
}

test('BE reminder payload keeps nested item URL, tag and item metadata through notification click', async () => {
  const sw = worker()
  const url = '/meetings?taskId=item-1&clubId=club-1'
  await sw.push({
    type: 'TASK_REMINDER',
    title: '자료 제출',
    body: '확인한 시간에 자료를 제출해 주세요.',
    tag: 'reminder:reminder-1',
    data: { url, clubId: 'club-1', confirmedItemId: 'item-1', reminderId: 'reminder-1' },
  })
  const { title, options } = sw.notifications[0]
  assert.equal(title, '자료 제출')
  assert.equal(options.tag, 'reminder:reminder-1')
  assert.equal(options.data.url, origin + url)
  assert.equal(options.data.clubId, 'club-1')
  assert.equal(options.data.confirmedItemId, 'item-1')
  assert.equal(options.data.reminderId, 'reminder-1')
  assert.equal(options.data.source, 'server-push')
  await sw.click(options.data)
  assert.deepEqual(sw.opened, [origin + url])
  assert.equal(sw.closed, 1)
})

test('nested data.url takes precedence over the legacy top-level URL', async () => {
  const sw = worker()
  await sw.push({ url: '/meetings?taskId=wrong', data: { url: '/meetings?taskId=correct' } })
  assert.equal(sw.notifications[0].options.data.url, `${origin}/meetings?taskId=correct`)
})

test('legacy URL and notificationId remain supported', async () => {
  const sw = worker()
  await sw.push({ url: '/meetings/meeting-1', notificationId: 'legacy-1' })
  assert.equal(sw.notifications[0].options.data.url, `${origin}/meetings/meeting-1`)
  assert.equal(sw.notifications[0].options.tag, 'legacy-1')
})

const unsafeUrls = [
  ['external origin', 'https://evil.example/meetings'],
  ['scheme-relative external origin', '//evil.example/meetings'],
  ['executable URL', 'javascript:alert(1)'],
  ['credentials in same-origin URL', 'https://name:password@meeting.example/meetings'],
  ['malformed URL', 'http://['],
]
for (const [label, url] of unsafeUrls) {
  test(`Push rejects ${label} in nested payload`, async () => {
    const sw = worker()
    await sw.push({ url: '/meetings?taskId=ignored', data: { url } })
    assert.equal(sw.notifications[0].options.data.url, fallback)
  })
  test(`notification click independently rejects ${label}`, async () => {
    const sw = worker()
    await sw.click({ url })
    assert.deepEqual(sw.opened, [fallback])
  })
}

test('malformed Push payload displays a generic safe notification', async () => {
  const sw = worker()
  await sw.malformedPush()
  assert.equal(sw.notifications[0].title, '운영해 알림')
  assert.equal(sw.notifications[0].options.data.url, fallback)
  assert.equal(sw.notifications[0].options.data.source, 'server-push')
})

test('click navigates and focuses an existing app window instead of opening a second window', async () => {
  const navigated = []
  let focused = false
  const sw = worker([
    {
      url: `${origin}/meetings/old`,
      navigate: async (url) => {
        navigated.push(url)
        return {
          focus: async () => {
            focused = true
          },
        }
      },
    },
  ])
  await sw.click({ url: '/meetings?taskId=item-1&clubId=club-1' })
  assert.deepEqual(navigated, [`${origin}/meetings?taskId=item-1&clubId=club-1`])
  assert.equal(focused, true)
  assert.deepEqual(sw.opened, [])
})
