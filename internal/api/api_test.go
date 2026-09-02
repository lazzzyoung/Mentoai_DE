package api

import (
	"context"
	"encoding/json"
	"io"
	"io/fs"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/web"
)

// ---------- 가짜 서비스 (생성자 주입으로 핸들러만 검증) ----------

type fakeUsers struct{ users []domain.UserSummary }

func (f *fakeUsers) ListSummaries(context.Context) ([]domain.UserSummary, error) {
	return f.users, nil
}

type fakeRecommender struct {
	result    domain.RecommendationListResponse
	err       error
	gotUserID int64
}

func (f *fakeRecommender) Recommend(_ context.Context, userID int64) (domain.RecommendationListResponse, error) {
	f.gotUserID = userID
	return f.result, f.err
}

type fakeAnalyzer struct {
	result domain.DetailedAnalysisResponse
	err    error
}

func (f *fakeAnalyzer) Analyze(context.Context, int64, int64) (domain.DetailedAnalysisResponse, error) {
	return f.result, f.err
}

type fakeAdmin struct {
	status       domain.Status
	runs         []domain.RunRow
	triggerErr   error
	jobs         []domain.JobAdminRow
	gotQuery     string
	gotLimit     int
	deleteJobErr error
	createErr    error
	created      domain.UserResponse
	switchOK     bool
	updateErr    error
	deleteErr    error
	models       domain.EmbeddingModels
	resolveErr   error
	rebuildOK    bool
	cacheRows    []domain.CacheRow
	deletedCount int64
	cacheDelErr  error
}

func (f *fakeAdmin) Status(context.Context) (domain.Status, error) { return f.status, nil }
func (f *fakeAdmin) ListRuns(context.Context, int) ([]domain.RunRow, error) {
	return f.runs, nil
}
func (f *fakeAdmin) TriggerPipeline(context.Context) error { return f.triggerErr }
func (f *fakeAdmin) ListJobs(_ context.Context, query string, limit int) ([]domain.JobAdminRow, error) {
	f.gotQuery, f.gotLimit = query, limit
	return f.jobs, nil
}
func (f *fakeAdmin) DeleteJob(context.Context, int64) error { return f.deleteJobErr }
func (f *fakeAdmin) CreateUser(_ context.Context, p domain.UserPayload) (domain.UserResponse, error) {
	if err := p.Validate(); err != nil {
		return domain.UserResponse{}, domain.Unprocessable(err.Error())
	}
	if f.createErr != nil {
		return domain.UserResponse{}, f.createErr
	}
	f.created = domain.UserResponse{ID: 7, Username: p.Username, DesiredJob: p.DesiredJob,
		CareerYears: p.CareerYears, Skills: p.Skills}
	return f.created, nil
}
func (f *fakeAdmin) UpdateUser(_ context.Context, id int64, p domain.UserPayload) (domain.UserResponse, error) {
	if f.updateErr != nil {
		return domain.UserResponse{}, f.updateErr
	}
	return domain.UserResponse{ID: id, Username: p.Username, DesiredJob: p.DesiredJob,
		CareerYears: p.CareerYears, Skills: p.Skills}, nil
}
func (f *fakeAdmin) DeleteUser(context.Context, int64) error { return f.deleteErr }
func (f *fakeAdmin) EmbeddingModels() domain.EmbeddingModels { return f.models }
func (f *fakeAdmin) ResolveEmbeddingTarget(provider, _ string, _ *int) (domain.Target, error) {
	if f.resolveErr != nil {
		return domain.Target{}, f.resolveErr
	}
	return domain.Target{Provider: provider, Model: "gemini-embedding-001", Dim: 1024}, nil
}
func (f *fakeAdmin) RebuildEmbeddings(context.Context) (int, error) { return 0, nil }
func (f *fakeAdmin) SwitchEmbeddingModel(context.Context, string, string, *int) (domain.SwitchResult, error) {
	return domain.SwitchResult{}, nil
}
func (f *fakeAdmin) StartBackground(name string, _ func(ctx context.Context) error) bool {
	if name == "embedding_switch" {
		return f.switchOK
	}
	return f.rebuildOK
}
func (f *fakeAdmin) ListCache(context.Context) ([]domain.CacheRow, error) { return f.cacheRows, nil }
func (f *fakeAdmin) ClearCache(context.Context) (int64, error)            { return f.deletedCount, nil }
func (f *fakeAdmin) DeleteCache(context.Context, int64, int64) error      { return f.cacheDelErr }

// ---------- 헬퍼 ----------

// fakeAuth는 인증 포트의 가짜다.
type fakeAuth struct {
	status        domain.AuthStatus
	loginURL      string
	loginURLok    bool
	token         string
	user          domain.UserResponse
	loginErr      error
	meErr         error
	meUser        domain.UserResponse
	updateErr     error
	authenticated bool
	gotUserID     int64
}

func (f *fakeAuth) Status() domain.AuthStatus              { return f.status }
func (f *fakeAuth) LoginURL(string, string) (string, bool) { return f.loginURL, f.loginURLok }
func (f *fakeAuth) Login(_ context.Context, _, _, _ string) (string, domain.UserResponse, error) {
	if f.loginErr != nil {
		return "", domain.UserResponse{}, f.loginErr
	}
	return f.token, f.user, nil
}
func (f *fakeAuth) Me(_ context.Context, userID int64) (domain.UserResponse, error) {
	f.gotUserID = userID
	if f.meErr != nil {
		return domain.UserResponse{}, f.meErr
	}
	return f.meUser, nil
}
func (f *fakeAuth) UpdateMe(_ context.Context, userID int64, p domain.ProfileUpdate) (domain.UserResponse, error) {
	if err := p.Validate(); err != nil {
		return domain.UserResponse{}, domain.Unprocessable(err.Error())
	}
	if f.updateErr != nil {
		return domain.UserResponse{}, f.updateErr
	}
	return domain.UserResponse{ID: userID, Username: "u", DesiredJob: p.DesiredJob,
		CareerYears: p.CareerYears, Skills: p.Skills}, nil
}
func (f *fakeAuth) SetSessionCookie(_ http.ResponseWriter, _ string) {}
func (f *fakeAuth) ClearSessionCookie(_ http.ResponseWriter)         {}
func (f *fakeAuth) SetStateCookie(_ http.ResponseWriter, _ string)   {}
func (f *fakeAuth) StateCookie(_ *http.Request) string               { return "" }
func (f *fakeAuth) Authenticated(_ *http.Request) (int64, string, bool) {
	if !f.authenticated {
		return 0, "", false
	}
	return 42, "로그인유저", true
}

func newTestServer(rec *fakeRecommender, ana *fakeAnalyzer, admin *fakeAdmin) *httptest.Server {
	return newTestServerAuth(rec, ana, admin, &fakeAuth{}, false)
}

func newTestServerAuth(rec *fakeRecommender, ana *fakeAnalyzer, admin *fakeAdmin, auth *fakeAuth, authRequired bool) *httptest.Server {
	users := &fakeUsers{users: []domain.UserSummary{
		{ID: 1, Username: "지원", DesiredJob: "데이터 엔지니어", CareerYears: 2},
	}}
	srv := New(users, rec, ana, admin, auth, authRequired)
	ts := httptest.NewServer(srv.Handler())
	return ts
}

func do(t *testing.T, method, url string, body string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(method, url, strings.NewReader(body))
	if err != nil {
		t.Fatal(err)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(resp.Body)
	if err != nil {
		t.Fatal(err)
	}
	return resp, string(raw)
}

// ---------- 정적 셸 ----------

func TestHealth(t *testing.T) {
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{})
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/health", "")
	if resp.StatusCode != 200 || body != "{\"status\":\"ok\"}\n" {
		t.Fatalf("health: %d %q", resp.StatusCode, body)
	}
}

func TestStaticShell(t *testing.T) {
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{})
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/", "")
	if resp.StatusCode != 200 || !strings.Contains(body, "멘토AI") {
		t.Fatalf("index: %d", resp.StatusCode)
	}

	for _, name := range []string{"app.css", "app.js", "admin.css", "admin.js",
		"icons/icon-192.png", "icons/icon-512.png", "icons/icon-maskable-512.png", "icons/apple-touch-icon.png"} {
		if resp, _ := do(t, http.MethodGet, ts.URL+"/"+name, ""); resp.StatusCode != 200 {
			t.Errorf("%s: %d", name, resp.StatusCode)
		}
	}

	if _, body := do(t, http.MethodGet, ts.URL+"/admin", ""); !strings.Contains(body, "멘토AI") {
		t.Error("admin.html 서빙 실패")
	}

	resp, body = do(t, http.MethodGet, ts.URL+"/manifest.webmanifest", "")
	if resp.StatusCode != 200 {
		t.Fatal("manifest 실패")
	}
	var manifest map[string]any
	_ = json.Unmarshal([]byte(body), &manifest)
	if manifest["display"] != "standalone" || manifest["theme_color"] != "#003b5c" {
		t.Fatalf("manifest 필드: %v", manifest)
	}

	_, sw := do(t, http.MethodGet, ts.URL+"/sw.js", "")
	if !strings.Contains(sw, "CACHE_NAME") || !strings.Contains(sw, `startsWith("/api/")`) {
		t.Error("sw.js 캐시 제외 규칙 확인")
	}

	// manifest가 두 페이지에서 링크되는지
	for _, page := range []string{"/", "/admin"} {
		if _, body := do(t, http.MethodGet, ts.URL+page, ""); !strings.Contains(body, "manifest.webmanifest") {
			t.Errorf("%s에 manifest 링크 없음", page)
		}
	}

	// 임베드 FS에 파일이 실제로 있는지 (admin.html 등)
	if _, err := fs.Stat(web.FS(), "admin.html"); err != nil {
		t.Fatalf("임베드 누락: %v", err)
	}
}

// ---------- v1 ----------

func TestListUsers(t *testing.T) {
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, &fakeAdmin{})
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/api/v1/users", "")
	if resp.StatusCode != 200 {
		t.Fatalf("status: %d", resp.StatusCode)
	}
	var users []domain.UserSummary
	_ = json.Unmarshal([]byte(body), &users)
	if len(users) != 1 || users[0].Username != "지원" || users[0].CareerYears != 2 {
		t.Fatalf("users: %s", body)
	}
}

func TestRecommendJobs(t *testing.T) {
	rec := &fakeRecommender{result: domain.RecommendationListResponse{
		UserName: "지원",
		Recommendations: []domain.JobSummary{{
			JobID: 5, Company: "A사", Title: "엔지니어", MatchScore: 87, MaxScore: 100,
			Skills: []string{}, MatchedSkills: []string{}, Reason: "유사",
		}},
	}}
	ts := newTestServer(rec, &fakeAnalyzer{}, &fakeAdmin{})
	defer ts.Close()

	resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/jobs/recommend/1", "")
	if resp.StatusCode != 200 {
		t.Fatalf("status: %d %s", resp.StatusCode, body)
	}
	if rec.gotUserID != 1 {
		t.Fatalf("user_id 전달: %d", rec.gotUserID)
	}
	if !strings.Contains(body, `"match_score":87`) {
		t.Fatalf("응답: %s", body)
	}

	// 404
	rec.err = domain.NotFound("User not found")
	resp, body = do(t, http.MethodPost, ts.URL+"/api/v1/jobs/recommend/99", "")
	if resp.StatusCode != 404 || !strings.Contains(body, "User not found") {
		t.Fatalf("404: %d %s", resp.StatusCode, body)
	}

	// 비정수 경로 → 422
	if resp, _ := do(t, http.MethodPost, ts.URL+"/api/v1/jobs/recommend/abc", ""); resp.StatusCode != 422 {
		t.Fatalf("422 기대: %d", resp.StatusCode)
	}
}

func TestAnalyzeJob(t *testing.T) {
	ana := &fakeAnalyzer{result: domain.DetailedAnalysisResponse{JobTitle: "엔지니어", CurrentScore: 72, MaxScore: 100}}
	ts := newTestServer(&fakeRecommender{}, ana, &fakeAdmin{})
	defer ts.Close()

	resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/jobs/3/analyze/1", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"current_score":72`) {
		t.Fatalf("분석: %d %s", resp.StatusCode, body)
	}

	ana.err = domain.NotFound("해당 공고를 찾을 수 없습니다.")
	if resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/jobs/999/analyze/1", ""); resp.StatusCode != 404 ||
		!strings.Contains(body, "해당 공고를 찾을 수 없습니다.") {
		t.Fatalf("404: %d %s", resp.StatusCode, body)
	}
}

// ---------- admin ----------

func TestAdminStatsAndRuns(t *testing.T) {
	admin := &fakeAdmin{status: domain.Status{Bronze: 10, Jobs: 8, Embeddings: 8, Users: 3,
		CachedAnalyses: 1, EmbeddingModel: "gemini:gemini-embedding-001", EmbeddingDim: 1024,
		Sizes: domain.Sizes{BronzeSize: "1 kB", JobsSize: "2 kB", EmbeddingsSize: "3 kB"}}}
	admin.runs = []domain.RunRow{{ID: 1, Status: "success", StartedAt: "2026-09-01T09:00:00Z"}}

	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/api/v1/admin/stats", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"embedding_model":"gemini:gemini-embedding-001"`) ||
		!strings.Contains(body, `"bronze_size":"1 kB"`) {
		t.Fatalf("stats: %d %s", resp.StatusCode, body)
	}

	resp, body = do(t, http.MethodGet, ts.URL+"/api/v1/admin/pipeline-runs", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"status":"success"`) {
		t.Fatalf("runs: %d %s", resp.StatusCode, body)
	}
}

func TestAdminTriggerPipeline(t *testing.T) {
	admin := &fakeAdmin{}
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/admin/pipeline", "")
	if resp.StatusCode != 200 || !strings.Contains(body, "started") {
		t.Fatalf("트리거: %d %s", resp.StatusCode, body)
	}

	admin.triggerErr = domain.Conflict("파이프라인이 이미 실행 중입니다")
	resp, body = do(t, http.MethodPost, ts.URL+"/api/v1/admin/pipeline", "")
	if resp.StatusCode != 409 || !strings.Contains(body, "파이프라인이 이미 실행 중입니다") {
		t.Fatalf("409: %d %s", resp.StatusCode, body)
	}
}

func TestAdminJobsList(t *testing.T) {
	admin := &fakeAdmin{jobs: []domain.JobAdminRow{{ID: 1, Source: "wanted", SourceID: "1"}}}
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	resp, _ := do(t, http.MethodGet, ts.URL+"/api/v1/admin/jobs?query=%ED%85%8C%EC%8A%A4%ED%8A%B8&limit=10", "")
	if resp.StatusCode != 200 {
		t.Fatalf("jobs: %d", resp.StatusCode)
	}
	if admin.gotQuery != "테스트" || admin.gotLimit != 10 {
		t.Fatalf("쿼리 전달: %q %d", admin.gotQuery, admin.gotLimit)
	}
}

func TestAdminDeleteJob(t *testing.T) {
	admin := &fakeAdmin{}
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	if resp, _ := do(t, http.MethodDelete, ts.URL+"/api/v1/admin/jobs/1", ""); resp.StatusCode != 204 {
		t.Fatalf("204 기대: %d", resp.StatusCode)
	}
	admin.deleteJobErr = domain.NotFound("공고 없음: 1")
	if resp, body := do(t, http.MethodDelete, ts.URL+"/api/v1/admin/jobs/1", ""); resp.StatusCode != 404 ||
		!strings.Contains(body, "공고 없음") {
		t.Fatalf("404: %d %s", resp.StatusCode, body)
	}
}

func TestAdminUserCRUD(t *testing.T) {
	admin := &fakeAdmin{}
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	payload := `{"username":"새인재","desired_job":"백엔드","career_years":3,"skills":["Java"]}`
	resp, body := do(t, http.MethodPost, ts.URL+"/api/v1/admin/users", payload)
	if resp.StatusCode != 201 || !strings.Contains(body, `"id":7`) {
		t.Fatalf("생성: %d %s", resp.StatusCode, body)
	}

	admin.createErr = domain.Conflict("이미 존재하는 사용자: 새인재")
	resp, body = do(t, http.MethodPost, ts.URL+"/api/v1/admin/users", payload)
	if resp.StatusCode != 409 || !strings.Contains(body, "이미 존재하는 사용자") {
		t.Fatalf("409: %d %s", resp.StatusCode, body)
	}

	// 검증 실패 → 422
	for _, bad := range []string{
		`{"username":"","desired_job":"백엔드","career_years":3}`,
		`{"username":"x","desired_job":"백엔드","career_years":99}`,
	} {
		if resp, _ := do(t, http.MethodPost, ts.URL+"/api/v1/admin/users", bad); resp.StatusCode != 422 {
			t.Fatalf("422 기대: %d (%s)", resp.StatusCode, bad)
		}
	}

	resp, _ = do(t, http.MethodPut, ts.URL+"/api/v1/admin/users/7", payload)
	if resp.StatusCode != 200 {
		t.Fatalf("수정: %d", resp.StatusCode)
	}
	admin.updateErr = domain.NotFound("사용자 없음: 99")
	if resp, _ := do(t, http.MethodPut, ts.URL+"/api/v1/admin/users/99", payload); resp.StatusCode != 404 {
		t.Fatalf("수정 404: %d", resp.StatusCode)
	}

	admin.deleteErr = domain.NotFound("사용자 없음: 99")
	if resp, _ := do(t, http.MethodDelete, ts.URL+"/api/v1/admin/users/99", ""); resp.StatusCode != 404 {
		t.Fatalf("삭제 404: %d", resp.StatusCode)
	}
	admin.deleteErr = nil
	if resp, _ := do(t, http.MethodDelete, ts.URL+"/api/v1/admin/users/1", ""); resp.StatusCode != 204 {
		t.Fatalf("삭제 204: %d", resp.StatusCode)
	}
}

func TestAdminEmbeddingEndpoints(t *testing.T) {
	admin := &fakeAdmin{models: domain.EmbeddingModels{
		Current: "gemini:gemini-embedding-001", Provider: "gemini", Dim: 1024,
		Available:     []domain.ModelInfo{{Provider: "gemini", Model: "gemini-embedding-001", Dim: 1024}},
		GeminiDefault: "gemini-embedding-001",
	}, rebuildOK: true}
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/api/v1/admin/embedding/models", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"current":"gemini:gemini-embedding-001"`) {
		t.Fatalf("models: %d %s", resp.StatusCode, body)
	}

	resp, _ = do(t, http.MethodPost, ts.URL+"/api/v1/admin/embedding/rebuild", "")
	if resp.StatusCode != 200 {
		t.Fatalf("rebuild: %d", resp.StatusCode)
	}
	admin.rebuildOK = false
	resp, body = do(t, http.MethodPost, ts.URL+"/api/v1/admin/embedding/rebuild", "")
	if resp.StatusCode != 409 || !strings.Contains(body, "이미 실행 중입니다") {
		t.Fatalf("rebuild 409: %d %s", resp.StatusCode, body)
	}

	// switch: 미등록 provider → 400
	admin.resolveErr = domain.BadRequest("알 수 없는 provider: openai (gemini)")
	resp, body = do(t, http.MethodPost, ts.URL+"/api/v1/admin/embedding/switch?provider=openai", "")
	if resp.StatusCode != 400 || !strings.Contains(body, "알 수 없는 provider") {
		t.Fatalf("switch 400: %d %s", resp.StatusCode, body)
	}

	// switch: 성공 → target/dim
	admin.resolveErr = nil
	admin.switchOK = true
	resp, body = do(t, http.MethodPost, ts.URL+"/api/v1/admin/embedding/switch?provider=gemini", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"target":"gemini:gemini-embedding-001"`) ||
		!strings.Contains(body, `"dim":1024`) {
		t.Fatalf("switch: %d %s", resp.StatusCode, body)
	}

	// switch: provider 누락 → 422
	if resp, _ := do(t, http.MethodPost, ts.URL+"/api/v1/admin/embedding/switch", ""); resp.StatusCode != 422 {
		t.Fatalf("provider 필수 422: %d", resp.StatusCode)
	}
}

func TestAdminCache(t *testing.T) {
	admin := &fakeAdmin{deletedCount: 2}
	admin.cacheRows = []domain.CacheRow{{JobID: 1, UserID: 1, Model: "m", Username: "지원"}}
	ts := newTestServer(&fakeRecommender{}, &fakeAnalyzer{}, admin)
	defer ts.Close()

	resp, body := do(t, http.MethodGet, ts.URL+"/api/v1/admin/cache", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"username":"지원"`) {
		t.Fatalf("캐시 목록: %d %s", resp.StatusCode, body)
	}

	resp, body = do(t, http.MethodDelete, ts.URL+"/api/v1/admin/cache", "")
	if resp.StatusCode != 200 || !strings.Contains(body, `"deleted":2`) {
		t.Fatalf("캐시 삭제: %d %s", resp.StatusCode, body)
	}

	if resp, _ := do(t, http.MethodDelete, ts.URL+"/api/v1/admin/cache/1/1", ""); resp.StatusCode != 204 {
		t.Fatalf("개별 삭제: %d", resp.StatusCode)
	}
	admin.cacheDelErr = domain.NotFound("캐시 없음: job=1 user=1")
	if resp, body := do(t, http.MethodDelete, ts.URL+"/api/v1/admin/cache/1/1", ""); resp.StatusCode != 404 ||
		!strings.Contains(body, "캐시 없음") {
		t.Fatalf("개별 삭제 404: %d %s", resp.StatusCode, body)
	}
}
