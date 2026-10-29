# Meeting beta backend

This backend adds persistent record indexing, user-confirmed tasks and one-shot
reminders, account-owned Web Push, and the [continuous audio WS](meeting-audio.md).
The backend calls the public `app.ai` boundary for indexing and live meeting lookup.
Meeting lookup requires the AI version that exports `JudgeUtteranceRequest` and
`judge_utterance(..., records=...)`; task extraction requires its independent public
contract below. Missing contracts fail explicitly. The backend does not import
internal AI nodes or replace failures with dummy answers.

## Run locally

From the repository root:

```sh
docker compose -p unyounghae-be-beta up -d db
cd be
uv sync --locked
cp -n .env.example .env
# Set DATABASE_URL, STT and Push fields in the ignored .env as appropriate.
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

Keep `TEST_MODE=false` for the beta. The old HTTP dummy STT and test-support routes
are development fixtures. Access logs are disabled here because the browser WS
uses the existing opaque session token query parameter. One server process owns
the audio connections and reminder poller. DB/files must be preserved between runs.

For Web Push, supply a stable P-256 VAPID key pair: public key is uncompressed X9.62
base64url without padding, private key is a PEM file path or base64 DER accepted by
pywebpush. Keep private files under ignored `be/var/` or another private location.
Set `WEB_PUSH_VAPID_SUBJECT` to your contact URI, and enable
`REMINDER_DISPATCHER_ENABLED=true`. Localhost is sufficient for browser development;
the shared beta needs HTTPS for microphone, Service Worker and Push permissions.

## API examples

All REST calls keep `Authorization: Bearer <opaque access token>`, camelCase,
`{data,meta}` success and `{error:{code,message,fields?}}` failure envelopes.
Use signup/login and `GET /api/v1/me` to discover the account and clubs.

The service is for organization chairs/representatives (`OWNER`) and committee
members (`MANAGER`). There is no service-wide ADMIN role. Ordinary club members
are not service users: legacy `MEMBER` roster rows are retained, but are excluded
from `/me` clubs, business HTTP/WS access, invitations, and reminder assignee and
recipient selection/delivery. Identity signup/login and creating one's first
organization remain available; a new organization makes its creator OWNER.
Account-level Push APIs require at least one active OWNER/MANAGER membership.

- `POST /api/v1/records` multipart `clubId`, `category`, optional `eventId`, `file`.
  Parsing is followed by a real `app.ai.index_record` attempt. `INDEXED` means chunks
  were persisted; `COMPLETED` with `indexError` means parsing succeeded and search
  preparation failed. The response waits for this attempt; 201 is not a background
  job completion promise. `GET /api/v1/records?clubId=...` lists authorized records.
  `POST /api/v1/records/{id}/index` retries indexing; an already INDEXED record is reused.
- `GET /api/v1/clubs/{clubId}/task-suggestions?sourceType=MEETING_TRANSCRIPT&meetingId=...`
  returns review candidates, including evidence source/version, optional suggested
  name, kind, dueDate (date), dueAt/scheduledAt (interpreted instants), unresolvedFields.
  `/accept` remains an acceptance record without creating a reminder.
- `GET /api/v1/clubs/{clubId}/reminder-recipients` returns active account-linked
  OWNER/MANAGER members as `{accountId,memberId,name,role}`. A name alone is not an account ID.
- `POST /api/v1/clubs/{clubId}/task-suggestions/{id}/confirm` requires OWNER/MANAGER:

```json
{
  "expectedVersion": 1,
  "kind": "TASK",
  "title": "회의 자료 정리",
  "description": "확인한 작업 내용",
  "assigneeName": "민수",
  "assigneeAccountId": null,
  "dueAt": "2026-10-20T18:00:00+09:00",
  "timezone": "Asia/Seoul",
  "reminderAt": "2026-10-20T17:00:00+09:00",
  "recipientAccountIds": ["account ID from the picker"]
}
```

For SCHEDULE, send `scheduledAt` instead of `dueAt`. The user confirms all values;
the backend never infers recipients from a person's name or adds the assignee to
recipients implicitly. Instants require an explicit offset, are stored in UTC, and
the IANA timezone is retained for display. Both item and reminder must be future;
reminderAt cannot be after the item time. Foreign/inactive recipients return 422.
Stale source evidence and optimistic version conflicts return 409. Exact retries
return the same confirmed item/reminder; a different body cannot re-confirm the source.

`GET /api/v1/clubs/{clubId}/confirmed-tasks?meetingId=...` (optional suggestionId)
and `GET /.../confirmed-tasks/{id}` restore confirmed items with nested reminder.
`PATCH /.../{id}` sends the full confirmation fields plus the current expectedVersion
and updates the existing reminder. `POST /.../{id}/cancel {"expectedVersion":1}`
cancels a pending reminder. SENDING returns 409; already accepted Push cannot be recalled.

## Push and scheduling semantics

`GET /api/v1/push/vapid-public-key` returns `{data:{publicKey},meta:null}`.
After explicit browser permission, POST the browser `PushSubscription.toJSON()` to
`/api/v1/push/subscriptions`. GET lists only one's subscriptions; DELETE `/{id}`
removes one's subscription. Another account cannot take over an existing endpoint.
`POST /api/v1/push/test {"subscriptionId":"..."}` targets only the logged-in account.

Test responses expose SERVICE_ACCEPTED / PARTIAL_FAILURE / FAILED with device
acceptedCount, failedCount and invalidatedCount. Reminder states are PENDING,
SENDING, SERVICE_ACCEPTED, FAILED, CANCELLED; failedCount/lastError can be present
even when at least one device was accepted. 404/410 invalidates that subscription.
The dispatcher rechecks active OWNER/MANAGER organization membership before sending and never broadcasts
to unspecified members. The payload deep link is `/meetings?taskId=...&clubId=...`.

Service acceptance does not prove a notification was displayed. Browser permission,
OS settings, network, TTL and device availability affect delivery; exact on-time
arrival is not guaranteed. No subscriptions or missing keys are explicit failures.
This is a small single-process poller. If a process exits during SENDING, it does
not resend automatically because the service may already have accepted the Push;
the visible state remains uncertain. There is no retry/lease platform in this slice.

## AI boundary

`PostgresRecordSearch(club_id)` implements the existing public RecordSearchPort.
Each query uses a short session, applies organization plus INDEXED/category/event
filters in PostgreSQL, and returns actual stored text/locations with cosine scores.
The caller's injected organization cannot be widened by a query.

Live meeting integration uses these public exports from `app.ai`:

- `JudgeUtteranceRequest` and `judge_utterance(request, records=RecordSearchPort)`.
  The AI facade owns its existing meeting lookup and retrieval flow; BE does not
  reimplement retrieval or answer generation. The local BE branch's older AI must
  be integrated with the version supplying this public contract before use.
- The independent extraction contract, `TaskExtractionRequest` and
  `extract_task_suggestions(request)`, returns
  `.suggestions` drafts with kind, title, optional description/suggested_assignee,
  due_date/due_at/scheduled_at, unresolved_fields. No account assignment or execution.

Both requests carry `meeting_id`, `club_id`, `utterance` (utterance_id, seq, version,
text, aware started_at/ended_at), and ordered `context` (previous four utterances).
Extraction also receives `timezone:"Asia/Seoul"` and aware `occurred_at`. Its call
is independent of RAG/NONE and still runs if lookup fails. The backend owns evidence
IDs, confirmation, membership, storage and delivery. Missing public contracts yield
`AI_PUBLIC_CONTRACT_UNAVAILABLE`. Lookup failure is stored as ERROR/FAILED,
not NONE. A successful independent candidate can coexist with a PARTIAL decision.
Agent jobs retain safe per-feature errors and candidate IDs; no provider secrets
or exception bodies are returned.

## Verification boundaries

Focused tests exercise real PostgreSQL, HTTP/WS, scope, idempotent confirmation,
updates/cancellation, persistent pgvector queries, subscription ownership and
dispatcher behavior. Test providers replace AI/STT/external Push HTTP; transport
tests also exercise real encryption and VAPID signing before intercepting HTTP.
These checks do not establish actual gateway quality or device display. Verify one
real record, spoken utterance, user confirmation and designated-device notification
with configured providers and browser subscription before claiming that full flow.
