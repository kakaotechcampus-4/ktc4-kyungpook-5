// ① 모드 선택. 고른 값에 따라 아래 ③(동아리 찾기) 또는 ④(새 동아리 입력)가 나타난다.
import type { SignupMode } from '@/features/auth/types'
import { cn } from '@/shared/lib/cn'

const MODES: Array<{ value: SignupMode; label: string; desc: string }> = [
  { value: 'JOIN', label: '기존 동아리에 참여', desc: '대표가 허가하면 이용할 수 있어요' },
  { value: 'CREATE', label: '동아리 새로 만들기', desc: '내가 대표가 됩니다' },
]

interface ModeCardsProps {
  value: SignupMode
  onChange: (mode: SignupMode) => void
}

export function ModeCards({ value, onChange }: ModeCardsProps) {
  return (
    <div className="flex gap-[10px]">
      {MODES.map((mode) => {
        const selected = mode.value === value
        return (
          <button
            key={mode.value}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(mode.value)}
            className={cn(
              'flex flex-1 items-start gap-[9px] rounded-[12px] border px-[14px] py-[13px] text-left',
              selected ? 'border-blue-600 bg-blue-50' : 'border-soft bg-card hover:bg-bg',
            )}
          >
            <span
              className={cn(
                'mt-[2px] flex size-[15px] shrink-0 items-center justify-center rounded-full border',
                selected ? 'border-blue-600' : 'border-soft',
              )}
            >
              {selected && <span className="size-[7px] rounded-full bg-blue-600" />}
            </span>
            <span className="flex flex-col gap-[3px]">
              <span
                className={cn('text-[12.5px] font-bold', selected ? 'text-blue-700' : 'text-ink')}
              >
                {mode.label}
              </span>
              <span className="text-[10.5px] text-mute">{mode.desc}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
