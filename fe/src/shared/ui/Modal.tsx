// 모달 공통 틀: 헤더(제목·칩·부제·✕) / 본문 / 하단(안내 문구 + 버튼).
// 브라우저 <dialog>를 써서 Esc 닫기·포커스 가두기·배경 막기는 브라우저에 맡긴다.
import { useEffect, useRef, type ReactNode } from 'react'
import { cn } from '@/shared/lib/cn'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  chip?: ReactNode
  subtitle?: string
  children: ReactNode
  // 하단 왼쪽 안내 문구(예: "답변하면 바로 완료로 가요")
  footerNote?: string
  // 하단 오른쪽 버튼들. 없으면 하단을 그리지 않는다.
  footer?: ReactNode
  // 시안 기준 600~660px
  width?: number
  className?: string
}

export function Modal({
  open,
  onClose,
  title,
  chip,
  subtitle,
  children,
  footerNote,
  footer,
  width = 640,
  className,
}: ModalProps) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      // open이 이미 false면 부모가 닫은 것이라 다시 부르지 않음
      // Esc처럼 브라우저가 직접 닫았을 때만 onClose를 부름
      onClose={() => open && onClose()}
      // 배경(= dialog 자신)을 누르면 닫는다. 안쪽 클릭은 target이 자식이라 걸리지 않는다.
      onClick={(e) => e.target === e.currentTarget && onClose()}
      style={{ width }}
      className={cn(
        'm-auto max-h-[calc(100vh-64px)] max-w-[calc(100vw-32px)] flex-col overflow-hidden rounded-[20px] bg-card p-0 text-ink shadow-[0_12px_36px_rgba(0,0,0,0.18)] backdrop:bg-backdrop open:flex',
        className,
      )}
    >
      <header className="flex flex-col gap-[7px] border-b border-line pt-[26px] pr-[22px] pb-[18px] pl-[28px]">
        <div className="flex items-center justify-between gap-[12px]">
          <div className="flex min-w-0 items-center gap-[10px]">
            <h2 className="text-[20px] font-bold">{title}</h2>
            {chip}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="shrink-0 rounded-[9px] bg-bg px-[9px] py-[6px] text-[12px] font-medium text-ink2 hover:bg-line"
          >
            ✕
          </button>
        </div>
        {subtitle && <p className="text-[12px] text-mute">{subtitle}</p>}
      </header>

      <div className="flex flex-1 flex-col gap-[15px] overflow-y-auto px-[28px] pt-[22px] pb-[24px]">
        {children}
      </div>

      {footer && (
        <footer className="flex items-center justify-between gap-[12px] border-t border-line pt-[16px] pr-[24px] pb-[20px] pl-[28px]">
          <p className="text-caption text-mute">{footerNote}</p>
          <div className="flex gap-[8px]">{footer}</div>
        </footer>
      )}
    </dialog>
  )
}
