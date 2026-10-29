import { loadOnboarding } from './model'

// 로컬 목업 기록은 이 브라우저의 안내 선호와 진행 상태만 나타낸다.
export function onboardingEntry(
  hasVerifiedSession: boolean,
): '/dashboard' | '/login' | '/onboarding' {
  if (hasVerifiedSession) return '/dashboard'
  const preview = loadOnboarding()
  return !preview.guideEnabled || preview.savedItems.length > 0 ? '/login' : '/onboarding'
}
