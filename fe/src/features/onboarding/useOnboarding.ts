import { useCallback, useRef, useState } from 'react'
import {
  loadOnboarding,
  resetOnboarding,
  saveOnboarding,
  selectPreviewCandidate,
  updatePreviewCandidate,
  savePreviewCandidate,
  type OnboardingState,
  type PreviewTask,
} from './model'

// fresh: 체험에 새로 들어온 것으로 보고 지난 진행을 버린다. 단계 이동은
// 같은 컴포넌트가 계속 떠 있어 다시 돌지 않는다(= 들어올 때 한 번).
export function useOnboarding({ fresh = false }: { fresh?: boolean } = {}) {
  const [state, setState] = useState(fresh ? resetOnboarding : loadOnboarding)
  const current = useRef(state)
  const commit = useCallback((next: OnboardingState) => {
    const persisted = saveOnboarding(next)
    current.current = persisted
    setState(persisted)
  }, [])

  const update = useCallback(
    (patch: Partial<OnboardingState>) => {
      commit({ ...current.current, ...patch })
    },
    [commit],
  )

  const reset = useCallback(() => {
    const next = resetOnboarding()
    current.current = next
    setState(next)
  }, [])

  const selectCandidate = useCallback(
    (id: string) => {
      const next = selectPreviewCandidate(current.current, id)
      if (next !== current.current) commit(next)
    },
    [commit],
  )

  const updateCandidate = useCallback(
    (id: string, patch: Partial<Omit<PreviewTask, 'id'>>) => {
      const next = updatePreviewCandidate(current.current, id, patch)
      if (next !== current.current) commit(next)
    },
    [commit],
  )

  const saveCandidate = useCallback(
    (id: string) => {
      const next = savePreviewCandidate(current.current, id)
      if (next !== current.current) commit(next)
    },
    [commit],
  )

  return { state, update, reset, selectCandidate, updateCandidate, saveCandidate }
}
