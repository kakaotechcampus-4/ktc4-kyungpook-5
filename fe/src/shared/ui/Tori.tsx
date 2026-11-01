// 토리: 화면 안에서 함께 일하는 작은 디지털 동반자.
import { cn } from '@/shared/lib/cn'

interface ToriProps {
  size?: number
  className?: string
}

export function Tori({ size = 56, className }: ToriProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      fill="none"
      aria-hidden
      className={cn('shrink-0', className)}
    >
      <path d="M25 20h46v5h6v46h-6v5H25v-5h-6V25h6v-5Z" fill="#E7EDF8" />
      <path d="M25 20h46v5h6v46h-6v5H25v-5h-6V25h6v-5Z" stroke="#526E9F" strokeWidth="3" strokeLinejoin="round" />
      <path d="M30 29h36v31H30z" fill="#354E79" />
      <path d="M38 40v5M58 40v5" stroke="#fff" strokeWidth="4" strokeLinecap="round" />
      <path d="M43 51c3 2.5 7 2.5 10 0" stroke="#C8D8F2" strokeWidth="2.5" strokeLinecap="round" />
      <path d="M31 75v5h8v-5M57 75v5h8v-5" stroke="#526E9F" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M19 44h-5v13h5M77 44h5v13h-5" stroke="#526E9F" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M35 68h26" stroke="#A7BBDD" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}
