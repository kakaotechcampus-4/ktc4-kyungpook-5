import assert from 'node:assert/strict'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import test from 'node:test'
import { build } from 'esbuild'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const { outputFiles } = await build({
  entryPoints: [path.join(root, 'src/features/records/presentation.ts')],
  bundle: true,
  write: false,
  platform: 'node',
  format: 'esm',
  alias: { '@': path.join(root, 'src') },
})
const { categoryChips, filterByCategory, highlightParts, matchLabel } = await import(
  `data:text/javascript;base64,${Buffer.from(outputFiles[0].text).toString('base64')}`
)

const item = (id, category) => ({ id, category })

test('category filter keeps the server order', () => {
  const items = [item('a', 'EVENT_HISTORY'), item('b', 'LEDGER'), item('c', 'EVENT_HISTORY')]
  assert.deepEqual(filterByCategory(items, null).map((i) => i.id), ['a', 'b', 'c'])
  assert.deepEqual(filterByCategory(items, 'EVENT_HISTORY').map((i) => i.id), ['a', 'c'])
})

test('chips count each category and start with 전체', () => {
  const chips = categoryChips([item('a', 'EVENT_HISTORY'), item('b', 'LEDGER'), item('c', 'EVENT_HISTORY')])
  assert.deepEqual(
    chips.map((chip) => [chip.value, chip.count]),
    [[null, 3], ['EVENT_HISTORY', 2], ['LEDGER', 1]],
  )
  assert.equal(chips[0].label, '전체')
})

test('chips are hidden when every result has the same category', () => {
  assert.deepEqual(categoryChips([item('a', 'LEDGER'), item('b', 'LEDGER')]), [])
})

test('highlight marks every hit ignoring case', () => {
  assert.deepEqual(highlightParts('봄 mt, 가을 MT', 'MT'), [
    { text: '봄 ', hit: false },
    { text: 'mt', hit: true },
    { text: ', 가을 ', hit: false },
    { text: 'MT', hit: true },
  ])
})

test('highlight leaves text alone without a query or a hit', () => {
  assert.deepEqual(highlightParts('예비비 정산', ''), [{ text: '예비비 정산', hit: false }])
  assert.deepEqual(highlightParts('예비비 정산', '버스'), [{ text: '예비비 정산', hit: false }])
})

test('match label explains why a record appeared', () => {
  assert.equal(matchLabel(['FILENAME', 'SEMANTIC']), '제목 일치 · AI 추천')
  assert.equal(matchLabel(['CONTENT']), '본문 일치')
  assert.equal(matchLabel(['SEMANTIC']), 'AI 추천')
})
