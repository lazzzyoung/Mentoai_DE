// Package api는 HTTP API와 모놀리식 UI 서빙을 담당한다.
// 기존 FastAPI 애플리케이션과 엔드포인트·상태코드·에러 형식({"detail": ...})이 동일하다.
package api

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strconv"

	"github.com/Chae-JS/mentoai/internal/domain"
	"github.com/Chae-JS/mentoai/internal/web"
)

// ---------- 서비스 포트 (테스트에서 가짜 구현 주입) ----------

// UsersLister는 인재 목록 조회다.
type UsersLister interface {
	ListSummaries(ctx context.Context) ([]domain.UserSummary, error)
}

// Recommender는 채용공고 추천이다.
type Recommender interface {
	Recommend(ctx context.Context, userID int64) (domain.RecommendationListResponse, error)
}

// Analyzer는 공고 상세 분석이다.
type Analyzer interface {
	Analyze(ctx context.Context, jobID, userID int64) (domain.DetailedAnalysisResponse, error)
}

// AdminService는 어드민 운영 전체다.
type AdminService interface {
	Status(ctx context.Context) (domain.Status, error)
	ListRuns(ctx context.Context, limit int) ([]domain.RunRow, error)
	TriggerPipeline(ctx context.Context) error
	ListJobs(ctx context.Context, query string, limit int) ([]domain.JobAdminRow, error)
	DeleteJob(ctx context.Context, jobID int64) error
	CreateUser(ctx context.Context, p domain.UserPayload) (domain.UserResponse, error)
	UpdateUser(ctx context.Context, userID int64, p domain.UserPayload) (domain.UserResponse, error)
	DeleteUser(ctx context.Context, userID int64) error
	EmbeddingModels() domain.EmbeddingModels
	ResolveEmbeddingTarget(provider, model string, dim *int) (domain.Target, error)
	RebuildEmbeddings(ctx context.Context) (int, error)
	SwitchEmbeddingModel(ctx context.Context, provider, model string, dim *int) (domain.SwitchResult, error)
	StartBackground(name string, fn func(ctx context.Context) error) bool
	ListCache(ctx context.Context) ([]domain.CacheRow, error)
	ClearCache(ctx context.Context) (int64, error)
	DeleteCache(ctx context.Context, jobID, userID int64) error
}

// AuthService는 인증 기능의 포트다. auth.Service가 구현하며,
// authRequired=false일 때도 인터페이스는 제공된다(엔드포인트는 항상 등록).
type AuthService interface {
	Status() domain.AuthStatus
	LoginURL(provider, state string) (string, bool)
	Login(ctx context.Context, provider, code, referrer string) (token string, user domain.UserResponse, err error)
	Me(ctx context.Context, userID int64) (domain.UserResponse, error)
	UpdateMe(ctx context.Context, userID int64, p domain.ProfileUpdate) (domain.UserResponse, error)
	SetSessionCookie(w http.ResponseWriter, token string)
	ClearSessionCookie(w http.ResponseWriter)
	SetStateCookie(w http.ResponseWriter, state string)
	StateCookie(r *http.Request) string
	Authenticated(r *http.Request) (userID int64, username string, ok bool)
}

// ErrorReporter는 에러 리포팅 포트다 (telemetry.Reporter가 구조적으로 충족).
type ErrorReporter interface {
	CaptureError(err error, tags map[string]string)
}

// ---------- 서버 ----------

// Server는 HTTP 핸들러 묶음이다.
type Server struct {
	mux          *http.ServeMux
	users        UsersLister
	rec          Recommender
	ana          Analyzer
	admin        AdminService
	auth         AuthService
	authRequired bool
	adminIDs     map[int64]bool
	reporter     ErrorReporter
}

// New는 의존성을 주입받아 서버를 조립한다.
func New(users UsersLister, rec Recommender, ana Analyzer, admin AdminService, auth AuthService, authRequired bool, reporter ErrorReporter, adminUserIDs ...int64) *Server {
	s := &Server{mux: http.NewServeMux(), users: users, rec: rec, ana: ana, admin: admin, auth: auth, authRequired: authRequired, reporter: reporter}
	s.adminIDs = make(map[int64]bool)
	for _, id := range adminUserIDs {
		if id > 0 {
			s.adminIDs[id] = true
		}
	}
	s.routes()
	return s
}

// Handler는 루트 핸들러를 돌려준다. panic은 리포팅 후 500으로 변환한다.
func (s *Server) Handler() http.Handler {
	return s.recoverPanics(s.mux)
}

// recoverPanics는 핸들러 패닉을 잡아 리포팅하고 일관된 500 응답을 돌려준다.
// (net/http 기본 동작은 연결만 끊기 때문에 클라이언트가 에러 형식을 못 받는다.)
func (s *Server) recoverPanics(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if rec := recover(); rec != nil {
				s.reporter.CaptureError(
					fmt.Errorf("핸들러 패닉: %v", rec),
					map[string]string{"method": r.Method, "path": r.URL.Path, "kind": "panic"},
				)
				slog.Error("핸들러 패닉", "path", r.URL.Path, "panic", rec)
				writeJSON(w, http.StatusInternalServerError,
					map[string]string{"detail": "내부 오류가 발생했습니다"})
			}
		}()
		next.ServeHTTP(w, r)
	})
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /health", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// v1
	s.mux.HandleFunc("GET /api/v1/users", s.guard(s.listUsers))
	s.mux.HandleFunc("POST /api/v1/jobs/recommend/{user_id}", s.guard(s.recommendJobs))
	s.mux.HandleFunc("POST /api/v1/jobs/{job_id}/analyze/{user_id}", s.guard(s.analyzeJob))

	// 인증 (기본 OFF: 공급자 설정이 없으면 status만 응답한다)
	s.mux.HandleFunc("GET /api/v1/auth/status", s.authStatus)
	s.mux.HandleFunc("GET /api/v1/auth/{provider}/login", s.authLogin)
	s.mux.HandleFunc("GET /api/v1/auth/{provider}/callback", s.authCallback)
	s.mux.HandleFunc("POST /api/v1/auth/toss/callback", s.authTossCallback)
	s.mux.HandleFunc("GET /api/v1/auth/me", s.authMe)
	s.mux.HandleFunc("PUT /api/v1/auth/me", s.authUpdateMe)
	s.mux.HandleFunc("POST /api/v1/auth/logout", s.authLogout)

	// admin
	s.mux.HandleFunc("GET /api/v1/admin/stats", s.adminGuard(s.adminStats))
	s.mux.HandleFunc("GET /api/v1/admin/pipeline-runs", s.adminGuard(s.adminPipelineRuns))
	s.mux.HandleFunc("POST /api/v1/admin/pipeline", s.adminGuard(s.adminTriggerPipeline))
	s.mux.HandleFunc("GET /api/v1/admin/jobs", s.adminGuard(s.adminJobsList))
	s.mux.HandleFunc("DELETE /api/v1/admin/jobs/{job_id}", s.adminGuard(s.adminDeleteJob))
	s.mux.HandleFunc("POST /api/v1/admin/users", s.adminGuard(s.adminCreateUser))
	s.mux.HandleFunc("PUT /api/v1/admin/users/{user_id}", s.adminGuard(s.adminUpdateUser))
	s.mux.HandleFunc("DELETE /api/v1/admin/users/{user_id}", s.adminGuard(s.adminDeleteUser))
	s.mux.HandleFunc("GET /api/v1/admin/embedding/models", s.adminGuard(s.adminEmbeddingModels))
	s.mux.HandleFunc("POST /api/v1/admin/embedding/rebuild", s.adminGuard(s.adminRebuildEmbeddings))
	s.mux.HandleFunc("POST /api/v1/admin/embedding/switch", s.adminGuard(s.adminSwitchEmbedding))
	s.mux.HandleFunc("GET /api/v1/admin/cache", s.adminGuard(s.adminCacheList))
	s.mux.HandleFunc("DELETE /api/v1/admin/cache", s.adminGuard(s.adminCacheClear))
	s.mux.HandleFunc("DELETE /api/v1/admin/cache/{job_id}/{user_id}", s.adminGuard(s.adminCacheDelete))

	// 모놀리식 UI: 빌드 도구 없는 정적 페이지를 같은 프로세스에서 서빙한다.
	// "/"는 가장 덜 구체적인 패턴이라 위 라우트들이 우선한다.
	static := web.FS()
	s.mux.HandleFunc("GET /admin", func(w http.ResponseWriter, r *http.Request) {
		http.ServeFileFS(w, r, static, "admin.html")
	})
	s.mux.Handle("GET /", http.FileServerFS(static))
}

// ---------- 응답 헬퍼 ----------

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	enc := json.NewEncoder(w)
	enc.SetEscapeHTML(false)
	_ = enc.Encode(v)
}

// writeError는 서비스 오류를 FastAPI와 같은 {"detail": ...} 형식으로 변환한다.
// 5xx(내부 오류)는 에러 리포팅으로 전송한다 — 4xx는 클라이언트 오류라 제외.
func (s *Server) writeError(w http.ResponseWriter, r *http.Request, err error) {
	httpErr := domain.AsHTTPError(err)
	if httpErr.Code >= 500 && s.reporter != nil {
		s.reporter.CaptureError(err, map[string]string{
			"method": r.Method, "path": r.URL.Path, "status": strconv.Itoa(httpErr.Code),
		})
	}
	if httpErr.Code >= 500 {
		slog.Error("요청 처리 실패", "status", httpErr.Code, "error", err)
	}
	writeJSON(w, httpErr.Code, map[string]string{"detail": httpErr.Detail})
}

// guard는 AUTH_REQUIRED=true일 때 로그인하지 않은 요청을 401로 막는다.
// 기본값(false)에서는 기존과 동일하게 전부 개방이다.
func (s *Server) guard(next http.HandlerFunc) http.HandlerFunc {
	if !s.authRequired {
		return next
	}
	return func(w http.ResponseWriter, r *http.Request) {
		id, _, ok := s.auth.Authenticated(r)
		if !ok {
			writeJSON(w, http.StatusUnauthorized, map[string]string{"detail": "로그인이 필요합니다"})
			return
		}
		if _, err := s.auth.Me(r.Context(), id); err != nil {
			if domain.AsHTTPError(err).Code == http.StatusNotFound {
				writeJSON(w, http.StatusUnauthorized, map[string]string{"detail": "사용 가능한 계정이 아닙니다"})
			} else {
				s.writeError(w, r, err)
			}
			return
		}
		next(w, r)
	}
}

// adminGuard는 인증 모드에서 명시적으로 지정한 관리자만 허용한다.
func (s *Server) adminGuard(next http.HandlerFunc) http.HandlerFunc {
	return s.guard(func(w http.ResponseWriter, r *http.Request) {
		if s.authRequired {
			id, _, ok := s.auth.Authenticated(r)
			if !ok || !s.adminIDs[id] {
				writeJSON(w, http.StatusForbidden, map[string]string{"detail": "관리자 권한이 필요합니다"})
				return
			}
		}
		next(w, r)
	})
}

// canAccessUser는 URL의 ID를 신뢰하지 않고 세션 소유자와 비교한다.
func (s *Server) canAccessUser(w http.ResponseWriter, r *http.Request, userID int64) bool {
	if !s.authRequired {
		return true
	}
	id, _, ok := s.auth.Authenticated(r)
	if !ok || (id != userID && !s.adminIDs[id]) {
		writeJSON(w, http.StatusForbidden, map[string]string{"detail": "다른 사용자의 데이터에 접근할 수 없습니다"})
		return false
	}
	return true
}

// pathInt는 경로 파라미터를 int64로 파싱한다. FastAPI처럼 변환 실패는 422다.
func pathInt(w http.ResponseWriter, r *http.Request, name string) (int64, bool) {
	v, err := strconv.ParseInt(r.PathValue(name), 10, 64)
	if err != nil {
		writeJSON(w, http.StatusUnprocessableEntity, map[string]string{
			"detail": "정수 경로 파라미터가 필요합니다: " + name,
		})
		return 0, false
	}
	return v, true
}
