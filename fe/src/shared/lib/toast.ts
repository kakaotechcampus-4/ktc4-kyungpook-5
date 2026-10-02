// 토스트 상태. 어디서든 toast.show({...})로 띄우고, <Toaster />(shared/ui/Toast)가 그린다.
import { create } from 'zustand'

// done: 승인 완료·저장됨 · progress: 처리 중(자동으로 안 사라짐) · error: 실패
export type ToastKind = 'done' | 'progress' | 'error'

export interface ToastItem {
  id: string
  kind: ToastKind
  title: string
  desc?: string
  // 오른쪽 버튼(예: 보기, 다시 시도)
  action?: { label: string; onClick: () => void }
}

const DURATION_MS = 4000

interface ToastStore {
  items: ToastItem[]
  show: (item: Omit<ToastItem, 'id'> & { id?: string }) => string
  dismiss: (id: string) => void
}

export const useToastStore = create<ToastStore>((set, get) => ({
  items: [],
  // 같은 id로 다시 부르면 바꿔 끼운다. "보내는 중" → "승인했어요"처럼 이어 쓸 때.
  show: ({ id = crypto.randomUUID(), ...rest }) => {
    set((s) => ({ items: [...s.items.filter((t) => t.id !== id), { id, ...rest }] }))
    if (rest.kind !== 'progress') {
      setTimeout(() => {
        if (get().items.find((t) => t.id === id)?.kind !== 'progress') get().dismiss(id)
      }, DURATION_MS)
    }
    return id
  },
  dismiss: (id) => set((s) => ({ items: s.items.filter((t) => t.id !== id) })),
}))

export const toast = {
  show: (item: Parameters<ToastStore['show']>[0]) => useToastStore.getState().show(item),
  dismiss: (id: string) => useToastStore.getState().dismiss(id),
}
