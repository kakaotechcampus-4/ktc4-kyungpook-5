// Run from fe/: node --test tests/planning-reply-text.test.mjs
// 토리 답변의 마크다운 일부(굵게·목록·문단)를 화면 덩어리로 나누기(#304). 입력은 저장된 실제 답변의 모양이다.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import ts from 'typescript'

const source = await readFile(
  new URL('../src/features/planning/replyText.ts', import.meta.url),
  'utf8',
)
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const { parseReply, parseSpans } = await import(
  `data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`
)

test('굵게는 기호를 빼고 굵은 조각으로 나눈다', () => {
  assert.deepEqual(parseSpans('인원은 **40명**, 일정은 **12월 5~6일**로 수정했어요.'), [
    { text: '인원은 ' },
    { text: '40명', bold: true },
    { text: ', 일정은 ' },
    { text: '12월 5~6일', bold: true },
    { text: '로 수정했어요.' },
  ])
})

test('빈 줄은 문단을 나누고, 한 번 줄바꿈과 줄 끝 공백 두 칸은 같은 문단의 다음 줄이다', () => {
  const blocks = parseReply(
    '행사 이름은 **2026년 MT**로 변경했어요.  \n다만 일정 기록은 찾지 못했어요.\n\n작년 일정표를 보내 주세요.',
  )
  assert.deepEqual(blocks, [
    {
      kind: 'p',
      lines: [
        [{ text: '행사 이름은 ' }, { text: '2026년 MT', bold: true }, { text: '로 변경했어요.' }],
        [{ text: '다만 일정 기록은 찾지 못했어요.' }],
      ],
    },
    { kind: 'p', lines: [[{ text: '작년 일정표를 보내 주세요.' }]] },
  ])
})

test('목록 줄은 항목이 되고, 앞뒤 문단과 나뉜다', () => {
  const blocks = parseReply(
    '초안 만들었어요!\n\n- **행사:** MT\n- **인원:** 40명\n\n준비 흐름은 이래요.',
  )
  assert.equal(blocks.length, 3)
  assert.deepEqual(blocks[1], {
    kind: 'list',
    ordered: false,
    items: [
      { text: [{ text: '행사:', bold: true }, { text: ' MT' }] },
      { text: [{ text: '인원:', bold: true }, { text: ' 40명' }] },
    ],
  })
})

test('들여쓴 목록은 위 항목의 하위 목록이 되고, 빈 줄로 띄운 항목도 같은 목록으로 잇는다', () => {
  const blocks = parseReply(
    [
      '아래를 주의하면 좋아요.',
      '',
      '- **날씨와 이동**',
      '  - 일교차가 커요.',
      '  - 우천 동선을 준비하세요.',
      '',
      '- **장소 확인**',
      '  - 빔프로젝터를 점검하세요.',
      '',
      '먼저 일정부터 정해요.',
    ].join('\n'),
  )
  assert.deepEqual(
    blocks.map((block) => block.kind),
    ['p', 'list', 'p'],
  )
  const list = blocks[1]
  assert.equal(list.loose, true)
  assert.equal(list.items.length, 2)
  assert.deepEqual(
    list.items[0].children.items.map((item) => item.text[0].text),
    ['일교차가 커요.', '우천 동선을 준비하세요.'],
  )
  assert.equal(list.items[1].children.items.length, 1)
})

test('번호 목록은 ordered로 나누고, 기호 종류가 바뀌면 새 목록이다', () => {
  const blocks = parseReply('1. 장소 예약\n2) 참가비 안내\n- 기타')
  assert.deepEqual(
    blocks.map((block) => [block.kind, block.ordered, block.items.length]),
    [
      ['list', true, 2],
      ['list', false, 1],
    ],
  )
})

test('목록이 아닌 별표·하이픈과 꺾쇠는 글자 그대로 둔다', () => {
  assert.deepEqual(parseReply('참가비 2-3만 원 * 40명 <b>예상</b>'), [
    { kind: 'p', lines: [[{ text: '참가비 2-3만 원 * 40명 <b>예상</b>' }]] },
  ])
})

test('받는 중: 닫히지 않은 굵게는 기호 없이 굵게 두고, 끝에 별표 하나만 온 것은 잠시 숨긴다', () => {
  assert.deepEqual(parseReply('인원은 **40', true), [
    { kind: 'p', lines: [[{ text: '인원은 ' }, { text: '40', bold: true }]] },
  ])
  assert.deepEqual(parseReply('인원은 *', true), [{ kind: 'p', lines: [[{ text: '인원은 ' }]] }])
  // 다 받은 답변의 끝 별표는 그대로 둔다.
  assert.deepEqual(parseReply('인원은 *', false), [{ kind: 'p', lines: [[{ text: '인원은 *' }]] }])
})

test('받는 중: 기호만 먼저 온 목록 줄은 빈 항목으로 둬 "-"가 글자로 보였다 사라지지 않는다', () => {
  assert.deepEqual(parseReply('정리하면\n-', true), [
    { kind: 'p', lines: [[{ text: '정리하면' }]] },
    { kind: 'list', ordered: false, items: [{ text: [] }] },
  ])
})
