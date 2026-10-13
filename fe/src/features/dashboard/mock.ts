// 시연용 예시 데이터(?demo). 토리의 판단은 API가 없어 문구를 그대로 적는다.
import type { ToriJudgement } from '@/features/dashboard/types'

export const DEMO_JUDGEMENTS: Record<string, ToriJudgement> = {
  evt_9f2c8a: {
    title: '지금 가장 급한 일',
    reason:
      '납부 마감이 이틀 남았는데 1차 안내 이후 사흘째 추가 입금이 없어요. 계약금 납부일이 명단 확정일보다 하루 뒤라, 미납이 정리되지 않으면 인원 기준 없이 계약금을 넣게 돼요.',
    evidence: [
      { label: '회원 명단 · 32명', source: '운영진 등록 · 지난주' },
      { label: '신청 응답 · 23명', source: '자료 갱신 · 오늘 10:30' },
      { label: '입금 확인 · 28건', source: '입금 마감 전 집계' },
    ],
  },
  evt_c41d07: {
    title: '장소부터 확정해요',
    reason:
      '세미나실 대관 신청 기한이 사흘 남았어요. 참가 모집 공지에 장소와 야간 사용 여부를 적어야 해서, 대관이 늦어지면 모집 공지도 함께 밀려요.',
    evidence: [{ label: '작년 해커톤 참가 · 26명', source: '2025 겨울 해커톤 기록' }],
  },
}
