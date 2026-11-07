// 토리 답변 글을 문단·목록·굵게로 그린다(#304). 나누는 규칙은 replyText.ts에 있다.
// 문단 사이는 빈 줄 대신 8px, 목록은 점과 내어쓰기로 보여 줄이 바뀌어도 글머리 아래로 파고들지 않는다.
import { Fragment } from 'react'
import { cn } from '@/shared/lib/cn'
import { parseReply, type ReplyList, type Span } from '@/features/planning/replyText'

function Spans({ spans }: { spans: Span[] }) {
  return spans.map((span, index) =>
    span.bold ? (
      <strong key={index} className="font-semibold">
        {span.text}
      </strong>
    ) : (
      <Fragment key={index}>{span.text}</Fragment>
    ),
  )
}

function List({ list, nested = false }: { list: ReplyList; nested?: boolean }) {
  const Tag = list.ordered ? 'ol' : 'ul'
  return (
    <Tag
      className={cn(
        'flex flex-col pl-[1.15em]',
        list.ordered ? 'list-decimal tabular-nums' : nested ? 'list-[circle]' : 'list-disc',
        // 빈 줄로 띄운 목록은 항목마다 하위 목록을 거느린 묶음이라 묶음 사이를 더 띄운다.
        list.loose ? 'gap-[8px]' : 'gap-[3px]',
        nested && 'mt-[3px]',
        'marker:text-mute',
      )}
    >
      {list.items.map((item, index) => (
        <li key={index} className="pl-[2px]">
          <Spans spans={item.text} />
          {item.children && <List list={item.children} nested />}
        </li>
      ))}
    </Tag>
  )
}

export function ReplyText({ text, partial = false }: { text: string; partial?: boolean }) {
  return parseReply(text, partial).map((block, index) =>
    block.kind === 'list' ? (
      <List key={index} list={block} />
    ) : (
      <p key={index}>
        {block.lines.map((spans, line) => (
          <Fragment key={line}>
            {line > 0 && <br />}
            <Spans spans={spans} />
          </Fragment>
        ))}
      </p>
    ),
  )
}
