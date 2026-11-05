import { PHASES, STEP_CATALOGUE } from './catalogue'
import type { components } from '@/shared/api/schema'

type Step = components['schemas']['PlannedStepOut']

// 그룹은 카탈로그로, 그룹 안 순서는 서버 배열로 결정한다. 미래 코드는 누락시키지 않는다.
export function reviewGroups(steps: Step[]) {
  const phaseOf = (code: string) => STEP_CATALOGUE.find((entry) => entry.code === code)?.phase
  const groups: { name: string; steps: Step[] }[] = PHASES.map((name) => ({
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
