import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { consumeKakaoCallback } from '@/features/auth/kakao'
import { useKakaoLogin } from '@/features/auth/hooks'
import { StateScreen } from '@/shared/ui/StateScreen'

export default function KakaoCallbackPage() {
  const navigate = useNavigate()
  const { mutateAsync } = useKakaoLogin()
  const started = useRef(false)
  const [error, setError] = useState('')
  useEffect(() => {
    if (started.current) return
    started.current = true
    let code: string
    try {
      code = consumeKakaoCallback(window.location.search)
    } catch {
      window.history.replaceState(null, '', window.location.pathname)
      setError('카카오 인증을 확인하지 못했어요. 다시 시도해 주세요.')
      return
    }
    window.history.replaceState(null, '', window.location.pathname)
    void mutateAsync(code)
      .then(() => navigate('/login', { replace: true }))
      .catch(() => {
        setError('카카오 로그인에 실패했어요. 이메일 동의와 연결 상태를 확인해 주세요.')
      })
  }, [mutateAsync, navigate])
  return (
    <StateScreen
      title={error ? '로그인하지 못했어요' : '카카오 로그인 확인 중'}
      desc={error || '잠시만 기다려 주세요.'}
    >
      {error && (
        <Link className="text-blue-700 underline" to="/login">
          로그인으로 돌아가기
        </Link>
      )}
    </StateScreen>
  )
}
