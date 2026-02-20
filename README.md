# MentoAI: Lightweight Career Recommendation Service

MentoAI는 구직자 프로필을 기반으로 채용 공고를 추천하고, 공고별 상세 분석을 제공하는 FastAPI 서비스입니다.

이번 버전은 **4GB Ubuntu 환경**을 기준으로 경량화되어 아래 구조로 동작합니다.

- **실행 지원 플랫폼**: macOS ARM64(Apple Silicon), Linux x86_64
- **FastAPI + 정적 UI 3페이지**
- **SQLModel + SQLite 단일 저장소**
- **Hybrid RAG (SQLite FTS5 + Python semantic rerank)**
- **APScheduler 기반 순수 Python 크롤러 주기 실행**

---

## 1) 주요 엔드포인트

- `POST /api/v3/auth/quick-login`
- `POST /api/v3/jobs/recommend/{user_id}` (optional query: `limit`)
- `POST /api/v3/jobs/{job_id}/analyze/{user_id}`

유지되는 페이지/경로:

- `/`
- `/jobs/recommend`
- `/jobs/detail`
- `/health`

---

## 2) 실행 방법 (uv 기반)

```bash
uv sync
uv run poe env-init
```

`.env`에서 최소 설정:

- `OPENAI_API_KEY`
- `OPENAI_DEFAULT_MODEL` (기본: `gpt-5-mini`)
- `ANALYSIS_MODEL` (기본: `gpt-5-mini`)
- `SQLITE_DB_PATH`
- `CRAWLER_INTERVAL_MINUTES`
- `RECOMMENDATION_LIMIT` (기본: `20`, 추천 카드 초기 풀 크기)

> 계정에서 `gpt-5-mini` 접근이 안 되면 `ANALYSIS_MODEL=gpt-4o-mini`로 설정하세요.
> 이전 변수명 `OPENAI_MODEL`도 하위호환으로 인식합니다.

서버 실행:

```bash
uv run poe run-server
```

스케줄러 실행(별도 터미널):

```bash
uv run poe run-scheduler
```

크롤러 1회 실행:

```bash
uv run poe crawl-once
```

데이터(SQLite) 리셋:

```bash
uv run poe reset-data
```

---

## 3) 개발 품질 명령

```bash
uv run poe check
```

---

## 4) 아키텍처 요약

### 데이터 저장
- `users`, `user_specs`, `jobs`, `job_embeddings` 테이블: SQLModel
- `jobs_fts`: SQLite FTS5 virtual table

### 추천 검색 흐름
1. 사용자 프로필 텍스트 생성
2. FTS5에서 후보 공고 조회
3. query embedding vs 후보 embedding 코사인 재랭크
4. 결합 점수로 상위 공고 반환

### 상세 분석 흐름
- 공고 단건 조회 후 LLM 분석
- LLM 키가 없거나 오류 시 안전한 fallback 분석 응답 제공

---

## 5) Ubuntu 운영 스크립트

- `setup_ubuntu.sh`: swap + uv + python + sqlite + certbot 설치
- `setup_https_domain_only.sh`: certbot 인증서 + uvicorn HTTPS(systemd) 구성

---

## 6) 테스트 범위

- v3 API 라우트 회귀
- UI 라우트 접근 회귀
- SQLModel 사용자 생성/조회 로직
- 오류 응답 메시지(사용자 친화 한국어)
