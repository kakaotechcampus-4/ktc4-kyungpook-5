// 토리 캐릭터. v11 「0·기준」의 벡터 스탠드인이며, 원본 일러스트가 나오면 이 파일만 바꾼다.
import { cn } from '@/shared/lib/cn'

interface ToriProps {
  // px. 시안 기준 상태 화면 104 · 빈 상태 96 · AI 블록 56 · 안내 박스 36 · 로고 30 · 칩 26
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
      <circle cx="12.48" cy="50.88" r="12.48" fill="#7B9BD4" />
      <circle cx="83.52" cy="50.88" r="12.48" fill="#7B9BD4" />
      <ellipse
        cx="46.5578"
        cy="15.9201"
        rx="7.2"
        ry="14.4"
        transform="rotate(18 46.5578 15.9201)"
        fill="#7B9BD4"
      />
      <ellipse cx="48" cy="56.64" rx="37.9" ry="35.02" fill="#FAF8F4" stroke="#DFDDD7" />
      <ellipse cx="24.48" cy="59.52" rx="6.24" ry="3.84" fill="#F3C9CE" />
      <ellipse cx="71.52" cy="59.52" rx="6.24" ry="3.84" fill="#F3C9CE" />
      <ellipse cx="36.96" cy="49.44" rx="4.32" ry="6.24" fill="#2B3E63" />
      <ellipse cx="59.04" cy="49.44" rx="4.32" ry="6.24" fill="#2B3E63" />
    </svg>
  )
}
