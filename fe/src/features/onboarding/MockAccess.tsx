import { useCallback, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'
import { Input } from '@/shared/ui/Input'
import { Tori } from '@/shared/ui/Tori'
import { FlowRail } from './FlowRail'
import { PreviewControls } from './PreviewControls'
import { Spotlight } from './Spotlight'
import type { useOnboarding } from './useOnboarding'

export function MockAccess({
  onboarding,
  team = false,
}: {
  onboarding: ReturnType<typeof useOnboarding>
  team?: boolean
}) {
  const { state, update } = onboarding
  const navigate = useNavigate()
  const closeGuide = useCallback(() => {
    update({ guideEnabled: false })
    document.querySelector<HTMLButtonElement>('[data-guide-toggle]')?.focus()
  }, [update])
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && state.guideEnabled) {
        event.preventDefault()
        closeGuide()
      }
    }
    window.addEventListener('keydown', close)
    return () => window.removeEventListener('keydown', close)
  }, [state.guideEnabled, closeGuide])
  return (
    <div className="min-h-dvh bg-bg px-4 py-5 sm:py-8">
      <div className="mx-auto max-w-[920px]">
        <PreviewControls onboarding={onboarding} />
        <div className="mx-auto mt-7 max-w-[520px]">
          <div className="mb-6 flex items-center gap-3">
            <Tori size={42} />
            <div>
              <p className="text-[20px] font-bold">운영해</p>
              <p className="mt-1 text-caption text-mute">
                자료를 참고하고, 회의에서 다음 할 일을 챙겨요.
              </p>
            </div>
          </div>
          <FlowRail current={team ? 2 : 1} />
          <Card className="p-6 sm:p-8">
            {team ? (
              <>
                <p className="text-[11px] font-bold text-blue-600">로그인 완료 · 목업 계정</p>
                <h1 className="mt-3 text-[25px] font-bold">어느 팀에서 시작할까요?</h1>
                <p className="mt-3 text-[13px] leading-6 text-ink2">
                  {state.operatorName}님이 초대된 팀이에요. 팀을 고르면 해당 팀의 자료와 회의를 볼
                  수 있어요.
                </p>
                <div className="my-6 rounded-2xl border border-blue-200 bg-blue-50 p-5">
                  <p className="text-h3">{state.teamName}</p>
                  <p className="mt-2 text-caption text-blue-700">
                    초대됨 · {state.role === 'OWNER' ? '회장' : '임원'}
                  </p>
                </div>
                <Button
                  data-guide-target="team-enter"
                  className="w-full"
                  size="lg"
                  onClick={() => {
                    update({ clubSelected: true, setupDone: true })
                    navigate('/onboarding', { replace: true })
                  }}
                >
                  이 팀으로 들어가기
                </Button>
              </>
            ) : (
              <>
                <h1 className="text-[25px] font-bold">로그인</h1>
                <p className="mt-3 text-[13px] leading-6 text-ink2">
                  처음 로그인하는 임원으로 시작해 볼게요.
                  <br />
                  준비된 체험 계정을 사용해 주세요.
                </p>
                <form
                  className="mt-6 space-y-4"
                  onSubmit={(event) => {
                    event.preventDefault()
                    update({ signedIn: true })
                    navigate('/onboarding/team', { replace: true })
                  }}
                >
                  <Input label="이메일" value="crew@onbit.example" readOnly autoComplete="off" />
                  <Input
                    label="비밀번호"
                    type="password"
                    value="preview-only"
                    readOnly
                    autoComplete="off"
                  />
                  <p className="text-[11px] leading-5 text-mute">
                    실제 이메일·비밀번호를 입력하지 않아도 돼요.
                    <br />이 화면에서는 서버 로그인 요청을 보내지 않아요.
                  </p>
                  <Button
                    data-guide-target="login-submit"
                    type="submit"
                    size="lg"
                    className="w-full"
                  >
                    예시 계정으로 로그인
                  </Button>
                </form>
              </>
            )}
          </Card>
          <p className="mt-5 text-center text-[11px] leading-6 text-mute">
            로그인 → 팀 선택 → 자료 준비 → 회의 → 할 일 확인
            <br />
            처음 이용하는 순서대로 직접 눌러 보세요.
          </p>
        </div>
      </div>
      {state.guideEnabled && (
        <Spotlight
          target={team ? '[data-guide-target="team-enter"]' : '[data-guide-target="login-submit"]'}
          title={team ? '초대된 팀으로 들어가세요' : '로그인부터 시작해요'}
          description={
            team
              ? '이 팀으로 들어가기를 누르면 처음 로그인한 팀의 메인이 열려요.'
              : '예시 계정으로 로그인을 눌러 주세요. 실제 계정 정보는 필요하지 않아요.'
          }
          step={team ? 2 : 1}
          total={5}
          onClose={closeGuide}
        />
      )}
    </div>
  )
}
