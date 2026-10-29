import type { PlanPreview } from '@/features/planning/generation-playground'
import { toPreviewSteps } from '@/features/planning/generation-playground'
import { toAgentFacts } from '@/features/planning/agent-playground'
import { PlanFacts } from './PlanFacts'
import { StepFlow } from './StepFlow'
import { Card } from '@/shared/ui/Card'

export function AgentPlanPreview({ preview, current }: { preview: PlanPreview; current: boolean }) {
  return (
    <section aria-label="생성된 계획 초안" className="flex flex-col gap-4">
      <Card className="flex flex-col gap-2 p-5">
        <h2 className="text-h2">흐름 만들기 · 계획 초안</h2>
        <p className="text-caption text-ink2">
          검토용 초안이에요. 날짜·잠정 조건을 확인하며 대화를 이어갈 수 있어요.
        </p>
        {!current && (
          <p role="status" className="text-caption text-failed">
            현재 조건과 다른 이전 초안이에요. 대화에서 조건을 확인하고 다시 만들어 주세요.
          </p>
        )}
      </Card>
      <div className="flex flex-col items-start gap-5 xl:flex-row">
        <StepFlow steps={toPreviewSteps(preview)} />
        <aside className="flex w-full flex-col gap-4 xl:w-[360px] xl:shrink-0">
          <PlanFacts
            wide
            facts={toAgentFacts(preview.basis_draft)}
            showProgress={false}
            showNext={false}
            onNext={() => {}}
          />
          <Card className="flex flex-col gap-3 p-5">
            <h3 className="text-h3">추가로 정할 내용</h3>
            <p className="text-caption text-mute">
              지금 모두 답할 필요는 없어요. 보류한 내용은 나중에 정해도 괜찮아요.
            </p>
            {preview.open_questions.length ? (
              <ul className="list-inside list-disc text-caption">
                {preview.open_questions.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            ) : (
              <p className="text-caption text-mute">추가로 확인할 내용은 없어요.</p>
            )}
            <h3 className="text-h3">주의할 내용</h3>
            {preview.warnings.length ? (
              <ul className="list-inside list-disc text-caption">
                {preview.warnings.map((text, i) => (
                  <li key={i}>{text}</li>
                ))}
              </ul>
            ) : (
              <p className="text-caption text-mute">별도 경고는 없어요.</p>
            )}
          </Card>
          <Card className="flex flex-col gap-3 p-5">
            <h3 className="text-h3">계획의 가정과 참고 자료</h3>
            {preview.assumptions.length === 0 && (
              <p className="text-caption text-mute">별도로 둔 가정은 없어요.</p>
            )}
            {preview.assumptions.map((assumption, i) => (
              <div key={i} className="text-caption">
                <p>{assumption.content}</p>
                {assumption.sources.map((source, j) => (
                  <p key={j} className="mt-1 text-mute">
                    {source.file_name} · {source.location.label}
                  </p>
                ))}
              </div>
            ))}
          </Card>
          <Card className="flex flex-col gap-3 p-5">
            <h3 className="text-h3">포함하지 않은 단계</h3>
            {preview.excluded_steps.length === 0 && (
              <p className="text-caption text-mute">모든 단계를 포함했어요.</p>
            )}
            {preview.excluded_steps.map((step) => (
              <div key={step.code} className="text-caption">
                <p className="font-bold">{step.name}</p>
                <p className="mt-1 text-ink2">{step.reason}</p>
              </div>
            ))}
          </Card>
        </aside>
      </div>
    </section>
  )
}
