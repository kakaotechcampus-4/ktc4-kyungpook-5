// S1 회원가입 카드
import { Link } from 'react-router-dom'
import { cn } from '@/shared/lib/cn'
import { Button } from '@/shared/ui/Button'
import { Chip } from '@/shared/ui/Chip'
import { Input } from '@/shared/ui/Input'
import { useSignupForm } from '@/features/auth/hooks'
import type { JoinMode } from '@/features/auth/types'

const MODE_OPTIONS: { mode: JoinMode; title: string; description: string }[] = [
  { mode: 'JOIN_EXISTING', title: '기존 동아리에 참여', description: '대표가 허가하면 이용할 수 있습니다' },
  { mode: 'CREATE_NEW', title: '동아리 새로 만들기', description: '내가 대표가 됩니다' },
]

export function SignupForm() {
  const form = useSignupForm()

  return (
    <div className="flex w-[540px] flex-col gap-[22px] rounded-[22px] border border-[#e8e8e8] bg-white p-[34px] shadow-[0px_8px_20px_-6px_rgba(0,0,0,0.05),0px_1px_3px_0px_rgba(0,0,0,0.05)]">
      <div className="flex flex-col gap-[6px]">
        <p className="text-[26px] font-bold text-[#1f1f1f]">운영해 시작하기</p>
        <p className="text-[13px] text-[#6b6b6b]">두 가지만 적으면 바로 쓸 수 있습니다. 나머지는 쓰면서 채워도 됩니다.</p>
      </div>

      <div className="flex w-full flex-col gap-[10px]">
        <p className="text-[11.5px] font-semibold text-[#737373]">어떻게 시작하시나요</p>
        <div className="flex w-full gap-[10px]">
          {MODE_OPTIONS.map((option) => {
            const active = form.mode === option.mode
            return (
              <button
                key={option.mode}
                type="button"
                onClick={() => form.setMode(option.mode)}
                className={cn(
                  'flex flex-1 flex-col gap-[5px] rounded-[12px] px-[15px] py-[13px] text-left',
                  active ? 'border-2 border-[#404040] bg-[#f9f9f9]' : 'border-[1.5px] border-dashed border-[#dedede] bg-white',
                )}
              >
                <span className="flex items-center gap-[7px]">
                  <span
                    className={cn(
                      'size-[14px] rounded-full border-[1.5px]',
                      active ? 'border-[#404040] bg-[#404040]' : 'border-[#c9c9c9] bg-white',
                    )}
                  />
                  <span className="text-[12.5px] font-semibold text-[#2e2e2e]">{option.title}</span>
                </span>
                <span className="w-[200px] text-[11px] text-[#737373]">{option.description}</span>
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex w-full flex-col gap-[14px]">
        <p className="text-[11.5px] font-semibold text-[#737373]">계정</p>
        <Input
          id="signup-email"
          label="이메일"
          required
          type="email"
          placeholder="name@knu.ac.kr"
          value={form.email}
          onChange={(e) => form.setEmail(e.target.value)}
        />
        <Input
          id="signup-password"
          label="비밀번호"
          required
          type="password"
          placeholder="••••••••"
          hint="8자 이상"
          value={form.password}
          onChange={(e) => form.setPassword(e.target.value)}
        />
        <Input
          id="signup-name"
          label="이름"
          required
          placeholder="박수겸"
          value={form.name}
          onChange={(e) => form.setName(e.target.value)}
        />
      </div>

      <div className="h-px w-full bg-[#ebebeb]" />

      <div className="flex w-full flex-col gap-[14px]">
        <p className="text-[11.5px] font-semibold text-[#737373]">동아리</p>

        {form.mode === 'JOIN_EXISTING' ? (
          <>
            <div className="flex w-full flex-col gap-[6px]">
              <div className="flex w-full items-center gap-[6px]">
                <span className="text-[12px] font-medium text-[#4d4d4d]">동아리 찾기</span>
                <div className="h-px flex-1" />
                <span className="text-[11.5px] font-medium text-[#737373]">🔍</span>
              </div>
              <span className="flex w-full items-center gap-[8px] rounded-[10px] border border-[#d9d9d9] bg-white px-[14px] py-[13px]">
                <input
                  placeholder="컴퓨터학부 학술동아리 ○○"
                  className="w-full flex-1 border-none text-[13px] text-[#262626] outline-none placeholder:text-[#999]"
                  value={form.clubKeyword}
                  onChange={(e) => void form.searchClub(e.target.value)}
                />
              </span>
              {form.clubResults.length > 0 && (
                <ul className="flex w-full flex-col overflow-hidden rounded-[10px] border border-[#e0e0e0]">
                  {form.clubResults.map((club) => (
                    <li key={club.id}>
                      <button
                        type="button"
                        onClick={() => form.selectClub(club)}
                        className="w-full px-[14px] py-[10px] text-left text-[12.5px] text-[#333] hover:bg-[#f7f7f7]"
                      >
                        {club.name}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {form.selectedClub && (
              <div className="flex w-full items-center gap-[10px] rounded-[10px] border border-[#e0e0e0] bg-[#f9f9f9] px-[14px] py-[12px]">
                <div className="size-[26px] shrink-0 rounded-[9px] bg-[#e0e0e0]" />
                <div className="flex flex-col gap-px">
                  <p className="text-[12.5px] font-medium text-[#333]">{form.selectedClub.name}</p>
                  <p className="text-[10.5px] text-[#808080]">
                    {form.selectedClub.category} · 대표 {form.selectedClub.ownerName} · 임원 {form.selectedClub.officerCount}명
                  </p>
                </div>
                <div className="h-px flex-1" />
                <Chip>선택됨</Chip>
              </div>
            )}

            <Input
              id="signup-role"
              label="내 역할"
              placeholder="총무"
              value={form.role}
              onChange={(e) => form.setRole(e.target.value)}
            />

            {form.selectedClub && (
              <div className="w-full rounded-[10px] bg-[#f8f8f8] px-[14px] py-[12px] text-[11.5px] text-[#595959]">
                요청을 보내면 대표 {form.selectedClub.ownerName} 님에게 알림이 갑니다. 허가 전까지는 동아리 자료와 행사에
                접근할 수 없습니다.
              </div>
            )}
          </>
        ) : (
          <Input
            id="signup-new-club-name"
            label="동아리 이름"
            required
            placeholder="컴퓨터학부 학술동아리 ○○"
            value={form.newClubName}
            onChange={(e) => form.setNewClubName(e.target.value)}
          />
        )}
      </div>

      <label className="flex items-center gap-[10px] text-[12px] text-[#666]">
        <input
          type="checkbox"
          className="size-[18px] rounded-[5px] border-[1.5px] border-[#383838] accent-[#383838]"
          checked={form.agreedToTerms}
          onChange={(e) => form.setAgreedToTerms(e.target.checked)}
        />
        이용약관과 개인정보 처리방침에 동의합니다
      </label>

      {form.error && <p className="text-[12px] text-red-600">{form.error}</p>}

      <Button className="w-full" disabled={!form.canSubmit} onClick={() => void form.submit()}>
        {form.submitting ? '보내는 중...' : form.mode === 'JOIN_EXISTING' ? '참여 요청 보내기' : '동아리 만들기'}
      </Button>

      <p className="flex w-full items-center justify-center gap-[6px] text-[12.5px]">
        <span className="text-[#6b6b6b]">이미 계정이 있으신가요?</span>
        <Link to="/login" className="font-semibold text-[#262626] hover:underline">
          로그인
        </Link>
      </p>
    </div>
  )
}
