import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { beginKakaoLogin, consumeKakaoCallback } from '@/features/auth/kakao'
import { useKakaoLogin } from '@/features/auth/hooks'
import { ApiError } from '@/shared/api/types'
import { Button } from '@/shared/ui/Button'
import { StateScreen } from '@/shared/ui/StateScreen'

export default function KakaoCallbackPage() {
  const navigate = useNavigate()
  const { mutateAsync } = useKakaoLogin()
  const started = useRef(false)
  const [error, setError] = useState('')
  const [emailConsentNext, setEmailConsentNext] = useState<string | null>(null)
  useEffect(() => {
    if (started.current) return
    started.current = true
    let callback: ReturnType<typeof consumeKakaoCallback>
    try {
      callback = consumeKakaoCallback(window.location.search)
    } catch {
      window.history.replaceState(null, '', window.location.pathname)
      setError('카카오 인증을 확인하지 못했어요. 다시 시도해 주세요.')
      return
    }
    window.history.replaceState(null, '', window.location.pathname)
    void mutateAsync(callback.code)
      .then(() =>
        navigate(`/login?${new URLSearchParams({ next: callback.next })}`, { replace: true }),
      )
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.fields?.emailConsent) {
          setEmailConsentNext(callback.next)
          setError('가입하려면 카카오 이메일 제공 동의가 필요해요.')
        } else if (cause instanceof ApiError && cause.fields?.email) {
          setError('카카오 계정에서 이메일을 받지 못했어요. 카카오 계정의 이메일을 확인해 주세요.')
        } else {
          setError('카카오 로그인에 실패했어요. 다시 시도해 주세요.')
        }
      })
  }, [mutateAsync, navigate])
  return (
    <StateScreen
      title={error ? '로그인하지 못했어요' : '카카오 로그인 확인 중'}
      desc={error || '잠시만 기다려 주세요.'}
    >
      {emailConsentNext && (
        <Button onClick={() => {
          try { beginKakaoLogin(emailConsentNext, true) }
          catch { setError('카카오 동의를 시작하지 못했어요. 로그인 화면에서 다시 시도해 주세요.') }
        }}>
          이메일 제공 동의하기
        </Button>
      )}
      {error && (
        <Link className="text-blue-700 underline" to="/login">
          로그인으로 돌아가기
        </Link>
      )}
    </StateScreen>
  )
}
