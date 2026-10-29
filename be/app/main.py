"""FastAPI 앱.

회의 WS·자료 색인·확정 항목/예약·Push는 실제 저장과 외부 호출 경계로 연결한다.
회의 AI 공개 facade와 공급자 설정이 없으면 명시 실패한다. 기존 행사 mock,
OCR·Discord·TEST_MODE fixture의 구현 상태는 docs/meeting-beta.md에서 구분한다.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routers import (
    accounting,
    agent,
    auth,
    clubs,
    discord,
    events,
    meetings,
    records,
    tasks,
    confirmed_tasks,
    reminder_recipients,
    push,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = asyncio.Event()
    worker = None
    if get_settings().reminder_dispatcher_enabled:
        from app.services.push_service import run_reminder_dispatcher
        worker = asyncio.create_task(run_reminder_dispatcher(stop))
    try:
        yield
    finally:
        stop.set()
        if worker is not None:
            await worker


app = FastAPI(title="운영해 BE", version="0.1.0", lifespan=lifespan)


@app.get("/api/v1/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}

# Vite 개발 서버 기본 포트. 배포 도메인은 배포 구성이 정해질 때 추가한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(clubs.router)
app.include_router(accounting.router)
app.include_router(meetings.router)
app.include_router(records.router)
app.include_router(agent.router)
app.include_router(discord.router)
app.include_router(tasks.router)
app.include_router(confirmed_tasks.router)
app.include_router(reminder_recipients.router)
app.include_router(push.router)
app.include_router(events.router)

if get_settings().test_mode:
    from app.routers import test_support

    app.include_router(test_support.router)
