// S0/S1 공용 상단바 — 로고 + "다른 화면으로" 링크
import { Link } from 'react-router-dom'

interface AuthHeaderProps {
  promptText: string
  linkText: string
  linkTo: string
}

export function AuthHeader({ promptText, linkText, linkTo }: AuthHeaderProps) {
  return (
    <header className="flex w-full items-center gap-[12px] border-b border-[#e8e8e8] bg-white px-[24px] py-[14px]">
      <div className="size-[28px] shrink-0 rounded-[9px] bg-[#262626]" />
      <p className="text-[16px] font-bold text-[#212121]">운영해</p>
      <div className="h-px flex-1" />
      <p className="text-[12px] text-[#737373]">{promptText}</p>
      <Link
        to={linkTo}
        className="rounded-[10px] border border-[#dbdbdb] bg-white px-[14px] py-[11px] text-[13px] font-medium text-[#525252] hover:bg-[#f7f7f7]"
      >
        {linkText}
      </Link>
    </header>
  )
}
