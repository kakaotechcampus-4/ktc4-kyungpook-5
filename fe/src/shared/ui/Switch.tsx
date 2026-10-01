// 켬/끔 토글
import { cn } from '@/shared/lib/cn'

interface SwitchProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label?: string
}

export function Switch({ checked, onChange, label }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-[21px] w-[38px] shrink-0 rounded-full transition-colors',
        checked ? 'bg-[#262626]' : 'bg-[#e0e0e0]',
      )}
    >
      <span
        className={cn(
          'absolute top-[2px] size-[17px] rounded-full bg-white shadow-sm transition-transform',
          checked ? 'translate-x-[19px]' : 'translate-x-[2px]',
        )}
      />
    </button>
  )
}
