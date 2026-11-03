import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Card } from '@/shared/ui/Card'
import { cn } from '@/shared/lib/cn'

export type PillKind =
  'connecting' | 'recording' | 'paused' | 'off' | 'finalizing' | 'ended' | 'failed' | 'silent'

const PILL_CLASS: Record<PillKind, string> = {
  connecting: 'bg-chip text-ink2',
  recording: 'bg-failed-bg text-failed',
  paused: 'bg-pending-bg text-pending',
  off: 'bg-pending-bg text-pending',
  finalizing: 'bg-chip text-ink2',
  ended: 'bg-chip text-ink2',
  failed: 'bg-failed-bg text-failed',
  silent: 'bg-pending-bg text-pending',
}

export function StatusPill({ kind, children }: { kind: PillKind; children: ReactNode }) {
  const dot = kind === 'recording' || kind === 'paused' || kind === 'off'
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1.5 rounded-[8px] px-[11px] py-[6px] text-[11.5px] font-bold whitespace-nowrap',
        PILL_CLASS[kind],
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={cn(
            'size-[7px] rounded-full',
            kind === 'recording'
              ? 'animate-pulse bg-[#c4574d] motion-reduce:animate-none'
              : 'bg-pending',
          )}
        />
      )}
      {children}
    </span>
  )
}

export function MeetingHeader({
  title,
  pills,
  meta,
  actions,
}: {
  title: string
  pills: ReactNode
  meta: string
  actions?: ReactNode
}) {
  return (
    <>
      <nav aria-label="경로" className="flex items-center gap-2.5 text-caption text-ink2">
        <Link
          to="/meetings"
          aria-label="회의 첫 화면으로"
          className="rounded-[8px] border border-line px-2.5 py-1 hover:bg-bg"
        >
          ‹
        </Link>
        <Link to="/meetings" className="hover:underline">
          회의
        </Link>
        <span aria-hidden>/</span>
        <span className="truncate font-bold text-ink">{title}</span>
      </nav>
      <Card className="flex flex-wrap items-center justify-between gap-4 px-7 py-6">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="min-w-0 break-words text-h1">{title}</h1>
            {pills}
          </div>
          <p className="mt-3 text-caption text-ink2">{meta}</p>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </Card>
    </>
  )
}

const BANNER_CLASS = {
  pending: 'border-pending-line bg-pending-bg text-pending',
  failed: 'border-failed-line bg-failed-bg text-failed',
  info: 'border-blue-200 bg-blue-50 text-blue-700',
}

export function MeetingBanner({
  tone,
  title,
  children,
  action,
}: {
  tone: keyof typeof BANNER_CLASS
  title?: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div
      role={tone === 'info' ? 'status' : 'alert'}
      className={cn(
        'flex flex-wrap items-center justify-between gap-3 rounded-[12px] border px-4 py-3 text-caption',
        BANNER_CLASS[tone],
      )}
    >
      <div className="min-w-0">
        {title && <p className="font-bold">{title}</p>}
        {children && <p className={title ? 'mt-0.5' : 'font-medium'}>{children}</p>}
      </div>
      {action}
    </div>
  )
}
