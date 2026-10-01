// 공용 텍스트 입력. 라벨 + 필수 배지 + 힌트를 함께 그린다.
import type { InputHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  required?: boolean
  hint?: string
}

export function Input({ label, required, hint, id, className, ...props }: InputProps) {
  return (
    <label className="flex w-full flex-col gap-[6px]" htmlFor={id}>
      {label && (
        <span className="flex items-center gap-[6px] text-[12px] font-medium text-[#4d4d4d]">
          {label}
          {required && <span className="text-[10px] font-normal text-[#737373]">필수</span>}
        </span>
      )}
      <span className="flex w-full items-center gap-[8px] rounded-[10px] border border-[#d9d9d9] bg-white px-[14px] py-[13px] focus-within:border-[#a3a3a3]">
        <input
          id={id}
          className={cn(
            'w-full flex-1 border-none text-[13px] text-[#262626] outline-none placeholder:text-[#999]',
            className,
          )}
          {...props}
        />
        {hint && <span className="shrink-0 text-[11.5px] text-[#8c8c8c]">{hint}</span>}
      </span>
    </label>
  )
}
