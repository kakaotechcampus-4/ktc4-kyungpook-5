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

export function useOnboarding() {
  const [state, setState] = useState(loadOnboarding)
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
