import type { Decision, Meeting, Suggestion, Transcript } from './types'
export const fixtureMeeting: Meeting = {
  id: 'fixture-meeting',
  clubId: 'fixture-club',
  title: '가을 워크숍 준비 회의',
  language: 'ko-KR',
  status: 'RECORDING',
  startedAt: '2026-10-19T05:00:00Z',
  endedAt: null,
  version: 1,
}
const transcript = (id: string, seq: number, text: string, minute: number): Transcript => ({
  id,
  sourceId: id,
  sourceVersion: 1,
  seq,
  text,
  final: true,
  version: 1,
  speakerLabel: null,
  startMs: minute * 60000,
  endMs: minute * 60000 + 5000,
  decisionJobId: null,
  createdAt: `2026-10-19T05:0${minute}:00Z`,
  modifiedAt: `2026-10-19T05:0${minute}:00Z`,
})
export const fixtureTranscripts = [
  transcript('f1', 1, '작년 워크숍은 어디에서 했지? 장소 기록을 찾아 줘.', 0),
  transcript('f2', 2, '자료 정리는 내일 오후 세 시까지 끝내자. 수겸님이 맡아 주세요.', 1),
  transcript('f3', 3, '', 2),
  transcript('f4', 4, '지난 회의에서 간식 예산을 정했었나?', 3),
]
const decision = (
  id: string,
  source: string,
  kind: 'ANSWER' | 'NOT_FOUND',
  minute: number,
  output: string | null,
): Decision => ({
  id,
  jobId: `job-${id}`,
  sourceType: 'MEETING_TRANSCRIPT',
  meetingId: 'fixture-meeting',
  connectionId: null,
  sources: [{ sourceId: source, sourceVersion: 1 }],
  status: 'SUCCEEDED',
  route: 'RAG',
  kind,
  reasonSummary: null,
  question: null,
  output,
  citations:
    kind === 'ANSWER'
      ? [
          {
            fileName: '2025 워크숍 회고.pdf',
            location: { label: '2쪽 · 장소' },
            text: '워크숍 장소는 교내 세미나실이었다.',
          },
        ]
      : [],
  toolCalls: [],
  modelVersion: '개발 fixture',
  policyVersion: 'fixture',
  createdAt: `2026-10-19T05:0${minute}:30Z`,
})
export const fixtureDecisions = [
  decision('d1', 'f1', 'ANSWER', 2, '지난 워크숍은 교내 세미나실에서 진행했어요.'),
  decision('d2', 'f4', 'NOT_FOUND', 3, null),
]
export const fixtureSuggestion: Suggestion = {
  id: 'fixture-task',
  decisionId: 'd1',
  sourceType: 'MEETING_TRANSCRIPT',
  title: '워크숍 자료 정리',
  description: '내일 오후 세 시까지 자료를 정리한다.',
  suggestedAssignee: '수겸',
  dueDate: '2026-10-20',
  evidence: [{ sourceId: 'f2', sourceVersion: 1 }],
  status: 'PROPOSED',
  version: 1,
  acceptedBy: null,
  acceptedAt: null,
  createdAt: '2026-10-19T05:01:10Z',
}
