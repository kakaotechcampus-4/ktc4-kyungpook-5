// 이니셜 원형 아바타
import { cn } from '@/shared/lib/cn'

interface AvatarProps {
  name: string
  size?: 'sm' | 'md' | 'lg'
  emphasis?: boolean
  className?: string
}

const SIZE_CLASS = {
  sm: 'size-[24px] text-[10px]',
  md: 'size-[26px] text-[11px]',
  lg: 'size-[72px] text-[24px]',
}

export function Avatar({ name, size = 'md', emphasis, className }: AvatarProps) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full font-bold',
        emphasis ? 'bg-[#404040] text-[#fafafa]' : 'bg-[#dbdbdb] text-[#595959]',
        SIZE_CLASS[size],
        className,
      )}
    >
      {name.slice(0, 1)}
    </span>
  )
}
