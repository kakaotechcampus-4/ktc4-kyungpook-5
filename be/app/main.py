"""FastAPI 앱.

auth·clubs·accounting·meetings는 실제 DB로 동작한다(#131, #133, #135). events는
아직 mock이다(이슈 #30, #41). meetings의 판단은 더미다 — 실제 VAD·Whisper·AI
판단 연동은 #135 범위 밖(후속 이슈).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routers import accounting, auth, clubs, events, meetings

app = FastAPI(title="운영해 BE", version="0.1.0")


@app.get("/api/v1/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}

# Vite 개발 서버 기본 포트. 배포 도메인은 배포 구성이 정해질 때 추가한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(clubs.router)
app.include_router(accounting.router)
app.include_router(meetings.router)
app.include_router(events.router)

if get_settings().test_mode:
    from app.routers import test_support

    app.include_router(test_support.router)
