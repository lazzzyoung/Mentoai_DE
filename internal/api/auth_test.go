package api

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Chae-JS/mentoai/internal/domain"
)

func newTestServerReporter(rec *fakeRecommender, ana *fakeAnalyzer, admin *fakeAdmin, rep *fakeReporter) *httptest.Server {
	srv := New(&fakeUsers{}, rec, ana, admin, &fakeAuth{}, false, rep)
	ts := httptest.NewServer(srv.Handler())
	return ts
}

func TestAuthStatus(t *testing.T) {
	t.Parallel()
	auth := &fakeAuth{status: domain.AuthStatus{Providers: []domain.ProviderStatus{
		{Provider: "google", Enabled: true, LoginPath: "/api/v1/auth/google/login"},
		{Provider: "toss", Enabled: false},
	}}}
	ts := newTestServerAuth(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, auth, true)
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/api/v1/auth/status", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"auth_required":true`) ||
		!strings.Contains(body, `"login_path":"/api/v1/auth/google/login"`) {
		t.Fatalf("status: %d %s", resp.StatusCode, body)
	}
}

func TestAuthLoginRedirect(t *testing.T) {
	t.Parallel()
	auth := &fakeAuth{loginURL: "https://accounts.google.com/o/oauth2/v2/auth?state=abc", loginURLok: true}
	ts := newTestServerAuth(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, auth, false)
	defer ts.Close()

	noRedirect := &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}}
	req, _ := http.NewRequest(http.MethodGet, ts.URL+"/api/v1/auth/google/login", nil)
	direct, err := noRedirect.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	direct.Body.Close()
	if direct.StatusCode != 302 || !strings.Contains(direct.Header.Get("Location"), "state=abc") {
		t.Fatalf("302 리다이렉트 기대: %d %s", direct.StatusCode, direct.Header.Get("Location"))
	}

	// redirect 미지원 공급자 → 400
	auth.loginURLok = false
	if resp, _ := do(t, http.MethodGet, ts.URL+"/api/v1/auth/toss/login", ""); resp.StatusCode != 400 {
		t.Fatalf("400 기대: %d", resp.StatusCode)
	}
}

func TestAuthCallback(t *testing.T) {
	t.Parallel()
	auth := &fakeAuth{token: "tok", user: domain.UserResponse{ID: 7, Username: "user"}}
	ts := newTestServerAuth(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, auth, false)
	defer ts.Close()

	// state 쿠키가 없는 요청 → 400 (CSRF 방어)
	req, _ := http.NewRequest(http.MethodGet, ts.URL+"/api/v1/auth/google/callback?state=x&code=c", nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 400 {
		t.Fatalf("state 불일치 400 기대: %d", resp.StatusCode)
	}

	// state 쿠키를 실러도 handler가 StateCookie()=="" 를 반환하는 fake 특성상
	// redirect 방식 세부는 internal/auth 통합 테스트가 담당한다.
}

func TestAuthTossCallback(t *testing.T) {
	t.Parallel()
	auth := &fakeAuth{token: "toss-token", user: domain.UserResponse{ID: 9, Username: "토스사용자"}}
	ts := newTestServerAuth(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, auth, false)
	defer ts.Close()

	resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/auth/toss/callback",
		`{"authorizationCode":"abc","referrer":"DEFAULT"}`)
	if resp.StatusCode != 200 || !strings.Contains(body, `"token":"toss-token"`) ||
		!strings.Contains(body, `"username":"토스사용자"`) {
		t.Fatalf("토스 콜백: %d %s", resp.StatusCode, body)
	}

	// 코드 누락 → 422
	if resp, _ := do(t, http.MethodPost, ts.URL+"/api/v1/auth/toss/callback", `{}`); resp.StatusCode != 422 {
		t.Fatalf("422 기대: %d", resp.StatusCode)
	}
}

func TestAuthMeAndLogout(t *testing.T) {
	t.Parallel()
	auth := &fakeAuth{authenticated: true, meUser: domain.UserResponse{
		ID: 42, Username: "로그인유저", DesiredJob: "백엔드", CareerYears: 3, Skills: []string{},
	}}
	ts := newTestServerAuth(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, auth, false)
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/api/v1/auth/me", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"username":"로그인유저"`) {
		t.Fatalf("me: %d %s", resp.StatusCode, body)
	}
	if auth.gotUserID != 42 {
		t.Fatalf("세션 user_id 전달: %d", auth.gotUserID)
	}

	// 미로그인 → 401
	auth.authenticated = false
	if resp, _ := do(t, http.MethodGet, ts.URL+"/api/v1/auth/me", ""); resp.StatusCode != 401 {
		t.Fatalf("401 기대: %d", resp.StatusCode)
	}

	// 스펙 수정
	auth.authenticated = true
	resp, body = do(t, http.MethodPut, ts.URL+"/api/v1/auth/me",
		`{"desired_job":"데이터 엔지니어","career_years":2,"skills":["Go"]}`)
	if resp.StatusCode != 200 || !strings.Contains(body, `"desired_job":"데이터 엔지니어"`) {
		t.Fatalf("me 수정: %d %s", resp.StatusCode, body)
	}
	// 검증 실패 → 422
	if resp, _ := do(t, http.MethodPut, ts.URL+"/api/v1/auth/me", `{"desired_job":"","career_years":0}`); resp.StatusCode != 422 {
		t.Fatalf("422 기대: %d", resp.StatusCode)
	}

	if resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/auth/logout", ""); resp.StatusCode != 200 ||
		!strings.Contains(body, "ok") {
		t.Fatalf("logout: %d %s", resp.StatusCode, body)
	}
}

func TestAuthRequiredGate(t *testing.T) {
	t.Parallel()
	ts := newTestServerAuth(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{}, &fakeAuth{}, true)
	defer ts.Close()

	// 미로그인: 보호 대상(admin, jobs)은 401
	if resp, _ := do(t, http.MethodGet, ts.URL+"/api/v1/admin/stats", ""); resp.StatusCode != 401 {
		t.Fatalf("admin 401 기대: %d", resp.StatusCode)
	}
	if resp, _ := do(t, http.MethodPost, ts.URL+"/api/v1/jobs/recommend/1", ""); resp.StatusCode != 401 {
		t.Fatalf("recommend 401 기대: %d", resp.StatusCode)
	}
	// 인증 모드의 사용자 목록도 보호한다
	if resp, _ := do(t, http.MethodGet, ts.URL+"/api/v1/users", ""); resp.StatusCode != 401 {
		t.Fatalf("users 401 기대: %d", resp.StatusCode)
	}
}

// fakeReporter는 에러 리포팅 포트의 기록용 가짜다.
type fakeReporter struct {
	mu    sync.Mutex
	calls []reported
}

type reported struct {
	err  string
	tags map[string]string
}

func (f *fakeReporter) CaptureError(err error, tags map[string]string) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, reported{err: err.Error(), tags: tags})
}
func (f *fakeReporter) Close(timeout time.Duration) {}

func TestErrorReportingOn500(t *testing.T) {
	t.Parallel()
	rep := &fakeReporter{}
	rec := &fakeRecommender{err: errors.New("gemini 키 만료")}
	ts := newTestServerReporter(rec, &fakeAnalyzer{}, &fakeAdmin{}, rep)
	defer ts.Close()

	resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/jobs/recommend/1", "")
	if resp.StatusCode != 500 || !strings.Contains(body, "gemini 키 만료") {
		t.Fatalf("500 응답: %d %s", resp.StatusCode, body)
	}
	if len(rep.calls) != 1 || !strings.Contains(rep.calls[0].err, "gemini 키 만료") {
		t.Fatalf("리포터 호출: %+v", rep.calls)
	}
	if rep.calls[0].tags["method"] != http.MethodPost {
		t.Fatalf("태그: %+v", rep.calls[0].tags)
	}

	// 4xx는 리포팅 대상이 아니다
	rep.calls = nil
	rec.err = domain.NotFound("User not found")
	do(t, http.MethodPost, ts.URL+"/api/v1/jobs/recommend/1", "")
	if len(rep.calls) != 0 {
		t.Fatalf("4xx는 리포팅되지 않아야 한다: %+v", rep.calls)
	}
}
