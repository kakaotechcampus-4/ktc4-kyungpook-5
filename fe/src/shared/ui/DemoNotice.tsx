import { Link, useLocation } from 'react-router-dom'
import { demoNavigationPath, supportsDemoPath } from '@/shared/lib/demo'

export function DemoNotice() {
  const { pathname, search, hash } = useLocation()
  const realPath = demoNavigationPath(pathname, search, hash)
  if (!realPath || !supportsDemoPath(pathname)) return null

  return (
    <aside
      role="note"
      aria-label="데모 모드 안내"
      className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-blue-200 bg-blue-50 px-4 py-3 text-caption text-blue-900"
    >
      <div className="min-w-0">
        <p className="font-bold">데모 모드 · 예시 데이터</p>
        <p className="mt-1 text-blue-800">
          실제 서비스와 분리된 화면이에요. 예약·알림·외부 발송은 실행되지 않아요.
        </p>
      </div>
      <Link className="shrink-0 font-semibold underline underline-offset-2" to={realPath}>
        실제 서비스로 이동
      </Link>
    </aside>
  )
}
