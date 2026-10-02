// 토스트: 승인·저장 직후 화면 아래에 잠깐 떴다 사라진다. 띄우는 쪽은 shared/lib/toast.
import { useToastStore, type ToastItem, type ToastKind } from '@/shared/lib/toast'

const ICON: Record<ToastKind, { bg: string; mark: string }> = {
  done: { bg: 'bg-done', mark: '✓' },
  progress: { bg: 'bg-blue-400', mark: '●' },
  error: { bg: 'bg-failed', mark: '!' },
}

export function ToastView({ kind, title, desc, action }: Omit<ToastItem, 'id'>) {
  const icon = ICON[kind]
  return (
    <div
      role={kind === 'error' ? 'alert' : 'status'}
      className="flex w-[420px] max-w-full items-center justify-between gap-[12px] rounded-[14px] bg-ink py-[14px] pr-[14px] pl-[18px] shadow-[0_8px_24px_rgba(0,0,0,0.22)]"
    >
      <div className="flex min-w-0 flex-1 items-center gap-[12px]">
        <span
          className={`flex size-[26px] shrink-0 items-center justify-center rounded-full font-bold text-white ${icon.bg} ${kind === 'progress' ? 'text-[9px]' : 'text-[12px]'}`}
        >
          {icon.mark}
        </span>
        <div className="flex min-w-0 flex-col gap-[3px]">
          <p className="text-[13.5px] font-bold text-white">{title}</p>
          {desc && <p className="truncate text-caption text-toast-sub">{desc}</p>}
        </div>
      </div>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="shrink-0 rounded-[9px] bg-toast-btn px-[13px] py-[8px] text-[12px] font-bold text-white hover:bg-ink2"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

export function Toaster() {
  const items = useToastStore((s) => s.items)
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[24px] z-50 flex flex-col items-center gap-[8px] px-[16px]">
      {items.map(({ id, ...item }) => (
        <div key={id} className="pointer-events-auto max-w-full">
          <ToastView {...item} />
        </div>
      ))}
    </div>
  )
}
