export function PlanStageNav({ current }: { current: 'conditions' | 'review' }) {
  return (
    <ol
      aria-label="행사 계획 단계"
      className="flex flex-wrap items-center gap-4 border-b border-line pb-5 text-caption"
    >
      {(['conditions', 'review'] as const).map((stage, index) => (
        <li
          key={stage}
          aria-current={current === stage ? 'step' : undefined}
          className={`flex items-center gap-2 ${current === stage ? 'font-bold text-blue-700' : 'text-mute'}`}
        >
          <span
            className={`grid size-6 place-items-center rounded-full text-label ${current === stage ? 'bg-blue-600 text-white' : 'bg-blue-100 text-blue-700'}`}
          >
            {index + 1}
          </span>
          {stage === 'conditions' ? '행사 조건' : '계획 검토'}
          {index === 0 && (
            <span aria-hidden className="ml-2 text-mute">
              →
            </span>
          )}
        </li>
      ))}
    </ol>
  )
}
