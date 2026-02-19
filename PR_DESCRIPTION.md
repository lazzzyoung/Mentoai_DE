# PR 제목
`refactor: v3 전용 API 구조 정리 및 완전 비동기 스택 전환`

## 배경
기존 `server/app/main.py`에 라우팅/스키마/비즈니스 로직이 집중되어 유지보수 난이도가 높았고, 동기 I/O가 혼재되어 있었습니다.  
이번 변경은 **v3 API 2개만 유지**하면서 코드 구조를 분리하고, 서버 처리 경로를 **비동기 중심**으로 정리하는 것을 목표로 했습니다.

---

## 주요 변경사항

### 1) API 정리 (v3만 유지)
- 유지:
  - `POST /api/v3/jobs/recommend/{user_id}`
  - `POST /api/v3/jobs/{job_id}/analyze/{user_id}`
  - `GET /` (health)
- 제거:
  - `api/v1/*`, `api/v2/*` 라우트

> v3 두 엔드포인트의 경로/메서드/응답 인터페이스는 유지했습니다.

### 2) 서버 구조 분할 (클리닝)
- `server/app/main.py` 경량화 (앱 생성/라우터 등록/라이프사이클)
- 신규 모듈 분리:
  - `server/app/api/routes/v3.py`
  - `server/app/services/rag_v3_service.py`
  - `server/app/repositories/user_repository.py`
  - `server/app/schemas/v3.py`
  - `server/app/core/config.py`
- 패키지 `__init__.py` 정리

### 3) async 스택 적용
- DB: `psycopg2-binary` → **`asyncpg`**
  - async pool 생성/재사용, shutdown 시 close
- Qdrant: `QdrantClient` → **`AsyncQdrantClient`**
  - `query_points`, `retrieve` 비동기 호출
- LLM 체인: `invoke` → **`ainvoke`**
- FastAPI lifecycle:
  - `lifespan`에서 리소스 정리(`close_resources`, `close_pool`)

### 4) 품질 도구/CI 도입
- `pyproject.toml` 추가 (uv/ruff/ty 기반)
- `uv.lock` 추가
- `.github/workflows/ci-quality.yml` 추가
  - ruff / ty / pytest 실행
- `.gitignore`에 `.omx/` 추가
- README에 개발 품질 명령 추가

### 5) 테스트
- `tests/server/test_v3_api.py` 추가
  - health 체크
  - v1/v2 제거 확인(404)
  - v3 recommend/analyze 성공/에러 시나리오

---

## 변경 파일 요약
- 총 21 files changed  
- `4442 insertions(+), 419 deletions(-)`  
  (uv.lock 포함)

---

## 검증 내역
로컬에서 아래 통과 확인:
- `ruff check` ✅
- `ty check` ✅
- `pytest` ✅ (6 passed)
- OpenAPI path 확인 ✅
  - `/`
  - `/api/v3/jobs/recommend/{user_id}`
  - `/api/v3/jobs/{job_id}/analyze/{user_id}`

---

## Breaking Change / 주의사항
- `api/v1`, `api/v2` 엔드포인트는 제거되어 404 반환됩니다.
- 서버 의존성에서 DB 드라이버가 `asyncpg`로 변경되었습니다. (Docker 빌드 시 반영 필요)

---

## 체크리스트
- [x] v3 API 인터페이스 유지
- [x] 서버 구조 분리 완료
- [x] 비동기 처리 적용(asyncpg/AsyncQdrant/ainvoke)
- [x] 테스트/린트/타입체크 통과
- [x] CI 워크플로우 추가
