# ktc4-team-09
카카오테크 캠퍼스 4기 2단계 팀 프로젝트 — 경북대 5팀

## 로컬 개발 환경 (Docker Compose)

저장소 루트에서 실행하세요.



```bash
docker compose up
```

| 주소 | 내용 |
| --- | --- |
| http://localhost:5173 | FE (Vite 개발 서버) |
| http://localhost:8000/docs | BE Swagger |

- 첫 실행은 이미지 빌드와 `npm ci` 때문에 몇 분 걸립니다. 이후에는 캐시와 볼륨이 남아 빨라집니다.
- `be/app`, `fe/src` 를 수정하면 다시 빌드하지 않아도 반영됩니다.
- 의존성(`be/pyproject.toml`, `fe/package.json`)을 바꿨을 때만 `docker compose up --build` 로 다시 빌드하세요.
- PostgreSQL 은 포함하지 않습니다. 현재 BE 는 mock API 라 DB 에 접속하지 않습니다.
- Docker 없이 각각 띄우려면 `be/README.md`, `fe/README.md` 를 보세요.
