import { OnboardingLayout } from '@/app/layout/OnboardingLayout'
import { useOnboarding } from '@/features/onboarding/useOnboarding'
import { OnboardingExperience } from '@/features/onboarding/OnboardingExperience'

export default function OnboardingPage() {
  const onboarding = useOnboarding()
  return (
    <OnboardingLayout teamName={onboarding.state.teamName} role={onboarding.state.role}>
      <OnboardingExperience onboarding={onboarding} />
    </OnboardingLayout>
  )
}
