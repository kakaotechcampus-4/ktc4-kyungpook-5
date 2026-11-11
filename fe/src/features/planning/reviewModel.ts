import { PHASES, STEP_CATALOGUE } from './catalogue'
import type { components } from '@/shared/api/schema'

type Step = components['schemas']['PlannedStepOut']

// 그룹은 카탈로그로, 그룹 안 순서는 서버 배열로 결정한다. 미래 코드는 누락시키지 않는다.
// P2(PlannedStepOut)와 행사 상세의 계획 중 요약(EventStep, #337)이 같이 쓴다. code가 없으면 기타 단계다.
export function reviewGroups<T extends { code?: string | null }>(steps: T[]) {
  const phaseOf = (code?: string | null) =>
    STEP_CATALOGUE.find((entry) => entry.code === code)?.phase
  const groups: { name: string; steps: T[] }[] = PHASES.map((name) => ({
    name,
    steps: steps.filter((step) => phaseOf(step.code) === name),
  }))
  const unknown = steps.filter((step) => !phaseOf(step.code))
  if (unknown.length) groups.push({ name: '기타 단계', steps: unknown })
  return groups.filter((group) => group.steps.length)
}

export function currentExcluded(steps: Step[]) {
  const included = new Set<string>(steps.map((step) => step.code))
  return STEP_CATALOGUE.filter((step) => !included.has(step.code))
}

export function planningStage(stage: string | null, hasSteps: boolean): 'review' | 'conditions' {
  if (stage === 'conditions') return 'conditions'
  return hasSteps ? 'review' : 'conditions'
}
