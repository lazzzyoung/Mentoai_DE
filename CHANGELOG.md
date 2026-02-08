# 변경 이력

이 문서는 주요 변경 사항을 기록합니다.

## [Unreleased]

### 문서
- `README.md`를 현재 코드/실행 흐름 기준으로 재정리.
- 설계 문서를 `DESIGN.md`(한글)로 정리하고 README에 링크 추가.
- 기존 `DESIGN_DOC.md` 제거.
- 간결한 Poe Task(`dev`, `run`, `up`, `mig`, `rev` 등) 사용법 문서화.

### 웹/UI 라우팅
- `main.py`의 중복 웹 라우트를 제거하고 `server/app/api/routes/web.py`로 일원화.
- HTMX 요청 시 partial 레이아웃(`layout/partial.html`)을 사용하도록 렌더링 경로 정리.
- `POST /api/action` 기본 경로와 `POST /api/web/action` 호환 경로를 함께 유지.

### 개발 도구
- Poe Task에 간결한 alias(`env`, `sync`, `dev`, `run`, `mig`, `rev`, `up/down/ps/logs`, `pw/pd/pb`, `brz/slv/gld`) 추가.
- 기존 긴 이름 task는 호환을 위해 유지.

### 정리
- 헬스 체크 메시지 표현 정리.
- 템플릿 내 과도한 설명성 주석/문구 정리.

## [0.1.0] - 2026-02-08

### 추가
- 비동기 DB 세션 정규화 테스트 및 앱 import 스모크 테스트 추가.
- RAG/Spark 핵심 헬퍼 로직 단위 테스트 추가.
- GitHub Actions CI(`uv run poe check`) 추가.
- Alembic 초기 마이그레이션 스크립트 추가.

### 변경
- API 엔드포인트를 `/api/v1`로 통합.
- 로드맵 응답을 구조화 스키마(`server/app/schemas/v1.py`)로 정리.
- 블로킹 LLM/벡터 스토어 호출을 스레드풀로 오프로딩해 비동기 안정성 개선.
- Docker Compose의 `version` 필드 및 아키텍처 고정 설정 제거.

### 제거
- `server/app/api/routes/v2.py`, `server/app/api/routes/v3.py`
- `server/app/schemas/v2.py`, `server/app/schemas/v3.py`
