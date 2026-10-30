import type { components } from '@/shared/api/schema'

type S = components['schemas']
type Action = S['PlannedStepActionOut']
type Draft = { title: string; amount: number | null; payload: S['ActionPayloadOut'] }

export function buildActionUpdate(action: Action, draft: Draft): S['ActionUpdateIn'] | null {
  if (!action.editable) return null
  const previous = action.payload ?? {}
  const changed = Object.fromEntries(
    Object.entries(draft.payload).filter(
      ([key, value]) => previous[key as keyof S['ActionPayloadOut']] !== value,
    ),
  ) as S['ActionPayloadOut']
  const body: S['ActionUpdateIn'] = { expectedVersion: action.version }
  if (draft.title !== action.title) body.title = draft.title
  if (draft.amount !== action.amount) body.amount = draft.amount
  if (Object.keys(changed).length) body.payload = changed
  return Object.keys(body).length > 1 ? body : null
}
