import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Button } from '@/shared/ui/Button'
import { Card } from '@/shared/ui/Card'

interface SpotlightProps {
  target: string
  title: string
  description: string
  step: number
  total: number
  onClose: () => void
}

interface TargetRect {
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
}

function viewport() {
  const visible = window.visualViewport
  return {
    width: window.innerWidth,
    height: window.innerHeight,
    left: visible?.offsetLeft ?? 0,
    top: visible?.offsetTop ?? 0,
    visibleWidth: visible?.width ?? window.innerWidth,
    visibleHeight: visible?.height ?? window.innerHeight,
  }
}

function sameRect(previous: TargetRect | null, next: TargetRect | null) {
  if (!previous || !next) return previous === next
  return (Object.keys(previous) as (keyof TargetRect)[]).every(
    (key) => Math.abs(previous[key] - next[key]) < 0.5,
  )
}

/** 공개 DOM의 위치만 읽는다. 클릭·입력·포커스는 실제 화면 동작을 유지한다. */
export function Spotlight({ target, title, description, step, total, onClose }: SpotlightProps) {
  const id = useId().replace(/:/g, '')
  const card = useRef<HTMLDivElement>(null)
  const [fullCardHeight, setFullCardHeight] = useState(160)
  const [measurement, setMeasurement] = useState(() => ({
    target: '',
    rect: null as TargetRect | null,
    viewport: viewport(),
    container: document.body as Element,
  }))

  useEffect(() => {
    let frame = 0
    let observed: Element | null = null
    let scrolled: Element | null = null
    let disposed = false
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(schedule)

    function schedule() {
      if (!disposed && !frame) frame = window.requestAnimationFrame(measure)
    }

    function measure() {
      frame = 0
      if (disposed) return
      const visible = viewport()
      let element: Element | undefined
      try {
        // 동일 selector가 반응형 메뉴에 반복되면 실제 보이는 항목을 선택한다.
        element = [...document.querySelectorAll(target)].find((candidate) => {
          const rect = candidate.getBoundingClientRect()
          const style = window.getComputedStyle(candidate)
          return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden'
        })
      } catch {
        // 화면 전환 중 없거나 잘못된 selector여도 실제 화면 사용을 막지 않는다.
      }
      if (element !== observed) {
        resize?.disconnect()
        if (element) resize?.observe(element)
        observed = element ?? null
      }
      let rect: TargetRect | null = null
      if (element) {
        let bounds = element.getBoundingClientRect()
        if (scrolled !== element) {
          scrolled = element
          if (
            bounds.top < visible.top + 12 ||
            bounds.bottom > visible.top + visible.visibleHeight - 12 ||
            bounds.left < visible.left ||
            bounds.right > visible.left + visible.visibleWidth
          ) {
            element.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'auto' })
            bounds = element.getBoundingClientRect()
          }
        }
        rect = {
          left: bounds.left,
          top: bounds.top,
          right: bounds.right,
          bottom: bounds.bottom,
          width: bounds.width,
          height: bounds.height,
        }
      }
      // native dialog의 top layer 안 target도 가려지지 않도록 같은 layer에 둔다.
      const container = element?.closest('dialog[open]') ?? document.body
      setMeasurement((previous) =>
        previous.target === target &&
        previous.container === container &&
        sameRect(previous.rect, rect) &&
        (Object.keys(visible) as (keyof typeof visible)[]).every(
          (key) => Math.abs(previous.viewport[key] - visible[key]) < 0.5,
        )
          ? previous
          : { target, rect, viewport: visible, container },
      )
    }

    const mutations = new MutationObserver(schedule)
    mutations.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['class', 'style', 'hidden', 'open'],
    })
    window.addEventListener('resize', schedule)
    window.addEventListener('scroll', schedule, true)
    window.visualViewport?.addEventListener('resize', schedule)
    window.visualViewport?.addEventListener('scroll', schedule)
    schedule()
    return () => {
      disposed = true
      window.cancelAnimationFrame(frame)
      resize?.disconnect()
      mutations.disconnect()
      window.removeEventListener('resize', schedule)
      window.removeEventListener('scroll', schedule, true)
      window.visualViewport?.removeEventListener('resize', schedule)
      window.visualViewport?.removeEventListener('scroll', schedule)
    }
  }, [target])

  const rect = measurement.target === target ? measurement.rect : null
  const visible = measurement.viewport
  const margin = 12
  const gap = 14
  const width = Math.min(300, Math.max(0, visible.visibleWidth - margin * 2))
  const minLeft = visible.left + margin
  const maxLeft = Math.max(minLeft, visible.left + visible.visibleWidth - width - margin)
  const minTop = visible.top + margin
  const bottomEdge = visible.top + visible.visibleHeight - margin
  const left = Math.max(minLeft, Math.min(rect?.left ?? maxLeft, maxLeft))
  const compactHeight = 60

  function placement(height: number, useLargerSpace: boolean) {
    if (!rect) return { top: Math.max(minTop, bottomEdge - height) }
    const belowTop = Math.max(minTop, rect.bottom + gap)
    const aboveBottom = Math.min(bottomEdge, rect.top - gap)
    const belowSpace = bottomEdge - belowTop
    const aboveSpace = aboveBottom - minTop
    const canUseBelow = belowSpace >= height
    const canUseAbove = aboveSpace >= height
    const useBelow = canUseBelow && (!useLargerSpace || !canUseAbove || belowSpace >= aboveSpace)
    if (!useBelow && !canUseAbove) return null
    const top = useBelow ? belowTop : aboveBottom - height
    // 위치를 화면 끝으로 clamp해서 대상 위로 밀어 올리지 않는다.
    const overlaps =
      left < rect.right && left + width > rect.left && top < rect.bottom && top + height > rect.top
    return overlaps ? null : { top }
  }

  const fullPlacement = placement(fullCardHeight, false)
  const compactPlacement = !fullPlacement ? placement(compactHeight, true) : null
  const mode = fullPlacement ? 'full' : compactPlacement ? 'compact' : 'hidden'
  const top = fullPlacement?.top ?? compactPlacement?.top ?? minTop
  const container = measurement.target === target ? measurement.container : document.body

  useLayoutEffect(() => {
    const element = card.current
    if (!element || mode !== 'full') return
    const measure = () => {
      const height = element.getBoundingClientRect().height
      setFullCardHeight((previous) => (Math.abs(previous - height) < 0.5 ? previous : height))
    }
    measure()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(element)
    return () => observer?.disconnect()
  }, [title, description, step, total, container, width, mode])

  return createPortal(
    <div data-onboarding-spotlight className="pointer-events-none fixed inset-0 z-40">
      {rect && (
        <svg
          aria-hidden
          className="pointer-events-none fixed left-0 top-0"
          width={visible.width}
          height={visible.height}
          viewBox={`0 0 ${visible.width} ${visible.height}`}
        >
          <defs>
            <mask id={`spotlight-${id}`} maskUnits="userSpaceOnUse">
              <rect width={visible.width} height={visible.height} fill="white" />
              <rect
                x={rect.left - 6}
                y={rect.top - 6}
                width={rect.width + 12}
                height={rect.height + 12}
                rx="12"
                fill="black"
              />
            </mask>
          </defs>
          <rect
            width={visible.width}
            height={visible.height}
            fill="rgba(15, 23, 42, 0.48)"
            mask={`url(#spotlight-${id})`}
          />
          <rect
            x={rect.left - 6}
            y={rect.top - 6}
            width={rect.width + 12}
            height={rect.height + 12}
            rx="12"
            fill="none"
            stroke="#2563eb"
            strokeWidth="3"
          />
        </svg>
      )}
      {mode !== 'hidden' && (
        <div
          ref={card}
          className="pointer-events-auto fixed overflow-y-auto rounded-[18px] shadow-xl"
          style={{ left, top, width, maxHeight: Math.max(0, visible.visibleHeight - margin * 2) }}
        >
          {mode === 'compact' ? (
            <Card
              role="region"
              aria-labelledby={`spotlight-title-${id}`}
              className="flex h-[60px] items-center justify-between gap-2 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="text-[10px] font-bold leading-4 text-blue-700">
                  시작 안내 · {step} / {total}
                </p>
                <h2
                  id={`spotlight-title-${id}`}
                  className="truncate text-[12px] font-bold leading-5 text-ink"
                >
                  {title}
                </h2>
              </div>
              <Button size="sm" variant="ghost" aria-label="하이라이트 안내 끄기" onClick={onClose}>
                끄기
              </Button>
            </Card>
          ) : (
            <Card role="region" aria-labelledby={`spotlight-title-${id}`} className="p-4">
              <p className="mb-1 text-[11px] font-bold text-blue-700">
                시작 안내 · {step} / {total}
              </p>
              <h2 id={`spotlight-title-${id}`} className="text-[14px] font-bold text-ink">
                {title}
              </h2>
              <p className="mt-2 text-[12px] leading-5 text-ink2" aria-live="polite">
                {description}
              </p>
              {!rect && (
                <p className="mt-2 text-[11px] text-mute">안내할 항목을 기다리고 있어요.</p>
              )}
              <Button
                size="sm"
                variant="ghost"
                className="mt-3"
                aria-label="하이라이트 안내 끄기"
                onClick={onClose}
              >
                안내 끄기
              </Button>
            </Card>
          )}
        </div>
      )}
    </div>,
    container,
  )
}
