// useAuth... 커스텀 훅. 컴포넌트는 반드시 이 훅을 거쳐 서버 상태에 접근한다.
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as authApi from '@/features/auth/api'
import type { ClubSearchResult, JoinMode, SignupPayload } from '@/features/auth/types'

export function useLoginForm() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [keepSignedIn, setKeepSignedIn] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit() {
    setSubmitting(true)
    setError(null)
    try {
      await authApi.login({ email, password, keepSignedIn })
      navigate('/')
    } catch {
      setError('이메일 또는 비밀번호를 확인해 주세요.')
    } finally {
      setSubmitting(false)
    }
  }

  return {
    email,
    setEmail,
    password,
    setPassword,
    keepSignedIn,
    setKeepSignedIn,
    submitting,
    error,
    canSubmit: email.trim().length > 0 && password.trim().length > 0 && !submitting,
    submit,
  }
}

export function useSignupForm() {
  const navigate = useNavigate()
  const [mode, setMode] = useState<JoinMode>('JOIN_EXISTING')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [clubKeyword, setClubKeyword] = useState('')
  const [clubResults, setClubResults] = useState<ClubSearchResult[]>([])
  const [selectedClub, setSelectedClub] = useState<ClubSearchResult | null>(null)
  const [newClubName, setNewClubName] = useState('')
  const [role, setRole] = useState('')
  const [agreedToTerms, setAgreedToTerms] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function searchClub(keyword: string) {
    setClubKeyword(keyword)
    setClubResults(await authApi.searchClubs(keyword))
  }

  function selectClub(club: ClubSearchResult) {
    setSelectedClub(club)
    setClubResults([])
    setClubKeyword('')
  }

  const canSubmit =
    email.trim().length > 0 &&
    password.trim().length >= 8 &&
    name.trim().length > 0 &&
    agreedToTerms &&
    (mode === 'JOIN_EXISTING' ? selectedClub !== null : newClubName.trim().length > 0) &&
    !submitting

  async function submit() {
    setSubmitting(true)
    setError(null)
    const payload: SignupPayload = {
      mode,
      email,
      password,
      name,
      club: selectedClub,
      newClubName,
      role,
      agreedToTerms,
    }
    try {
      await authApi.signup(payload)
      navigate('/')
    } catch {
      setError('가입 요청을 보내지 못했습니다. 잠시 후 다시 시도해 주세요.')
    } finally {
      setSubmitting(false)
    }
  }

  return {
    mode,
    setMode,
    email,
    setEmail,
    password,
    setPassword,
    name,
    setName,
    clubKeyword,
    clubResults,
    searchClub,
    selectedClub,
    selectClub,
    newClubName,
    setNewClubName,
    role,
    setRole,
    agreedToTerms,
    setAgreedToTerms,
    submitting,
    error,
    canSubmit,
    submit,
  }
}
