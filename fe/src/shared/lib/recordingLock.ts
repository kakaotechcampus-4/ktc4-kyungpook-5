// 회의를 녹음하는 동안 사이드바의 소속 선택을 잠근다.
// 소속이 바뀌면 회의 화면이 새로 그려져 녹음이 확인 없이 끊긴다.
import { create } from 'zustand'

interface RecordingLockState {
  recording: boolean
  setRecording: (recording: boolean) => void
}

export const useRecordingLock = create<RecordingLockState>((set) => ({
  recording: false,
  setRecording: (recording) => set({ recording }),
}))
