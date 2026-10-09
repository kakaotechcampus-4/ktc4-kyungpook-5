// 원형 아바타. 이름이 있으면 첫 글자를 넣는다.
import { cn } from '@/shared/lib/cn'

interface AvatarProps {
  name?: string
  size?: number
  className?: string
}

export function Avatar({ name, size = 28, className }: AvatarProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full bg-blue-100 font-bold text-blue-700',
        className,
      )}
      style={{ width: size, height: size, fontSize: size * 0.4 }}
    >
      {name?.slice(0, 1)}
    </span>
  )
}
