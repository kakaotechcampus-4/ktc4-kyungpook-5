// 상단바 + 사이드바 + 본문 자리
import { Outlet } from 'react-router-dom'
import { TopBar } from '@/app/layout/TopBar'
import { Sidebar } from '@/app/layout/Sidebar'

export function AppLayout() {
  return (
    <div className="flex min-h-screen w-full flex-col bg-[#f6f6f6]">
      <TopBar
        right={
          <div className="rounded-[8px] border border-dashed border-[#e6e6e6] bg-[#f7f7f7] px-[20px] py-[9px] text-[11px] text-[#999]">
            추후 네비게이션 영역
          </div>
        }
      />
      <div className="flex flex-1 items-start">
        <Sidebar />
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
