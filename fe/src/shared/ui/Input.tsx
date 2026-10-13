// 공용 입력. 라벨 + 입력칸(Input) / 여러 줄 입력 + 글자 수(Textarea).
import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/cn'

const FIELD_CLASS =
  'w-full rounded-[11px] border border-soft bg-bg px-[15px] py-[12px] text-[13.5px] text-ink outline-none placeholder:text-mute focus:border-blue-600 focus:bg-card'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  // 무엇이 잘못됐는지 한 줄. 넣으면 라벨·테두리가 빨개지고 아래에 줄이 붙는다.
  error?: string
}

export function Input({ label, error, className, ...props }: InputProps) {
  const input = (
    <input
      className={cn(FIELD_CLASS, error && 'border-failed bg-failed-bg/30', className)}
      {...props}
    />
  )
  if (!label && !error) return input
  return (
    <label className="flex w-full flex-col gap-[7px]">
      {label && (
        <span className={cn('text-[11.5px] font-bold', error ? 'text-failed' : 'text-ink2')}>
          {label}
        </span>
      )}
      {input}
      {error && (
        <span className="flex items-center gap-[6px] text-[11px] font-medium text-failed">
          <span aria-hidden>!</span>
          {error}
        </span>
      )}
    </label>
  )
}

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
}

// maxLength가 있으면 「112 / 500자」 카운터를 라벨 오른쪽에 붙인다.
export function Textarea({ label, maxLength, value, className, ...props }: TextareaProps) {
  const count = typeof value === 'string' ? value.length : 0
  return (
    <label className="flex w-full flex-col gap-[10px]">
      {(label || maxLength) && (
        <span className="flex items-center justify-between">
          <span className="text-h3 text-ink">{label}</span>
          {maxLength && (
            <span className="text-[11px] text-mute">
              {count} / {maxLength}자
            </span>
          )}
        </span>
      )}
      <textarea
        maxLength={maxLength}
        value={value}
        className={cn(FIELD_CLASS, 'min-h-[100px] resize-none leading-[21px]', className)}
        {...props}
      />
    </label>
  )
}
