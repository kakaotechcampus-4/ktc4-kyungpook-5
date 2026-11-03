import { Navigate, useParams } from 'react-router-dom'
import { OnboardingLayout } from '@/app/layout/OnboardingLayout'
import { useOnboarding } from '@/features/onboarding/useOnboarding'
import { OnboardingExperience } from '@/features/onboarding/OnboardingExperience'
import { MockAccess } from '@/features/onboarding/MockAccess'

export default function OnboardingPage() {
  const onboarding = useOnboarding({ fresh: true })
  const { view = '' } = useParams<{ view: string }>()
  const { state } = onboarding
  if (view === 'login') return <MockAccess onboarding={onboarding} />
  if (!state.signedIn) return <Navigate to="/onboarding/login" replace />
  if (view === 'team' || !state.clubSelected) return <MockAccess onboarding={onboarding} team />
  if (view === 'meetings' && !state.recordsAdded)
    return <Navigate to="/onboarding/records" replace />
  if (view === 'review' && !state.meetingPlayed)
    return <Navigate to="/onboarding/meetings" replace />
  if (view === 'complete' || view === 'setup') return <Navigate to="/onboarding" replace />
  return (
    <OnboardingLayout teamName={state.teamName} role={state.role}>
      <OnboardingExperience onboarding={onboarding} />
    </OnboardingLayout>
  )
}
