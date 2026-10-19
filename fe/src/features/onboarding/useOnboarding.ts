import { useCallback, useRef, useState } from 'react'
import { loadOnboarding, resetOnboarding, saveOnboarding, type OnboardingState } from './model'

export function useOnboarding() {
  const [state, setState] = useState(loadOnboarding)
  const current = useRef(state)

  const update = useCallback((patch: Partial<OnboardingState>) => {
    // candidate는 호출자가 전달한 전체 객체로 교체한다.
    const next = saveOnboarding({ ...current.current, ...patch })
    current.current = next
    setState(next)
  }, [])

  const reset = useCallback(() => {
    const next = resetOnboarding()
    current.current = next
    setState(next)
  }, [])

  return { state, update, reset }
}
