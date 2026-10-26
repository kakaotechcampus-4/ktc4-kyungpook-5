import type { StepPhase } from './types'

// 테스트용 묶음 안내 문구. 모델 생성 결과와 구분한다.
export const PHASE_DESC: Record<StepPhase, string> = {
  '사전 준비': '인원과 예산의 윤곽을 잡습니다',
  '모집 · 확정': '자리를 잡고 참가비를 걷습니다',
  '행사 진행 · 마무리': '돈을 정산하고 기록을 남깁니다',
}
