// 서버 응답 타입. schema.d.ts(생성 파일)의 긴 경로에 이름만 붙여 둔 곳이다.
//
// schema.d.ts는 BE의 openapi.json에서 뽑는다. 손으로 고치지 않는다.
//   npm run gen:api-types        (BE가 http://localhost:8000 에 떠 있어야 한다)
//
// 서버를 안 띄우고 뽑으려면 be/ 에서 아래로 openapi.json을 덤프한 뒤 그 파일을 넘긴다.
//   uv run python -c "import json;from app.main import app;print(json.dumps(app.openapi()))"
//
// 이름은 BE 스키마 그대로 둔다(EventOut 등). FE에서 다시 지어 붙이면 BE가 바꿨을 때
// 어느 타입이 달라졌는지 추적이 끊긴다.
import type { components } from '@/shared/api/schema'

type Schemas = components['schemas']

// enum — 값이 곧 API 코드다(be/app/core/enums.py의 StrEnum).
export type EventStatus = Schemas['EventStatus']
export type ActionStatus = Schemas['ActionStatus']
export type ActionType = Schemas['ActionType']
export type StepActor = Schemas['StepActor']
export type StepState = Schemas['StepState']
export type MemberRole = Schemas['MemberRole']

// GET /events
export type EventOut = Schemas['EventOut']
export type StepProgressOut = Schemas['StepProgressOut']

// GET /events/{eventId}/steps
export type StepOut = Schemas['StepOut']
export type DoneActionOut = Schemas['DoneActionOut']
export type RemainingActionOut = Schemas['RemainingActionOut']

// GET /events/{eventId}/actions
export type ActionOut = Schemas['ActionOut']
export type ActionOption = Schemas['ActionOption']
export type ResolvedBy = Schemas['ResolvedBy']
