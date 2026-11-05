import { useEffect, useRef } from 'react'
import { Button } from '@/shared/ui/Button'
import type { components } from '@/shared/api/schema'

export function GenerationFailureNotice({
  result,
  hasPrevious,
}: {
  result: components['schemas']['GenerationResultOut']
  hasPrevious: boolean
}) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    heading.current?.focus()
  }, [result])
  const clarify = result.status === 'needs_clarification'
  return (
    <section
      className="rounded-xl border border-line bg-card p-5"
      aria-labelledby="generation-failure-title"
    >
      <h2
        id="generation-failure-title"
        ref={heading}
        tabIndex={-1}
        className="text-h3 focus:outline-none"
      >
        {clarify ? '초안을 만들기 전에 확인할 내용이 있어요' : '초안을 완성하지 못했어요'}
      </h2>
      <p className="mt-2 break-keep text-ink2">{result.reason || '행사 조건을 확인해 주세요.'}</p>
      {hasPrevious && <p className="mt-2 text-caption text-ink2">기존 초안은 유지했어요.</p>}
      <Button
        className="mt-4"
        variant="secondary"
        onClick={() => document.getElementById('planning-chat-answer')?.focus()}
      >
        조건 이어서 정하기
      </Button>
    </section>
  )
}
