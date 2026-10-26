# AI 행사계획 테스트 UI

AI 동작 재현과 BE/FE 협의를 위한 독립 로컬 앱이다. 제품 FE 구현은 FE팀이 담당한다. #174에서 테스트 화면·타입·스타일을 이 폴더로 분리했다.

## 실행

저장소 루트에서 터미널 두 개로 실행한다.

```sh
cd be
.venv/bin/python -m app.ai.scripts.planning_playground
```

```sh
cd be/app/ai/tests/ui/planning
npm ci
npm run dev
```

http://127.0.0.1:5174/ 에서 대화한다. UI의 `/__planning-test` 요청은 자체 Vite 프록시로 `127.0.0.1:8011`의 AI API에 전달된다. 키는 `be/.env`에서 서버만 읽는다. 브라우저 대화·조건은 메모리 상태이며 새로고침하면 초기화된다. 샘플 기록은 서버 메모리에만 색인한다.

`fe/` 설치·실행·import·심볼릭 링크가 필요 없다. 테스트 앱 자체 package.json/package-lock.json, node_modules와 빌드 설정을 사용한다. `npm run build`, `npm run lint`로 검증한다. 빌드는 타입·번들 확인용이며 `dist/`의 배포나 실서비스 API를 제공하는 구성이 아니다.

## 코드와 팀 경계

- `src/main.tsx`: 제품 라우터 없이 테스트 화면 하나를 실행.
- `src/pages/PlanningPlaygroundPage.tsx`: 브라우저 임시 세션·API 호출·로딩/오류/재시도.
- `src/features/planning/`: 테스트용 wire 타입·상태 표시 변환·대화/조건/참고 자료 화면.
- `src/shared/`, `src/styles/`: 초기 FE 화면 조각을 참고한 복사본. 출처는 기존 저장소의 `fe/`이며 이제 AI 테스트용으로 독립 관리한다. 자동 동기화하거나 제품 FE가 가져다 써야 하는 공용 라이브러리가 아니다.
- [실행·협의 안내](../../../docs/planning/step-03-ui.md), [입력→코드→결과](../../../docs/planning/walkthrough.md).

FE팀에는 조건의 잠정/보류·현재값/참고값·출처·오류 상태와 필요한 API 계약을 문서로 전달한다. 실제 제품 라우팅·UI·저장/수정 연결은 FE팀이 구현한다. 이 앱의 DTO는 공개 BE 계약을 확정한 것이 아니다.
