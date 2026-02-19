<!-- Generated: 2026-02-19 | Updated: 2026-02-19 -->

# MentoAI_DE Agent Guide

## Purpose
이 저장소는 채용 공고 데이터 파이프라인(Kafka/Spark/Airflow)과 FastAPI 기반 RAG 서비스를 결합해, 일반 구직자에게 **맞춤 공고 추천**과 **공고별 상세 분석**을 제공하는 프로젝트다.

현재 사용자 접점은 웹 UI 3개 페이지(`홈`, `추천`, `상세분석`)와 v3 API 3개(`간편로그인`, `추천`, `분석`) 중심으로 운영된다.

---

## Current Product Scope (중요)

### User-facing pages
- `/` : 메인 홈(빠른 로그인 + 추천/상세 진입)
- `/jobs/recommend` : 추천 + 인라인 상세 분석
- `/jobs/detail` or `/jobs/detail/{job_id}?user_id={user_id}` : 단일 공고 분석

### Active APIs
- `POST /api/v3/auth/quick-login`
- `POST /api/v3/jobs/recommend/{user_id}`
- `POST /api/v3/jobs/{job_id}/analyze/{user_id}`

### API1 core flow (반드시 유지)
1. 사용자 ID 입력
2. DB에서 사용자 가입 정보(희망 직무/경력/기술) 조회
3. 사용자 정보 임베딩
4. Vector DB(Qdrant)에 유사 공고 N개 검색

---

## Key Files

| File | Description |
|---|---|
| `pyproject.toml` | 의존성/ruff/pytest/poe task 정의 |
| `README.md` | 실행 방법, API/페이지 접근, 운영 가이드 |
| `.env.example` | 필수 환경 변수 템플릿 |
| `infra/docker-compose.yml` | 로컬 통합 인프라(Postgres/Qdrant/Kafka/Spark/Airflow/Server) |
| `server/app/main.py` | FastAPI 앱 생성, 정적 페이지 라우트, `/health` |
| `server/app/api/routes/v3.py` | 현재 서비스의 공식 API 엔드포인트 |
| `server/app/services/rag_v3_service.py` | 추천/상세분석/간편로그인 핵심 비즈니스 로직 |
| `server/app/repositories/user_repository.py` | 사용자 조회/생성 DB 레이어 |
| `server/app/schemas/v3.py` | v3 요청/응답 스키마 |
| `server/app/static/home.html` | 메인 홈 UI |
| `server/app/static/index.html` | 추천 화면 UI |
| `server/app/static/detail.html` | 공고 상세 분석 UI |
| `server/app/static/js/jobsite.js` | 추천 화면 동작(세션/검색/정렬/북마크/상세 호출) |
| `server/app/static/js/detail.js` | 상세 화면 동작(분석 요청/렌더링) |
| `tests/server/test_v3_api.py` | 현재 API/UI 라우트 회귀 테스트 핵심 |
| `tests/server/test_user_repository.py` | 가입 시 사용자 테이블 자동 초기화/생성 로직 테스트 |
| `dags/mentoai_pipeline.py` | Kafka→Bronze→Silver→Gold 배치 파이프라인 DAG |
| `spark/job_*.py` | Bronze/Silver/Gold Spark 처리 단계 |
| `kafka/producer_*.py` | 공고 수집 및 Kafka publish |

---

## Subdirectories

| Directory | Purpose |
|---|---|
| `server/` | FastAPI + RAG 서비스 + 정적 UI |
| `tests/` | 서버 중심 테스트(현재는 v3 API 중심) |
| `infra/` | Docker 기반 로컬 실행 환경 |
| `dags/` | Airflow 오케스트레이션 |
| `kafka/` | 수집기/프로듀서 |
| `spark/` | 데이터 처리/정제/임베딩 업서트 |

---

## Recommended OMX Skills (Project-fit)

아래 스킬들을 현재 저장소 작업에서 우선 고려한다.

| Skill | 언제 쓰는지 |
|---|---|
| `deepsearch` | 코드 위치/연관 파일을 빠르게 찾을 때 |
| `frontend-ui-ux` | 사용자용 UI/UX 개선, 화면 완성도 향상 시 |
| `build-fix` | 린트/타입/테스트/빌드 에러를 최소 변경으로 고칠 때 |
| `tdd` | API/서비스 로직 변경 전후 테스트를 먼저/함께 보강할 때 |
| `analyze` | 구조/원인 분석이 선행돼야 하는 문제를 조사할 때 |
| `deepinit` | AGENTS.md/문서 구조를 재정비할 때 |
| `autopilot` | 기획→구현→검증을 한 번에 끝까지 자동 진행할 때 |
| `ralph` | 완료까지 반복 루프로 밀어붙여야 하는 중대 작업일 때 |

> 위 스킬은 “프로젝트 적합 기본 세트”이며, 요청 맥락에 따라 최소 조합만 사용한다.

---

## For AI Agents

### Working Rules (반드시 준수)
1. **사용자 화면에는 개발/내부 구현 정보 노출 금지**  
   - stack trace, raw exception, 내부 경로/모델명/쿼리 노출 금지
2. **UI 문구는 일반 사용자 중심**  
   - 기술 버전 표기(`v1/v2/v3`)를 화면 문구에 노출하지 않음
   - 특정 외부 서비스 브랜드명을 UI 텍스트에 직접 노출하지 않음
3. **기존 공개 라우트 유지**  
   - `/`, `/jobs/recommend`, `/jobs/detail`, `/health`
   - 위 경로를 깨는 변경은 피하고, 필요 시 테스트와 README 동시 갱신
4. **v1/v2 엔드포인트 부활 금지**  
   - 현재 운영 API는 v3만 유지
5. **오류 메시지는 사용자 친화 한국어 우선**

### Development Workflow
프로젝트 루트에서 아래 순서 권장:

```bash
uv sync
uv run poe env-init   # .env 없을 때
uv run poe check      # ruff + ty + pytest
```

인프라 포함 종합 점검이 필요할 때:

```bash
uv run poe all
```

> `poe all`은 Docker daemon 실행 + `.env` 준비가 선행되어야 함.

### Testing Requirements
- 백엔드/API/UI 라우트 변경 시 최소 `uv run poe check` 통과 필수
- 엔드포인트/응답 스키마 변경 시 `tests/server/test_v3_api.py` 함께 수정
- 사용자 가입/저장소 로직 변경 시 `tests/server/test_user_repository.py` 함께 수정
- 정적 JS 수정 시 문법 오류 확인 권장:
  - `node --check server/app/static/js/jobsite.js`
  - `node --check server/app/static/js/detail.js`

### Common Patterns
- FastAPI 라우트는 `server/app/api/routes/v3.py`에서 정의
- 비즈니스 로직은 `services`, DB 접근은 `repositories`로 분리
- 사용자 세션/북마크는 브라우저 `localStorage` 사용
- 리소스(임베딩/LLM/Qdrant)는 서비스 레벨에서 lazy-init 후 재사용

---

## Dependencies

### Internal
- `server/app/core/config.py` 환경변수 → 서비스/저장소 레이어에서 사용
- `server/app/services/rag_v3_service.py` ↔ `server/app/repositories/user_repository.py`
- `server/app/static/*` ↔ `server/app/main.py` 정적 라우트

### External (핵심)
- FastAPI / Uvicorn
- asyncpg (PostgreSQL)
- qdrant-client (Vector DB)
- LangChain + Google Generative AI
- sentence-transformers / KoSimCSE
- Spark / Kafka / Airflow (데이터 파이프라인)

---

## Definition of Done (PR/작업 완료 기준)
- [ ] 사용자 페이지(`/`, `/jobs/recommend`, `/jobs/detail`) 정상 접속
- [ ] v3 API 흐름(간편로그인→추천→상세분석) 동작 확인
- [ ] `uv run poe check` 통과
- [ ] 라우트/명령/설정 변경 시 README 업데이트

<!-- MANUAL: 아래 영역은 수동 메모용 (자동 갱신 시 보존 대상) -->
