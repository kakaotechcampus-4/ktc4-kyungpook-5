const STATE_KEY = 'unyounghae_kakao_oauth_state'
const clientId = import.meta.env.VITE_KAKAO_REST_API_KEY?.trim() ?? ''
export const kakaoConfigured = Boolean(clientId)

export function beginKakaoLogin() {
  if (!clientId || !window.crypto?.getRandomValues) throw new Error('Kakao unavailable')
  const state = Array.from(crypto.getRandomValues(new Uint8Array(32)), (value) =>
    value.toString(16).padStart(2, '0'),
  ).join('')
  sessionStorage.setItem(STATE_KEY, state)
  const url = new URL('https://kauth.kakao.com/oauth/authorize')
  url.searchParams.set('client_id', clientId)
  url.searchParams.set('redirect_uri', `${window.location.origin}/auth/kakao/callback`)
  url.searchParams.set('response_type', 'code')
  url.searchParams.set('state', state)
  window.location.assign(url.toString())
}

export function consumeKakaoCallback(search: string): string {
  const params = new URLSearchParams(search)
  const saved = sessionStorage.getItem(STATE_KEY)
  sessionStorage.removeItem(STATE_KEY)
  const state = params.get('state')
  const code = params.get('code')
  if (!saved || !state || state !== saved || !code || params.has('error')) {
    throw new Error('카카오 인증을 확인하지 못했어요. 다시 시도해 주세요.')
  }
  return code
}
