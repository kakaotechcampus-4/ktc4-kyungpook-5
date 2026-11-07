import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import vm from 'node:vm'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/meetings/confirmed.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
})
const exports = {}
vm.runInNewContext(outputText, { exports, require: () => ({}) })
const { notificationTaskDetail } = exports
const linked = { clubId: 'club-a', taskId: 'task-a', task: { id: 'task-a', title: '알림의 할 일' } }

test('notification opens only the authenticated result for the current club and requested task', () => {
  assert.equal(notificationTaskDetail(undefined, 'club-a', 'task-a', null).open, false)
  const ready = notificationTaskDetail(linked, 'club-a', 'task-a', null)
  assert.equal(ready.open, true)
  assert.equal(ready.task, linked.task)
  for (const [club, taskId] of [
    ['club-b', 'task-a'],
    ['club-a', 'task-b'],
    ['club-a', undefined],
  ]) {
    const switched = notificationTaskDetail(linked, club, taskId, null)
    assert.equal(switched.open, false)
    assert.equal(switched.task, null)
  }
  assert.equal(
    notificationTaskDetail({ ...linked, task: { id: 'wrong-task' } }, 'club-a', 'task-a', null)
      .task,
    null,
  )
})

test('dismissal survives refreshed data while explicit reopening and a new target can open', () => {
  const opened = notificationTaskDetail(linked, 'club-a', 'task-a', null)
  const refreshed = {
    ...linked,
    task: { ...linked.task, title: '서버에서 갱신된 제목', version: 2 },
  }
  assert.equal(notificationTaskDetail(refreshed, 'club-a', 'task-a', opened.key).open, false)
  assert.equal(notificationTaskDetail(refreshed, 'club-a', 'task-a', null).open, true)
  const next = { clubId: 'club-b', taskId: 'task-b', task: { id: 'task-b' } }
  assert.equal(notificationTaskDetail(next, 'club-b', 'task-b', opened.key).open, true)
})
