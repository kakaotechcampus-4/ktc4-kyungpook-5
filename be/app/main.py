"""FastAPI 앱.

현재 등록된 엔드포인트는 DB 없이 고정 응답을 내는 mock이다 (이슈 #30).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.exceptions import register_exception_handlers
from app.routers import events

app = FastAPI(title="운영해 BE", version="0.1.0")

# Vite 개발 서버 기본 포트. 배포 도메인은 배포 구성이 정해질 때 추가한다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(events.router)
