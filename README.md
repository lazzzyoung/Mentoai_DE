# MentoAI: Personalized AI Career Roadmap Service

**MentoAI**는 사용자의 기술 스펙과 희망 직무를 분석하여, 최신 채용 공고 기반의 맞춤형 커리어 로드맵을 제공하는 AI 서비스입니다.

v2(Kafka + Spark + Airflow + S3 + Qdrant, 컨테이너 9개) → v3(FastAPI + PostgreSQL/pgvector, 컨테이너 2개)에 이어, 이번에는 **Go + 내장 SQLite 단일 스택**으로 완전히 다시 썼습니다.

- **외부 서비스 0개**: PostgreSQL·pgvector·Qdrant 컨테이너 제거. SQLite 파일 하나에 Medallion 구조가 녹아 있다.
- **단일 바이너리**: `go build` 결과물 하나가 API 서버 + 파이프라인 CLI + 스케줄러 + UI 전부다 (CGO 불필요, distroless에 그대로 배포).
- **벡터 검색**: pgvector HNSW 대신 프로세스 메모리 인덱스(코사인 전수 검색). 수천~수만 건 규모에서 쿼리당 수 ms.
- **DI**: 모든 계층이 인터페이스(port)에 의존하고 `cmd/mentoai`(composition root)에서 생성자 주입으로 조립된다. 임베딩 공급자는 `Embedder` 인터페이스 + 레지스트리로 교체 가능하며, **Gemini API가 참조 구현**이다.

## 🏗️ Architecture

```
[Wanted API]  ─┐
[work24 리스트] ─┴─► Go 스크래퍼 ─► bronze_raw_postings (JSON 원본 보존)
                                    │ silver.Build (HTML 제거·소스 통합·중복 제거 keep-last)
                                    ▼
                                silver_jobs (통합 공고 스키마)
                                    │ 임베딩: Gemini API (Embedder 포트의 참조 구현)
                                    ▼
                                silver_job_embeddings (float32 BLOB + 메모리 인덱스)
                                    │
             robfig/cron ───────────┤ 전체 파이프라인 스케줄링
                                    ▼
                   net/http ─► 추천: 코사인 유사도 + 휴리스틱 (LLM 0호출)
                            └► 상세 분석: Gemini 구조화 출력 + analysis_cache (1회만 호출)
```

## 🧰 Stack

| 영역 | 기술 | 비고 |
|---|---|---|
| 언어 | Go 1.27 | 외부 의존성 3개뿐 |
| DB | SQLite (`modernc.org/sqlite`) | 순수 Go 드라이버, WAL 모드 |
| 마이그레이션 | 버전 관리 SQL (`internal/storage/sqlite/migrations/`, embed.FS) | 기동 시 자동 적용 |
| 수집 | net/http + goquery | Wanted JSON API / work24 HTML |
| 임베딩 | `Embedder` 포트 + 레지스트리 | 참조 구현: `gemini-embedding-001` (1024차원) |
| LLM | Gemini `generateContent` 구조화 출력 | `responseSchema`로 DetailedAnalysisResponse 강제 |
| API | net/http 1.22+ ServeMux | 프레임워크 없음, FastAPI와 동일한 엔드포인트/에러 형식 |
| UI | 바이너리에 임베드된 정적 페이지 (`embed.FS`) | 모놀리식 — 빌드 도구·npm 없음, 바닐라 JS PWA |
| 스케줄링 | robfig/cron v3 | tzdata 포함 → 컨테이너에서도 Asia/Seoul 동작 |
| 품질 | gofmt, go vet, go test | GitHub Actions CI |

외부 라이브러리: `modernc.org/sqlite`, `github.com/PuerkitoBio/goquery`, `github.com/robfig/cron/v3` — 그 외 전부 표준 라이브러리.

## 🚀 Quick Start

```bash
cp .env.example .env          # GOOGLE_API_KEY 입력
go run ./cmd/mentoai migrate && go run ./cmd/mentoai seed
go run ./cmd/mentoai pipeline # 수집→정제→임베딩
go run ./cmd/mentoai serve    # http://localhost:8000 (관리자: /admin)
```

## 📦 배포 (원터치, Caddy 자동 HTTPS + HTTP/3)

### 우분투 서버 — 진짜 한 방

```bash
sudo bash scripts/setup-ubuntu.sh        # Docker Engine·Compose 설치 (최초 1회, --with-go로 Go도 설치)
bash scripts/deploy.sh                   # .env 준비 → 빌드 → 기동 → 헬스체크까지 자동
```

- `deploy.sh`는 Docker가 없으면 자동 설치하고, `.env`가 없으면 예시에서 생성(AUTH_SECRET 자동 발급), ufw가 켜져 있으면 80/443(tcp)·443(udp) 포트를 열고, 443 헬스체크가 지날 때까지 기다린 뒤 결과를 출력한다.
- 도메인 배포: `.env`의 `CADDY_DOMAIN=도메인`을 채우고 DNS를 서버로 맞춘 뒤 `deploy.sh`를 다시 실행하면 Let's Encrypt 인증서가 자동 발급된다.
- 값을 바꾼 뒤에는 `docker compose up -d`로 env를 재적용한다.

### 로컬(Docker Desktop 등)

```bash
make up        # api 빌드+기동(마이그레이션·시드 자동) + caddy(HTTPS 자동)
```

- `CADDY_DOMAIN=localhost`(기본)이면 **내부 CA 자체서명 인증서**로 HTTPS 구동 — `curl -k` 또는 브라우저 경고 진행으로 확인.
- `.env`에 `CADDY_DOMAIN=여러분의도메인.com`을 넣고 80/443(tcp+**udp**)을 열면 **Let's Encrypt 인증서가 자동 발급·갱신**된다 (ACME 이메일 없이도 동작).
- **HTTP/3(QUIC)는 기본 활성** — HTTPS 사이트에서 `alt-svc: h3=":443"`를 광고하고, 지원 클라이언트는 QUIC으로 협상된다(미지원 시 HTTP/2로 자동 폴백). 검증: `curl --http3-only https://도메인/health`.
- HTTP/1.1 80포트는 308으로 HTTPS에 리다이렉트. zstd/gzip 압축과 기본 보안 헤더(HSTS·nosniff·X-Frame-Options·Referrer-Policy) 적용.
- api는 호스트에 8000 포트를 노출하지 않고 caddy 뒤에만 있다 (`docker compose exec api /mentoai status`로 내부 조회 가능).

### 단일 컨테이너 옵션

`deploy/Dockerfile.single`은 Caddy와 앱을 **한 컨테이너**에 넣은 변형이다:

```bash
docker build -f deploy/Dockerfile.single -t mentoai-single . && docker run -p 443:443 -p 443:443/udp -e CADDY_DOMAIN=localhost mentoai-single
```

컨테이너 수가 1개로 줄지만, 감독 프로세스가 없어 **앱이 죽어도 컨테이너가 살아있는 것처럼 보이며 502만 반환**한다(실측 확인). 기본 구성은 compose 2-서비스(api `restart: unless-stopped` + caddy)를 권장한다.

### CLI

```
mentoai serve       # API 서버 (시작 시 마이그레이션 자동 적용)
mentoai migrate     # 마이그레이션 적용
mentoai seed        # 샘플 사용자 적재 (멱등)
mentoai status      # DB 현황·모델·스케줄·최근 실행 요약
mentoai scrape      # Bronze: 수집 → bronze_raw_postings
mentoai transform   # Silver: 정제 → silver_jobs
mentoai embed       # Gold: 임베딩 (--force 전량 재계산)
mentoai pipeline    # 전체 실행 (pipeline_runs에 이력 기록)
mentoai jobs list/rm    # 공고 조회/삭제 (원본·임베딩·캐시 함께)
mentoai users list/set/rm   # 인재 조회/등록·수정/삭제
mentoai models      # 등록된 임베딩 provider 목록
mentoai switch-embedding --provider gemini --yes   # 임베딩 모델 전환
```

## 📡 API Endpoints

### 1. 기업 목록 추천
* **POST** `/api/v1/jobs/recommend/{user_id}`
* 벡터 유사도 검색 + 기술스택/경력 휴리스틱으로 상위 N개 공고와 적합도 점수를 **즉시(LLM 호출 없이)** 반환.

### 2. 상세 커리어 컨설팅
* **POST** `/api/v1/jobs/{job_id}/analyze/{user_id}`
* Gemini가 부족한 역량·액션 플랜·면접 팁을 구조화된 JSON으로 제공.
* 동일 (공고, 사용자, 모델) 조합은 `analysis_cache`에 캐시되어 **Gemini 호출 1회만** 발생.

### 3. 관리자 (`/admin` 페이지 + `/api/v1/admin/*`, CLI와 같은 로직 공유)
* 현황 대시보드(카운트·테이블 용량·모델·스케줄 다음 실행·진행 중 작업)
* 파이프라인 즉시 실행(백그라운드, 중복 409) + 실행 이력
* 공고 검색·삭제, 인재 등록/수정/삭제, 분석 캐시 관리
* 임베딩 운영: 모델 목록 조회·전환(백그라운드)·전량 재계산
* 데모 기본값은 무인증이며, 아래 로그인을 켜고 `AUTH_REQUIRED=true`로 보호 가능

### 4. 로그인 (구글 / 앱인토스 — 설정만으로 켜진다)
* **기본 완전 OFF**: 관련 env가 비어 있으면 기존과 동일하게 무인증으로 동작.
* **구글**: 표준 OAuth2. `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`(콘솔에 `GOOGLE_REDIRECT_URL` 등록)만 넣으면 상단 "구글로 로그인" 버튼이 활성화된다. 첫 로그인 시 자동 회원가입(users+user_specs 생성) 후 세션 쿠키 발급.
* **앱인토스**: 클라이언트 SDK(`@apps-in-toss/web-framework`의 `appLogin()`)가 받은 인가 코드를 `POST /api/v1/auth/toss/callback`으로 보내면 서버가 `generate-token`(mTLS 필수, `TOSS_MTLS_CERT_PATH`/`TOSS_MTLS_KEY_PATH`) → `login-me`로 `userKey`를 조회해 로그인 처리.
* 세션은 DB 없는 HMAC 서명 토큰(`AUTH_SECRET` 필요) — 쿠키(HttpOnly)와 `Authorization: Bearer` 모두 지원, 30일 유효.
* `AUTH_REQUIRED=true`면 `/api/v1/admin/*`와 `/api/v1/jobs/*`(Gemini 비용 보호)에 401 게이트. `/api/v1/users`·static은 항상 개방.
* 로그인 사용자는 `GET/PUT /api/v1/auth/me`로 자기 스펙(직무/경력/스킬)을 직접 관리하고 맞춤 추천을 받는다.

## 📂 Project Structure

```
mentoai_de/
├── cmd/mentoai/               # main.go(CLI 서브커맨드) + wire.go(composition root)
├── internal/
│   ├── config/                # Settings (.env + 환경변수) + 실행 중 교체용 Holder
│   ├── domain/                # 계층 공유 DTO + HTTPError
│   ├── envfile/               # .env 로더 + 줄 보존 편집기(백업)
│   ├── vector/                # float32 BLOB 직렬화 + 코사인 유사도
│   ├── storage/               # 저장소 포트(인터페이스)
│   │   └── sqlite/            # SQLite 구현 + 마이그레이션 러너 + 메모리 벡터 인덱스
│   ├── embedding/             # Embedder 포트 + 레지스트리 + 실행 중 전환 홀더
│   │   └── gemini/            # 참조 구현 (batch 100, RETRIEVAL_QUERY/DOCUMENT)
│   ├── llm/                   # AnalysisGenerator 포트
│   │   └── gemini/            # 구조화 출력 구현
│   ├── auth/                  # 로그인 포트 + 세션(HMAC) + 서비스
│   │   ├── google/            # 구글 OAuth2
│   │   └── toss/              # 앱인토스 토스 로그인 (mTLS)
│   ├── silver/                # 정제 순수 함수 (normalize_wanted/work24, full_text)
│   ├── scoring/               # 점수/사유 휴리스틱 순수 함수
│   ├── pipeline/              # bronze / silver / gold / runner
│   ├── scrapers/              # wanted / work24
│   ├── recommend/             # 추천 서비스
│   ├── analysis/              # 상세 분석 서비스 (캐시)
│   ├── ops/                   # CLI·어드민 공유 운영 계층 + 백그라운드 가드
│   ├── scheduler/             # cron 스케줄러
│   ├── api/                   # HTTP 핸들러 (net/http ServeMux)
│   └── web/                   # 정적 UI 임베드 (internal/web/static)
├── deploy/                    # 단일 컨테이너 변형 (선택)
├── Caddyfile                  # 자동 HTTPS·HTTP/3 리버스 프록시
├── compose.yaml               # api + caddy (make up 원터치)
├── Dockerfile                 # 멀티스테이지 → distroless 단일 바이너리
└── .github/workflows/         # gofmt / vet / test
```

### DI 원칙

- 소비자는 **포트를 선언**하고 구현체를 생성자 인자로 받는다 (`recommend.New(users, embeds, jobs, embedder, settings)`).
- 파이프라인·ops·서비스는 `storage.UserRepo`, `embedding.Embedder` 같은 인터페이스에만 의존한다. SQLite를 Postgres/pgvector로 바꾸려면 새 구현 패키지를 추가하고 wire.go의 조립만 고치면 된다.
- 임베딩 공급자 추가: `embedding.Embedder` 구현 → `registry.Register("openai", ...)` 한 줄. 실행 중 전환(`switch-embedding`, 어드민 API)은 `AtomicEmbedder` 교체로 즉시 반영된다.
- 테스트는 이 구조 덕에 DB/네트워크 없이 가짜 주입만으로 핸들러·서비스를 검증한다 (`internal/api/api_test.go`, `internal/pipeline/pipeline_test.go`).

## 🔎 v3(Python) → v4(Go) 이행 노트

- 엔드포인트·상태코드(201/204/409/422)·에러 바디 `{"detail": ...}`·한국어 메시지를 그대로 유지해 기존 UI가 무수정 동작한다. (임베딩 모델 목록 응답만 `fastembed` 카탈로그 → `available`(레지스트리)로 교체)
- `vector(1024)` HNSW → `float32 BLOB` + 프로세스 메모리 코사인 인덱스(쓰기 시 무효화). similarity 산식은 동일(코사인 유사도, 점수 = clamp(round(sim×100), 40, 99)).
- `text[]`/`jsonb` → JSON TEXT 컬럼, 타임스탬프는 고정폭 UTC 문자열(문자열 비교 = 시간 비교).
- gold의 재임베딩 판정(신규 / `embedded_at < updated_at` / 모델 불일치)도 동일하다.
- fastembed(로컬 ONNX)는 Go에 직접 대체재가 없어 미포함. 필요하면 ONNX Runtime 바인딩으로 `Embedder`를 구현해 레지스트리에 등록하면 된다.

## 📈 확장 설계서 (재도입 시점)

| 신호 | 도입 기술 | 마이그레이션 경로 |
|---|---|---|
| 수집 소스 10개+ · 실시간성 요구 | Kafka/Redpanda | 스크래퍼 → producer 전환 (bronze 인터페이스 불변) |
| 일일 수백만 건 | Spark/Flink | `silver.Build`만 교체 (순수 함수 → UDF 포팅 용이) |
| 파이프라인 20+ 태스크 · SLA 추적 | Airflow 3 / Dagster | `RunPipeline`을 태스크로 래핑 |
| 벡터 수십만 개+ | Qdrant 또는 Postgres+pgvector | `storage.EmbeddingRepo` 구현 교체 (SearchTopK 계약 불변) |

모든 계층이 인터페이스(scraper→bronze→silver→gold→API)로 분리되어 있어, 위 전환은 각각 한 구현체 교체로 끝납니다.
