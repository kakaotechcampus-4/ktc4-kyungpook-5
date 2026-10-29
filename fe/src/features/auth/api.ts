import { apiGet, apiPost } from '@/shared/api/client'
import type { components } from '@/shared/api/schema'

type Schemas = components['schemas']
export type LoginInput = Schemas['LoginIn']
export type CurrentAccount = Schemas['MeOut']

export const login = (body: LoginInput) => apiPost<Schemas['SessionOut']>('/auth/login', body)
export const loginWithKakao = (code: string) =>
  apiPost<Schemas['SessionOut']>('/auth/kakao/callback', { code })
export const getMe = () => apiGet<CurrentAccount>('/me')
export const logout = (refreshToken: string) =>
  apiPost<void>('/auth/logout', { refreshToken } satisfies Schemas['LogoutIn'])
