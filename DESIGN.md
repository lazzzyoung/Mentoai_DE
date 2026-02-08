# MentoAI 웹 UI 설계 문서

이 문서는 FastAPI + Jinja2 + HTMX + Tailwind 기반 웹 UI 구조를 정의합니다.  
목표는 모바일 WebView(예: Capacitor)와 데스크톱 브라우저에서 모두 일관된 화면/라우팅 동작을 제공하는 것입니다.

## 1. 목표와 범위

### 목표

- 서버 렌더링 기반 UI를 유지하면서 화면 전환 체감을 빠르게 만듭니다.
- 모바일 화면에서 상단/하단 고정 내비게이션을 제공합니다.
- 기존 API 구조와 충돌 없이 웹 UI 라우트를 공존시킵니다.

### 범위

- 포함: 템플릿 구조, 라우팅 정책, HTMX partial 응답 규칙, 기본 스타일 가이드.
- 제외: 네이티브 앱 번들링 설정, 인증/권한 상세 정책, 비즈니스 로직 변경.

## 2. 기술 선택

- 백엔드: FastAPI
- 템플릿: Jinja2 (`starlette.templating`)
- 프런트 상호작용: HTMX
- 스타일: Tailwind CSS (CDN)

## 3. 화면 구조(App Shell)

앱 기본 레이아웃은 3개 영역으로 구성합니다.

1. 상단 헤더(고정)
2. 본문 영역(스크롤)
3. 하단 탭바(모바일 고정)

```text
+------------------------------------+
| Safe Area Top                      |
+------------------------------------+
| Header (fixed)                     |
+------------------------------------+
| Main Content (scroll)              |
|                                    |
+------------------------------------+
| Bottom Tab (mobile, fixed)         |
+------------------------------------+
| Safe Area Bottom                   |
+------------------------------------+
```

## 4. Safe Area / Viewport 정책

모바일 WebView 대응을 위해 다음을 적용합니다.

- viewport: `user-scalable=no`, `viewport-fit=cover`
- safe area CSS:
  - `env(safe-area-inset-top)`
  - `env(safe-area-inset-bottom)`

적용 위치:

- 헤더 상단 padding
- 하단 탭바 하단 padding
- 메인 영역의 상/하단 여백 계산

## 5. 라우팅 및 렌더링 규칙

웹 UI 라우트는 `server/app/api/routes/web.py`에서 관리합니다.

### 라우트

- `GET /` : 홈
- `GET /search` : 검색
- `GET /profile` : 프로필
- `POST /api/action` : HTMX 액션 응답
- `POST /api/web/action` : 기존 경로 호환 alias

참고:

- `GET /`에 `Accept: application/json`만 요청하는 클라이언트에는 헬스 JSON을 반환합니다.

### 렌더링 분기

- HTMX 요청(`HX-Request` 헤더 있음): `layout/partial.html` 사용
- 일반 요청: `layout/app_shell.html` 사용

이 규칙으로 첫 진입은 전체 셸을 렌더링하고, 탭 이동은 본문만 교체합니다.

## 6. 템플릿 구조

현재 구조:

```text
server/app/templates/
├── layout/
│   ├── base.html
│   ├── app_shell.html
│   └── partial.html
└── pages/
    ├── home/index.html
    ├── search/index.html
    └── profile/index.html
```

역할:

- `layout/base.html`: 공통 head/script/style
- `layout/app_shell.html`: 헤더/탭바 포함 전체 레이아웃
- `layout/partial.html`: HTMX 교체용 최소 블록
- `pages/*`: 화면별 본문 템플릿

## 7. HTMX 동작 규칙

- 탭/내비게이션 링크는 `hx-get` + `hx-target="#main-content"` + `hx-push-url="true"` 사용
- 서버는 HTML fragment를 반환하고, 전체 새로고침을 피합니다.
- 공통 로딩 표시기는 `#global-progress`를 사용합니다.

## 8. 스타일 가이드

- 기본 컬러
  - Primary: `#4F46E5`
  - Secondary: `#0F172A`
  - Background: `#F8FAFC`
  - Accent: `#8B5CF6`
- 기본 폰트: Inter
- 터치 타겟 최소 높이: 44px 이상
- 카드/버튼은 라운드와 명확한 상태 변화(hover/active/focus) 유지

## 9. 테스트 기준

최소 확인 항목:

- `GET /` HTML 렌더 응답
- `POST /api/action` partial 응답
- `GET /` + `Accept: application/json` 헬스 JSON 호환
- `GET /health` 정상 응답

관련 테스트: `tests/server/test_web_ui_routes.py`

## 10. 향후 확장 방향

- 공통 컴포넌트(`components/`) 분리
- 화면별 partial 템플릿 세분화
- 사용자 상태/권한에 따른 탭/메뉴 동적 제어
- SSR + HTMX 패턴 기반의 점진적 기능 추가
