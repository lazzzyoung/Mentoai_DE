# MentoAI_DE Agent Guide

## Purpose
이 저장소는 일반 구직자에게 맞춤 공고 추천과 공고별 상세 분석을 제공하는 FastAPI 서비스다.

현재 아키텍처는 경량 운영을 위해 **SQLModel + SQLite + Hybrid RAG(FTS5 + semantic rerank)** 중심으로 구성된다.

---

## Current Product Scope

### User-facing pages
- `/` : 메인 홈
- `/jobs/recommend` : 추천 + 인라인 상세 분석
- `/jobs/detail` or `/jobs/detail/{job_id}?user_id={user_id}` : 단일 공고 분석

### Active APIs
- `POST /api/v3/auth/quick-login`
- `POST /api/v3/jobs/recommend/{user_id}`
- `POST /api/v3/jobs/{job_id}/analyze/{user_id}`

### API1 core flow (반드시 유지)
1. 사용자 ID 입력
2. SQLite에서 사용자 프로필 조회
3. FTS5 후보 검색 + semantic rerank
4. 상위 공고 반환

---

## Key Files

| File | Description |
|---|---|
| `pyproject.toml` | 의존성/ruff/pytest/poe task |
| `.env.example` | 필수 환경 변수 템플릿 |
| `server/app/main.py` | FastAPI 앱 생성, 정적 라우트, `/health` |
| `server/app/api/routes/v3.py` | 공식 v3 API 엔드포인트 |
| `server/app/services/rag_v3_service.py` | 추천/상세/간편로그인 로직 |
| `server/app/services/hybrid_retriever.py` | FTS5 + semantic 재랭크 |
| `server/app/services/crawler_pipeline.py` | 순수 Python 크롤링/적재 |
| `server/app/services/scheduler_service.py` | APScheduler 주기 실행 |
| `server/app/repositories/user_repository.py` | 사용자 SQLModel 레이어 |
| `server/app/repositories/job_repository.py` | 공고/임베딩/FTS 레이어 |
| `server/app/models/*.py` | SQLModel 테이블 모델 |
| `tests/server/test_v3_api.py` | API/UI 라우트 회귀 테스트 |
| `tests/server/test_user_repository.py` | 사용자 저장소 로직 테스트 |

---

## Working Rules (반드시 준수)
1. 사용자 화면에는 내부 구현/예외 상세 노출 금지
2. UI 문구는 일반 사용자 중심
3. 공개 라우트 유지: `/`, `/jobs/recommend`, `/jobs/detail`, `/health`
4. v1/v2 엔드포인트 부활 금지
5. 오류 메시지는 사용자 친화 한국어 우선
6. **UI 파일(`server/app/static/*`) 수정 금지**

---

## Development Workflow

```bash
uv sync
uv run poe env-init
uv run poe check
```

실행:

```bash
uv run poe run-server
uv run poe run-scheduler
```

---

## Testing Requirements
- API/서비스 변경 시 `uv run poe check` 통과 필수
- 엔드포인트/스키마 변경 시 `tests/server/test_v3_api.py` 동시 갱신
- 저장소 로직 변경 시 `tests/server/test_user_repository.py` 동시 갱신
- 정적 JS 수정은 금지

---

## Definition of Done
- [ ] 사용자 페이지(`/`, `/jobs/recommend`, `/jobs/detail`) 정상 접속
- [ ] v3 API 흐름(간편로그인→추천→상세분석) 동작
- [ ] `uv run poe check` 통과
- [ ] 문서/설정 변경 사항 README 반영

