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
        'relative h-[23px] w-[40px] shrink-0 rounded-full transition-colors',
        checked ? 'bg-blue-600' : 'bg-soft',
      )}
    >
      <span
        className={cn(
          'absolute top-[2px] left-0 size-[19px] rounded-full bg-white shadow-sm transition-transform',
          checked ? 'translate-x-[19px]' : 'translate-x-[2px]',
        )}
      />
    </button>
  )
}
